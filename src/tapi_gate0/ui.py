"""Tenant-scoped read model for the first authenticated live product surface.

This is a zero-cost, read-only projection over the real SQL domain and outbox.
It intentionally does not collect platform data or perform paid operations.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from .identity import Principal
from .sa_store import (
    creators, content_items, metrics_snapshots, rubric_assessments,
    insights, creative_versions, domain_events,
)


class OverviewCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    creators: int = Field(ge=0)
    posts: int = Field(ge=0)
    metrics_snapshots: int = Field(ge=0)
    assessments: int = Field(ge=0)
    insights: int = Field(ge=0)
    creatives: int = Field(ge=0)
    events: int = Field(ge=0)


class OverviewPost(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content_id: str
    creator_id: str
    media_type: str
    published_at: datetime
    origin: str


class OverviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    data_scope: str = "synthetic_local"
    external_actions_enabled: bool = False
    financial_spend_ceiling_brl: int = 0
    counts: OverviewCounts
    recent_posts: list[OverviewPost]
    recent_events: list[dict]
    last_event_seq: int = Field(ge=0)


def router_for_authenticated_view(current_principal):
    router = APIRouter(prefix="/v1/ui", tags=["Product overview"])

    @router.get("/overview", response_model=OverviewResponse)
    def overview(request: Request, principal: Principal = Depends(current_principal)):
        tenant = principal.tenant_id
        engine = request.app.state.local_domain_store.engine
        tables = {
            "creators": creators,
            "posts": content_items,
            "metrics_snapshots": metrics_snapshots,
            "assessments": rubric_assessments,
            "insights": insights,
            "creatives": creative_versions,
            "events": domain_events,
        }
        with engine.connect() as conn:
            counts = {
                key: int(conn.execute(select(func.count()).select_from(table).where(table.c.tenant_id == tenant)).scalar_one())
                for key, table in tables.items()
            }
            raw_posts = conn.execute(select(content_items.c.payload).where(
                content_items.c.tenant_id == tenant,
            ).order_by(content_items.c.published_at.desc(), content_items.c.id.desc()).limit(8)).scalars().all()
            # Tenant scoping is explicit even on aggregates and cursor lookup.
            last_seq = conn.execute(select(func.max(domain_events.c.seq)).where(domain_events.c.tenant_id == tenant)).scalar()
            raw_events = conn.execute(select(domain_events).where(domain_events.c.tenant_id == tenant).order_by(
                domain_events.c.seq.desc()).limit(12)).mappings().all()
        posts = []
        for raw in raw_posts:
            post = json.loads(raw)
            posts.append(OverviewPost(**{key: post[key] for key in (
                "content_id", "creator_id", "media_type", "published_at", "origin")}) )
        # Return only metadata needed by the UI; no captions, tokens, PII or arbitrary event payloads.
        sanitized_events = [{key: event[key] for key in (
            "seq", "event_id", "aggregate_type", "aggregate_id", "event_type", "occurred_at")}
            for event in reversed(raw_events)]
        scope = "authorized_metadata_and_synthetic" if any(p.origin != "synthetic_local" for p in posts) else "synthetic_local"
        return OverviewResponse(tenant_id=tenant, data_scope=scope, counts=OverviewCounts(**counts), recent_posts=posts,
                                recent_events=sanitized_events, last_event_seq=int(last_seq or 0))

    return router
