"""Explicit, local admin recovery of A5 failures; no provider reads or quota reset."""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import re
from uuid import uuid4

from sqlalchemy import delete, insert, select, update, func

from .connectors import ConnectorError, Platform
from .discovery_history import cycle_leases, history_checkpoints, read_checkpoint, lock_tenant
from .identity import Principal
from .ingestion import ingestion_runs, source_grants, stable_id
from .sa_store import domain_events, outbox
from .storage import now_utc

CYCLE_KEY = re.compile(r"a5(?:history|refresh)-[0-9]{14}-[a-f0-9]{8}\Z")
RUN_KEY = re.compile(r"a5(?:history|refresh)-[0-9]{14}-[a-f0-9]{8}-0[1-5]\Z")
RECOVERY_EVENT = "business_discovery.failed_run_reviewed"


def reviewed_failure(db, tenant, run_key):
    return db.execute(select(domain_events.c.seq).where(
        domain_events.c.tenant_id == tenant,
        domain_events.c.aggregate_type == "bd_recovery",
        domain_events.c.aggregate_id == stable_id("bd-recovery-run", tenant, run_key),
        domain_events.c.event_type == RECOVERY_EVENT,
    ).limit(1)).first() is not None


def _event(db, tenant, actor, key, event_type, payload):
    aggregate_id = stable_id("bd-recovery-run" if event_type == RECOVERY_EVENT
                             else "bd-recovery-cycle", tenant, key)
    event = db.execute(insert(domain_events).values(
        event_id=str(uuid4()), tenant_id=tenant, aggregate_type="bd_recovery",
        aggregate_id=aggregate_id, aggregate_version=1, event_type=event_type,
        occurred_at=now_utc().isoformat(),
        payload=json.dumps({"actor_id": actor, **payload}, sort_keys=True)))
    db.execute(insert(outbox).values(seq=event.inserted_primary_key[0], attempts=0, dead_letter=0))


def _admin(principal, stopped):
    if principal.role != "admin":
        raise ConnectorError("BD_RECOVERY_ADMIN_REQUIRED", 403)
    if not stopped:
        raise ConnectorError("BD_RECOVERY_STOP_ALL_INGESTION_REQUIRED", 409)


def _reservations(db, tenant):
    return db.execute(select(ingestion_runs).where(
        ingestion_runs.c.tenant_id == tenant,
        ingestion_runs.c.status == "reserved")).mappings().all()


def _lease(db, tenant):
    return db.execute(select(cycle_leases).where(cycle_leases.c.tenant_id == tenant)).mappings().first()


def _observations(db, tenant, run_key):
    return db.execute(select(func.count()).select_from(domain_events).where(
        domain_events.c.tenant_id == tenant,
        domain_events.c.aggregate_type == "bd_technical_run",
        domain_events.c.aggregate_id == stable_id("bd-observation-run", tenant, run_key),
        domain_events.c.event_type == "business_discovery.metadata_observed")).scalar_one()


def inspect_recovery(engine, tenant):
    """Safe read-only summary; never return raw cursor, approval or provider payload."""
    with engine.connect() as db:
        lease = _lease(db, tenant)
        runs = db.execute(select(ingestion_runs).where(
            ingestion_runs.c.tenant_id == tenant,
            ingestion_runs.c.platform == Platform.INSTAGRAM.value,
        ).order_by(ingestion_runs.c.requested_at.desc(), ingestion_runs.c.run_key.desc())).mappings().all()
        latest = {}
        for run in runs:
            latest.setdefault(run["source_account_id"], run)
        blocked = []
        for run in latest.values():
            if run["status"] in {"failed", "reserved"} and RUN_KEY.fullmatch(run["run_key"]):
                blocked.append({"source_account_id":run["source_account_id"],
                    "run_key":run["run_key"], "status":run["status"],
                    "reviewed":reviewed_failure(db, tenant, run["run_key"]),
                    "observations_recorded":_observations(db, tenant, run["run_key"])})
        return {"status":"RECOVERY_INSPECTION", "lease":dict(lease) if lease else None,
                "latest_a5_blocked_runs":blocked,
                "reserved_runs":len(_reservations(db, tenant)), "external_data_accessed":False}


def review_failure(engine, principal: Principal, run_key: str, *, stopped: bool,
                   restart_history: bool = False):
    """Acknowledge exactly the latest failed A5 run, optionally reset history to top.

    A failed run remains failed. Its reservation and observations are preserved.
    The next cycle requires a fresh run key and all existing authorization gates.
    """
    _admin(principal, stopped)
    if not RUN_KEY.fullmatch(run_key) or (restart_history and not run_key.startswith("a5history-")):
        raise ConnectorError("BD_RECOVERY_INVALID_RUN", 422)
    tenant = principal.tenant_id
    with engine.begin() as db:
        lock_tenant(db, tenant)
        if _lease(db, tenant) or _reservations(db, tenant):
            raise ConnectorError("BD_RECOVERY_INGESTION_ACTIVE", 409)
        run = db.execute(select(ingestion_runs).where(ingestion_runs.c.tenant_id == tenant,
            ingestion_runs.c.run_key == run_key,
            ingestion_runs.c.platform == Platform.INSTAGRAM.value)).mappings().first()
        if not run or run["status"] != "failed":
            raise ConnectorError("BD_RECOVERY_FAILED_RUN_REQUIRED", 409)
        source = run["source_account_id"]
        latest = db.execute(select(ingestion_runs.c.run_key).where(
            ingestion_runs.c.tenant_id == tenant,
            ingestion_runs.c.platform == Platform.INSTAGRAM.value,
            ingestion_runs.c.source_account_id == source,
        ).order_by(ingestion_runs.c.requested_at.desc(), ingestion_runs.c.run_key.desc()).limit(1)).scalar_one()
        if latest != run_key or reviewed_failure(db, tenant, run_key):
            raise ConnectorError("BD_RECOVERY_RUN_NOT_LATEST_UNREVIEWED", 409)
        grant = db.execute(select(source_grants).where(source_grants.c.tenant_id == tenant,
            source_grants.c.platform == Platform.INSTAGRAM.value,
            source_grants.c.source_account_id == source).with_for_update()).mappings().first()
        if not grant or not grant["enabled"] or datetime.fromisoformat(grant["expires_at"]) <= now_utc():
            raise ConnectorError("VALID_SOURCE_GRANT_REQUIRED", 403)
        checkpoint = read_checkpoint(db, tenant, source)
        if restart_history:
            if checkpoint is None or checkpoint["last_run_key"] == run_key:
                raise ConnectorError("BD_RECOVERY_SAFE_CHECKPOINT_REQUIRED", 409)
            if checkpoint["approval_reference"] != grant["approval_reference"]:
                raise ConnectorError("BD_HISTORY_SCOPE_CHANGED", 403)
            db.execute(delete(history_checkpoints).where(history_checkpoints.c.tenant_id == tenant,
                history_checkpoints.c.source_account_id == source))
        payload = {"run_key":run_key, "source_account_id":source,
                   "action":"restart_history" if restart_history else "retry_reviewed_failure",
                   "previous_checkpoint_pages":checkpoint["pages_examined"] if checkpoint else 0,
                   "previous_checkpoint_run":checkpoint["last_run_key"] if checkpoint else None,
                   "observations_recorded":_observations(db, tenant, run_key),
                   "operator_confirmed_ingestion_stopped":True}
        _event(db, tenant, principal.actor_id, run_key, RECOVERY_EVENT, payload)
    return {"status":"FAILED_RUN_REVIEWED", **payload, "quota_reservation_preserved":True,
            "external_data_accessed":False}


def recover_orphan_lease(engine, principal: Principal, cycle_key: str, *, stopped: bool):
    """Release only the exact stale A5 lease after offline operator attestation.

    No automatic expiry: age alone never proves a process has stopped.
    Matching abandoned reservations become failed, not completed or deleted.
    """
    _admin(principal, stopped)
    if not CYCLE_KEY.fullmatch(cycle_key):
        raise ConnectorError("BD_RECOVERY_INVALID_CYCLE", 422)
    tenant = principal.tenant_id
    with engine.begin() as db:
        lock_tenant(db, tenant)
        lease = _lease(db, tenant)
        if not lease or lease["cycle_key"] != cycle_key:
            raise ConnectorError("BD_RECOVERY_LEASE_MISMATCH", 409)
        if datetime.fromisoformat(lease["started_at"]) > now_utc() - timedelta(minutes=30):
            raise ConnectorError("BD_RECOVERY_LEASE_TOO_RECENT", 409)
        runs = _reservations(db, tenant)
        if any(r["platform"] != Platform.INSTAGRAM.value or
               not RUN_KEY.fullmatch(r["run_key"]) or
               not r["run_key"].startswith(cycle_key + "-") for r in runs):
            raise ConnectorError("BD_RECOVERY_UNRELATED_RESERVATION", 409)
        abandoned = []
        for r in runs:
            key = r["run_key"]
            changed = db.execute(update(ingestion_runs).where(
                ingestion_runs.c.tenant_id == tenant, ingestion_runs.c.run_key == key,
                ingestion_runs.c.status == "reserved").values(status="failed",
                    reason_code="BD_ORPHANED_RUN_OPERATOR_RECOVERY"))
            if changed.rowcount != 1:
                raise ConnectorError("BD_RECOVERY_RESERVATION_CHANGED", 409)
            abandoned.append({"run_key":key, "observations_recorded":_observations(db,tenant,key)})
        changed = db.execute(delete(cycle_leases).where(cycle_leases.c.tenant_id == tenant,
            cycle_leases.c.cycle_key == cycle_key))
        if changed.rowcount != 1:
            raise ConnectorError("BD_RECOVERY_LEASE_MISMATCH", 409)
        payload = {"cycle_key":cycle_key, "abandoned_runs":abandoned,
                   "operator_confirmed_ingestion_stopped":True}
        _event(db, tenant, principal.actor_id, cycle_key,
               "business_discovery.orphan_lease_recovered", payload)
    return {"status":"ORPHAN_LEASE_RECOVERED", **payload,
            "quota_reservation_preserved":True, "external_data_accessed":False}
