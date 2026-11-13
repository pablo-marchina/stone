"""Admin-only, opt-in ingestion of Business Discovery metadata into corpus.

A source must have an audited local approval, explicit persistence scope,
matching tenant-scoped grant and corpus registration BEFORE any Meta request.
The official response is read in the SAME invocation as the database writes:
never import user-edited preview JSON as provider evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (Table, Column, String, ForeignKeyConstraint,
                        select, insert, update, inspect)
from sqlalchemy.exc import IntegrityError

from .connectors import ConnectorError, OfficialHttp, NormalizedItem, Platform, credential_for
from .domain import MediaType
from .identity import IdentityFailure, Principal
from .ingestion import A6_BD_GRANT_PREFIX, IngestionStore, IngestionRequest, source_grants, ingestion_records, ingestion_runs, stable_id
from .mpe_sources import SourceGateError, ResearchSourceEntry, ResearchSourceFrame, authorized_source, load_frame
from .scientific_corpus import source_research_contexts
from .corpus import corpus_profiles
from .mpe_evidence import FirstEligibleSampler, canonical_hash
from .storage import now_utc
from .sa_store import metadata

# An append-only record for every official read. No access tokens, original
# approval documents, downloaded media or opaque pagination cursors are stored.
business_discovery_provenance = Table("business_discovery_provenance", metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("run_key", String(128), primary_key=True),
    Column("source_item_id", String(128), primary_key=True),
    Column("platform", String(32), nullable=False),
    Column("source_account_id", String(128), nullable=False),
    Column("content_id", String(128), nullable=False),
    Column("media_integrity_sha256", String(64), nullable=False),
    Column("batch_metadata_sha256", String(64), nullable=False),
    Column("approval_proof_sha256", String(64), nullable=False),
    Column("approval_reference", String(512), nullable=False),
    Column("acquisition_method", String(40), nullable=False),
    Column("graph_api_version", String(20), nullable=False),
    Column("observed_at", String(40), nullable=False),
    Column("recorded_at", String(40), nullable=False),
    ForeignKeyConstraint(["tenant_id", "run_key"],
                         ["ingestion_runs.tenant_id", "ingestion_runs.run_key"]),
    ForeignKeyConstraint(["tenant_id", "content_id"],
                         ["content_items.tenant_id", "content_items.id"]),
    ForeignKeyConstraint(["tenant_id", "platform", "source_account_id", "source_item_id"],
                         ["ingestion_records.tenant_id", "ingestion_records.platform",
                          "ingestion_records.source_account_id", "ingestion_records.source_item_id"]),
)


class DiscoveryCorpusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=30, pattern=r"^[A-Za-z0-9_.]+$")
    expected_ig_id: str = Field(min_length=5, max_length=32, pattern=r"^[0-9]+$")
    run_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    viewer_ig_id: str = Field(default="17841459971757521", min_length=5, max_length=32, pattern=r"^[0-9]+$")
    limit: int = Field(default=5, ge=1, le=10)
    max_pages: int = Field(default=2, ge=1, le=3)


class DiscoveryCorpusService:
    def __init__(self, store: IngestionStore):
        self.store = store

    def ingest(self, tenant: str, source: ResearchSourceEntry, approval_dir: Path,
               req: DiscoveryCorpusRequest, *, http: OfficialHttp | None = None,
               token: str | None = None) -> dict:
        # All authorization guards occur before a network call.
        if os.getenv("TAPI_MPE_PERSISTENCE_ENABLED") != "1":
            raise ConnectorError("MPE_PERSISTENCE_DISABLED", 403)
        if os.getenv("TAPI_OFFICIAL_METADATA_READS") != "1":
            raise ConnectorError("OFFICIAL_READS_DISABLED", 403)
        if os.getenv("TAPI_ZERO_BILLING_CONFIRMED") != "1":
            raise ConnectorError("PROVIDER_ZERO_BILLING_NOT_CONFIRMED", 403)
        if not isinstance(source, ResearchSourceEntry):
            raise ConnectorError("SOURCE_FRAME_V2_REQUIRED", 403)
        if req.username.casefold() != source.username.casefold():
            raise ConnectorError("SOURCE_USERNAME_MISMATCH", 403)
        try:
            approval = authorized_source(source, approval_dir)
        except SourceGateError as exc:
            raise ConnectorError(exc.code, 403) from exc
        if "corpus_metadata_ingest" not in source.allowed_operations:
            raise ConnectorError("CORPUS_PERSISTENCE_SCOPE_REQUIRED", 403)
        grant = self.store.read_grant(tenant, Platform.INSTAGRAM, req.expected_ig_id)
        if grant["approval_reference"].startswith(A6_BD_GRANT_PREFIX):
            raise ConnectorError("BD_GRANT_TECHNICAL_ROUTE_ONLY", 403)
        if grant["approval_reference"] != approval["approval_reference"]:
            raise ConnectorError("SOURCE_GRANT_REFERENCE_MISMATCH", 403)
        if not inspect(self.store.engine).has_table("corpus_profiles"):
            raise ConnectorError("CORPUS_REGISTRY_REQUIRED", 403)
        if not inspect(self.store.engine).has_table("corpus_source_research_contexts"):
            raise ConnectorError("SOURCE_CONTEXT_MIGRATION_REQUIRED", 403)
        if not inspect(self.store.engine).has_table("business_discovery_provenance"):
            raise ConnectorError("PROVENANCE_MIGRATION_REQUIRED", 403)
        # The legacy registry accepts five sectors. Financial institutions
        # remain eligible via v2 creator_type, sector_context and stratum.
        registry_sector = (
            source.sector_context if source.sector_context in
            {"commerce", "food", "services", "beauty", "other"} else "other"
        )
        with self.store.engine.connect() as con:
            registered = con.execute(select(corpus_profiles).where(
                corpus_profiles.c.tenant_id == tenant,
                corpus_profiles.c.platform == Platform.INSTAGRAM.value,
                corpus_profiles.c.source_account_id == req.expected_ig_id,
            )).mappings().first()
            context = con.execute(select(source_research_contexts).where(
                source_research_contexts.c.tenant_id == tenant,
                source_research_contexts.c.platform == Platform.INSTAGRAM.value,
                source_research_contexts.c.source_account_id == req.expected_ig_id,
            )).mappings().first()
        if not registered:
            raise ConnectorError("CORPUS_REGISTRATION_REQUIRED", 403)
        if (registered["sector"] != registry_sector or
            registered["sampling_stratum"] != source.sampling_stratum or
            registered["evidence_reference"] != source.source_evidence_reference):
            raise ConnectorError("CORPUS_REGISTRATION_MISMATCH", 403)
        if not context:
            raise ConnectorError("SOURCE_RESEARCH_CONTEXT_REQUIRED", 403)
        if (context["creator_type"] != source.creator_type or
            context["business_size_class"] != source.business_size_class or
            context["business_size_evidence_reference"] != source.business_size_evidence_reference or
            context["sector_context"] != source.sector_context or
            context["audience_intent"] != source.audience_intent or
            context["audience_rationale_reference"] != source.audience_rationale_reference):
            raise ConnectorError("SOURCE_RESEARCH_CONTEXT_MISMATCH", 403)
        access_token = token if token is not None else credential_for(Platform.INSTAGRAM)
        ingestion_req = IngestionRequest(platform=Platform.INSTAGRAM,
                                         source_account_id=req.expected_ig_id,
                                         run_key=req.run_key, limit=req.limit)
        # Reserve daily quota and run-key idempotency before network.
        self.store._reserve(tenant, ingestion_req)
        transport = http or OfficialHttp()
        created = duplicates = refreshed = 0
        try:
            report = FirstEligibleSampler(transport).scan(
                req.viewer_ig_id, access_token, approval,
                limit=req.limit, max_pages=req.max_pages)
            if (report.get("scientific_eligibility_status") != "UNREVIEWED_CONTENT" or
                report.get("counts", {}).get("scientifically_eligible_14d") != 0):
                raise ConnectorError("DISCOVERY_SCIENTIFIC_STATUS_UNEXPECTED", 502)
            actual = report["source"]
            if (actual["instagram_user_id"] != req.expected_ig_id or
                actual["username"].casefold() != source.username.casefold()):
                raise ConnectorError("DISCOVERY_ACCOUNT_MISMATCH", 403)
            # Validate complete provider batch before persisting any item.
            items = []
            for raw in report["eligible_media"]:
                if (raw.get("technical_metrics_eligible") is not True or
                    raw.get("scientific_eligible") is not False or
                    raw.get("observed_content_modalities") != []):
                    raise ConnectorError("DISCOVERY_TECHNICAL_ONLY_REQUIRED", 502)
                digest = raw.get("integrity_sha256")
                if digest != canonical_hash({k: v for k, v in raw.items()
                                            if k != "integrity_sha256"}):
                    raise ConnectorError("DISCOVERY_EVIDENCE_INTEGRITY_FAILED", 502)
                if raw["source_account_id"] != req.expected_ig_id:
                    raise ConnectorError("DISCOVERY_ACCOUNT_MISMATCH", 403)
                items.append(NormalizedItem(
                    platform=Platform.INSTAGRAM,
                    source_account_id=req.expected_ig_id,
                    source_item_id=raw["source_item_id"],
                    creator_handle=source.username,
                    media_type=MediaType(raw["media_type"]),
                    source_url=raw["source_url"],
                    published_at=datetime.fromisoformat(raw["published_at"]),
                    likes=raw["likes"], comments=raw["comments"],
                    follower_count=raw["follower_count"],
                    denominator_quality="observed_current_only",
                    metadata_only=True,
                ))
            # A human may revoke the source grant while the remote request is
            # in flight; revalidate approval/grant immediately before writes.
            try:
                current_approval = authorized_source(source, approval_dir)
            except SourceGateError as exc:
                raise ConnectorError(exc.code, 403) from exc
            current_grant = self.store.read_grant(tenant, Platform.INSTAGRAM, req.expected_ig_id)
            with self.store.engine.connect() as db:
                current_context = db.execute(select(source_research_contexts).where(
                    source_research_contexts.c.tenant_id == tenant,
                    source_research_contexts.c.platform == "instagram",
                    source_research_contexts.c.source_account_id == req.expected_ig_id,
                )).mappings().first()
            if (current_grant["approval_reference"] != current_approval["approval_reference"] or
                current_approval["approval_proof_sha256"] != approval["approval_proof_sha256"] or
                not current_context or dict(current_context) != dict(context) or
                "corpus_metadata_ingest" not in source.allowed_operations):
                raise ConnectorError("SOURCE_APPROVAL_CHANGED_DURING_READ", 403)
            # Discovery cursors are distinct from /{id}/media checkpoints.
            # Never mutate the ordinary first-party checkpoint.
            batch_digest = canonical_hash({"page_sha256": report["page_metadata_sha256"],
                                           "source_ig_id": req.expected_ig_id,
                                           "run_key": req.run_key})
            for item, evidence in zip(items, report["eligible_media"], strict=True):
                # Both the domain mutation and provenance are part of the
                # SAME item-level transaction. Failures roll back both.
                def write_provenance(db, content_id):
                    db.execute(insert(business_discovery_provenance).values(
                        tenant_id=tenant, run_key=req.run_key,
                        source_item_id=item.source_item_id, platform="instagram",
                        source_account_id=req.expected_ig_id,
                        content_id=content_id,
                        media_integrity_sha256=evidence["integrity_sha256"],
                        batch_metadata_sha256=batch_digest,
                        approval_proof_sha256=approval["approval_proof_sha256"],
                        approval_reference=approval["approval_reference"],
                        acquisition_method="graph_business_discovery",
                        graph_api_version=evidence["graph_api_version"],
                        observed_at=evidence["observed_at"],
                        recorded_at=now_utc().isoformat()))
                status = self.store._persist_item(
                    tenant, item, provenance_writer=write_provenance, run_key=req.run_key)
                if status == "created":
                    created += 1
                elif status == "refreshed":
                    refreshed += 1
                else:
                    duplicates += 1
            with self.store.engine.begin() as db:
                self.store._lock_reserved_run(db, tenant, req.run_key,
                    platform=Platform.INSTAGRAM, source=req.expected_ig_id)
                db.execute(update(source_grants).where(
                    source_grants.c.tenant_id == tenant,
                    source_grants.c.platform == "instagram",
                    source_grants.c.source_account_id == req.expected_ig_id,
                ).values(technical_verified_at=now_utc().isoformat()))
            self.store._finish(tenant, req.run_key, "completed", created, duplicates, refreshed)
            return {
                "status": "DISCOVERY_TECHNICAL_METADATA_COMMITTED",
                "scientifically_eligible_posts_created": 0,
                "scientific_review_required": True,
                "run_key": req.run_key,
                "source_account_id": req.expected_ig_id,
                "username": source.username,
                "new_records": created,
                "duplicate_records": duplicates,
                "refreshed_records": refreshed,
                "excluded_items": report["counts"],
                "pages_examined": report["pages_examined"],
                "next_page_available": report["another_page_possible"],
                "checkpoint_saved": False,
                "denominator_quality": "observed_current_only",
            }
        except (ConnectorError, ValueError, IntegrityError) as exc:
            reason = exc.code if isinstance(exc, ConnectorError) else "DISCOVERY_INGESTION_FAILED"
            self.store._finish(tenant, req.run_key, "failed", created, duplicates, refreshed, reason)
            if isinstance(exc, ConnectorError):
                raise
            raise ConnectorError(reason, 422) from exc
        finally:
            if http is None:
                transport.close()


def router_for_discovery_ingestion(identity, store: IngestionStore):
    router = APIRouter(prefix="/v1/ingestion", tags=["Curated MPE-targeted metadata ingestion"])

    def principal(request: Request) -> Principal:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token or " " in token:
            raise IdentityFailure()
        return identity.resolve(token)

    @router.post("/business-discovery/runs")
    def execute(payload: DiscoveryCorpusRequest, p: Principal = Depends(principal)):
        if p.role != "admin":
            raise IdentityFailure("FORBIDDEN", 403)
        frame_path = os.getenv("TAPI_MPE_APPROVED_FRAME_PATH")
        approval_path = os.getenv("TAPI_MPE_APPROVAL_PROOFS_DIR")
        if not frame_path or not approval_path:
            raise ConnectorError("APPROVED_SOURCE_FRAME_NOT_CONFIGURED", 403)
        try:
            frame = load_frame(Path(frame_path))
        except (ValueError, OSError, SourceGateError) as exc:
            raise ConnectorError("APPROVED_SOURCE_FRAME_INVALID", 403) from exc
        if not isinstance(frame, ResearchSourceFrame):
            raise ConnectorError("SOURCE_FRAME_V2_REQUIRED", 403)
        matches = [s for s in frame.sources if s.username.casefold() == payload.username.casefold()]
        if len(matches) != 1:
            raise ConnectorError("SOURCE_NOT_IN_APPROVED_FRAME", 403)
        return DiscoveryCorpusService(store).ingest(p.tenant_id, matches[0],
                                                     Path(approval_path), payload)
    return router
