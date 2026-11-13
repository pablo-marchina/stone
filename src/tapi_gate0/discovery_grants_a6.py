"""Provision revocable, technical-only grants from audited A6 identities (DEC-018)."""
from datetime import datetime, timedelta

from sqlalchemy import insert, select, update

from .business_discovery import IG_ID
from .connectors import ConnectorError, Platform
from .discovery_batch import BatchManifest
from .discovery_reconcile_a6 import _trace
from .identity import Principal
from .ingestion import IngestionStore, source_grants, ingestion_runs, A6_BD_GRANT_PREFIX
from .sa_store import domain_events, outbox, tenants
from .storage import now_utc

PREFIX = A6_BD_GRANT_PREFIX
LEASE_DAYS = 30  # Local technical credential lifetime, not institutional expiration.


def _prepare(db, tenant, viewer, manifest, handles):
    if not IG_ID.fullmatch(viewer):
        raise ConnectorError("BD_GRANT_INVALID_VIEWER", 422)
    names = [h.casefold() for h in handles]
    if not 1 <= len(names) <= 10 or len(set(names)) != len(names):
        raise ConnectorError("BD_GRANT_INVALID_SELECTION", 422)
    if not db.execute(select(tenants.c.tenant_id).where(tenants.c.tenant_id == tenant)).first():
        raise ConnectorError("INGESTION_TENANT_NOT_FOUND", 404)
    if db.execute(select(ingestion_runs.c.run_key).where(ingestion_runs.c.tenant_id == tenant,
            ingestion_runs.c.status == "reserved").limit(1)).first():
        raise ConnectorError("BD_GRANT_INGESTION_ACTIVE", 409)
    rows = db.execute(select(domain_events, outbox.c.seq.label("outbox_seq"))
        .outerjoin(outbox, outbox.c.seq == domain_events.c.seq).where(
            domain_events.c.tenant_id == tenant, domain_events.c.aggregate_type == "bd_identity")
        .order_by(domain_events.c.aggregate_id, domain_events.c.aggregate_version)).mappings().all()
    groups = {}
    for row in rows:
        groups.setdefault(row["aggregate_id"], []).append(row)
    known, ids, evidence = {}, {}, {}
    for group in groups.values():
        reserve, result = _trace(group)
        if not result or result["status"] != "IDENTIFIED":
            continue
        name, ident = reserve["username"].casefold(), result["instagram_id"]
        if known.setdefault(name, ident) != ident or ids.setdefault(ident, name) != name:
            raise ConnectorError("BD_RECONCILE_IDENTITY_CONFLICT", 409)
        if reserve["viewer_ig_id"] == viewer:
            evidence[name] = ident
    by_name = {s.username.casefold(): s for s in manifest.sources}
    selected = []
    for name in names:
        s = by_name.get(name)
        if (not s or s.status not in {"candidate", "review"} or not s.expected_ig_id
                or s.expected_ig_id == viewer or s.audience_intent == "not_mpe_targeted"
                or not s.audience_rationale_reference or evidence.get(name) != s.expected_ig_id
                or s.approval_reference or s.expires_at or s.allowed_operations):
            raise ConnectorError("BD_GRANT_SOURCE_NOT_ELIGIBLE", 403)
        ref = PREFIX + viewer + ":" + s.expected_ig_id
        existing = db.execute(select(source_grants).where(source_grants.c.tenant_id == tenant,
            source_grants.c.platform == Platform.INSTAGRAM.value,
            source_grants.c.source_account_id == s.expected_ig_id).with_for_update()).mappings().first()
        if existing and (not existing["enabled"] or existing["approval_reference"] != ref
                or datetime.fromisoformat(existing["expires_at"]) <= now_utc()):
            raise ConnectorError("BD_GRANT_EXISTING_CONFLICT_OR_EXPIRED", 409)
        expiry = datetime.fromisoformat(existing["expires_at"]) if existing else now_utc() + timedelta(days=LEASE_DAYS)
        selected.append((s, ref, expiry, bool(existing)))
    return selected


def provision(engine, tenant, viewer, manifest, handles, *, principal=None):
    """Preview by default; authenticated admin creates all new grants in one transaction."""
    if principal is not None and (principal.role != "admin" or principal.tenant_id != tenant):
        raise ConnectorError("BD_GRANT_ADMIN_REQUIRED", 403)
    with engine.begin() as db:
        if principal is not None:
            locked = db.execute(update(tenants).where(tenants.c.tenant_id == tenant).values(name=tenants.c.name))
            if locked.rowcount != 1:
                raise ConnectorError("INGESTION_TENANT_NOT_FOUND", 404)
        selected = _prepare(db, tenant, viewer, manifest, handles)
        updates = {}
        for s, ref, expiry, existing in selected:
            updates[s.username.casefold()] = s.model_copy(update={"status":"approved",
                "approval_reference":ref, "expires_at":expiry,
                "allowed_operations":["business_discovery_metadata_read"]})
            if principal is not None and not existing:
                db.execute(insert(source_grants).values(tenant_id=tenant,platform=Platform.INSTAGRAM.value,
                    source_account_id=s.expected_ig_id,approval_reference=ref,approved_by=principal.actor_id,
                    approved_at=now_utc().isoformat(),expires_at=expiry.isoformat(),enabled=1))
                IngestionStore._audit_grant(db,tenant,principal.actor_id,Platform.INSTAGRAM.value,
                    s.expected_ig_id,"ingestion.grant.created",1)
        updated = BatchManifest.model_validate({"schema_version":manifest.schema_version,
            "sources":[updates.get(s.username.casefold(),s).model_dump() for s in manifest.sources]})
    return updated, {"status":"TECHNICAL_GRANTS_PROVISIONED" if principal else "TECHNICAL_GRANTS_PLANNED",
        "institutional_decision":"DEC-018", "technical_lease_days":LEASE_DAYS,
        "manifest_sha256_before":manifest.fingerprint(),
        "manifest_sha256_after":updated.fingerprint() if principal else None,
        "selected":[{"username":s.username,"instagram_id":s.expected_ig_id,"existing":existing} for s,_,_,existing in selected],
        "grants_created":sum(not existing for _,_,_,existing in selected) if principal else 0,
        "grants_to_create":sum(not existing for _,_,_,existing in selected),
        "approved":sum(s.status=="approved" for s in updated.sources) if principal else sum(s.status=="approved" for s in manifest.sources),
        "external_data_accessed":False,"technical_verified":False,"scientific_admissions":0}
