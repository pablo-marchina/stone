"""DEC-016/018 sampling-frame bridge and local lexical signal inventory."""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import re
from uuid import uuid4

from sqlalchemy import insert, select, update

from .connectors import ConnectorError
from .corpus import corpus_profiles
from .discovery_audience_signals import POLICY, assess_caption, sampling_sector
from .discovery_corpus_readiness import readiness_report, source_gate
from .discovery_history import lock_tenant
from .ingestion import cycle_leases, ingestion_runs, source_grants, stable_id
from .sa_store import domain_events, outbox, tenants
from .storage import now_utc


def _plan(db, tenant, manifest, viewer):
    if not re.fullmatch(r"[0-9]{5,32}", viewer):
        raise ConnectorError("BD_BATCH_INVALID_VIEWER", 422)
    if not db.execute(select(tenants.c.tenant_id).where(tenants.c.tenant_id == tenant)).first():
        raise ConnectorError("INGESTION_TENANT_NOT_FOUND", 404)
    now = now_utc()
    grants = {r["source_account_id"]: r for r in db.execute(select(source_grants).where(
        source_grants.c.tenant_id == tenant, source_grants.c.platform == "instagram")).mappings()}
    profiles = {r["source_account_id"]: r for r in db.execute(select(corpus_profiles).where(
        corpus_profiles.c.tenant_id == tenant, corpus_profiles.c.platform == "instagram")).mappings()}
    rows = []
    for source in manifest.sources:
        if source.status != "approved":
            continue
        sid = source.expected_ig_id
        sector = sampling_sector(source.sampling_stratum)
        reason = source_gate(source, grants.get(sid), now)
        if sid == viewer:
            reason = "BD_BATCH_VIEWER_IS_TARGET"
        profile = profiles.get(sid)
        if reason == "TECHNICAL_SCOPE_MATCHED":
            if profile is None:
                reason = "REGISTER"
            elif (profile["sector"], profile["sampling_stratum"], profile["evidence_reference"]) == (
                    sector, source.sampling_stratum, source.source_evidence_reference):
                reason = "ALREADY_REGISTERED"
            else:
                reason = "EXISTING_PROFILE_CONFLICT"
        rows.append((source, sector, reason))
    return rows


def _summary(rows):
    return [{"username": s.username, "sampling_stratum": s.sampling_stratum,
             "sector": sector, "action": action} for s, sector, action in rows]


def plan_registry(engine, tenant, manifest, viewer):
    with engine.connect() as db:
        return _summary(_plan(db, tenant, manifest, viewer))


def register_sampling_profiles(engine, principal, manifest, viewer, *, stopped):
    """Atomic admin registration; never creates grants, contexts or reviews."""
    if principal.role != "admin" or not stopped:
        raise ConnectorError("BD_CORPUS_ADMIN_STOP_REQUIRED", 403)
    tenant = principal.tenant_id
    with engine.begin() as db:
        lock_tenant(db, tenant)
        if (db.execute(select(cycle_leases.c.cycle_key).where(
                cycle_leases.c.tenant_id == tenant)).first() or
            db.execute(select(ingestion_runs.c.run_key).where(
                ingestion_runs.c.tenant_id == tenant, ingestion_runs.c.status == "reserved")).first()):
            raise ConnectorError("BD_CORPUS_INGESTION_ACTIVE", 409)
        rows = _plan(db, tenant, manifest, viewer)
        if any(action == "EXISTING_PROFILE_CONFLICT" for _, _, action in rows):
            raise ConnectorError("BD_CORPUS_PROFILE_CONFLICT", 409)
        registered = 0
        for source, sector, action in rows:
            if action != "REGISTER":
                continue
            sid = source.expected_ig_id
            # Same grant lock used by revocation; recheck scope after locking.
            where = (source_grants.c.tenant_id == tenant,
                     source_grants.c.platform == "instagram",
                     source_grants.c.source_account_id == sid)
            locked = db.execute(update(source_grants).where(*where).values(enabled=source_grants.c.enabled))
            if locked.rowcount != 1:
                raise ConnectorError("BD_CORPUS_GRANT_CHANGED", 409)
            grant = db.execute(select(source_grants).where(*where)).mappings().one()
            now = now_utc()
            if source_gate(source, grant, now) != "TECHNICAL_SCOPE_MATCHED":
                raise ConnectorError("BD_CORPUS_GRANT_CHANGED", 409)
            db.execute(insert(corpus_profiles).values(tenant_id=tenant, platform="instagram",
                source_account_id=sid, sector=sector, sampling_stratum=source.sampling_stratum,
                evidence_reference=source.source_evidence_reference, registered_at=now.isoformat()))
            seq = db.execute(insert(domain_events).values(event_id=str(uuid4()), tenant_id=tenant,
                aggregate_type="bd_sampling_profile", aggregate_id=stable_id("bd-profile", tenant, sid),
                aggregate_version=1, event_type="business_discovery.sampling_profile_registered",
                occurred_at=now.isoformat(), payload=json.dumps({"actor_id": principal.actor_id,
                    "source_account_id": sid, "sampling_stratum": source.sampling_stratum,
                    "sector": sector, "manifest_sha256": manifest.fingerprint(),
                    "institutional_reference": "DEC-018"}, sort_keys=True))).inserted_primary_key[0]
            db.execute(insert(outbox).values(seq=seq, attempts=0, dead_letter=0))
            registered += 1
    return {"status": "SAMPLING_PROFILES_REGISTERED", "new_profiles": registered,
            "already_registered": sum(a == "ALREADY_REGISTERED" for _, _, a in rows),
            "plan": _summary(rows), "source_contexts_created": 0, "scientific_admissions": 0,
            "external_data_accessed": False, "database_mutated": bool(registered),
            "production_approved": False}


def audience_preview(engine, tenant, manifest, viewer, *, include_private_evidence=False):
    """No network, no DB mutation, no scientific admission; optional hashed local evidence."""
    counts = Counter()
    per_source = defaultdict(Counter)
    details = []
    def observe(source, content_id, caption):
        result = assess_caption(caption)
        status = result["signal_status"]
        counts[status] += 1
        per_source[source.username][status] += 1
        if include_private_evidence:
            details.append({"content_id": content_id, "username": source.username, **result})
    readiness = readiness_report(engine, tenant, manifest, viewer, _caption_observer=observe)
    if sum(counts.values()) != readiness["first_blocking_stage"]["CAPTION_AVAILABLE_FOR_ASSESSMENT"]:
        raise ConnectorError("BD_AUDIENCE_PARTITION_MISMATCH", 409)
    statuses = ("EXPLICIT_AUDIENCE_SIGNAL", "MENTION_ONLY_UNCERTAIN", "NO_EXPLICIT_SIGNAL_ABSTAIN")
    report = {"schema_version": "tapi-bd-audience-preview.v1", "status": "AUDIENCE_SIGNALS_PLANNED",
              "policy_version": POLICY, "as_of": readiness["as_of"],
              "manifest_sha256": manifest.fingerprint(), "assessed_captions": sum(counts.values()),
              "signal_counts": {s: counts[s] for s in statuses},
              "per_source": [{"username": s, "counts": {k: c[k] for k in statuses}}
                             for s, c in sorted(per_source.items())],
              "registration_plan": plan_registry(engine, tenant, manifest, viewer),
              "canonical_corpus_card": readiness["canonical_corpus_card"],
              "targeting_decisions": 0, "human_reviews": 0, "scientific_admissions": 0,
              "external_data_accessed": False, "database_mutated": False,
              "scientifically_validated": False, "production_approved": False}
    if include_private_evidence:
        report["private_evidence"] = sorted(details, key=lambda d: (d["username"], d["content_id"]))
    return report
