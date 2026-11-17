"""DEC-018 operation-specific local caption research and documentary context.

Uses durable authenticated-admin events, not the human-review tables. A grant
for metadata reads alone never enables model inference. No media, network,
publication, aggregation release or independently verified rights are implied.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from uuid import uuid4

from sqlalchemy import insert, select, update
from .connectors import ConnectorError
from .discovery_corpus_readiness import source_gate
from .discovery_history import lock_tenant
from .ingestion import cycle_leases, ingestion_runs, source_grants, stable_id
from .sa_store import domain_events, outbox
from .storage import now_utc

AGG = "bd_caption_research"
EVENT = "business_discovery.caption_research_provisioned"
REVOKED = "business_discovery.caption_research_revoked"
OPERATION = "offline_bd_caption_candidate_classification"
VERSION = "dec018-bd-caption-research.v1"

# Documentary hypotheses from the sampling labels, never legal business size.
TYPES = {
    "cross_sector_institution": ("sector_organization", "cross_sector"),
    "financial_services_mpe": ("fintech", "finance"),
    "merchant_payments_mpe": ("fintech", "finance"),
    "business_financial_management": ("sector_brand", "services"),
    "foodservice_association_regional": ("sector_organization", "food"),
    "beauty_industry_association": ("sector_organization", "beauty"),
    "municipal_entrepreneur_support": ("sector_organization", "cross_sector"),
    "women_entrepreneurship": ("sector_organization", "cross_sector"),
    "entrepreneurship_education": ("educator_expert", "cross_sector"),
    "black_entrepreneurship_creative": ("sector_organization", "cross_sector"),
    "ecommerce_education": ("sector_brand", "commerce"),
    "accounting_mpe": ("sector_brand", "services"),
    # V9/V10: documentary source context only, never a per-post sector/size label.
    "inclusive_microenterprise_support": ("sector_organization", "cross_sector"),
    "digital_marketing_education": ("educator_expert", "services"),
    "beauty_entrepreneurship_education": ("sector_brand", "beauty"),
    "foodservice_platform_education": ("sector_brand", "food"),
    "fashion_microenterprise_inclusion": ("sector_organization", "commerce"),
    "ecommerce_logistics": ("sector_brand", "commerce"),
    "artisan_market_access": ("sector_organization", "commerce"),
    "pet_retail_education": ("educator_expert", "commerce"),
    "retail_digital_training": ("sector_organization", "commerce"),
}


def source_description(source):
    creator, sector = TYPES.get(source.sampling_stratum, ("other", "other"))
    return {"username": source.username, "source_account_id": source.expected_ig_id,
            "sampling_stratum": source.sampling_stratum,
            "source_evidence_reference": source.source_evidence_reference,
            "audience_rationale_reference": source.audience_rationale_reference,
            "declared_audience_intent": source.audience_intent,
            "creator_type_candidate": creator, "sector_context_candidate": sector,
            "business_size_class": "unknown"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def active_payload(payload, profile, grant, as_of):
    """Check stored operation against current durable profile and active grant."""
    if not isinstance(payload, dict) or not profile or not grant:
        return False
    try:
        description = payload["context"]
        return bool(
            payload["policy_version"] == VERSION and payload["operation"] == OPERATION
            and payload["institutional_reference"] == "DEC-018"
            and payload["human_review"] is False
            and isinstance(payload["actor_id"], str) and payload["actor_id"]
            and re.fullmatch(r"[0-9]{5,32}", payload["viewer_ig_id"])
            and payload["viewer_ig_id"] != profile["source_account_id"]
            and re.fullmatch(r"[a-f0-9]{64}", payload["manifest_sha256"])
            and payload["context_sha256"] == digest(description)
            and description["source_account_id"] == profile["source_account_id"]
            and description["sampling_stratum"] == profile["sampling_stratum"]
            and description["source_evidence_reference"] == profile["evidence_reference"]
            and description["business_size_class"] == "unknown"
            and description["declared_audience_intent"] in ("uncertain", "mpe_targeted")
            and description["audience_rationale_reference"]
            and profile["platform"] == grant["platform"] == "instagram"
            and profile["tenant_id"] == grant["tenant_id"]
            and profile["source_account_id"] == grant["source_account_id"]
            and payload["grant_reference"] == grant["approval_reference"]
            and payload["grant_approved_at"] == grant["approved_at"]
            and grant["enabled"] and datetime.fromisoformat(grant["expires_at"]) > as_of
            and grant["technical_verified_at"]
            and datetime.fromisoformat(grant["technical_verified_at"]) <= as_of)
    except (KeyError, TypeError, ValueError):
        return False


def _events(db, tenant, as_of):
    rows = db.execute(select(domain_events, outbox.c.seq.label("outbox_seq"))
        .outerjoin(outbox, outbox.c.seq == domain_events.c.seq)
        .where(domain_events.c.tenant_id == tenant, domain_events.c.aggregate_type == AGG)
        .order_by(domain_events.c.aggregate_id, domain_events.c.aggregate_version)).mappings().all()
    grouped = {}
    for row in rows:
        if datetime.fromisoformat(row["occurred_at"]) <= as_of:
            grouped.setdefault(row["aggregate_id"], []).append(row)
    result = {}
    for key, group in grouped.items():
        # Only a single provision, optionally followed by explicit revocation.
        if len(group) not in (1, 2):
            continue
        if any(r["aggregate_version"] != i or r["outbox_seq"] != r["seq"]
               for i, r in enumerate(group, 1)):
            continue
        first = group[0]
        if first["event_type"] != EVENT:
            continue
        try:
            payload = json.loads(first["payload"])
            sid = payload["context"]["source_account_id"]
            if key != stable_id("bd-caption-research", tenant, sid):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        if len(group) == 2:
            if group[1]["event_type"] != REVOKED:
                continue
            result[sid] = (None, "REVOKED")
        else:
            result[sid] = (payload, "PROVISIONED")
    return result


def documentary_contexts(db, tenant, as_of, profiles, grants):
    """Only current validated documentary contexts; not human reviews."""
    events = _events(db, tenant, as_of)
    return {("instagram", sid): payload for sid, (payload, state) in events.items()
            if state == "PROVISIONED" and active_payload(payload,
                profiles.get(("instagram", sid)), grants.get(("instagram", sid)), as_of)}


def _rows(db, tenant, manifest, viewer, now):
    from .corpus import corpus_profiles
    if not re.fullmatch(r"[0-9]{5,32}", viewer):
        raise ConnectorError("BD_BATCH_INVALID_VIEWER", 422)
    profiles = {r["source_account_id"]: r for r in db.execute(select(corpus_profiles).where(
        corpus_profiles.c.tenant_id == tenant, corpus_profiles.c.platform == "instagram")).mappings()}
    grants = {r["source_account_id"]: r for r in db.execute(select(source_grants).where(
        source_grants.c.tenant_id == tenant, source_grants.c.platform == "instagram")).mappings()}
    events = _events(db, tenant, now)
    rows = []
    for source in manifest.sources:
        if source.status != "approved":
            continue
        sid = source.expected_ig_id
        profile, grant = profiles.get(sid), grants.get(sid)
        action = source_gate(source, grant, now)
        context = source_description(source)
        payload = None
        if action == "TECHNICAL_SCOPE_MATCHED":
            if sid == viewer:
                action = "BD_BATCH_VIEWER_IS_TARGET"
            elif not profile or profile["sampling_stratum"] != source.sampling_stratum or \
                    profile["evidence_reference"] != source.source_evidence_reference:
                action = "REGISTERED_PROFILE_REQUIRED"
            else:
                existing, state = events.get(sid, (None, None))
                if state == "REVOKED":
                    action = "SCOPE_REVOKED"
                elif state == "PROVISIONED":
                    action = "ALREADY_PROVISIONED" if (
                        active_payload(existing, profile, grant, now)
                        and existing["viewer_ig_id"] == viewer
                        and existing["context_sha256"] == digest(context)) else "EXISTING_SCOPE_CONFLICT"
                    payload = existing
                else:
                    action = "PROVISION"
                    payload = {"context": context, "context_sha256": digest(context),
                        "policy_version": VERSION, "operation": OPERATION,
                        "institutional_reference": "DEC-018", "human_review": False,
                        "viewer_ig_id": viewer, "manifest_sha256": manifest.fingerprint(),
                        "grant_reference": grant["approval_reference"],
                        "grant_approved_at": grant["approved_at"]}
        rows.append((source, action, payload))
    return rows


def _summary(rows):
    return [{"username": s.username, "action": action,
             "context": source_description(s)} for s, action, _ in rows]


def plan_research(engine, tenant, manifest, viewer):
    with engine.connect() as db:
        rows = _rows(db, tenant, manifest, viewer, now_utc())
    return {"status": "CAPTION_RESEARCH_PLANNED", "operation": OPERATION,
            "sources": _summary(rows),
            "scoped_sources": sum(a == "ALREADY_PROVISIONED" for _, a, _ in rows),
            "sources_to_provision": sum(a == "PROVISION" for _, a, _ in rows),
            "human_reviews": 0, "scientific_admissions": 0,
            "external_data_accessed": False, "database_mutated": False}


def _idle(db, tenant):
    if (db.execute(select(cycle_leases.c.cycle_key).where(
            cycle_leases.c.tenant_id == tenant)).first() or
        db.execute(select(ingestion_runs.c.run_key).where(
            ingestion_runs.c.tenant_id == tenant, ingestion_runs.c.status == "reserved")).first()):
        raise ConnectorError("BD_CORPUS_INGESTION_ACTIVE", 409)


def _append(db, tenant, sid, version, event, payload):
    seq = db.execute(insert(domain_events).values(event_id=str(uuid4()), tenant_id=tenant,
        aggregate_type=AGG, aggregate_id=stable_id("bd-caption-research", tenant, sid),
        aggregate_version=version, event_type=event, occurred_at=now_utc().isoformat(),
        payload=json.dumps(payload, sort_keys=True, ensure_ascii=False))).inserted_primary_key[0]
    db.execute(insert(outbox).values(seq=seq, attempts=0, dead_letter=0))


def provision_research(engine, principal, manifest, viewer, *, stopped):
    if principal.role != "admin" or not stopped:
        raise ConnectorError("BD_CORPUS_ADMIN_STOP_REQUIRED", 403)
    tenant = principal.tenant_id
    with engine.begin() as db:
        lock_tenant(db, tenant)
        _idle(db, tenant)
        rows = _rows(db, tenant, manifest, viewer, now_utc())
        if not rows or any(a not in ("PROVISION", "ALREADY_PROVISIONED") for _, a, _ in rows):
            raise ConnectorError("BD_CAPTION_RESEARCH_PLAN_BLOCKED", 409)
        # Lock source grants before re-planning, serializing concurrent revocation.
        for s, _, _ in sorted(rows, key=lambda x: x[0].expected_ig_id):
            locked = db.execute(update(source_grants).where(
                source_grants.c.tenant_id == tenant, source_grants.c.platform == "instagram",
                source_grants.c.source_account_id == s.expected_ig_id).values(enabled=source_grants.c.enabled))
            if locked.rowcount != 1:
                raise ConnectorError("BD_CAPTION_RESEARCH_GRANT_CHANGED", 409)
        rows = _rows(db, tenant, manifest, viewer, now_utc())
        if any(a not in ("PROVISION", "ALREADY_PROVISIONED") for _, a, _ in rows):
            raise ConnectorError("BD_CAPTION_RESEARCH_PLAN_BLOCKED", 409)
        new = 0
        for s, action, payload in rows:
            if action == "PROVISION":
                _append(db, tenant, s.expected_ig_id, 1, EVENT,
                        {**payload, "actor_id": principal.actor_id})
                new += 1
    return {"status": "CAPTION_RESEARCH_PROVISIONED", "new_contexts_and_scopes": new,
            "already_provisioned": len(rows)-new, "operation": OPERATION,
            "human_reviews": 0, "scientific_admissions": 0,
            "external_data_accessed": False, "database_mutated": bool(new)}


def require_scoped_research(engine, tenant, manifest, viewer):
    """Dedicated local capability; never changes the global external deny gate."""
    with engine.connect() as db:
        _idle(db, tenant)
        rows = _rows(db, tenant, manifest, viewer, now_utc())
    if not rows or any(a != "ALREADY_PROVISIONED" for _, a, _ in rows):
        raise ConnectorError("BD_CONTEXTUAL_CLASSIFICATION_SCOPE_BLOCKED", 403)
    return VERSION


def revoke_research(engine, principal, manifest, viewer, username, *, stopped):
    if principal.role != "admin" or not stopped:
        raise ConnectorError("BD_CORPUS_ADMIN_STOP_REQUIRED", 403)
    tenant = principal.tenant_id
    source = next((s for s in manifest.sources if s.username.casefold() == username.casefold()), None)
    if source is None or not source.expected_ig_id:
        raise ConnectorError("BD_CAPTION_RESEARCH_SOURCE_UNKNOWN", 404)
    sid = source.expected_ig_id
    with engine.begin() as db:
        lock_tenant(db, tenant)
        _idle(db, tenant)
        payload, state = _events(db, tenant, now_utc()).get(sid, (None, None))
        if state != "PROVISIONED" or payload["viewer_ig_id"] != viewer:
            raise ConnectorError("BD_CAPTION_RESEARCH_SCOPE_NOT_ACTIVE", 409)
        _append(db, tenant, sid, 2, REVOKED,
                {"actor_id": principal.actor_id, "source_account_id": sid,
                 "operation": OPERATION, "institutional_reference": "DEC-018"})
    return {"status": "CAPTION_RESEARCH_REVOKED", "username": source.username,
            "human_reviews": 0, "scientific_admissions": 0,
            "external_data_accessed": False, "database_mutated": True}
