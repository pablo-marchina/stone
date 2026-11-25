"""Supervised, durable single hourly acquisition tick. No daemon or automatic retry."""
from __future__ import annotations

from datetime import timezone
import json
import os
from uuid import uuid4

from sqlalchemy import insert, select

from .connectors import ConnectorError
from .discovery_batch import BatchLimits
from .discovery_continuous import execute_cycle, plan_cycle, tenant_coverage
from .discovery_history import lock_tenant
from .discovery_recovery import inspect_recovery
from .ingestion import cycle_leases, ingestion_runs
from .sa_store import domain_events, outbox
from .storage import now_utc

AGGREGATE = "bd_scheduler"
CLAIM = "business_discovery.scheduler_claimed"
FINISH = "business_discovery.scheduler_finished"
ACK = "business_discovery.scheduler_stop_acknowledged"
SUCCESS = {"BATCH_COMPLETED", "BATCH_NO_ELIGIBLE_OBSERVATIONS", "NO_DUE_AUTHORIZED_SOURCES"}


def hour_slot(now):
    return now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()


def _latest(db, tenant):
    return db.execute(select(domain_events).where(
        domain_events.c.tenant_id == tenant,
        domain_events.c.aggregate_type == AGGREGATE,
        domain_events.c.aggregate_id == tenant,
    ).order_by(domain_events.c.aggregate_version.desc()).limit(1)).mappings().first()


def _state(row):
    if row is None:
        return {"status": "NEVER_RUN", "slot": None, "event_seq": None}
    payload = json.loads(row["payload"])
    kind = row["event_type"]
    status = ("CLAIMED" if kind == CLAIM else "ACKNOWLEDGED" if kind == ACK else
              "FINISHED" if kind == FINISH and payload.get("result") in SUCCESS else "STOPPED")
    return {"status": status, "slot": payload["slot"], "event_seq": row["seq"]}


def _append(db, tenant, previous, kind, payload):
    seq = db.execute(insert(domain_events).values(
        event_id=str(uuid4()), tenant_id=tenant, aggregate_type=AGGREGATE,
        aggregate_id=tenant, aggregate_version=1 if previous is None else previous["aggregate_version"] + 1,
        event_type=kind, occurred_at=now_utc().isoformat(), payload=json.dumps(payload, sort_keys=True),
    )).inserted_primary_key[0]
    db.execute(insert(outbox).values(seq=seq, attempts=0, dead_letter=0))
    return seq


def _active(db, tenant):
    return (db.execute(select(cycle_leases.c.cycle_key).where(cycle_leases.c.tenant_id == tenant)).first()
            or db.execute(select(ingestion_runs.c.run_key).where(
                ingestion_runs.c.tenant_id == tenant, ingestion_runs.c.status == "reserved")).first())


def _state_block(state, slot):
    if state["status"] in {"CLAIMED", "STOPPED"}:
        return "BD_SCHEDULER_STOP_REVIEW_REQUIRED"
    if state["slot"] is not None and state["slot"] >= slot:
        return "BD_SCHEDULER_SLOT_ALREADY_CONSUMED"
    return None


def _recovery_blocks(inspection):
    result = []
    if inspection["lease"] or inspection["reserved_runs"] or inspection["orphan_runs_without_lease"]:
        result.append("BD_SCHEDULER_INGESTION_ACTIVE")
    if inspection["quarantined_sources"] or any(not r["reviewed"] for r in inspection["latest_a5_blocked_runs"]):
        result.append("BD_SCHEDULER_SOURCE_REVIEW_REQUIRED")
    if inspection["meta_auth"]["blocked"]:
        result.append("BD_META_AUTH_BLOCKED")
    expiry = inspection["meta_credential_expiry"]
    if expiry["blocked"]:
        result.append(expiry["reason_code"])
    elif not expiry["token_expires_at"]:
        result.append("BD_SCHEDULER_TOKEN_EXPIRY_REQUIRED")
    return result


def _options(max_sources, daily_budget, refresh_hours):
    # Deliberate fixed bounded policy; existing A5 validates limits and quotas.
    return {
        "history": dict(mode="history", limits=BatchLimits(max_sources=max_sources, page_limit=10,
                        max_pages=4, persist_limit=40), daily_request_budget=daily_budget,
                        refresh_hours=refresh_hours, priority_policy="coverage"),
        "refresh": dict(mode="refresh", limits=BatchLimits(max_sources=max_sources, page_limit=10,
                         max_pages=2, persist_limit=12), daily_request_budget=daily_budget,
                         refresh_hours=refresh_hours, priority_policy="recency"),
    }


def preview_tick(store, tenant, manifest, viewer, *, max_sources=3, daily_budget=80, refresh_hours=24):
    now = now_utc()
    slot = hour_slot(now)
    options = _options(max_sources, daily_budget, refresh_hours)
    inspection = inspect_recovery(store.engine, tenant)
    with store.engine.connect() as db:
        state = _state(_latest(db, tenant))
    plans = {mode: plan_cycle(store, tenant, manifest, viewer, **opt)[0]
             for mode, opt in options.items()}
    # Three history-preferred hours, then one refresh-preferred hour (UTC).
    preferred = "refresh" if now.astimezone(timezone.utc).hour % 4 == 3 else "history"
    other = "history" if preferred == "refresh" else "refresh"
    chosen = next((m for m in (preferred, other) if plans[m]["selected_sources"]), None)
    blockers = _recovery_blocks(inspection)
    reason = _state_block(state, slot)
    if reason:
        blockers.append(reason)
    return {"schema_version": "tapi-bd-scheduler.v1", "status": "SCHEDULER_PLAN_ONLY",
            "policy_version": "bd-supervised-hourly.v1", "slot": slot,
            "manifest_sha256": manifest.fingerprint(), "state": state,
            "preferred_mode": preferred, "proposed_mode": chosen, "execution_blockers": blockers,
            "plans": plans, "tenant_coverage": tenant_coverage(store, tenant),
            "external_data_accessed": False, "scientific_admissions": 0,
            "production_approved": False}


def _claim(store, tenant, report):
    with store.engine.begin() as db:
        lock_tenant(db, tenant)
        if hour_slot(now_utc()) != report["slot"]:
            raise ConnectorError("BD_SCHEDULER_SLOT_CHANGED", 409)
        last = _latest(db, tenant)
        reason = _state_block(_state(last), report["slot"])
        if reason:
            raise ConnectorError(reason, 409)
        if _active(db, tenant):
            raise ConnectorError("BD_SCHEDULER_INGESTION_ACTIVE", 409)
        return _append(db, tenant, last, CLAIM, {"slot": report["slot"],
                       "mode": report["proposed_mode"], "manifest_sha256": report["manifest_sha256"]})


def _finish(store, tenant, seq, slot, result, cycle_key=None):
    with store.engine.begin() as db:
        lock_tenant(db, tenant)
        last = _latest(db, tenant)
        if last is None or last["seq"] != seq or last["event_type"] != CLAIM:
            raise ConnectorError("BD_SCHEDULER_CLAIM_CHANGED", 409)
        return _append(db, tenant, last, FINISH, {"slot": slot, "claim_seq": seq,
                       "result": result, "cycle_key": cycle_key})



EXECUTION_FLAGS = ("TAPI_BD_SCHEDULER_ENABLED", "TAPI_BD_CONTINUOUS_ENABLED",
                   "TAPI_BD_TECHNICAL_INGEST", "TAPI_OFFICIAL_METADATA_READS",
                   "TAPI_ZERO_BILLING_CONFIRMED", "TAPI_META_REQUIRE_TOKEN_EXPIRY")


def local_preflight_summary(report):
    """Read-only CLI readiness, not a provider check or reservation."""
    from collections import Counter
    missing_flags = [name for name in EXECUTION_FLAGS if os.getenv(name) != "1"]
    token_present = bool(os.getenv("TAPI_INSTAGRAM_ACCESS_TOKEN", "").strip())
    blockers = list(report["execution_blockers"])
    if missing_flags:
        blockers.append("BD_SCHEDULER_FLAGS_REQUIRED")
    if not token_present:
        blockers.append("BD_SCHEDULER_TOKEN_REQUIRED")
    plan = report["plans"][report["proposed_mode"] or report["preferred_mode"]]
    if not report["proposed_mode"] and not blockers:
        blockers.append("BD_SCHEDULER_NO_DUE_SOURCES")
    return {"schema_version":"tapi-bd-scheduler-preflight.v1",
            "status":"SCHEDULER_LOCAL_READY" if not blockers else "SCHEDULER_LOCAL_BLOCKED",
            "slot":report["slot"],"state":report["state"],"proposed_mode":report["proposed_mode"],
            "execution_blockers":blockers,"missing_flags":missing_flags,"token_present":token_present,
            "meta_auth":plan["meta_auth"],"meta_credential_expiry":plan["meta_credential_expiry"],
            "selected_sources":plan["selected_sources"],
            "deferred_reason_counts":dict(Counter(r["reason"] for r in plan["deferred"])),
            "daily_request_budget":plan["daily_request_budget"],
            "reserved_pages_today":plan["conservative_reserved_pages_today"],
            "max_official_requests":plan["max_official_requests"],
            "max_observations_to_persist":plan["max_observations_to_persist"],
            "tenant_coverage":report["tenant_coverage"],"provider_verified":False,
            "external_data_accessed":False,"database_mutated":False,"scientific_admissions":0}


def cycle_summary(cycle):
    """Expose counts and outcome, never raw observations or provider payloads."""
    batch = cycle.get("batch", {})
    return {"mode":cycle["mode"],"status":cycle["status"],
            "tenant_coverage_before":cycle["tenant_coverage_before"],
            "tenant_coverage_after":cycle["tenant_coverage_after"],
            "counts":batch.get("counts",{}),
            "sources":[{k:r[k] for k in ("username","status","new_records","refreshed_records",
                                         "pages_examined","audit_all_traces_valid") if k in r}
                       for r in batch.get("sources",[])],
            "failure_code":batch.get("failure_code"),
            "scientific_admissions":0}


def execute_tick(store, tenant, manifest, viewer, *, max_sources=3, daily_budget=80,
                 refresh_hours=24, token=None, http=None):
    if any(os.getenv(k) != "1" for k in EXECUTION_FLAGS):
        raise ConnectorError("BD_SCHEDULER_FLAGS_REQUIRED", 403)
    report = preview_tick(store, tenant, manifest, viewer, max_sources=max_sources,
                          daily_budget=daily_budget, refresh_hours=refresh_hours)
    if report["execution_blockers"]:
        raise ConnectorError(report["execution_blockers"][0], 409)
    mode = report["proposed_mode"]
    if mode is None:
        return {**report, "status": "SCHEDULER_NO_DUE_SOURCES"}
    seq = _claim(store, tenant, report)
    # A5 replans under its existing lease and enforces grant/quota/auth again.
    # Any unexpected interruption leaves the durable claim for explicit review.
    try:
        result = execute_cycle(store, tenant, manifest, viewer, token=token, http=http,
                               **_options(max_sources, daily_budget, refresh_hours)[mode])
    except ConnectorError as exc:
        _finish(store, tenant, seq, report["slot"], "BLOCKED")
        return {**report, "status": "SCHEDULER_STOPPED", "claim_seq": seq,
                "code": exc.code, "external_data_accessed": None}
    _finish(store, tenant, seq, report["slot"], result["status"], result.get("cycle_key"))
    return {**report, "status": "SCHEDULER_COMPLETED" if result["status"] in SUCCESS else "SCHEDULER_STOPPED",
            "claim_seq": seq, "cycle": result, "external_data_accessed": None}


def acknowledge_stop(store, principal, event_seq, *, stopped):
    """Admin acknowledges a specific stopped claim after inspection; no retry/refund."""
    if principal.role != "admin" or not stopped:
        raise ConnectorError("BD_SCHEDULER_ADMIN_STOP_REQUIRED", 403)
    tenant = principal.tenant_id
    inspection = inspect_recovery(store.engine, tenant)
    # Credential metadata may be repaired later; recovery/active/auth issues must be cleared first.
    blocks = _recovery_blocks(inspection)
    if any(b in {"BD_SCHEDULER_INGESTION_ACTIVE", "BD_SCHEDULER_SOURCE_REVIEW_REQUIRED", "BD_META_AUTH_BLOCKED"} for b in blocks):
        raise ConnectorError("BD_SCHEDULER_RECOVERY_REQUIRED", 409)
    with store.engine.begin() as db:
        lock_tenant(db, tenant)
        last = _latest(db, tenant)
        state = _state(last)
        if state["event_seq"] != event_seq or state["status"] not in {"CLAIMED", "STOPPED"} or _active(db, tenant):
            raise ConnectorError("BD_SCHEDULER_STOP_NOT_CURRENT", 409)
        _append(db, tenant, last, ACK, {"slot": state["slot"], "acknowledged_seq": event_seq,
                       "actor_id": principal.actor_id})
    return {"status": "SCHEDULER_STOP_ACKNOWLEDGED", "consumed_slot": state["slot"],
            "external_data_accessed": False, "quota_reservation_preserved": True}
