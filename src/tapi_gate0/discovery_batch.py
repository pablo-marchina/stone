"""Bounded, explicitly curated multi-source Meta Business Discovery technical batch.

No automatic profile discovery, no source approval, no media downloading, no
scientific corpus admission. Existing per-source grants and per-run safety
checks are mandatory. All actual network access goes through the pre-existing
TechnicalDiscoveryService and fixed-host official transport.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select

from .connectors import ConnectorError, OfficialHttp, Platform
from .discovery_technical import (
    TechnicalDiscoveryRequest, TechnicalDiscoveryService, audit_run,
)
from .ingestion import IngestionStore, ingestion_records, ingestion_runs
from .mpe_sources import BANNED_TECHNICAL_TEST_ACCOUNTS
from .storage import now_utc


class BatchSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(pattern=r"^[A-Za-z0-9_.]{1,30}$")
    expected_ig_id: str | None = Field(default=None, pattern=r"^[0-9]{5,32}$")
    sampling_stratum: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]+$")
    audience_intent: Literal["mpe_targeted", "uncertain", "not_mpe_targeted"] = "uncertain"
    source_evidence_reference: str = Field(min_length=12, max_length=256)
    audience_rationale_reference: str | None = Field(default=None, max_length=256)
    status: Literal["candidate", "review", "approved", "rejected"] = "candidate"
    approval_reference: str | None = Field(default=None, min_length=12, max_length=512)
    expires_at: datetime | None = None
    allowed_operations: list[Literal["business_discovery_metadata_read"]] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_selection(self):
        if (self.username.startswith(".") or self.username.endswith(".") or
                self.username.casefold() in BANNED_TECHNICAL_TEST_ACCOUNTS):
            raise ValueError("BD_BATCH_INVALID_SOURCE")
        if self.status == "approved":
            if not (self.expected_ig_id and self.approval_reference and
                    self.audience_rationale_reference and self.expires_at and
                    self.allowed_operations == ["business_discovery_metadata_read"]):
                raise ValueError("BD_BATCH_SOURCE_APPROVAL_INCOMPLETE")
            if self.expires_at.tzinfo is None:
                raise ValueError("BD_BATCH_APPROVAL_EXPIRY_NEEDS_TIMEZONE")
            if self.audience_intent == "not_mpe_targeted":
                raise ValueError("BD_BATCH_NOT_MPE_TARGETED")
        return self


class BatchManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["tapi-bd-technical-batch.v1"]
    sources: list[BatchSource] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def no_duplicate_profiles(self):
        handles = [s.username.casefold() for s in self.sources]
        ids = [s.expected_ig_id for s in self.sources if s.expected_ig_id]
        if len(handles) != len(set(handles)) or len(ids) != len(set(ids)):
            raise ValueError("BD_BATCH_DUPLICATE_SOURCE")
        return self

    def fingerprint(self) -> str:
        # Fingerprints the curated manifest; does not attest legal authority.
        value = self.model_dump(mode="json", exclude_none=True)
        return hashlib.sha256(json.dumps(value, sort_keys=True,
            ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


class BatchLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_sources: int = Field(default=3, ge=1, le=5)
    page_limit: int = Field(default=10, ge=1, le=10)
    max_pages: int = Field(default=4, ge=1, le=4)
    persist_limit: int = Field(default=12, ge=1, le=40)

    @model_validator(mode="after")
    def bounded(self):
        if self.persist_limit > self.page_limit * self.max_pages:
            raise ValueError("BD_BATCH_PERSIST_EXCEEDS_REQUEST_BUDGET")
        return self


def selection_plan(manifest: BatchManifest, limits: BatchLimits) -> dict:
    approved = [s for s in manifest.sources if s.status == "approved"]
    selected = approved[:limits.max_sources]
    return {
        "schema_version": "tapi-bd-technical-plan.v1",
        "status": "PLAN_ONLY_NO_EXTERNAL_READ",
        "manifest_sha256": manifest.fingerprint(),
        "profiles_in_manifest": len(manifest.sources),
        "profiles_marked_approved_unverified": len(approved),
        "profiles_selected_unverified": len(selected),
        "profiles_deferred": len(manifest.sources) - len(selected),
        "max_official_requests": len(selected) * limits.max_pages,
        "max_observations_to_persist": len(selected) * limits.persist_limit,
        "selected_sources": [{"username": s.username, "expected_ig_id": s.expected_ig_id,
                              "sampling_stratum": s.sampling_stratum,
                              "audience_intent": s.audience_intent} for s in selected],
        "source_approvals_verified": False,
        "external_data_accessed": False,
        "scientific_corpus_accepted": False,
    }


def _unique_posts_by_source(store: IngestionStore, tenant: str, sources: list[BatchSource]) -> dict[str, int]:
    keys = [s.expected_ig_id for s in sources]
    if not keys:
        return {}
    with store.engine.connect() as db:
        rows = db.execute(select(
            ingestion_records.c.source_account_id,
            func.count().label("count"),
        ).where(
            ingestion_records.c.tenant_id == tenant,
            ingestion_records.c.platform == Platform.INSTAGRAM.value,
            ingestion_records.c.source_account_id.in_(keys),
            ingestion_records.c.metadata_only == 1,
        ).group_by(ingestion_records.c.source_account_id)).all()
    return {s.expected_ig_id: next((count for target, count in rows if target == s.expected_ig_id), 0)
            for s in sources}


def _preflight(store: IngestionStore, tenant: str, sources: list[BatchSource],
               batch_key: str, viewer_ig_id: str) -> None:
    """Fail *before the first network call* if any selected source is unsafe."""
    if any(os.getenv(k) != "1" for k in (
        "TAPI_OFFICIAL_METADATA_READS", "TAPI_ZERO_BILLING_CONFIRMED",
        "TAPI_BD_TECHNICAL_INGEST",
    )):
        raise ConnectorError("BD_BATCH_FLAGS_REQUIRED", 403)
    if not sources:
        raise ConnectorError("BD_BATCH_NO_APPROVED_SOURCES", 422)
    now = now_utc()
    for index, source in enumerate(sources, start=1):
        if source.expires_at <= now:
            raise ConnectorError("BD_BATCH_MANIFEST_APPROVAL_EXPIRED", 403)
        if source.expected_ig_id == viewer_ig_id:
            raise ConnectorError("BD_BATCH_VIEWER_IS_TARGET", 422)
        grant = store.read_grant(tenant, Platform.INSTAGRAM, source.expected_ig_id)
        if grant["approval_reference"] != source.approval_reference:
            raise ConnectorError("BD_BATCH_GRANT_REFERENCE_MISMATCH", 403)
        run_key = f"{batch_key}-{index:02d}"
        with store.engine.connect() as db:
            used = db.execute(select(ingestion_runs.c.run_key).where(
                ingestion_runs.c.tenant_id == tenant,
                ingestion_runs.c.run_key == run_key,
            )).first()
            if used:
                raise ConnectorError("BD_BATCH_RUN_KEY_ALREADY_USED", 409)
            today = now.date().isoformat()
            count = db.execute(select(func.count()).select_from(ingestion_runs).where(
                ingestion_runs.c.tenant_id == tenant,
                ingestion_runs.c.platform == Platform.INSTAGRAM.value,
                ingestion_runs.c.source_account_id == source.expected_ig_id,
                ingestion_runs.c.requested_at >= today,
            )).scalar_one()
            if count >= 5:
                raise ConnectorError("BD_BATCH_DAILY_SOURCE_QUOTA_REACHED", 429)


class TechnicalDiscoveryBatch:
    def __init__(self, store: IngestionStore):
        self.store = store

    def execute(self, tenant: str, manifest: BatchManifest, limits: BatchLimits,
                viewer_ig_id: str, *, batch_key: str | None = None,
                token: str | None = None, http: OfficialHttp | None = None) -> dict:
        approved = [s for s in manifest.sources if s.status == "approved"]
        selected = approved[:limits.max_sources]
        batch_key = batch_key or ("bdbatch-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                                  + "-" + secrets.token_hex(4))
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{8,80}", batch_key):
            raise ConnectorError("BD_BATCH_INVALID_KEY", 422)
        # Request type validates the viewer ID before any source can run.
        if not re.fullmatch(r"[0-9]{5,32}", viewer_ig_id):
            raise ConnectorError("BD_BATCH_INVALID_VIEWER", 422)
        _preflight(self.store, tenant, selected, batch_key, viewer_ig_id)
        before = _unique_posts_by_source(self.store, tenant, selected)
        report = {
            "schema_version": "tapi-bd-technical-coverage.v1",
            "status": "BATCH_COMPLETED",
            "batch_key": batch_key,
            "manifest_sha256": manifest.fingerprint(),
            "as_of": now_utc().isoformat(),
            "tenant_id": tenant,
            "technical_metadata_only": True,
            "scientifically_validated": False,
            "scientific_admissions_from_batch": 0,
            "rights_independently_verified": False,
            "production_approved": False,
            "target_reference": {"minimum_profiles": 30, "minimum_posts": 2000,
                                 "post_age_days": 14},
            "selection": {"total_sources": len(manifest.sources),
                          "approved_declarations": len(approved),
                          "attempted": 0, "deferred": len(manifest.sources)-len(selected)},
            "limits": {"max_sources": limits.max_sources,
                       "page_limit": limits.page_limit, "max_pages": limits.max_pages,
                       "persist_limit": limits.persist_limit,
                       "max_official_requests": len(selected)*limits.max_pages},
            "counts": {"new_records": 0, "refreshed_records": 0, "unchanged_duplicate_records": 0,
                       "provider_duplicate_items": 0, "returned": 0,
                       "too_recent": 0, "eligible_observations": 0,
                       "pages_examined": 0},
            "sources": [],
        }
        service = TechnicalDiscoveryService(self.store)
        for index, source in enumerate(selected, start=1):
            req = TechnicalDiscoveryRequest(
                username=source.username,
                expected_ig_id=source.expected_ig_id,
                viewer_ig_id=viewer_ig_id,
                run_key=f"{batch_key}-{index:02d}",
                page_limit=limits.page_limit, max_pages=limits.max_pages,
                persist_limit=limits.persist_limit,
            )
            report["selection"]["attempted"] += 1
            try:
                # A previous source may take time to read; a later grant must
                # still match the specific approval selected by the operator.
                current_grant = self.store.read_grant(
                    tenant, Platform.INSTAGRAM, source.expected_ig_id)
                if current_grant["approval_reference"] != source.approval_reference:
                    raise ConnectorError("BD_BATCH_GRANT_REFERENCE_MISMATCH", 403)
                result = service.execute(tenant, req, token=token, http=http)
                audit = audit_run(self.store.engine, tenant, req.run_key)
                if not audit["all_traces_valid"] or any(
                    item["source_account_id"] != source.expected_ig_id or
                    item["viewer_ig_id"] != viewer_ig_id for item in audit["items"]
                ):
                    report["status"] = "BATCH_AUDIT_FAILED"
                    report["failed_run_key"] = req.run_key
                    break
                counters = result["sample"]["counts"]
                for key, value in (("new_records", result["new_records"]),
                                   ("refreshed_records", result["refreshed_records"]),
                                   ("unchanged_duplicate_records", result["duplicate_records"]),
                                   ("provider_duplicate_items", counters["duplicate_in_page"]),
                                   ("returned", counters["returned"]),
                                   ("too_recent", counters["too_recent"]),
                                   ("eligible_observations", counters["accepted"]),
                                   ("pages_examined", result["sample"]["pages_examined"])):
                    report["counts"][key] += value
                report["sources"].append({
                    "username": source.username, "source_account_id": source.expected_ig_id,
                    "sampling_stratum": source.sampling_stratum,
                    "audience_intent": source.audience_intent,
                    "status": result["status"], "run_key": req.run_key,
                    "new_records": result["new_records"],
                    "refreshed_records": result["refreshed_records"],
                    "unchanged_duplicate_records": result["duplicate_records"],
                    "pages_examined": result["sample"]["pages_examined"],
                    "provider_counts": counters,
                    "next_page_possible": result["sample"]["next_page_possible"],
                    "audit_all_traces_valid": True,
                    "audit_observations": audit["observations"],
                    "evidence": [{"source_item_id": item["source_item_id"],
                                  "content_id": item["content_id"],
                                  "snapshot_id": item["snapshot_id"],
                                  "metadata_sha256": item["metadata_sha256"]}
                                 for item in audit["items"]],
                })
            except ConnectorError as exc:
                # No provider payload, credentials or raw error text in report.
                report["status"] = "BATCH_STOPPED_ON_SOURCE_FAILURE"
                report["failed_run_key"] = req.run_key
                report["failure_code"] = exc.code
                break
        after = _unique_posts_by_source(self.store, tenant, selected)
        report["coverage"] = {
            "selected_source_profiles": len(selected),
            "profiles_with_persisted_technical_posts": sum(v>0 for v in after.values()),
            "unique_technical_posts_before": sum(before.values()),
            "unique_technical_posts_after": sum(after.values()),
            "unique_technical_posts_added": sum(after.values())-sum(before.values()),
            "per_source_unique_posts_after": [
                {"source_account_id": source.expected_ig_id,
                 "username": source.username, "unique_posts": after[source.expected_ig_id]}
                for source in selected],
            "scientific_reference_profiles_reached": False,
            "scientific_reference_posts_reached": False,
            "scientific_reference_comparable": False,
            "coverage_exhaustive": False,
        }
        if report["status"] == "BATCH_COMPLETED" and not report["counts"]["eligible_observations"]:
            report["status"] = "BATCH_NO_ELIGIBLE_OBSERVATIONS"
        return report
