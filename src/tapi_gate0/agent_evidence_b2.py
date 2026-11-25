"""B2: tenant-bound evidence retrieval and deterministic CreativeSpec handoff.

No external calls, no pseudo-gold and no instruction following from captions.
The candidate JSON matches CAP-023 CreativeSpec v1 for the integration PR.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from .domain import Id, ContentItem, Creator, MetricsCreate
from .sa_store import content_items, creators, metrics_snapshots


class EvidenceNotFound(Exception):
    pass


class ObservedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content_id: Id
    creator_id: Id
    origin: str
    source_url: str | None
    media_type: str
    published_at: datetime
    caption_excerpt: str | None
    caption_was_truncated: bool
    caption_is_untrusted_data: Literal[True] = True
    snapshot_id: Id | None
    likes: int | None = None
    comments: int | None = None
    followers: int | None = None
    observed_at: datetime | None = None
    metric_warning: str = "Observed counters are descriptive; historical follower denominator may differ."


class CreativeSpecHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["creative-spec.v1"] = "creative-spec.v1"
    spec_id: Id
    tenant_id: Id
    objective: str = Field(min_length=8, max_length=500)
    headline: str = Field(min_length=1, max_length=250)
    body: str = Field(min_length=1, max_length=2000)
    cta: str = Field(min_length=1, max_length=250)
    platform_intent: Literal["instagram_feed", "instagram_carousel"] = "instagram_feed"
    reference_content_ids: list[Id] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_references(self):
        if len(set(self.reference_content_ids)) != len(self.reference_content_ids):
            raise ValueError("CREATIVE_SPEC_DUPLICATE_REFERENCES")
        return self


class CreativeBriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec_id: Id
    objective: str = Field(min_length=8, max_length=500)
    headline: str = Field(min_length=1, max_length=250)
    body: str = Field(min_length=1, max_length=2000)
    cta: str = Field(min_length=1, max_length=250)
    platform_intent: Literal["instagram_feed", "instagram_carousel"] = "instagram_feed"
    reference_content_ids: list[Id] = Field(min_length=1, max_length=10)


class EvidenceRetriever:
    def __init__(self, engine):
        self.engine = engine

    def get(self, tenant_id: str, content_id: str,
            as_of: datetime | None = None, *, connection=None,
            lock_rows: bool = False) -> ObservedEvidence:
        as_of = as_of or datetime.now(timezone.utc)
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("EVIDENCE_AS_OF_TIMEZONE_REQUIRED")
        # The SQL index and the serialized payload are independent trust inputs.
        # Reject drift before returning captions/metrics or creating a spec.
        # A caller who owns a DB transaction may pass its trusted connection.
        # The validation and the subsequent Studio insert then share one view.
        if connection is None:
            with self.engine.connect() as con:
                return self.get(tenant_id, content_id, as_of,
                                connection=con, lock_rows=lock_rows)
        con = connection
        content_query = select(
            content_items.c.creator_id, content_items.c.origin,
            content_items.c.published_at, content_items.c.payload,
        ).where(
            content_items.c.tenant_id == tenant_id,
            content_items.c.id == content_id,
        )
        if lock_rows:
            content_query = content_query.with_for_update(read=True)
        record = con.execute(content_query).one_or_none()
        creator_query = select(
            creators.c.origin, creators.c.payload,
        ).where(
            creators.c.tenant_id == tenant_id,
            creators.c.id == record[0],
        ) if record is not None else None
        snapshot_query = select(
            metrics_snapshots.c.id, metrics_snapshots.c.observed_at,
            metrics_snapshots.c.payload,
        ).where(
            metrics_snapshots.c.tenant_id == tenant_id,
            metrics_snapshots.c.content_id == content_id,
        )
        if lock_rows:
            if creator_query is not None:
                creator_query = creator_query.with_for_update(read=True)
            snapshot_query = snapshot_query.with_for_update(read=True)
        creator_row = (con.execute(creator_query).one_or_none()
                       if creator_query is not None else None)
        snapshot_rows = (con.execute(snapshot_query).all()
                         if record is not None else [])
        if record is None:
            raise EvidenceNotFound("EVIDENCE_CONTENT_NOT_FOUND_IN_TENANT")
        if creator_row is None:
            raise EvidenceNotFound("EVIDENCE_CREATOR_NOT_FOUND_IN_TENANT")
        try:
            creator_id, origin, published_at, payload = record
            content = ContentItem.model_validate_json(payload)
            if (content.tenant_id != tenant_id
                    or content.content_id != content_id
                    or content.creator_id != creator_id
                    or content.origin.value != origin
                    or content.published_at != datetime.fromisoformat(published_at)):
                raise EvidenceNotFound("EVIDENCE_CONTENT_BINDING_INVALID")
            creator = Creator.model_validate_json(creator_row[1])
            if (creator.tenant_id != tenant_id
                    or creator.creator_id != creator_id
                    or creator.origin.value != origin
                    or creator_row[0] != origin):
                raise EvidenceNotFound("EVIDENCE_CREATOR_BINDING_INVALID")
            snapshots = []
            for indexed_id, indexed_time, blob in snapshot_rows:
                snap = MetricsCreate.model_validate_json(blob)
                if (snap.tenant_id != tenant_id
                        or snap.content_id != content_id
                        or snap.snapshot_id != indexed_id
                        or snap.observed_at != datetime.fromisoformat(indexed_time)):
                    raise EvidenceNotFound("EVIDENCE_SNAPSHOT_BINDING_INVALID")
                if snap.observed_at <= as_of:
                    snapshots.append(snap)
        except (ValueError, TypeError, AttributeError):
            # Never surface malformed tenant payloads or decoder details.
            raise EvidenceNotFound("EVIDENCE_STORED_PAYLOAD_INVALID") from None
        latest = max(snapshots, key=lambda m: (m.observed_at, m.snapshot_id),
                     default=None)
        caption = content.caption
        return ObservedEvidence(
            content_id=content.content_id, creator_id=content.creator_id,
            origin=content.origin.value,
            source_url=str(content.source_url) if content.source_url else None,
            media_type=content.media_type.value, published_at=content.published_at,
            caption_excerpt=caption[:500] if caption else None,
            caption_was_truncated=bool(caption and len(caption) > 500),
            snapshot_id=latest.snapshot_id if latest else None,
            likes=latest.likes if latest else None,
            comments=latest.comments if latest else None,
            followers=latest.follower_count if latest else None,
            observed_at=latest.observed_at if latest else None,
        )

    def handoff(self, tenant_id: str, request: CreativeBriefRequest, *, connection=None) -> CreativeSpecHandoff:
        # Research metadata and creative-use rights are distinct. This default
        # interface *only* permits truly synthetic, local, source-free fixtures.
        # No optional policy/grant parameter can weaken this B2 boundary.
        if connection is None:
            with self.engine.connect() as conn:
                return self.handoff(tenant_id, request, connection=conn)
        for content_id in request.reference_content_ids:
            evidence = self.get(tenant_id, content_id, connection=connection)
            row = connection.execute(select(content_items.c.payload).where(
                content_items.c.tenant_id == tenant_id,
                content_items.c.id == content_id,
            )).scalar_one_or_none()
            try:
                content = ContentItem.model_validate_json(row)
                if (evidence.origin != "synthetic_local"
                        or content.origin.value != "synthetic_local"
                        or content.is_synthetic is not True
                        or content.source_url is not None
                        or evidence.source_url is not None):
                    raise EvidenceNotFound("CREATIVE_REFERENCE_RIGHTS_PEP_REQUIRED")
            except (ValueError, TypeError, AttributeError):
                raise EvidenceNotFound("CREATIVE_REFERENCE_NOT_VERIFIED") from None
        return CreativeSpecHandoff(
            spec_id=request.spec_id, tenant_id=tenant_id,
            objective=request.objective, headline=request.headline,
            body=request.body, cta=request.cta,
            platform_intent=request.platform_intent,
            reference_content_ids=request.reference_content_ids,
        )
