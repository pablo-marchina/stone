"""Renew only existing A6 technical leases; no provider reads or new authority."""
from datetime import datetime, timedelta
import json
from uuid import uuid4

from sqlalchemy import insert, select, update

from .business_discovery import IG_ID
from .connectors import ConnectorError, Platform
from .discovery_batch import BatchManifest
from .discovery_grants_a6 import LEASE_DAYS, PREFIX
from .discovery_history import lock_tenant
from .discovery_reconcile_a6 import _trace
from .ingestion import cycle_leases, ingestion_runs, source_grants, MANUAL_ORPHAN_REASON, stable_id
from .sa_store import domain_events, outbox, tenants
from .storage import now_utc

RENEWAL = "business_discovery.technical_grant_renewed"
AGGREGATE = "bd_technical_grant_renewal"
RENEW_WITHIN_DAYS = 7


def _identity_evidence(db, tenant, viewer):
    rows = db.execute(select(domain_events, outbox.c.seq.label("outbox_seq"))
        .outerjoin(outbox, outbox.c.seq == domain_events.c.seq).where(
            domain_events.c.tenant_id == tenant,
            domain_events.c.aggregate_type == "bd_identity")
        .order_by(domain_events.c.aggregate_id, domain_events.c.aggregate_version)).mappings().all()
    groups = {}
    for row in rows:
        groups.setdefault(row["aggregate_id"], []).append(row)
    names, ids, evidence = {}, {}, {}
    for group in groups.values():
        reserve, result = _trace(group)
        if not result or result["status"] != "IDENTIFIED":
            continue
        name, ident = reserve["username"].casefold(), result["instagram_id"]
        if names.setdefault(name, ident) != ident or ids.setdefault(ident, name) != name:
            raise ConnectorError("BD_RECONCILE_IDENTITY_CONFLICT", 409)
        if reserve["viewer_ig_id"] == viewer:
            row = group[-1]
            if name not in evidence or row["seq"] > evidence[name][1]:
                evidence[name] = (ident, row["seq"])
    return evidence


def _last_renewal(db, tenant, account):
    return db.execute(select(domain_events, outbox.c.seq.label("outbox_seq"))
        .outerjoin(outbox, outbox.c.seq == domain_events.c.seq).where(
            domain_events.c.tenant_id == tenant, domain_events.c.aggregate_type == AGGREGATE,
            domain_events.c.aggregate_id == stable_id("bd-grant-renewal", tenant, account))
        .order_by(domain_events.c.aggregate_version.desc()).limit(1)).mappings().first()


def renew_due(engine, tenant, viewer, manifest, *, principal=None):
    """Preview by default; renew or reconcile an exact interrupted manifest write."""
    if not IG_ID.fullmatch(viewer):
        raise ConnectorError("BD_GRANT_INVALID_VIEWER", 422)
    if principal is not None and (principal.role != "admin" or principal.tenant_id != tenant):
        raise ConnectorError("BD_GRANT_ADMIN_REQUIRED", 403)
    now = now_utc()
    fingerprint = manifest.fingerprint()
    changes, skipped, replacements, writes = [], [], {}, []
    with engine.begin() as db:
        if principal is not None:
            lock_tenant(db, tenant)
        elif not db.execute(select(tenants.c.tenant_id).where(tenants.c.tenant_id == tenant)).first():
            raise ConnectorError("INGESTION_TENANT_NOT_FOUND", 404)
        if (db.execute(select(cycle_leases.c.cycle_key).where(cycle_leases.c.tenant_id == tenant)).first()
                or db.execute(select(ingestion_runs.c.run_key).where(
                    ingestion_runs.c.tenant_id == tenant, ingestion_runs.c.status == "reserved")).first()):
            raise ConnectorError("BD_GRANT_INGESTION_ACTIVE", 409)
        evidence = _identity_evidence(db, tenant, viewer)
        for s in manifest.sources:
            if s.status != "approved" or not s.approval_reference.startswith(PREFIX):
                continue
            account = s.expected_ig_id
            ref = PREFIX + viewer + ":" + account
            if (s.approval_reference != ref or account == viewer
                    or evidence.get(s.username.casefold(), (None,))[0] != account):
                raise ConnectorError("BD_GRANT_RENEWAL_SCOPE_MISMATCH", 409)
            scope = (source_grants.c.tenant_id == tenant,
                     source_grants.c.platform == Platform.INSTAGRAM.value,
                     source_grants.c.source_account_id == account)
            grant = db.execute(select(source_grants).where(*scope).with_for_update()).mappings().first()
            if not grant or grant["approval_reference"] != ref:
                raise ConnectorError("BD_GRANT_RENEWAL_SCOPE_MISMATCH", 409)
            quarantined = db.execute(select(ingestion_runs.c.run_key).where(
                ingestion_runs.c.tenant_id == tenant, ingestion_runs.c.platform == Platform.INSTAGRAM.value,
                ingestion_runs.c.source_account_id == account,
                ingestion_runs.c.reason_code == MANUAL_ORPHAN_REASON).limit(1)).first()
            if not grant["enabled"] or quarantined:
                skipped.append({"username":s.username,"reason":"REVOKED" if not grant["enabled"] else "QUARANTINED"})
                continue
            current = datetime.fromisoformat(grant["expires_at"])
            previous = s.expires_at
            last = _last_renewal(db, tenant, account)
            if current != previous:
                # Recover only the exact previously committed transition from
                # this input manifest, never accept unexplained DB divergence.
                p = json.loads(last["payload"]) if last else {}
                if (not last or last["event_type"] != RENEWAL or last["outbox_seq"] is None
                        or p.get("manifest_sha256_before") != fingerprint
                        or p.get("source_account_id") != account
                        or p.get("viewer_ig_id") != viewer
                        or p.get("previous_expires_at") != previous.isoformat()
                        or p.get("expires_at") != current.isoformat() or current <= now):
                    raise ConnectorError("BD_GRANT_RENEWAL_MANIFEST_MISMATCH", 409)
                expiry, action = current, "reconcile_manifest"
            elif current > now + timedelta(days=RENEW_WITHIN_DAYS):
                skipped.append({"username":s.username,"reason":"NOT_DUE","expires_at":current.isoformat()})
                continue
            else:
                expiry, action = now + timedelta(days=LEASE_DAYS), "renew"
                writes.append((scope, grant, last, account, evidence[s.username.casefold()][1], expiry))
            replacements[s.username.casefold()] = s.model_copy(update={"expires_at":expiry})
            changes.append({"username":s.username,"action":action,
                            "previous_expires_at":previous.isoformat(),"expires_at":expiry.isoformat()})
        updated = BatchManifest.model_validate({"schema_version":manifest.schema_version,
            "sources":[replacements.get(s.username.casefold(),s).model_dump() for s in manifest.sources]})
        if principal is not None:
            for scope, grant, last, account, evidence_seq, expiry in writes:
                changed = db.execute(update(source_grants).where(*scope,
                    source_grants.c.enabled == 1, source_grants.c.approval_reference == grant["approval_reference"],
                    source_grants.c.expires_at == grant["expires_at"]).values(expires_at=expiry.isoformat()))
                if changed.rowcount != 1:
                    raise ConnectorError("BD_GRANT_RENEWAL_CONCURRENT_CHANGE", 409)
                payload = {"actor_id":principal.actor_id,"institutional_decision":"DEC-018",
                    "source_account_id":account,"viewer_ig_id":viewer,"identity_result_seq":evidence_seq,
                    "manifest_sha256_before":fingerprint,"manifest_sha256_after":updated.fingerprint(),
                    "previous_expires_at":datetime.fromisoformat(grant["expires_at"]).isoformat(),
                    "expires_at":expiry.isoformat(),"operation":"business_discovery_metadata_read"}
                event = db.execute(insert(domain_events).values(event_id=str(uuid4()),tenant_id=tenant,
                    aggregate_type=AGGREGATE,aggregate_id=stable_id("bd-grant-renewal",tenant,account),
                    aggregate_version=1 if last is None else last["aggregate_version"]+1,
                    event_type=RENEWAL,occurred_at=now.isoformat(),payload=json.dumps(payload,sort_keys=True)))
                db.execute(insert(outbox).values(seq=event.inserted_primary_key[0],attempts=0,dead_letter=0))
    return updated, {"status":"TECHNICAL_GRANTS_RENEWED" if principal else "TECHNICAL_GRANT_RENEWAL_PLANNED",
        "manifest_sha256_before":fingerprint,"manifest_sha256_after":updated.fingerprint() if principal else None,
        "grants_to_renew":len(writes),"grants_renewed":len(writes) if principal else 0,
        "changes":changes,"skipped":skipped,"grants_created":0,"external_data_accessed":False,
        "scientific_admissions":0}
