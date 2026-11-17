"""A01.1/A01.2: read-only external technical inventory, not scientific corpus.

Tenant comes from the authenticated principal. Source grants are rechecked at
request time; no manifest admission, caption export, media access or inference.
The bounded local inventory is intentionally not a ranking implementation.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import and_, select

from .connectors import ConnectorError
from .corpus import corpus_profiles
from .corpus_rubric_read import read_stored_rubric
from .domain import ContentItem, Creator, MetricsCreate
from .identity import IdentityFailure, Principal, WRITE_RESEARCH
from .ingestion import ingestion_records, source_grants
from .sa_store import content_items, creators, metrics_snapshots
from .storage import now_utc

VERSION = "external-inventory-read.v1"
MAX_RECORDS = 10000
MAX_SNAPSHOTS = 20000


class InventoryFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Literal["instagram", "youtube"] | None = None
    media_type: Literal["reels", "carrossel", "imagem", "short"] | None = None
    source_account_id: str | None = Field(default=None, min_length=1, max_length=128)
    sector: Literal["commerce", "food", "services", "beauty", "other"] | None = None
    search: str | None = Field(default=None, max_length=100)
    offset: int = Field(default=0, ge=0, le=MAX_RECORDS)
    limit: int = Field(default=50, ge=1, le=100)


def _active(row, now):
    try:
        approved = datetime.fromisoformat(row["approved_at"])
        expires = datetime.fromisoformat(row["expires_at"])
        verified = datetime.fromisoformat(row["technical_verified_at"])
        return (row["enabled"] == 1 and approved <= verified <= now < expires)
    except (TypeError, ValueError):
        return False


def _base(db, tenant, now, *, content_id=None):
    r, p, g, c, a = ingestion_records, corpus_profiles, source_grants, content_items, creators
    join = r.join(p, and_(r.c.tenant_id == p.c.tenant_id, r.c.platform == p.c.platform,
                         r.c.source_account_id == p.c.source_account_id)).join(
        g, and_(r.c.tenant_id == g.c.tenant_id, r.c.platform == g.c.platform,
                r.c.source_account_id == g.c.source_account_id)).join(
        c, and_(r.c.tenant_id == c.c.tenant_id, r.c.content_id == c.c.id)).join(
        a, and_(c.c.tenant_id == a.c.tenant_id, c.c.creator_id == a.c.id))
    q = select(r.c.content_id, r.c.platform, r.c.source_account_id, r.c.source_item_id,
        r.c.denominator_quality, r.c.processed_at, p.c.sector, p.c.sampling_stratum,
        g.c.approved_at, g.c.expires_at, g.c.technical_verified_at, g.c.enabled,
        c.c.payload.label("content_payload"), c.c.origin.label("content_origin"),
        c.c.creator_id, c.c.published_at.label("indexed_published_at"),
        a.c.payload.label("creator_payload"), a.c.origin.label("creator_origin")
    ).select_from(join).where(r.c.tenant_id == tenant, r.c.metadata_only == 1,
        r.c.platform.in_(("instagram", "youtube")))
    if content_id is not None:
        q = q.where(r.c.content_id == content_id)
    rows = db.execute(q.limit(MAX_RECORDS + 1)).mappings().all()
    if len(rows) > MAX_RECORDS:
        raise ConnectorError("INVENTORY_LOCAL_LIMIT_EXCEEDED", 409)
    result = {}
    from collections import Counter
    multiplicity = Counter(row["content_id"] for row in rows)
    excluded = 0
    for row in rows:
        cid = row["content_id"]
        if multiplicity[cid] != 1:
            excluded += 1
            continue
        if not _active(row, now):
            excluded += 1
            continue
        try:
            post = ContentItem.model_validate_json(row["content_payload"])
            creator = Creator.model_validate_json(row["creator_payload"])
            if (post.tenant_id != tenant or creator.tenant_id != tenant
                    or post.content_id != cid or post.creator_id != row["creator_id"]
                    or creator.creator_id != post.creator_id or post.is_synthetic
                    or post.origin.value != row["platform"] or creator.origin != post.origin
                    or row["content_origin"] != row["platform"] or row["creator_origin"] != row["platform"]
                    or creator.source_profile_id != row["source_account_id"]
                    or post.published_at != datetime.fromisoformat(row["indexed_published_at"])
                    or post.published_at > now):
                raise ValueError("identity mismatch")
        except (ValidationError, ValueError, TypeError):
            excluded += 1
            continue
        result[cid] = (row, post, creator)
    return list(result.values()), excluded


def _snapshots(db, tenant, ids, now):
    result = {cid: [] for cid in ids}
    count = 0
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        rows = db.execute(select(metrics_snapshots.c.id, metrics_snapshots.c.content_id,
            metrics_snapshots.c.observed_at, metrics_snapshots.c.payload).where(
            metrics_snapshots.c.tenant_id == tenant,
            metrics_snapshots.c.content_id.in_(chunk)).limit(MAX_SNAPSHOTS - count + 1)).all()
        count += len(rows)
        if count > MAX_SNAPSHOTS:
            raise ConnectorError("INVENTORY_SNAPSHOT_LIMIT_EXCEEDED", 409)
        for sid, cid, observed, raw in rows:
            try:
                metric = MetricsCreate.model_validate_json(raw)
                if (metric.tenant_id != tenant or metric.content_id != cid or metric.snapshot_id != sid
                        or metric.observed_at != datetime.fromisoformat(observed)
                        or metric.observed_at > now or metric.followers_measured_at > metric.observed_at):
                    continue
            except (ValidationError, ValueError, TypeError):
                continue
            result[cid].append(metric)
    for items in result.values():
        items.sort(key=lambda m: (m.observed_at, m.snapshot_id), reverse=True)
    return result


def _metric(m):
    return {"snapshot_id": m.snapshot_id, "observed_at": m.observed_at.isoformat(),
            "followers_measured_at": m.followers_measured_at.isoformat(),
            "likes": m.likes, "comments": m.comments, "follower_count": m.follower_count,
            "views": m.views}


def _entry(row, post, creator, snapshots, now):
    latest = snapshots[0] if snapshots else None
    # Source URL is not returned yet: a metadata grant is not permission to
    # load or redistribute remote media. No external navigation is implied.
    return {
        "content_id": post.content_id, "creator_id": creator.creator_id,
        "source_account_id": row["source_account_id"], "source_item_id": row["source_item_id"],
        "platform": row["platform"], "handle": creator.handle,
        "media_type": post.media_type.value, "published_at": post.published_at.isoformat(),
        "operator_sector": row["sector"], "sampling_stratum": row["sampling_stratum"],
        "caption_available": bool(post.caption and post.caption.strip()),
        "age_at_least_14_days": post.published_at <= now - timedelta(days=14),
        "primary_instagram_format": row["platform"] == "instagram" and post.media_type.value in ("reels", "carrossel"),
        "source_grant_active_and_technically_verified": True,
        "grant_expires_at": row["expires_at"],
        "denominator_quality_latest_ingestion": row["denominator_quality"],
        "latest_snapshot": _metric(latest) if latest else None,
        "valid_snapshot_count": len(snapshots),
        # IDs break equal timestamps deterministically, not chronologically.
        "latest_snapshot_timestamp_tie": bool(len(snapshots) > 1 and snapshots[0].observed_at == snapshots[1].observed_at),
        "positive_latest_denominator": bool(latest and latest.follower_count > 0),
        "scientific_eligibility": "NOT_EVALUATED_BY_INVENTORY",
        "manifest_and_trace_reaudit_performed": False,
        "media_processing_allowed": False, "caption_text_returned": False,
    }


def _scope(now):
    return {"schema_version": VERSION, "as_of": now.isoformat(),
            "scope": "registered_external_metadata_with_current_technical_grant",
            "scientific_corpus": False, "ranking": False, "external_data_accessed": False,
            "snapshot_order": "observed_at_desc_snapshot_id_desc",
            "database_mutated": False, "production_approved": False}


def list_inventory(engine, tenant, filters: InventoryFilter):
    now = now_utc()
    with engine.connect() as db:
        rows, excluded = _base(db, tenant, now)
        search = (filters.search or "").strip().casefold()
        filtered = [(r, p, c) for r, p, c in rows
            if (not filters.platform or r["platform"] == filters.platform)
            and (not filters.media_type or p.media_type.value == filters.media_type)
            and (not filters.source_account_id or r["source_account_id"] == filters.source_account_id)
            and (not filters.sector or r["sector"] == filters.sector)
            and (not search or search in c.handle.casefold() or search in r["source_item_id"].casefold())]
        filtered.sort(key=lambda x: (x[1].published_at, x[1].content_id), reverse=True)
        page = filtered[filters.offset:filters.offset + filters.limit]
        snapshots = _snapshots(db, tenant, [p.content_id for _, p, _ in page], now)
        items = [_entry(r, p, c, snapshots[p.content_id], now) for r, p, c in page]
    return {**_scope(now), "total_visible_before_filters": len(rows),
            "excluded_joined_records": excluded, "total_filtered": len(filtered),
            "offset": filters.offset, "limit": filters.limit,
            "next_offset": filters.offset + len(items) if filters.offset + len(items) < len(filtered) else None,
            "items": items}


def get_inventory_item(engine, tenant, content_id, *, snapshot_limit=100, snapshot_offset=0, caption_replay=None):
    if not 1 <= snapshot_limit <= 100 or not 0 <= snapshot_offset <= MAX_SNAPSHOTS:
        raise ConnectorError("INVENTORY_SNAPSHOT_PAGE_INVALID", 422)
    now = now_utc()
    with engine.connect() as db:
        rows, _ = _base(db, tenant, now, content_id=content_id)
        if len(rows) != 1:
            raise ConnectorError("INVENTORY_CONTENT_NOT_FOUND", 404)
        row, post, creator = rows[0]
        snapshots = _snapshots(db, tenant, [content_id], now)[content_id]
        history = snapshots[snapshot_offset:snapshot_offset + snapshot_limit]
        return {**_scope(now), "item": _entry(row, post, creator, snapshots, now),
                "snapshots": [_metric(m) for m in history],
                "stored_rubric": read_stored_rubric(db, tenant, post, now),
                "caption_replay": caption_replay.detail(db,tenant,row,post,snapshots,now) if caption_replay is not None else {"status":"disabled"},
                "snapshot_offset": snapshot_offset, "snapshot_limit": snapshot_limit,
                "next_snapshot_offset": snapshot_offset + len(history) if snapshot_offset + len(history) < len(snapshots) else None}


def router_for_inventory(current_principal, engine, caption_replay=None):
    router = APIRouter(prefix="/v1/corpus/inventory", tags=["External technical inventory"])

    def reader(p: Principal = Depends(current_principal)):
        if p.role not in WRITE_RESEARCH:
            raise IdentityFailure("FORBIDDEN", 403)
        return p

    @router.get("")
    def listing(response: Response, p: Principal = Depends(reader),
                filters: InventoryFilter = Query()):
        response.headers["Cache-Control"] = "private, no-store"
        return list_inventory(engine, p.tenant_id, filters)

    @router.get("/{content_id}")
    def detail(content_id: str, response: Response, request: Request, p: Principal = Depends(reader),
               snapshot_limit: int = Query(100, ge=1, le=100),
               snapshot_offset: int = Query(0, ge=0, le=MAX_SNAPSHOTS)):
        response.headers["Cache-Control"] = "private, no-store"
        return get_inventory_item(engine, p.tenant_id, content_id,
            snapshot_limit=snapshot_limit, snapshot_offset=snapshot_offset,
            caption_replay=caption_replay if request.client and request.client.host in ('127.0.0.1','::1','testclient') else None)

    return router
