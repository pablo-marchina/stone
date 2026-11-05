"""Opt-in technical metadata ingestion from Meta Business Discovery.

No crawler, publishing, media download, scientific corpus admission or new
source-specific legal attestations. An EXISTING active, tenant-scoped grant for
the *target* is mandatory. A separate first-party IG ID is the API viewer.

Domain content/snapshots/events are persisted atomically per item; an audited
observation event correlates the provider metadata digest with a run_key.
No access tokens, raw provider cursor, or approval document bodies are logged.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from fastapi import APIRouter, Depends, Request
from .identity import IdentityFailure, Principal
from sqlalchemy import select, insert, update, func
from sqlalchemy.exc import IntegrityError

from .business_discovery import BusinessDiscoveryProbe, CURSOR, IG_ID, USERNAME
from .connectors import ConnectorError, NormalizedItem, OfficialHttp, Platform, _date, _integer, credential_for
from .domain import MediaType
from .ingestion import IngestionRequest, IngestionStore, source_grants, stable_id
from .mpe_evidence import _instagram_url, canonical_hash
from .sa_store import domain_events, outbox, metrics_snapshots, content_items
from .storage import now_utc


class TechnicalDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=30, pattern=r"^[A-Za-z0-9_.]+$")
    expected_ig_id: str = Field(min_length=5, max_length=32, pattern=r"^[0-9]+$")
    viewer_ig_id: str = Field(min_length=5, max_length=32, pattern=r"^[0-9]+$")
    run_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    page_limit: int = Field(default=10, ge=1, le=10)
    max_pages: int = Field(default=4, ge=1, le=4)
    persist_limit: int = Field(default=3, ge=1, le=3)
    min_age_days: Literal[14] = 14

    @model_validator(mode="after")
    def source_is_external(self):
        if not USERNAME.fullmatch(self.username) or self.username.startswith(".") or self.username.endswith("."):
            raise ValueError("INVALID_TARGET_USERNAME")
        if self.viewer_ig_id == self.expected_ig_id:
            raise ValueError("DISCOVERY_VIEWER_MUST_DIFFER_FROM_TARGET")
        if self.username.casefold() in {"academy_fellow_stone", "instagram"}:
            raise ValueError("DISCOVERY_TECHNICAL_SOURCE_DENIED")
        return self


class TechnicalObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: NormalizedItem
    observed_at: datetime
    metadata_sha256: str
    page_sha256: str


class TechnicalDiscoveryReader:
    """Make at most four bounded official requests through fixed-host HTTPS."""
    def __init__(self, http: OfficialHttp):
        self.http = http

    def fetch(self, request: TechnicalDiscoveryRequest, token: str,
              *, observed_at: datetime | None = None) -> tuple[list[TechnicalObservation], dict]:
        seen_ids: set[str] = set()
        seen_cursors: set[str] = set()
        entries: list[TechnicalObservation] = []
        observed_at = observed_at or now_utc()
        cutoff = observed_at - timedelta(days=request.min_age_days)
        counts = dict(returned=0, too_recent=0, unsupported_format=0,
                      missing_metrics=0, invalid_metadata=0, duplicate_in_page=0,
                      accepted=0)
        after = None
        pages = 0
        next_page_possible = False
        for _ in range(request.max_pages):
            payload = self.http.get(Platform.INSTAGRAM, request.viewer_ig_id, {
                "fields": BusinessDiscoveryProbe._fields(request.username, request.page_limit, after)
                    .replace("comments_count}}", "comments_count,caption}}")
            }, token)
            if str(payload.get("id")) != request.viewer_ig_id:
                raise ConnectorError("BD_VIEWER_ACCOUNT_MISMATCH", 403)
            source = payload.get("business_discovery")
            if not isinstance(source, dict):
                raise ConnectorError("BD_DISCOVERY_UNAVAILABLE", 403)
            if (str(source.get("id")) != request.expected_ig_id or
                str(source.get("username", "")).casefold() != request.username.casefold()):
                raise ConnectorError("BD_TARGET_ACCOUNT_MISMATCH", 403)
            followers = _integer(source.get("followers_count"))
            if followers is None or followers <= 0:
                raise ConnectorError("BD_FOLLOWERS_DENOMINATOR_UNAVAILABLE", 422)
            media = source.get("media")
            if not isinstance(media, dict) or not isinstance(media.get("data"), list):
                raise ConnectorError("BD_MEDIA_UNAVAILABLE", 502)
            if len(media["data"]) > request.page_limit:
                raise ConnectorError("BD_PAGE_LIMIT_EXCEEDED", 502)
            pages += 1
            page_observed_at = now_utc()
            rows = media["data"]
            page_sha = canonical_hash({"target_ig_id":request.expected_ig_id,
                                       "provider_metadata":rows})
            for raw in rows:
                counts["returned"] += 1
                if not isinstance(raw, dict) or not IG_ID.fullmatch(str(raw.get("id", ""))):
                    counts["invalid_metadata"] += 1
                    continue
                ident = str(raw["id"])
                if ident in seen_ids:
                    counts["duplicate_in_page"] += 1
                    continue
                seen_ids.add(ident)
                if raw.get("media_type") == "CAROUSEL_ALBUM":
                    fmt = MediaType.CAROUSEL
                elif raw.get("media_product_type") == "REELS":
                    fmt = MediaType.REELS
                elif raw.get("media_type") == "IMAGE":
                    fmt = MediaType.IMAGE
                else:
                    counts["unsupported_format"] += 1
                    continue
                if not _instagram_url(raw.get("permalink")):
                    counts["invalid_metadata"] += 1
                    continue
                try:
                    published = _date(raw.get("timestamp")).astimezone(timezone.utc)
                    likes = _integer(raw.get("like_count"))
                    comments = _integer(raw.get("comments_count"))
                except (ConnectorError, ValueError):
                    counts["invalid_metadata"] += 1
                    continue
                if published > cutoff:
                    counts["too_recent"] += 1
                    continue
                if likes is None or comments is None:
                    counts["missing_metrics"] += 1
                    continue
                caption = raw.get("caption")
                if caption is not None and not isinstance(caption, str):
                    counts["invalid_metadata"] += 1
                    continue
                item = NormalizedItem(
                    platform=Platform.INSTAGRAM, source_account_id=request.expected_ig_id,
                    source_item_id=ident, creator_handle=source["username"],
                    media_type=fmt, source_url=raw["permalink"],
                    published_at=published, caption=caption[:10000] if caption else None,
                    likes=likes, comments=comments, follower_count=followers,
                    denominator_quality="observed_current_only", metadata_only=True,
                )
                entries.append(TechnicalObservation(
                    item=item, observed_at=page_observed_at,
                    metadata_sha256=canonical_hash({"item":raw, "followers":followers}),
                    page_sha256=page_sha))
                counts["accepted"] += 1
                if len(entries) >= request.persist_limit:
                    break
            paging = media.get("paging") or {}
            if not isinstance(paging, dict) or not isinstance(paging.get("cursors") or {}, dict):
                raise ConnectorError("BD_INVALID_PAGING", 502)
            cursor = (paging.get("cursors") or {}).get("after")
            if cursor is not None and (not isinstance(cursor, str) or not CURSOR.fullmatch(cursor)):
                raise ConnectorError("BD_INVALID_PAGING_CURSOR", 502)
            if paging.get("next") and cursor is None:
                raise ConnectorError("BD_PAGING_CURSOR_MISSING", 502)
            next_page_possible = bool(cursor and (paging.get("next") or len(rows) == request.page_limit))
            if len(entries) >= request.persist_limit or not next_page_possible:
                break
            if cursor == after or cursor in seen_cursors:
                raise ConnectorError("BD_PAGINATION_STALLED", 502)
            seen_cursors.add(cursor)
            after = cursor
        return entries, {"pages_examined": pages, "counts": counts,
                         "next_page_possible":next_page_possible,
                         "provider_data_not_scientifically_reviewed":True}


def _event_provenance(db, *, tenant: str, run_key: str, viewer: str,
                      source: str, source_username: str, observation: TechnicalObservation,
                      content_id: str, approval_reference: str):
    # Called by IngestionStore._persist_item within the SAME SQL transaction.
    snap = db.execute(select(metrics_snapshots.c.id).where(
        metrics_snapshots.c.tenant_id == tenant,
        metrics_snapshots.c.content_id == content_id,
    ).order_by(metrics_snapshots.c.observed_at.desc()).limit(1)).scalar_one_or_none()
    if snap is None:
        raise ConnectorError("BD_SNAPSHOT_MISSING_AFTER_PERSIST", 500)
    aggregate_id = stable_id("bd-observation-run", tenant, run_key)
    version = db.execute(select(func.coalesce(func.max(domain_events.c.aggregate_version), 0)).where(
        domain_events.c.tenant_id == tenant,
        domain_events.c.aggregate_type == "bd_technical_run",
        domain_events.c.aggregate_id == aggregate_id)).scalar_one() + 1
    ev = db.execute(insert(domain_events).values(
        event_id=str(uuid4()), tenant_id=tenant,
        aggregate_type="bd_technical_run", aggregate_id=aggregate_id,
        aggregate_version=version, event_type="business_discovery.metadata_observed",
        occurred_at=now_utc().isoformat(),
        payload=json.dumps({
            "schema_version":"business-discovery-technical.v1",
            "run_key":run_key,
            "viewer_ig_id":viewer,
            "source_account_id":source,
            "source_username":source_username,
            "source_item_id":observation.item.source_item_id,
            "content_id":content_id,
            "snapshot_id":snap,
            "observed_at":observation.observed_at.isoformat(),
            "metadata_sha256":observation.metadata_sha256,
            "page_sha256":observation.page_sha256,
            "acquisition_method":"graph_business_discovery",
            "graph_api_version":"v26.0",
            "denominator_quality":"observed_current_only",
            "grant_approval_reference":approval_reference,
            "scientific_eligibility":"NOT_ASSESSED",
        },separators=(",", ":"),ensure_ascii=False)))
    db.execute(insert(outbox).values(seq=ev.inserted_primary_key[0],
                                          attempts=0,dead_letter=0))


class TechnicalDiscoveryService:
    def __init__(self, store: IngestionStore):
        self.store = store

    def execute(self, tenant: str, req: TechnicalDiscoveryRequest,
                *, token: str | None = None, http: OfficialHttp | None = None) -> dict:
        if os.getenv("TAPI_BD_TECHNICAL_INGEST") != "1":
            raise ConnectorError("BD_TECHNICAL_INGEST_DISABLED", 403)
        if os.getenv("TAPI_OFFICIAL_METADATA_READS") != "1":
            raise ConnectorError("OFFICIAL_READS_DISABLED", 403)
        if os.getenv("TAPI_ZERO_BILLING_CONFIRMED") != "1":
            raise ConnectorError("ZERO_BILLING_NOT_CONFIRMED", 403)
        # A DEC-018 institutional decision is not itself a database grant.
        grant = self.store.read_grant(tenant, Platform.INSTAGRAM, req.expected_ig_id)
        access_token = token if token is not None else credential_for(Platform.INSTAGRAM)
        run = IngestionRequest(platform=Platform.INSTAGRAM,
                               source_account_id=req.expected_ig_id,
                               run_key=req.run_key, limit=req.page_limit)
        self.store._reserve(tenant, run)
        transport = http or OfficialHttp(instagram_version="v26.0")
        created = refreshed = duplicates = 0
        try:
            observations, report = TechnicalDiscoveryReader(transport).fetch(req, access_token)
            # Recheck approval/grant against concurrent administrative revocation.
            current = self.store.read_grant(tenant, Platform.INSTAGRAM, req.expected_ig_id)
            if current["approval_reference"] != grant["approval_reference"]:
                raise ConnectorError("BD_GRANT_CHANGED_DURING_READ", 403)
            # The provider identified the target professional account and returned
            # an official metadata response. Record TECHNICAL verification only,
            # under the same per-source lock used for grant revocation. This does
            # not imply legal reuse rights, human scientific review or production.
            with self.store.engine.begin() as db:
                locked = db.execute(update(source_grants).where(
                    source_grants.c.tenant_id == tenant,
                    source_grants.c.platform == Platform.INSTAGRAM.value,
                    source_grants.c.source_account_id == req.expected_ig_id,
                    source_grants.c.approval_reference == grant["approval_reference"],
                    source_grants.c.enabled == 1,
                ).values(technical_verified_at=now_utc().isoformat()))
                if locked.rowcount != 1:
                    raise ConnectorError("BD_GRANT_REVOKED_DURING_READ", 403)
                expiry = db.execute(select(source_grants.c.expires_at).where(
                    source_grants.c.tenant_id == tenant,
                    source_grants.c.platform == Platform.INSTAGRAM.value,
                    source_grants.c.source_account_id == req.expected_ig_id,
                )).scalar_one()
                if datetime.fromisoformat(expiry) <= now_utc():
                    raise ConnectorError("BD_GRANT_EXPIRED_DURING_READ", 403)
            for observation in observations:
                item = observation.item
                def evidence_writer(db, content_id):
                    _event_provenance(db, tenant=tenant, run_key=req.run_key,
                        viewer=req.viewer_ig_id, source=req.expected_ig_id,
                        source_username=req.username, observation=observation,
                        content_id=content_id, approval_reference=grant["approval_reference"])
                outcome = self.store._persist_item(tenant, item,
                                                    provenance_writer=evidence_writer)
                if outcome == "created":
                    created += 1
                elif outcome == "refreshed":
                    refreshed += 1
                else:
                    duplicates += 1
            self.store._finish(tenant, req.run_key, "completed",
                               created, duplicates, refreshed)
            return {
                "status":("BD_TECHNICAL_METADATA_COMMITTED" if observations
                          else "BD_TECHNICAL_NO_ELIGIBLE_MEDIA"),
                "run_key":req.run_key,
                "viewer_ig_id":req.viewer_ig_id,
                "source_account_id":req.expected_ig_id,
                "source_username":req.username,
                "new_records":created, "refreshed_records":refreshed,
                "duplicate_records":duplicates,
                "audited_observations":len(observations),
                "sample":report,
                "metadata_only":True,
                "research_corpus_accepted":False,
                "scientifically_validated":False,
                "production_approved":False,
            }
        except (ConnectorError, IntegrityError, ValueError):
            self.store._finish(tenant, req.run_key, "failed",
                               created, duplicates, refreshed,
                               "BD_TECHNICAL_INGEST_FAILED")
            raise
        finally:
            if http is None:
                transport.close()


def audit_run(engine, tenant: str, run_key: str) -> dict:
    """Read-only correlation check: snapshots, content, outbox and run scope."""
    from .ingestion import ingestion_runs
    with engine.connect() as db:
        run = db.execute(select(ingestion_runs).where(
            ingestion_runs.c.tenant_id == tenant,
            ingestion_runs.c.run_key == run_key)).mappings().first()
        if run is None:
            raise ConnectorError("BD_RUN_NOT_FOUND", 404)
        events = db.execute(select(domain_events).where(
            domain_events.c.tenant_id == tenant,
            domain_events.c.aggregate_type == "bd_technical_run",
            domain_events.c.aggregate_id == stable_id("bd-observation-run",tenant,run_key),
        ).order_by(domain_events.c.aggregate_version)).mappings().all()
        details = []
        for e in events:
            value = json.loads(e["payload"])
            snapshot = db.execute(select(metrics_snapshots.c.id).where(
                metrics_snapshots.c.tenant_id == tenant,
                metrics_snapshots.c.id == value["snapshot_id"],
                metrics_snapshots.c.content_id == value["content_id"],
            )).scalar_one_or_none()
            stored = db.execute(select(content_items.c.id).where(
                content_items.c.tenant_id == tenant,
                content_items.c.id == value["content_id"],
            )).scalar_one_or_none()
            delivered = db.execute(select(outbox.c.seq).where(outbox.c.seq == e["seq"])).scalar_one_or_none()
            details.append({"source_item_id":value["source_item_id"],
                "content_id":value["content_id"],
                "snapshot_id":value["snapshot_id"],
                "snapshot_exists":bool(snapshot),
                "content_exists":bool(stored),
                "outbox_exists":delivered is not None,
                "metadata_sha256":value["metadata_sha256"],
                "acquisition_method":value["acquisition_method"],
                "viewer_ig_id":value["viewer_ig_id"],
                "source_account_id":value["source_account_id"],
                "scientific_eligibility":value["scientific_eligibility"],
            })
    expected = (run["new_records"] + run["refreshed_records"]
                + run["duplicate_records"])
    valid = (run["status"] == "completed" and len(details) == expected and
             all(x["snapshot_exists"] and x["content_exists"] and x["outbox_exists"]
                 for x in details))
    return {"run_key":run_key, "status":run["status"],
            "new_records":run["new_records"],
            "refreshed_records":run["refreshed_records"],
            "duplicate_records":run["duplicate_records"],
            "observations":len(details),
            "has_persisted_observations":len(details)>0,
            "all_traces_valid":valid,
            "items":details}


def router_for_discovery_technical(identity, store: IngestionStore):
    """Admin-only API, token always read from operator's backend environment."""
    router = APIRouter(prefix="/v1/ingestion", tags=["Business Discovery technical metadata"])

    def principal(request: Request) -> Principal:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token or " " in token:
            raise IdentityFailure()
        return identity.resolve(token)

    @router.post("/business-discovery/technical-runs")
    def execute(payload: TechnicalDiscoveryRequest, p: Principal = Depends(principal)):
        if p.role != "admin":
            raise IdentityFailure("FORBIDDEN", 403)
        return TechnicalDiscoveryService(store).execute(p.tenant_id, payload)

    @router.get("/business-discovery/technical-runs/{run_key}/audit")
    def get_audit(run_key: str, p: Principal = Depends(principal)):
        if p.role != "admin":
            raise IdentityFailure("FORBIDDEN", 403)
        if not 8 <= len(run_key) <= 128 or not re.fullmatch(r"[A-Za-z0-9_.:-]+", run_key):
            raise ConnectorError("INVALID_RUN_KEY", 422)
        return audit_run(store.engine, p.tenant_id, run_key)

    return router
