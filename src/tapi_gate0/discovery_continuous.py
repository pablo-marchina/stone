"""CAP-001 A5: one bounded, fair, private acquisition cycle; no background daemon."""
from __future__ import annotations

from datetime import timedelta
import os
import re
import secrets

from sqlalchemy import func, select

from .connectors import ConnectorError, Platform
from .discovery_batch import BatchLimits, BatchManifest, TechnicalDiscoveryBatch
from .discovery_history import cycle_lease, read_checkpoint
from .ingestion import IngestionStore, ingestion_records, ingestion_runs
from .storage import now_utc


def plan_cycle(store: IngestionStore, tenant: str, manifest: BatchManifest,
               viewer: str, *, mode: str, limits: BatchLimits,
               daily_request_budget: int = 80, refresh_hours: int = 24):
    if mode not in {"history", "refresh"} or not 4 <= daily_request_budget <= 80 or not 1 <= refresh_hours <= 720:
        raise ConnectorError("BD_CYCLE_INVALID_LIMITS", 422)
    if not re.fullmatch(r"[0-9]{5,32}", viewer):
        raise ConnectorError("BD_BATCH_INVALID_VIEWER", 422)
    if mode == "history" and limits.persist_limit != limits.page_limit * limits.max_pages:
        raise ConnectorError("BD_HISTORY_FULL_PAGE_BUDGET_REQUIRED", 422)
    now = now_utc()
    day = now.date().isoformat()
    due = []
    deferred = []
    with store.engine.connect() as db:
        rows = db.execute(select(ingestion_runs).where(
            ingestion_runs.c.tenant_id == tenant,
            ingestion_runs.c.platform == Platform.INSTAGRAM.value,
        ).order_by(ingestion_runs.c.requested_at.desc(), ingestion_runs.c.run_key.desc())).mappings().all()
        # Conservative bound: charge four pages for EVERY Instagram reservation,
        # including failed/reserved runs and A3/A4. Not a provider billing meter.
        used = 4 * sum(r["requested_at"] >= day for r in rows)
        for source in manifest.sources:
            reason = None
            latest = [r for r in rows if r["source_account_id"] == source.expected_ig_id]
            checkpoint = None
            if source.status != "approved":
                reason = "SOURCE_NOT_APPROVED"
            elif source.expected_ig_id == viewer:
                reason = "BD_BATCH_VIEWER_IS_TARGET"
            elif source.expires_at <= now:
                reason = "BD_BATCH_MANIFEST_APPROVAL_EXPIRED"
            else:
                try:
                    grant = store.read_grant(tenant, Platform.INSTAGRAM, source.expected_ig_id)
                    if grant["approval_reference"] != source.approval_reference:
                        reason = "BD_BATCH_GRANT_REFERENCE_MISMATCH"
                except ConnectorError as exc:
                    reason = exc.code
            if reason is None:
                if any(r["status"] == "reserved" for r in latest):
                    reason = "ACCOUNT_INGESTION_IN_PROGRESS"
                elif latest and latest[0]["status"] == "failed":
                    reason = "SOURCE_LAST_RUN_FAILED_REVIEW_REQUIRED"
                elif sum(r["requested_at"] >= day for r in latest) >= 5:
                    reason = "BD_BATCH_DAILY_SOURCE_QUOTA_REACHED"
            if reason is None and mode == "history":
                checkpoint = read_checkpoint(db, tenant, source.expected_ig_id)
                if checkpoint and (checkpoint["viewer_ig_id"] != viewer or
                        checkpoint["approval_reference"] != source.approval_reference):
                    reason = "BD_HISTORY_SCOPE_CHANGED"
                elif checkpoint and checkpoint["status"] != "continuation_available":
                    reason = "BD_HISTORY_FRONTIER_UNCONFIRMED"
            if mode == "refresh":
                refreshed = next((r for r in latest if r["run_key"].startswith("a5refresh-")
                                  and r["status"] == "completed"), None)
                if reason is None and refreshed and refreshed["requested_at"] > (now - timedelta(hours=refresh_hours)).isoformat():
                    reason = "REFRESH_NOT_DUE"
                priority = refreshed["requested_at"] if refreshed else ""
            else:
                priority = checkpoint["updated_at"] if checkpoint else ""
            if reason:
                deferred.append({"username": source.username, "reason": reason})
            else:
                due.append((priority, source.username, source))
    due.sort(key=lambda item: (item[0], item[1]))
    capacity = min(limits.max_sources, max(0, (daily_request_budget - used) // 4))
    selected = [s for _, _, s in due[:capacity]]
    deferred.extend({"username": s.username, "reason": "CYCLE_OR_DAILY_BUDGET_LIMIT"}
                    for _, _, s in due[capacity:])
    return {"schema_version": "tapi-bd-continuous-plan.v1",
            "status": "PLAN_ONLY_NO_EXTERNAL_READ", "mode": mode,
            "manifest_sha256": manifest.fingerprint(),
            "source_count": len(manifest.sources),
            "approved_source_count": sum(s.status == "approved" for s in manifest.sources),
            "selected_sources": [s.username for s in selected], "deferred": deferred,
            "daily_request_budget": daily_request_budget,
            "conservative_reserved_pages_today": used,
            "max_official_requests": len(selected) * limits.max_pages,
            "max_observations_to_persist": len(selected) * limits.persist_limit,
            "external_data_accessed": False, "scientific_admissions": 0}, selected


def tenant_coverage(store: IngestionStore, tenant: str) -> dict:
    with store.engine.connect() as db:
        base = [ingestion_records.c.tenant_id == tenant,
                ingestion_records.c.platform == Platform.INSTAGRAM.value,
                ingestion_records.c.metadata_only == 1]
        total, unique, profiles = db.execute(select(
            func.count(), func.count(func.distinct(ingestion_records.c.source_item_id)),
            func.count(func.distinct(ingestion_records.c.source_account_id))
        ).select_from(ingestion_records).where(*base)).one()
    return {"technical_records": total, "unique_media_ids": unique,
            "profiles_with_technical_records": profiles,
            "cross_source_duplicate_records": total - unique,
            "reference_minimum_profiles": 30, "reference_minimum_posts": 2000,
            "scientific_reference_comparable": False, "coverage_exhaustive": False}


def execute_cycle(store: IngestionStore, tenant: str, manifest: BatchManifest,
                  viewer: str, *, mode: str, limits: BatchLimits,
                  daily_request_budget: int = 80, refresh_hours: int = 24,
                  token=None, http=None):
    if os.getenv("TAPI_BD_CONTINUOUS_ENABLED") != "1":
        raise ConnectorError("BD_CONTINUOUS_DISABLED", 403)
    if any(os.getenv(k) != "1" for k in ("TAPI_OFFICIAL_METADATA_READS",
            "TAPI_ZERO_BILLING_CONFIRMED", "TAPI_BD_TECHNICAL_INGEST")):
        raise ConnectorError("BD_BATCH_FLAGS_REQUIRED", 403)
    if mode not in {"history", "refresh"}:
        raise ConnectorError("BD_CYCLE_INVALID_LIMITS", 422)
    key = f"a5{mode}-" + now_utc().strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(4)
    with cycle_lease(store.engine, tenant, key):
        plan, selected = plan_cycle(store, tenant, manifest, viewer, mode=mode,
            limits=limits, daily_request_budget=daily_request_budget, refresh_hours=refresh_hours)
        before = tenant_coverage(store, tenant)
        report = {"schema_version": "tapi-bd-continuous-cycle.v1", "cycle_key": key,
                  "mode": mode, "plan": plan, "status": "NO_DUE_AUTHORIZED_SOURCES",
                  "tenant_coverage_before": before, "tenant_coverage_after": before,
                  "scientific_admissions_from_batch": 0, "production_approved": False,
                  "scientifically_validated": False}
        if selected:
            subset = BatchManifest(schema_version=manifest.schema_version, sources=selected)
            report["batch"] = TechnicalDiscoveryBatch(store).execute(tenant, subset, limits,
                viewer, batch_key=key, token=token, http=http, history=mode == "history")
            report["status"] = report["batch"]["status"]
            report["tenant_coverage_after"] = tenant_coverage(store, tenant)
        return report
