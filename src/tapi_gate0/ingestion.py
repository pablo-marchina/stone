"""Audited official-API metadata ingestion with tenant grants and transaction outbox.

Network access defaults OFF. User-reported approval is kept distinct from an
account-token check; a grant alone never triggers an API call.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import (Table, Column, String, Integer, Text, ForeignKeyConstraint,
                        UniqueConstraint, select, insert, update, func)
from sqlalchemy.exc import IntegrityError

from .connectors import (Platform, ConnectorError, OfficialHttp, InstagramOfficial,
                         YouTubeOfficial, NormalizedItem, credential_for)
from .classification import classify_metadata_caption
from .domain import Creator, CreatorCreate, ContentCreate, MetricsCreate, Origin
from .sa_store import (metadata, tenants, creators, content_items, metrics_snapshots,
                       rubric_assessments, domain_events, outbox)
from .storage import now_utc
from .identity import Principal, IdentityFailure
from .gate0b_technical import assess_metadata_readiness


A6_BD_GRANT_PREFIX = "DEC-018:A6:business_discovery_metadata_read:"

source_grants = Table("ingestion_source_grants", metadata,
    Column("tenant_id",String(128),primary_key=True),
    Column("platform",String(32),primary_key=True),
    Column("source_account_id",String(128),primary_key=True),
    Column("approval_reference",String(512),nullable=False),
    Column("approved_by",String(128),nullable=False),
    Column("approved_at",String(40),nullable=False),
    Column("expires_at",String(40),nullable=False),
    Column("technical_verified_at",String(40)),
    Column("enabled",Integer,nullable=False,default=1),
    ForeignKeyConstraint(["tenant_id"],["tenants.tenant_id"]))

ingestion_runs = Table("ingestion_runs",metadata,
    Column("tenant_id",String(128),primary_key=True),
    Column("run_key",String(128),primary_key=True),
    Column("platform",String(32),nullable=False),
    Column("source_account_id",String(128),nullable=False),
    Column("requested_at",String(40),nullable=False),
    Column("status",String(24),nullable=False),
    Column("new_records",Integer,nullable=False,default=0),
    Column("refreshed_records",Integer,nullable=False,default=0,server_default="0"),
    Column("duplicate_records",Integer,nullable=False,default=0),
    Column("reason_code",String(80)),
    ForeignKeyConstraint(["tenant_id","platform","source_account_id"],
        ["ingestion_source_grants.tenant_id","ingestion_source_grants.platform",
         "ingestion_source_grants.source_account_id"]))

ingestion_records=Table("ingestion_records",metadata,
    Column("tenant_id",String(128),primary_key=True),
    Column("platform",String(32),primary_key=True),
    Column("source_account_id",String(128),primary_key=True),
    Column("source_item_id",String(128),primary_key=True),
    Column("content_id",String(128),nullable=False),
    Column("denominator_quality",String(40),nullable=False),
    Column("metadata_only",Integer,nullable=False),
    Column("processed_at",String(40),nullable=False),
    ForeignKeyConstraint(["tenant_id","content_id"],["content_items.tenant_id","content_items.id"]),
    ForeignKeyConstraint(["tenant_id","platform","source_account_id"],
        ["ingestion_source_grants.tenant_id","ingestion_source_grants.platform",
         "ingestion_source_grants.source_account_id"]))


# Persist only provider cursors (never URLs or tokens) after successful page commits.
# A separate table avoids retroactively changing migration 0002's run ledger.
ingestion_page_checkpoints = Table("ingestion_page_checkpoints", metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("platform", String(32), primary_key=True),
    Column("source_account_id", String(128), primary_key=True),
    Column("next_cursor", String(512)),
    Column("complete", Integer, nullable=False, default=0),
    Column("updated_at", String(40), nullable=False),
    ForeignKeyConstraint(["tenant_id", "platform", "source_account_id"],
        ["ingestion_source_grants.tenant_id", "ingestion_source_grants.platform",
         "ingestion_source_grants.source_account_id"]))


class GrantCreate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    platform: Platform
    source_account_id: str=Field(min_length=1,max_length=128,pattern=r"^[A-Za-z0-9_-]+$")
    approval_reference: str=Field(min_length=12,max_length=512)
    expires_at: datetime

    @model_validator(mode="after")
    def future(self):
        if self.expires_at.tzinfo is None or self.expires_at<=now_utc():
            raise ValueError("authorization expiry must be in the future and timezone-aware")
        return self


class IngestionRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    platform: Platform
    source_account_id: str=Field(min_length=1,max_length=128,pattern=r"^[A-Za-z0-9_-]+$")
    run_key: str=Field(min_length=8,max_length=128,pattern=r"^[A-Za-z0-9_.:-]+$")
    limit:int=Field(default=10,ge=1,le=10)
    min_age_days:int=Field(default=14,ge=14,le=3650)
    resume:bool=False
    video_ids:list[str]=Field(default_factory=list,max_length=10)
    shorts_evidence_reference: str | None=Field(default=None,min_length=12,max_length=512)

    @model_validator(mode="after")
    def scope(self):
        if self.platform==Platform.INSTAGRAM and (self.video_ids or self.shorts_evidence_reference):
            raise ValueError("Instagram collects bounded account media, not supplied video IDs")
        if self.platform==Platform.YOUTUBE and self.resume:
            raise ValueError("YouTube ID-list mode does not use an Instagram page checkpoint")
        if self.platform==Platform.YOUTUBE and (
            not self.video_ids or len(self.video_ids)>self.limit or not self.shorts_evidence_reference):
            raise ValueError("YouTube Shorts require explicit IDs and operator evidence reference")
        return self


class IngestionResult(BaseModel):
    run_key: str
    platform:Platform
    source_account_id:str
    new_records:int
    duplicate_records:int
    refreshed_records:int=0
    excluded_too_recent:int=0
    next_page_available:bool=False
    metadata_only:bool=True
    missing_modalities:list[str]=Field(default_factory=lambda:["image","video","audio","transcript"])
    ranking_warning:str="Denominators may be current or rounded; historical exact ranking requires source-specific validation."


def stable_id(prefix:str,*parts:str)->str:
    return prefix+"."+hashlib.sha256("\x1e".join(parts).encode()).hexdigest()[:22]


class IngestionStore:
    def __init__(self,engine):self.engine=engine

    def grant(self,tenant_id:str,actor_id:str,payload:GrantCreate):
        with self.engine.begin() as db:
            existing=db.execute(select(source_grants).where(
                source_grants.c.tenant_id==tenant_id,source_grants.c.platform==payload.platform.value,
                source_grants.c.source_account_id==payload.source_account_id)).first()
            if existing:raise ConnectorError("GRANT_ALREADY_EXISTS",409)
            db.execute(insert(source_grants).values(tenant_id=tenant_id,platform=payload.platform.value,
                source_account_id=payload.source_account_id,approval_reference=payload.approval_reference,
                approved_by=actor_id,approved_at=now_utc().isoformat(),
                expires_at=payload.expires_at.isoformat(),enabled=1))
            self._audit_grant(db,tenant_id,actor_id,payload.platform.value,
                              payload.source_account_id,"ingestion.grant.created",1)
        return {"platform":payload.platform.value,"source_account_id":payload.source_account_id,
                "authorization_recorded":True,"technical_verified":False}

    @staticmethod
    def _audit_grant(db, tenant, actor, platform, account, event_type, version):
        ev=db.execute(insert(domain_events).values(
            event_id=str(uuid4()),tenant_id=tenant,aggregate_type="ingestion_source_grant",
            aggregate_id=stable_id("grant",platform,account),
            event_type=event_type,aggregate_version=version,
            occurred_at=now_utc().isoformat(),
            payload=json.dumps({"platform":platform,"source_account_id":account,
                                "actor_id":actor},separators=(",",":"))))
        db.execute(insert(outbox).values(seq=ev.inserted_primary_key[0],
                                         attempts=0,dead_letter=0))

    def revoke_grant(self,tenant,actor,platform,account):
        """Admin caller, atomic revocation with durable audit event."""
        with self.engine.begin() as db:
            changed=db.execute(update(source_grants).where(
                source_grants.c.tenant_id==tenant,
                source_grants.c.platform==platform.value,
                source_grants.c.source_account_id==account,
                source_grants.c.enabled==1).values(enabled=0))
            if changed.rowcount!=1:
                raise ConnectorError("ACTIVE_SOURCE_GRANT_REQUIRED",404)
            self._audit_grant(db,tenant,actor,platform.value,account,
                              "ingestion.grant.revoked",2)
        return {"platform":platform.value,"source_account_id":account,
                "revoked":True,"audit_recorded":True}

    def read_grant(self,tenant,platform,account):
        with self.engine.connect() as db:
            row=db.execute(select(source_grants).where(source_grants.c.tenant_id==tenant,
                source_grants.c.platform==platform.value,
                source_grants.c.source_account_id==account)).mappings().first()
        if not row or not row["enabled"] or datetime.fromisoformat(row["expires_at"])<=now_utc():
            raise ConnectorError("VALID_SOURCE_GRANT_REQUIRED",403)
        return dict(row)

    def _resume_cursor(self, tenant: str, req: IngestionRequest) -> str:
        """Use only a cursor persisted from a prior successful authorized read."""
        with self.engine.connect() as db:
            row = db.execute(select(ingestion_page_checkpoints).where(
                ingestion_page_checkpoints.c.tenant_id == tenant,
                ingestion_page_checkpoints.c.platform == req.platform.value,
                ingestion_page_checkpoints.c.source_account_id == req.source_account_id,
            )).mappings().first()
        if not row:
            raise ConnectorError("PAGINATION_CHECKPOINT_REQUIRED", 409)
        if row["complete"] or not row["next_cursor"]:
            raise ConnectorError("PAGINATION_COMPLETE", 409)
        return row["next_cursor"]

    def _save_checkpoint(self, tenant: str, req: IngestionRequest, cursor: str | None):
        updated = now_utc().isoformat()
        where = (
            (ingestion_page_checkpoints.c.tenant_id == tenant) &
            (ingestion_page_checkpoints.c.platform == req.platform.value) &
            (ingestion_page_checkpoints.c.source_account_id == req.source_account_id)
        )
        with self.engine.begin() as db:
            old = db.execute(select(ingestion_page_checkpoints.c.tenant_id).where(where)).first()
            values = {"next_cursor": cursor, "complete": int(cursor is None), "updated_at": updated}
            if old:
                db.execute(update(ingestion_page_checkpoints).where(where).values(**values))
            else:
                db.execute(insert(ingestion_page_checkpoints).values(
                    tenant_id=tenant, platform=req.platform.value,
                    source_account_id=req.source_account_id, **values))

    def _reserve(self,tenant,req:IngestionRequest, *, cycle_key=None):
        """Reserve one of five bounded account reads per UTC day BEFORE network call."""
        with self.engine.begin() as db:
            if req.platform == Platform.INSTAGRAM:
                # Local imports avoid the ingestion/history/identity import cycle.
                from .discovery_history import lock_tenant, cycle_leases
                from .discovery_identity_a6 import identity_reserved_today
                lock_tenant(db, tenant)
                lease = db.execute(select(cycle_leases.c.cycle_key).where(
                    cycle_leases.c.tenant_id == tenant)).scalar_one_or_none()
                if lease != cycle_key or (cycle_key is not None and
                        not req.run_key.startswith(cycle_key + "-")):
                    raise ConnectorError("BD_CYCLE_RESERVATION_SCOPE_MISMATCH", 409)
                active_tenant = db.execute(select(ingestion_runs.c.run_key).where(
                    ingestion_runs.c.tenant_id == tenant,
                    ingestion_runs.c.platform == Platform.INSTAGRAM.value,
                    ingestion_runs.c.status == "reserved").limit(1)).first()
                if active_tenant:
                    raise ConnectorError("ACCOUNT_INGESTION_IN_PROGRESS", 409)
                day = now_utc().date().isoformat()
                used = db.execute(select(func.count()).select_from(ingestion_runs).where(
                    ingestion_runs.c.tenant_id == tenant,
                    ingestion_runs.c.platform == Platform.INSTAGRAM.value,
                    ingestion_runs.c.requested_at >= day)).scalar_one()
                if 4 * used + identity_reserved_today(db, tenant, day) + 4 > 80:
                    raise ConnectorError("BD_SHARED_DAILY_BUDGET_EXCEEDED", 429)
            # Acquire a per-account write/row lock before testing reservations.
            # SQLite serializes writers; PostgreSQL locks this grant row.
            locked = db.execute(update(source_grants).where(
                source_grants.c.tenant_id == tenant,
                source_grants.c.platform == req.platform.value,
                source_grants.c.source_account_id == req.source_account_id,
                source_grants.c.enabled == 1,
            ).values(enabled=source_grants.c.enabled))
            if locked.rowcount != 1:
                raise ConnectorError("VALID_SOURCE_GRANT_REQUIRED", 403)
            old=db.execute(select(ingestion_runs).where(
                ingestion_runs.c.tenant_id==tenant,ingestion_runs.c.run_key==req.run_key)).mappings().first()
            if old:
                if old["platform"]!=req.platform.value or old["source_account_id"]!=req.source_account_id:
                    raise ConnectorError("RUN_KEY_CONFLICT",409)
                raise ConnectorError("RUN_ALREADY_REGISTERED",409)
            active = db.execute(select(ingestion_runs.c.run_key).where(
                ingestion_runs.c.tenant_id == tenant,
                ingestion_runs.c.platform == req.platform.value,
                ingestion_runs.c.source_account_id == req.source_account_id,
                ingestion_runs.c.status == "reserved",
            ).limit(1)).first()
            if active:
                # Fail closed after crashes; reserved runs require an audited
                # operator recovery procedure rather than silent expiry.
                raise ConnectorError("ACCOUNT_INGESTION_IN_PROGRESS", 409)
            today=now_utc().date().isoformat()
            count=db.execute(select(func.count()).select_from(ingestion_runs).where(
                ingestion_runs.c.tenant_id==tenant,
                ingestion_runs.c.platform==req.platform.value,
                ingestion_runs.c.source_account_id==req.source_account_id,
                ingestion_runs.c.requested_at>=today)).scalar_one()
            if count>=5:raise ConnectorError("FREE_QUOTA_SAFETY_LIMIT",429)
            db.execute(insert(ingestion_runs).values(tenant_id=tenant,run_key=req.run_key,
                platform=req.platform.value,source_account_id=req.source_account_id,
                requested_at=now_utc().isoformat(),status="reserved",new_records=0,
                refreshed_records=0,duplicate_records=0))

    def _lock_reserved_run(self, db, tenant, run_key, *, platform=None, source=None):
        """Fence local writes against terminal runs under the recovery tenant lock."""
        locked = db.execute(update(tenants).where(tenants.c.tenant_id == tenant)
                            .values(name=tenants.c.name))
        if locked.rowcount != 1:
            raise ConnectorError("INGESTION_TENANT_NOT_FOUND", 404)
        scope = [ingestion_runs.c.tenant_id == tenant,
                 ingestion_runs.c.run_key == run_key,
                 ingestion_runs.c.status == "reserved"]
        if platform is not None:
            scope.append(ingestion_runs.c.platform == platform.value)
        if source is not None:
            scope.append(ingestion_runs.c.source_account_id == source)
        active = db.execute(update(ingestion_runs).where(*scope)
                            .values(status=ingestion_runs.c.status))
        if active.rowcount != 1:
            raise ConnectorError("INGESTION_RUN_NO_LONGER_RESERVED", 409)

    def _finish(self,tenant,run_key,status,added=0,duplicate=0,refreshed=0,reason=None, *, after_finish=None):
        if status not in {"completed", "failed"}:
            raise ConnectorError("INGESTION_INVALID_TERMINAL_STATUS", 422)
        with self.engine.begin() as db:
            self._lock_reserved_run(db, tenant, run_key)
            changed = db.execute(update(ingestion_runs).where(ingestion_runs.c.tenant_id==tenant,
                ingestion_runs.c.run_key==run_key, ingestion_runs.c.status=="reserved").values(status=status,
                  new_records=added,duplicate_records=duplicate,
                  refreshed_records=refreshed,reason_code=reason))
            if changed.rowcount != 1:
                raise ConnectorError("INGESTION_RUN_NO_LONGER_RESERVED", 409)
            if after_finish is not None:
                after_finish(db)

    def _persist_item(self, tenant: str, item: NormalizedItem, *, provenance_writer=None, run_key=None) -> str:
        """Store a new post or append a changed metric snapshot atomically.

        Returns 'created', 'refreshed', or 'unchanged'. A second read never
        overwrites a prior snapshot; unknown new values never erase history.
        """
        creator_id = stable_id("creator", item.platform.value, item.source_account_id)
        content_id = stable_id("content", item.platform.value,
                               item.source_account_id, item.source_item_id)
        created = now_utc()
        creator = CreatorCreate(
            creator_id=creator_id, tenant_id=tenant, origin=Origin(item.platform.value),
            handle=item.creator_handle, source_profile_id=item.source_account_id)
        content = ContentCreate(
            content_id=content_id, tenant_id=tenant, creator_id=creator_id,
            origin=Origin(item.platform.value), media_type=item.media_type,
            published_at=item.published_at, source_url=item.source_url,
            caption=item.caption, is_synthetic=False)
        assessed = classify_metadata_caption(item, tenant, content_id)
        complete = all(x is not None for x in (
            item.likes, item.comments, item.follower_count))
        with self.engine.begin() as db:
            if run_key is not None:
                self._lock_reserved_run(db, tenant, run_key, platform=item.platform,
                                        source=item.source_account_id)
            # Serialize Instagram media ownership across all ingestion paths.
            # Lock order: tenant, then source grant. The ownership check and
            # content/snapshot/outbox writes share the same transaction.
            if item.platform == Platform.INSTAGRAM:
                locked = db.execute(update(tenants).where(
                    tenants.c.tenant_id == tenant
                ).values(name=tenants.c.name))
                if locked.rowcount != 1:
                    raise ConnectorError("INGESTION_TENANT_NOT_FOUND", 404)
                conflict = db.execute(select(ingestion_records.c.source_account_id).where(
                    ingestion_records.c.tenant_id == tenant,
                    ingestion_records.c.platform == Platform.INSTAGRAM.value,
                    ingestion_records.c.source_item_id == item.source_item_id,
                    ingestion_records.c.source_account_id != item.source_account_id,
                ).limit(1)).first()
                if conflict:
                    raise ConnectorError("BD_CROSS_SOURCE_MEDIA_ID_CONFLICT", 409)
            # Serialize persistence against administrative revocation. A no-op
            # UPDATE holds the account row lock through the content transaction.
            active=db.execute(update(source_grants).where(
                source_grants.c.tenant_id==tenant,
                source_grants.c.platform==item.platform.value,
                source_grants.c.source_account_id==item.source_account_id,
                source_grants.c.enabled==1,
            ).values(enabled=source_grants.c.enabled))
            if active.rowcount!=1:
                raise ConnectorError("SOURCE_GRANT_REVOKED_BEFORE_PERSIST",403)
            grant_expiry=db.execute(select(source_grants.c.expires_at).where(
                source_grants.c.tenant_id==tenant,
                source_grants.c.platform==item.platform.value,
                source_grants.c.source_account_id==item.source_account_id,
            )).scalar_one()
            if datetime.fromisoformat(grant_expiry)<=now_utc():
                raise ConnectorError("SOURCE_GRANT_EXPIRED_BEFORE_PERSIST",403)
            found = db.execute(select(ingestion_records.c.content_id).where(
                ingestion_records.c.tenant_id == tenant,
                ingestion_records.c.platform == item.platform.value,
                ingestion_records.c.source_account_id == item.source_account_id,
                ingestion_records.c.source_item_id == item.source_item_id,
            )).scalar_one_or_none()
            if found:
                if not complete:
                    if provenance_writer is not None:
                        provenance_writer(db, found)
                    return "unchanged"
                snapshots = db.execute(select(metrics_snapshots.c.payload).where(
                    metrics_snapshots.c.tenant_id == tenant,
                    metrics_snapshots.c.content_id == found,
                )).scalars().all()
                previous = max(
                    (MetricsCreate.model_validate_json(p) for p in snapshots),
                    key=lambda m: (m.observed_at, m.snapshot_id),
                    default=None,
                )
                # Public APIs may omit fields temporarily. Do not replace a
                # previously known view count with null on refresh.
                views = item.views if item.views is not None else (
                    previous.views if previous else None)
                if previous is not None and (
                    previous.likes == item.likes
                    and previous.comments == item.comments
                    and previous.follower_count == item.follower_count
                    and previous.views == views
                ):
                    if provenance_writer is not None:
                        provenance_writer(db, found)
                    return "unchanged"
                snapshot = MetricsCreate(
                    snapshot_id=stable_id("metrics", content_id, str(uuid4())),
                    tenant_id=tenant, content_id=found, observed_at=created,
                    followers_measured_at=created, likes=item.likes,
                    comments=item.comments, follower_count=item.follower_count,
                    views=views)
                db.execute(insert(metrics_snapshots).values(
                    tenant_id=tenant, id=snapshot.snapshot_id,
                    content_id=found, observed_at=created.isoformat(),
                    payload=snapshot.model_dump_json()))
                # Preserve history and emit a separate event from post creation.
                version = db.execute(select(
                    func.coalesce(func.max(domain_events.c.aggregate_version), 0)
                ).where(
                    domain_events.c.tenant_id == tenant,
                    domain_events.c.aggregate_type == "content",
                    domain_events.c.aggregate_id == found)).scalar_one() + 1
                ev = db.execute(insert(domain_events).values(
                    event_id=str(uuid4()), tenant_id=tenant, aggregate_type="content",
                    aggregate_id=found, event_type="ingestion.metrics_refreshed",
                    aggregate_version=version, occurred_at=created.isoformat(),
                    payload=json.dumps({
                        "source": item.platform.value, "content_id": found,
                        "snapshot_id": snapshot.snapshot_id,
                        "denominator_quality": item.denominator_quality,
                    })))
                db.execute(insert(outbox).values(
                    seq=ev.inserted_primary_key[0], attempts=0, dead_letter=0))
                db.execute(update(ingestion_records).where(
                    ingestion_records.c.tenant_id == tenant,
                    ingestion_records.c.platform == item.platform.value,
                    ingestion_records.c.source_account_id == item.source_account_id,
                    ingestion_records.c.source_item_id == item.source_item_id,
                ).values(processed_at=created.isoformat(),
                         denominator_quality=item.denominator_quality))
                if provenance_writer is not None:
                    provenance_writer(db, found)
                return "refreshed"

            existing_creator = db.execute(select(creators.c.id).where(
                creators.c.tenant_id == tenant, creators.c.id == creator_id,
            )).scalar_one_or_none()
            if not existing_creator:
                db.execute(insert(creators).values(
                    tenant_id=tenant, id=creator_id, origin=item.platform.value,
                    payload=Creator(**creator.model_dump(),
                                    created_at=created).model_dump_json()))
            from .domain import ContentItem, RubricAssessment
            db.execute(insert(content_items).values(
                tenant_id=tenant, id=content_id, creator_id=creator_id,
                origin=item.platform.value, published_at=item.published_at.isoformat(),
                payload=ContentItem(**content.model_dump(),
                                    created_at=created).model_dump_json()))
            if complete:
                snapshot = MetricsCreate(
                    snapshot_id=stable_id("metrics", content_id, str(uuid4())),
                    tenant_id=tenant, content_id=content_id,
                    observed_at=created, followers_measured_at=created,
                    likes=item.likes, comments=item.comments,
                    follower_count=item.follower_count, views=item.views)
                db.execute(insert(metrics_snapshots).values(
                    tenant_id=tenant, id=snapshot.snapshot_id,
                    content_id=content_id, observed_at=created.isoformat(),
                    payload=snapshot.model_dump_json()))
            from .domain import RubricAssessment
            saved_assessment = RubricAssessment(**assessed.model_dump(), recorded_at=created)
            db.execute(insert(rubric_assessments).values(
                tenant_id=tenant, id=saved_assessment.assessment_id,
                content_id=content_id, recorded_at=created.isoformat(),
                payload=saved_assessment.model_dump_json()))
            db.execute(insert(ingestion_records).values(
                tenant_id=tenant, platform=item.platform.value,
                source_account_id=item.source_account_id,
                source_item_id=item.source_item_id, content_id=content_id,
                denominator_quality=item.denominator_quality,
                metadata_only=int(item.metadata_only),
                processed_at=created.isoformat()))
            ev = db.execute(insert(domain_events).values(
                event_id=str(uuid4()), tenant_id=tenant,
                aggregate_type="content", aggregate_id=content_id,
                event_type="ingestion.content_processed", aggregate_version=1,
                occurred_at=created.isoformat(),
                payload=json.dumps({
                    "source": item.platform.value,
                    "content_id": content_id, "metadata_only": True,
                    "denominator_quality": item.denominator_quality,
                })))
            db.execute(insert(outbox).values(
                seq=ev.inserted_primary_key[0], attempts=0, dead_letter=0))
            if provenance_writer is not None:
                provenance_writer(db, content_id)
        return "created"

    def run(self,tenant:str,req:IngestionRequest,http:OfficialHttp | None=None)->IngestionResult:
        if os.getenv("TAPI_OFFICIAL_METADATA_READS")!="1":
            raise ConnectorError("OFFICIAL_READS_DISABLED",403)
        # The operator must separately verify in the provider console that
        # this API usage cannot create a monetary charge or overage.
        if os.getenv("TAPI_ZERO_BILLING_CONFIRMED")!="1":
            raise ConnectorError("PROVIDER_ZERO_BILLING_NOT_CONFIRMED",403)
        grant=self.read_grant(tenant,req.platform,req.source_account_id)
        if grant["approval_reference"].startswith(A6_BD_GRANT_PREFIX):
            raise ConnectorError("BD_GRANT_TECHNICAL_ROUTE_ONLY",403)
        token=credential_for(req.platform)
        after = self._resume_cursor(tenant, req) if req.resume else None
        self._reserve(tenant,req)
        owns_http=http is None
        transport=http or OfficialHttp()
        created=duplicate=refreshed=excluded_recent=0
        next_cursor = None
        try:
            adapter=(InstagramOfficial(transport) if req.platform==Platform.INSTAGRAM
                     else YouTubeOfficial(transport))
            checked=adapter.verify(req.source_account_id,token)
            if req.platform == Platform.INSTAGRAM:
                items, next_cursor = adapter.fetch_page(
                    req.source_account_id, token, checked, req.limit, after=after)
            else:
                items = adapter.fetch(req.source_account_id,token,checked,req.limit,req.video_ids)
            if self.read_grant(tenant,req.platform,req.source_account_id)["approval_reference"]!=grant["approval_reference"]:
                raise ConnectorError("SOURCE_GRANT_CHANGED_DURING_READ",403)
            with self.engine.begin() as db:
                updated=db.execute(update(source_grants).where(
                    source_grants.c.tenant_id==tenant,
                    source_grants.c.platform==req.platform.value,
                    source_grants.c.source_account_id==req.source_account_id,
                    source_grants.c.enabled==1,
                    source_grants.c.approval_reference==grant["approval_reference"]).values(
                        technical_verified_at=now_utc().isoformat()))
                if updated.rowcount!=1:
                    raise ConnectorError("SOURCE_GRANT_REVOKED_DURING_READ",403)
            for item in items:
                self.read_grant(tenant,req.platform,req.source_account_id)
                if (now_utc() - item.published_at).total_seconds() < req.min_age_days * 86400:
                    excluded_recent += 1
                    continue
                status = self._persist_item(tenant,item)
                if status == "created": created += 1
                elif status == "refreshed": refreshed += 1
                else: duplicate += 1
            # Only advance a cursor after all eligible records were committed.
            if req.platform == Platform.INSTAGRAM:
                self._save_checkpoint(tenant, req, next_cursor)
            self._finish(tenant,req.run_key,"completed",created,duplicate,refreshed)
            return IngestionResult(run_key=req.run_key,platform=req.platform,
                source_account_id=req.source_account_id,new_records=created,
                duplicate_records=duplicate,refreshed_records=refreshed,
                excluded_too_recent=excluded_recent,
                next_page_available=next_cursor is not None)
        except (ConnectorError, ValueError, IntegrityError) as exc:
            reason=exc.code if isinstance(exc,ConnectorError) else "INGESTION_VALIDATION_FAILED"
            self._finish(tenant,req.run_key,"failed",created,duplicate,refreshed,reason)
            if isinstance(exc,ConnectorError):raise
            raise ConnectorError(reason,422) from exc
        finally:
            if owns_http:transport.close()


def router_for_ingestion(identity,store:IngestionStore):
    router=APIRouter(prefix="/v1/ingestion",tags=["Official metadata ingestion"])

    def principal(request:Request)->Principal:
        auth=request.headers.get("Authorization","")
        scheme,_,token=auth.partition(" ")
        if scheme.lower()!="bearer" or not token or " " in token:raise IdentityFailure()
        return identity.resolve(token)

    @router.post("/grants",status_code=201)
    def register_grant(payload:GrantCreate,p:Principal=Depends(principal)):
        if p.role!="admin":raise IdentityFailure("FORBIDDEN",403)
        return store.grant(p.tenant_id,p.actor_id,payload)

    @router.post("/grants/{platform}/{account_id}/revoke")
    def revoke_source_grant(platform:Platform,account_id:str,p:Principal=Depends(principal)):
        if p.role!="admin":raise IdentityFailure("FORBIDDEN",403)
        return store.revoke_grant(p.tenant_id,p.actor_id,platform,account_id)

    @router.post("/runs",response_model=IngestionResult)
    def run_ingestion(payload:IngestionRequest,p:Principal=Depends(principal)):
        if p.role not in {"admin","researcher","service"}:raise IdentityFailure("FORBIDDEN",403)
        return store.run(p.tenant_id,payload)

    @router.get("/connections/{platform}/{account_id}")
    def connection_readiness(platform:Platform,account_id:str,p:Principal=Depends(principal)):
        # Query only the authenticated tenant, including missing/expired grants;
        # the endpoint reports eligibility for a PRE-FLIGHT, not access approval.
        with store.engine.connect() as db:
            grant=db.execute(select(source_grants).where(
                source_grants.c.tenant_id==p.tenant_id,
                source_grants.c.platform==platform.value,
                source_grants.c.source_account_id==account_id,
            )).mappings().first()
        status=assess_metadata_readiness(
            dict(grant) if grant is not None else None,
            credential_present=bool(os.getenv({
                Platform.INSTAGRAM:"TAPI_INSTAGRAM_ACCESS_TOKEN",
                Platform.YOUTUBE:"TAPI_YOUTUBE_ACCESS_TOKEN",
            }[platform])),
            read_switch_enabled=os.getenv("TAPI_OFFICIAL_METADATA_READS")=="1",
            zero_billing_operator_confirmed=os.getenv("TAPI_ZERO_BILLING_CONFIRMED")=="1",
        )
        return {"platform":platform.value,"source_account_id":account_id,
                **status.model_dump(),
                "note":"A ready preflight is not a verified OAuth grant or production approval."}

    @router.get("/runs")
    def list_runs(p:Principal=Depends(principal)):
        with store.engine.connect() as db:
            rows=db.execute(select(ingestion_runs).where(ingestion_runs.c.tenant_id==p.tenant_id)
                            .order_by(ingestion_runs.c.requested_at.desc()).limit(100)).mappings().all()
        return {"items":[dict(r) for r in rows]}

    return router
