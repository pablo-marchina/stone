"""A6 identity-only batches. Identity is not consent to ingest posts."""
from __future__ import annotations

import json
import os
from uuid import uuid4

from sqlalchemy import func, insert, select

from .business_discovery import IG_ID
from .connectors import ConnectorError, OfficialHttp, Platform, credential_for
from .discovery_batch import BatchManifest
from .discovery_history import cycle_lease
from .identity import Principal
from .ingestion import ingestion_runs, stable_id
from .sa_store import domain_events, outbox
from .storage import now_utc

RESERVATION = "business_discovery.identity_reserved"
RESULT = "business_discovery.identity_result"


# DEC-018: standing institutional authorization communicated by the project owner.
# Do not ask the operator to re-attest it for each batch. This is not a provider
# permission, a media grant or a scientific admission.
INSTITUTIONAL_DECISION = "DEC-018"


def identity_reserved_today(db, tenant, day):
    return db.execute(select(func.count()).select_from(domain_events).where(
        domain_events.c.tenant_id == tenant, domain_events.c.event_type == RESERVATION,
        domain_events.c.occurred_at >= day)).scalar_one()


def _key(tenant, day, handle):
    return stable_id("bd-identity-attempt", tenant, day, handle.casefold())


def plan_identity(engine, tenant, manifest: BatchManifest, viewer, handles, *, daily_budget=80):
    if not IG_ID.fullmatch(viewer) or not 4 <= daily_budget <= 80:
        raise ConnectorError("BD_IDENTITY_INVALID_LIMITS", 422)
    requested = [h.casefold() for h in handles]
    if not 1 <= len(requested) <= 5 or len(set(requested)) != len(requested):
        raise ConnectorError("BD_IDENTITY_EXPLICIT_SOURCES_REQUIRED", 422)
    by_name = {s.username.casefold(): s for s in manifest.sources}
    day = now_utc().date().isoformat()
    with engine.connect() as db:
        used = identity_reserved_today(db, tenant, day)
        runs = db.execute(select(func.count()).select_from(ingestion_runs).where(
            ingestion_runs.c.tenant_id == tenant, ingestion_runs.c.platform == Platform.INSTAGRAM.value,
            ingestion_runs.c.requested_at >= day)).scalar_one()
        active = db.execute(select(ingestion_runs.c.run_key).where(
            ingestion_runs.c.tenant_id == tenant, ingestion_runs.c.status == "reserved").limit(1)).first()
        selected = []
        for name in requested:
            source = by_name.get(name)
            if (source is None or source.status not in {"candidate", "review"}
                    or source.audience_intent == "not_mpe_targeted"
                    or source.expected_ig_id == viewer):
                raise ConnectorError("BD_IDENTITY_SOURCE_NOT_ELIGIBLE", 422)
            seen = db.execute(select(domain_events.c.seq).where(
                domain_events.c.tenant_id == tenant, domain_events.c.aggregate_type == "bd_identity",
                domain_events.c.aggregate_id == _key(tenant, day, name)).limit(1)).first()
            if seen:
                raise ConnectorError("BD_IDENTITY_DAILY_ATTEMPT_EXISTS", 409)
            selected.append(source)
    if active:
        raise ConnectorError("BD_IDENTITY_INGESTION_ACTIVE", 409)
    if used + len(selected) > 10 or 4 * runs + used + len(selected) > daily_budget:
        raise ConnectorError("BD_IDENTITY_DAILY_BUDGET_EXCEEDED", 429)
    return {"status":"PLAN_ONLY_NO_EXTERNAL_READ", "manifest_sha256":manifest.fingerprint(),
        "institutional_decision":INSTITUTIONAL_DECISION, "utc_day":day,
        "selected_sources":[s.username for s in selected], "max_identity_requests":len(selected),
        "identity_reserved_today":used, "conservative_reserved_today":4 * runs + used,
        "daily_request_budget":daily_budget, "grants_created":0, "external_data_accessed":False}, selected


def _event(db, tenant, key, version, event_type, payload):
    row = db.execute(insert(domain_events).values(event_id=str(uuid4()), tenant_id=tenant,
        aggregate_type="bd_identity", aggregate_id=key, aggregate_version=version,
        event_type=event_type, occurred_at=now_utc().isoformat(), payload=json.dumps(payload, sort_keys=True)))
    db.execute(insert(outbox).values(seq=row.inserted_primary_key[0], attempts=0, dead_letter=0))


def execute_identity(engine, principal: Principal, manifest, viewer, handles,
                     *, daily_budget=80, token=None, http=None):
    if principal.role != "admin":
        raise ConnectorError("BD_IDENTITY_ADMIN_REQUIRED", 403)
    if any(os.getenv(k) != "1" for k in ("TAPI_BD_IDENTITY_ENABLED", "TAPI_OFFICIAL_METADATA_READS", "TAPI_ZERO_BILLING_CONFIRMED")):
        raise ConnectorError("BD_IDENTITY_FLAGS_REQUIRED", 403)
    tenant = principal.tenant_id
    access = token if token is not None else credential_for(Platform.INSTAGRAM)
    if len(access) < 10:
        raise ConnectorError("CREDENTIAL_MISSING", 403)
    cycle = "a6identity-" + now_utc().strftime("%Y%m%d%H%M%S") + "-" + uuid4().hex[:8]
    results = []
    with cycle_lease(engine, tenant, cycle):
        plan, selected = plan_identity(engine, tenant, manifest, viewer, handles, daily_budget=daily_budget)
        day = plan["utc_day"]
        if now_utc().date().isoformat() != day:
            raise ConnectorError("BD_IDENTITY_UTC_DAY_CHANGED", 409)
        # Reserve the entire batch before network. Interrupted/unattempted slots are
        # deliberately not refunded. The A5 lease serializes A5 and A6 cycles.
        with engine.begin() as db:
            for source in selected:
                _event(db, tenant, _key(tenant, day, source.username), 1, RESERVATION,
                    {"cycle_key":cycle,"username":source.username,"viewer_ig_id":viewer,
                     "manifest_sha256":manifest.fingerprint(),"actor_id":principal.actor_id,
                     "institutional_decision":INSTITUTIONAL_DECISION,
                     "operation":"business_discovery_identity_read"})
        transport = http or OfficialHttp(instagram_version="v26.0")
        known = {s.expected_ig_id:s.username.casefold() for s in manifest.sources if s.expected_ig_id}
        try:
            for source in selected:
                key = _key(tenant, day, source.username)
                try:
                    if now_utc().date().isoformat() != day:
                        raise ConnectorError("BD_IDENTITY_UTC_DAY_CHANGED", 409)
                    data = transport.get(Platform.INSTAGRAM, viewer,
                        {"fields":f"business_discovery.username({source.username})"+"{id,username}"}, access)
                    found = data.get("business_discovery")
                    if str(data.get("id")) != viewer or not isinstance(found, dict):
                        raise ConnectorError("BD_IDENTITY_VIEWER_OR_SOURCE_MISMATCH", 403)
                    ident, name = str(found.get("id", "")), found.get("username")
                    if (not IG_ID.fullmatch(ident) or ident == viewer or not isinstance(name, str)
                            or name.casefold() != source.username.casefold()
                            or (source.expected_ig_id and source.expected_ig_id != ident)
                            or known.get(ident, source.username.casefold()) != source.username.casefold()):
                        raise ConnectorError("BD_IDENTITY_TARGET_MISMATCH", 403)
                    known[ident] = source.username.casefold()
                    result = {"username":source.username,"status":"IDENTIFIED","instagram_id":ident}
                except ConnectorError as exc:
                    result = {"username":source.username,"status":"BLOCKED","code":exc.code}
                    if exc.provider_diagnostic:
                        result["provider_diagnostic"] = exc.provider_diagnostic
                with engine.begin() as db:
                    _event(db, tenant, key, 2, RESULT, result)
                results.append(result)
                if result["status"] != "IDENTIFIED":
                    break
        finally:
            if http is None:
                transport.close()
    return {"status":"IDENTITY_BATCH_COMPLETED" if len(results)==len(selected) and all(r["status"]=="IDENTIFIED" for r in results) else "IDENTITY_BATCH_STOPPED",
        "cycle_key":cycle,"plan":plan,"results":results,"reserved_requests":len(selected),
        "grants_created":0,"posts_collected":0,"scientific_admissions":0,"production_approved":False}
