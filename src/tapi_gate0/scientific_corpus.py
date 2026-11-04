"""DEC-016: explicit per-source context and per-post scientific audience review.

Technical metadata is insufficient to prove a post targets MPEs. Only a
reviewed, evidence-backed decision can qualify a post scientifically.
No inference from account type or follower count is permitted here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import (Table, Column, String, ForeignKeyConstraint,
                        select, insert)
from sqlalchemy.exc import IntegrityError

from .connectors import ConnectorError, Platform
from .domain import ContentItem
from .ingestion import ingestion_records
from .sa_store import metadata, content_items
from .storage import now_utc


source_research_contexts = Table("corpus_source_research_contexts", metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("platform", String(32), primary_key=True),
    Column("source_account_id", String(128), primary_key=True),
    Column("creator_type", String(40), nullable=False),
    Column("business_size_class", String(24), nullable=False),
    Column("business_size_evidence_reference", String(512)),
    Column("sector_context", String(32), nullable=False),
    Column("audience_intent", String(24), nullable=False),
    Column("audience_rationale_reference", String(512), nullable=False),
    Column("reviewed_by", String(128), nullable=False),
    Column("reviewed_at", String(40), nullable=False),
    ForeignKeyConstraint(["tenant_id", "platform", "source_account_id"],
                         ["corpus_profiles.tenant_id", "corpus_profiles.platform",
                          "corpus_profiles.source_account_id"]),
)

post_scientific_reviews = Table("corpus_post_scientific_reviews", metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("content_id", String(128), primary_key=True),
    Column("review_id", String(64), primary_key=True),
    Column("targeting_status", String(32), nullable=False),
    Column("evidence_quality", String(20), nullable=False),
    Column("evidence_reference", String(512), nullable=False),
    Column("observed_modalities", String(128), nullable=False),
    Column("rubric_observability", String(24), nullable=False),
    Column("reviewed_by", String(128), nullable=False),
    Column("reviewed_at", String(40), nullable=False),
    ForeignKeyConstraint(["tenant_id", "content_id"],
                         ["content_items.tenant_id", "content_items.id"]),
)


class SourceResearchContextCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Platform
    source_account_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    creator_type: Literal[
        "mpe_business", "independent_creator", "educator_expert",
        "financial_institution", "fintech", "sector_brand",
        "sector_organization", "other",
    ]
    business_size_class: Literal[
        "micro", "small", "medium", "large", "unknown", "not_applicable",
    ] = "unknown"
    business_size_evidence_reference: str | None = None
    sector_context: Literal[
        "commerce", "food", "services", "beauty", "finance", "cross_sector", "other",
    ] = "other"
    audience_intent: Literal["mpe_targeted", "uncertain", "not_mpe_targeted"]
    audience_rationale_reference: str = Field(min_length=12, max_length=512)

    @model_validator(mode="after")
    def non_mpe_source_allowed(self):
        if self.creator_type == "mpe_business":
            if self.business_size_class not in {"micro", "small"} or (
                not self.business_size_evidence_reference or len(self.business_size_evidence_reference) < 12
            ):
                raise ValueError("MPE_SIZE_EVIDENCE_REQUIRED")
        return self


class PostScientificReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content_id: str = Field(min_length=8, max_length=128)
    targeting_status: Literal["mpe_targeted", "uncertain", "not_mpe_targeted"]
    evidence_quality: Literal["sufficient", "partial", "unobservable"]
    evidence_reference: str = Field(min_length=12, max_length=512)
    observed_modalities: list[Literal["caption", "image", "video", "audio", "transcript"]] = Field(
        default_factory=list, max_length=5)
    rubric_observability: Literal["not_assessed", "partial", "reviewed"] = "not_assessed"

    @model_validator(mode="after")
    def evidence_gate(self):
        if len(set(self.observed_modalities)) != len(self.observed_modalities):
            raise ValueError("DUPLICATE_EVIDENCE_MODALITY")
        if self.targeting_status == "mpe_targeted" and (
            self.evidence_quality != "sufficient" or not self.observed_modalities
        ):
            raise ValueError("MPE_TARGETING_OBSERVATION_REQUIRED")
        if self.evidence_quality == "unobservable" and self.observed_modalities:
            raise ValueError("UNOBSERVABLE_CANNOT_HAVE_MODALITIES")
        if self.rubric_observability == "reviewed" and (
            self.evidence_quality != "sufficient" or not self.observed_modalities
        ):
            raise ValueError("RUBRIC_EVIDENCE_REQUIRED")
        return self


def register_research_source_context(engine, tenant: str, actor: str,
                                     payload: SourceResearchContextCreate) -> dict:
    """Explicit human documentation; no API call and no inferred post eligibility."""
    from .corpus import corpus_profiles
    with engine.begin() as db:
        row = db.execute(select(corpus_profiles).where(
            corpus_profiles.c.tenant_id == tenant,
            corpus_profiles.c.platform == payload.platform.value,
            corpus_profiles.c.source_account_id == payload.source_account_id,
        )).mappings().first()
        if not row:
            raise ConnectorError("CORPUS_PROFILE_REQUIRED", 403)
        if db.execute(select(source_research_contexts.c.source_account_id).where(
            source_research_contexts.c.tenant_id == tenant,
            source_research_contexts.c.platform == payload.platform.value,
            source_research_contexts.c.source_account_id == payload.source_account_id,
        )).first():
            raise ConnectorError("SOURCE_CONTEXT_ALREADY_REGISTERED", 409)
        try:
            db.execute(insert(source_research_contexts).values(
                tenant_id=tenant, platform=payload.platform.value,
                source_account_id=payload.source_account_id,
                creator_type=payload.creator_type,
                business_size_class=payload.business_size_class,
                business_size_evidence_reference=payload.business_size_evidence_reference,
                sector_context=payload.sector_context,
                audience_intent=payload.audience_intent,
                audience_rationale_reference=payload.audience_rationale_reference,
                reviewed_by=actor, reviewed_at=now_utc().isoformat()))
        except IntegrityError as exc:
            raise ConnectorError("SOURCE_CONTEXT_ALREADY_REGISTERED", 409) from exc
    return {"source_context_recorded": True, "post_targeting_verified": False,
            "platform": payload.platform.value, "source_account_id": payload.source_account_id}


def record_scientific_post_review(engine, tenant: str, actor: str,
                                  payload: PostScientificReviewCreate) -> dict:
    """Append a human review only for an authentic ingested, non-synthetic item."""
    from .corpus import corpus_profiles
    with engine.begin() as db:
        record = db.execute(select(ingestion_records).where(
            ingestion_records.c.tenant_id == tenant,
            ingestion_records.c.content_id == payload.content_id,
        )).mappings().first()
        if not record:
            raise ConnectorError("INGESTED_CONTENT_REQUIRED", 403)
        post_blob = db.execute(select(content_items.c.payload).where(
            content_items.c.tenant_id == tenant,
            content_items.c.id == payload.content_id,
        )).scalar_one_or_none()
        if post_blob is None or ContentItem.model_validate_json(post_blob).is_synthetic:
            raise ConnectorError("REAL_CONTENT_REQUIRED", 403)
        profile = db.execute(select(corpus_profiles.c.source_account_id).where(
            corpus_profiles.c.tenant_id == tenant,
            corpus_profiles.c.platform == record["platform"],
            corpus_profiles.c.source_account_id == record["source_account_id"],
        )).first()
        if not profile:
            raise ConnectorError("CORPUS_PROFILE_REQUIRED", 403)
        context = db.execute(select(source_research_contexts.c.source_account_id).where(
            source_research_contexts.c.tenant_id == tenant,
            source_research_contexts.c.platform == record["platform"],
            source_research_contexts.c.source_account_id == record["source_account_id"],
        )).first()
        if not context:
            raise ConnectorError("SOURCE_RESEARCH_CONTEXT_REQUIRED", 403)
        review_id = str(uuid4())
        db.execute(insert(post_scientific_reviews).values(
            tenant_id=tenant, content_id=payload.content_id, review_id=review_id,
            targeting_status=payload.targeting_status,
            evidence_quality=payload.evidence_quality,
            evidence_reference=payload.evidence_reference,
            observed_modalities=",".join(sorted(payload.observed_modalities)),
            rubric_observability=payload.rubric_observability,
            reviewed_by=actor, reviewed_at=now_utc().isoformat()))
    return {"review_id": review_id, "content_id": payload.content_id,
            "targeting_status": payload.targeting_status,
            "scientifically_eligible_if_technical": (
                payload.targeting_status == "mpe_targeted"
                and payload.evidence_quality == "sufficient"
                and bool(payload.observed_modalities)
            ),
            "note": "A human review is not independent verification of research rights."}
