"""Durable, tenant-wide Instagram credential circuit breaker.

No credentials, credential hashes, raw provider payloads or extra network reads.
All writes are serialized under the existing tenant lock by the caller.
"""
from uuid import uuid4
import json

from sqlalchemy import insert, select

from .connectors import ConnectorError
from .sa_store import domain_events, outbox
from .storage import now_utc
from .discovery_credential_expiry import require_expiry_available

AGGREGATE = "bd_meta_auth"
BLOCK = "business_discovery.meta_auth_blocked"
RESET = "business_discovery.meta_auth_reset"
AUTH_INVALID = "BD_META_AUTH_INVALID"
AUTH_BLOCKED = "BD_META_AUTH_BLOCKED"


def is_global_auth_failure(exc):
    if not isinstance(exc, ConnectorError):
        return False
    d = exc.provider_diagnostic
    return (type(d.get("code")) is int and d["code"] == 190
            and type(d.get("http_status")) is int and d["http_status"] in (400, 401, 403))


def _latest(db, tenant):
    return db.execute(select(domain_events).where(
        domain_events.c.tenant_id == tenant,
        domain_events.c.aggregate_type == AGGREGATE,
        domain_events.c.aggregate_id == tenant,
    ).order_by(domain_events.c.aggregate_version.desc()).limit(1)).mappings().first()


def auth_status(db, tenant):
    last = _latest(db, tenant)
    if not last:
        return {"status":"NOT_CHECKED", "blocked":False}
    if last["event_type"] == RESET:
        return {"status":"RESET_UNVERIFIED", "blocked":False, "updated_at":last["occurred_at"]}
    # Unknown event types fail closed.
    return {"status":"BLOCKED", "blocked":True, "updated_at":last["occurred_at"]}


def require_auth_available(db, tenant):
    if auth_status(db, tenant)["blocked"]:
        raise ConnectorError(AUTH_BLOCKED, 409)
    require_expiry_available()


def _append(db, tenant, event_type, payload):
    last = _latest(db, tenant)
    seq = db.execute(insert(domain_events).values(
        event_id=str(uuid4()), tenant_id=tenant, aggregate_type=AGGREGATE,
        aggregate_id=tenant, aggregate_version=1 if last is None else last["aggregate_version"]+1,
        event_type=event_type, occurred_at=now_utc().isoformat(),
        payload=json.dumps(payload, sort_keys=True))).inserted_primary_key[0]
    db.execute(insert(outbox).values(seq=seq, attempts=0, dead_letter=0))


def record_auth_failure(db, tenant, exc, operation_key):
    """Call inside the reserved-run or identity-result transaction."""
    if not is_global_auth_failure(exc):
        return
    d = exc.provider_diagnostic
    payload = {"operation_key":operation_key, "http_status":d["http_status"], "code":190}
    subcode = d.get("error_subcode")
    if type(subcode) is int and 0 <= subcode <= 2147483647:
        payload["error_subcode"] = subcode
    _append(db, tenant, BLOCK, payload)


def reset_after_rotation(engine, principal, *, stopped):
    """Local technical reset after operator rotates the credential, not validation."""
    from .discovery_history import lock_tenant
    from .ingestion import cycle_leases, ingestion_runs
    if principal.role != "admin":
        raise ConnectorError("BD_RECOVERY_ADMIN_REQUIRED", 403)
    if not stopped:
        raise ConnectorError("BD_RECOVERY_STOP_ALL_INGESTION_REQUIRED", 409)
    tenant = principal.tenant_id
    with engine.begin() as db:
        lock_tenant(db, tenant)
        if (db.execute(select(cycle_leases.c.cycle_key).where(cycle_leases.c.tenant_id==tenant)).first()
                or db.execute(select(ingestion_runs.c.run_key).where(
                    ingestion_runs.c.tenant_id==tenant, ingestion_runs.c.status=="reserved")).first()):
            raise ConnectorError("BD_RECOVERY_INGESTION_ACTIVE", 409)
        if not auth_status(db, tenant)["blocked"]:
            raise ConnectorError("BD_META_AUTH_NOT_BLOCKED", 409)
        _append(db, tenant, RESET, {"actor_id":principal.actor_id, "credential_rotation_reported":True})
    return {"status":"META_AUTH_RESET_UNVERIFIED", "quota_reservation_preserved":True,
            "external_data_accessed":False}
