"""A02.5/6 durable local multimodal scheduling, not a media worker.

Trusted host only, SQLite single writer. Jobs describe immutable work;
claims reserve bounded attempt budgets, not CPU time. Lease fencing rejects
stale receipts but cannot stop an already running subprocess. No inference,
network, bytes, payload publication, HTTP or automatic scheduler here.
"""
from contextlib import contextmanager
from datetime import timedelta
from hashlib import sha256
import json
from typing import Literal
from uuid import uuid4

from sqlalchemy import (Table,Column,String,Text,Integer,BigInteger,ForeignKeyConstraint,
                        CheckConstraint,Index,select,insert,update,func)
from pydantic import Field
from .sa_store import metadata,domain_events,outbox
from .asset_rights import RightsModel,Id,Digest,Permission,AssetRightsDenied
from .asset_lineage import RetainedAssetRef
from .asset_lineage_index import AssetLineageIndex,_load,_ancestors,_grant
from .storage import now_utc

MAX_PENDING=100
MAX_TENANT_HISTORY=20000
MAX_GLOBAL_HISTORY=50000
MAX_DAILY_TENANT_ATTEMPTS=50
MAX_DAILY_GLOBAL_ATTEMPTS=100
MAX_CONCURRENT=1
MAX_ATTEMPTS=3
LEASE_SECONDS=120
ATTEMPT_SECONDS=900
ACTIVE=("running","cancel_requested")
TERMINAL=("completed","failed","canceled")
OUTPUT={"ocr":"ocr","asr_vad":"transcript","vlm":"visual_features","temporal":"visual_features"}
INPUT={"ocr":("image","video"),"asr_vad":("audio","video"),"vlm":("image","video"),"temporal":("video",)}


class JobSpec(RightsModel):
    tenant_id: Id
    object_id: Digest
    purpose: Literal["research_analysis","studio_creation"]
    processor: Literal["ocr","asr_vad","vlm","temporal"]
    method_version: Id
    configuration_sha256: Digest

    @property
    def job_id(self):
        encoded=json.dumps(self.model_dump(mode="json"),sort_keys=True,separators=(",",":")).encode()
        return "job."+sha256(b"asset-job.v1:"+encoded).hexdigest()


jobs=Table("asset_processing_jobs",metadata,
    Column("tenant_id",String(128),primary_key=True),Column("job_id",String(128),primary_key=True),
    Column("object_id",String(64),nullable=False),Column("spec",Text,nullable=False),
    Column("state",String(24),nullable=False),Column("attempt",Integer,nullable=False),
    Column("version",Integer,nullable=False),Column("created_ms",BigInteger,nullable=False),
    Column("updated_ms",BigInteger,nullable=False),Column("available_ms",BigInteger,nullable=False),
    Column("worker",String(128)),Column("fence",String(32)),Column("lease_ms",BigInteger),
    Column("deadline_ms",BigInteger),Column("receipt_sha256",String(64)),Column("reason",String(64)),
    ForeignKeyConstraint(["tenant_id","object_id"],["asset_lineage_nodes.tenant_id","asset_lineage_nodes.node_id"]),
    CheckConstraint("state IN ('queued','running','cancel_requested','completed','failed','canceled')",name="ck_asset_job_state"),
    CheckConstraint("attempt BETWEEN 0 AND 3 AND version>=1",name="ck_asset_job_attempt"),
    CheckConstraint("(state IN ('running','cancel_requested') AND worker IS NOT NULL AND fence IS NOT NULL AND lease_ms IS NOT NULL AND deadline_ms IS NOT NULL AND lease_ms<=deadline_ms) OR (state NOT IN ('running','cancel_requested') AND worker IS NULL AND fence IS NULL AND lease_ms IS NULL AND deadline_ms IS NULL)",name="ck_asset_job_lease"),
    CheckConstraint("(state='completed' AND receipt_sha256 IS NOT NULL) OR (state!='completed' AND receipt_sha256 IS NULL)",name="ck_asset_job_receipt"))
Index("ix_asset_job_dispatch",jobs.c.tenant_id,jobs.c.state,jobs.c.available_ms,jobs.c.job_id)

attempts=Table("asset_processing_attempts",metadata,
    Column("tenant_id",String(128),primary_key=True),Column("job_id",String(128),primary_key=True),
    Column("attempt",Integer,primary_key=True),Column("started_ms",BigInteger,nullable=False),
    ForeignKeyConstraint(["tenant_id","job_id"],["asset_processing_jobs.tenant_id","asset_processing_jobs.job_id"]),
    CheckConstraint("attempt BETWEEN 1 AND 3",name="ck_asset_attempt_number"))
Index("ix_asset_attempt_budget",attempts.c.started_ms,attempts.c.tenant_id)


class Lease(RightsModel):
    tenant_id: Id
    job_id: Id
    worker: Id
    fence: str = Field(pattern=r"^[0-9a-f]{32}$")
    attempt: int = Field(ge=1,le=3,strict=True)
    lease_ms: int
    deadline_ms: int


def _fail(code):
    raise AssetRightsDenied("ASSET_JOB_"+code)


def _ms(now):
    return int(now.timestamp()*1000)


def _spec(row):
    spec=JobSpec.model_validate_json(row["spec"])
    if (spec.tenant_id,spec.job_id,spec.object_id)!=(row["tenant_id"],row["job_id"],row["object_id"]):
        _fail("SPEC_CORRUPT")
    return spec


def _event(db,row,event_type,now):
    seq=db.execute(insert(domain_events).values(event_id=str(uuid4()),tenant_id=row["tenant_id"],
        aggregate_type="asset_processing_job",aggregate_id=row["job_id"],aggregate_version=row["version"],
        event_type="asset_job."+event_type,occurred_at=now.isoformat(),
        payload=json.dumps({"state":row["state"],"attempt":row["attempt"],"reason":row["reason"],
                            "media_enabled":False}))).inserted_primary_key[0]
    db.execute(insert(outbox).values(seq=seq,attempts=0,dead_letter=0))


def _row(db,tenant,job_id):
    row=db.execute(select(jobs).where(jobs.c.tenant_id==tenant,jobs.c.job_id==job_id)).mappings().one_or_none()
    if row is None:
        _fail("NOT_FOUND")
    _spec(row)
    return dict(row)


def _transition(db,row,now,event_type,**changes):
    new={**row,**changes,"updated_ms":_ms(now),"version":row["version"]+1}
    result=db.execute(update(jobs).where(jobs.c.tenant_id==row["tenant_id"],jobs.c.job_id==row["job_id"],
        jobs.c.version==row["version"]).values(**{k:new[k] for k in (*changes,"updated_ms","version")}))
    if result.rowcount!=1:
        _fail("CONCURRENT_UPDATE")
    _event(db,new,event_type,now)
    return new


def _release(state,reason,available_ms):
    return dict(state=state,reason=reason,available_ms=available_ms,
                worker=None,fence=None,lease_ms=None,deadline_ms=None)


def _lease(row):
    return Lease(**{k:row[k] for k in ("tenant_id","job_id","worker","fence","attempt","lease_ms","deadline_ms")})


def _public(row):
    return {k:row[k] for k in ("tenant_id","job_id","object_id","state","attempt","version",
        "created_ms","updated_ms","available_ms","lease_ms","deadline_ms","receipt_sha256","reason")}


def _check_rights(db,spec,resolve_anchor,now):
    _,_,by_id=_load(db,spec.tenant_id)
    if spec.object_id not in by_id:
        _fail("INPUT_NOT_FOUND")
    ref=by_id[spec.object_id][1]
    if not isinstance(ref,RetainedAssetRef) or ref.target.media_kind not in INPUT[spec.processor]:
        _fail("INPUT_KIND_MISMATCH")
    _ancestors(by_id,spec.object_id,now,spec.purpose)
    anchor=resolve_anchor(ref)
    for op,field in (("retain",ref.target.media_kind),("process",ref.target.media_kind),
                     ("derive",OUTPUT[spec.processor])):
        _grant(db,anchor,ref,now,Permission(operation=op,purpose=spec.purpose,field=field))


class AssetJobQueue:
    def __init__(self,index:AssetLineageIndex,*,resolve_anchor):
        if not isinstance(index,AssetLineageIndex):
            _fail("INDEX_REQUIRED")
        self.index=index
        self.resolve_anchor=resolve_anchor

    @contextmanager
    def _transaction(self):
        with self.index._transaction() as db:
            now=now_utc()
            latest=db.scalar(select(func.max(jobs.c.updated_ms)))
            if latest is not None and latest>_ms(now):
                _fail("CLOCK_REGRESSION")
            yield db,now

    def enqueue(self,spec:JobSpec):
        spec=JobSpec.model_validate(spec.model_dump())
        with self._transaction() as (db,now):
            _check_rights(db,spec,self.resolve_anchor,now)
            existing=db.execute(select(jobs).where(jobs.c.tenant_id==spec.tenant_id,
                jobs.c.job_id==spec.job_id)).mappings().one_or_none()
            if existing is not None:
                if _spec(existing)!=spec:
                    _fail("ID_CONFLICT")
                return _public(existing)
            if (db.scalar(select(func.count()).select_from(jobs))>=MAX_GLOBAL_HISTORY or
                db.scalar(select(func.count()).select_from(jobs).where(jobs.c.tenant_id==spec.tenant_id))>=MAX_TENANT_HISTORY or
                db.scalar(select(func.count()).select_from(jobs).where(jobs.c.tenant_id==spec.tenant_id,
                    jobs.c.state.in_(("queued",*ACTIVE))))>=MAX_PENDING):
                _fail("QUEUE_QUOTA")
            ms=_ms(now)
            row=dict(tenant_id=spec.tenant_id,job_id=spec.job_id,object_id=spec.object_id,spec=spec.model_dump_json(),
                state="queued",attempt=0,version=1,created_ms=ms,updated_ms=ms,available_ms=ms,
                worker=None,fence=None,lease_ms=None,deadline_ms=None,receipt_sha256=None,reason=None)
            db.execute(insert(jobs).values(**row))
            _event(db,row,"enqueued",now)
            return _public(row)

    def _expire(self,db,now,tenant=None):
        ms=_ms(now)
        query=select(jobs).where(jobs.c.state.in_(ACTIVE),jobs.c.lease_ms<=ms)
        if tenant is not None:
            query=query.where(jobs.c.tenant_id==tenant)
        expired=db.execute(query).mappings().all()
        for row in expired:
            _spec(row)
            if row["state"]=="cancel_requested":
                state,reason,available="canceled","cancel_lease_expired",ms
            elif row["attempt"]>=MAX_ATTEMPTS:
                state,reason,available="failed","attempts_exhausted",ms
            else:
                state,reason,available="queued","lease_expired",ms+1000*15*2**(row["attempt"]-1)
            _transition(db,dict(row),now,"lease_expired",**_release(state,reason,available))

    def claim(self,tenant,worker):
        # Worker identity is supplied by a trusted local host, not authenticated
        # by this library. Only one concurrent lease globally, including cancel.
        if not isinstance(worker,str) or not 1<=len(worker)<=128 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-" for c in worker):
            _fail("WORKER_INVALID")
        with self._transaction() as (db,now):
            self._expire(db,now)
            if db.scalar(select(func.count()).select_from(jobs).where(jobs.c.state.in_(ACTIVE)))>=MAX_CONCURRENT:
                return {"status":"busy","lease":None}
            start=_ms(now.replace(hour=0,minute=0,second=0,microsecond=0))
            day=attempts.c.started_ms>=start
            if (db.scalar(select(func.count()).select_from(attempts).where(day))>=MAX_DAILY_GLOBAL_ATTEMPTS or
                db.scalar(select(func.count()).select_from(attempts).where(day,attempts.c.tenant_id==tenant))>=MAX_DAILY_TENANT_ATTEMPTS):
                return {"status":"quota","lease":None}
            ms=_ms(now)
            candidates=db.execute(select(jobs).where(jobs.c.tenant_id==tenant,
                jobs.c.state=="queued",jobs.c.available_ms<=ms).order_by(jobs.c.available_ms,jobs.c.job_id).limit(MAX_PENDING)).mappings().all()
            denied=0
            for row in candidates:
                spec=_spec(row)
                if row["attempt"]>=MAX_ATTEMPTS:
                    _fail("ATTEMPT_STATE_INVALID")
                try:
                    _check_rights(db,spec,self.resolve_anchor,now)
                except AssetRightsDenied:
                    denied+=1
                    continue
                n=row["attempt"]+1
                db.execute(insert(attempts).values(tenant_id=tenant,job_id=row["job_id"],attempt=n,started_ms=ms))
                row=_transition(db,dict(row),now,"claimed",state="running",attempt=n,worker=worker,
                    fence=uuid4().hex,lease_ms=ms+LEASE_SECONDS*1000,deadline_ms=ms+ATTEMPT_SECONDS*1000,reason=None)
                return {"status":"claimed","lease":_lease(row),"spec":spec}
            return {"status":"rights_blocked" if denied else "empty","lease":None,"blocked_candidates":denied}

    def _owned(self,db,lease,now,*,cancel=False):
        row=_row(db,lease.tenant_id,lease.job_id)
        if row["state"]!=("cancel_requested" if cancel else "running") or any(
            row[k]!=getattr(lease,k) for k in ("worker","fence","attempt")):
            _fail("STALE_LEASE")
        if _ms(now)>=min(row["lease_ms"],row["deadline_ms"]):
            _fail("LEASE_EXPIRED")
        return row

    def heartbeat(self,lease:Lease):
        with self._transaction() as (db,now):
            row=self._owned(db,lease,now)
            _check_rights(db,_spec(row),self.resolve_anchor,now)
            row=_transition(db,row,now,"heartbeat",
                lease_ms=min(_ms(now)+LEASE_SECONDS*1000,row["deadline_ms"]))
            return _lease(row)

    def finish(self,lease:Lease,receipt_sha256:str):
        """Accept a worker receipt hash only, NOT a verified or visible artifact."""
        if not isinstance(receipt_sha256,str) or len(receipt_sha256)!=64 or any(c not in "0123456789abcdef" for c in receipt_sha256):
            _fail("RECEIPT_INVALID")
        with self._transaction() as (db,now):
            row=self._owned(db,lease,now)
            _check_rights(db,_spec(row),self.resolve_anchor,now)
            row=_transition(db,row,now,"receipt_recorded",receipt_sha256=receipt_sha256,
                **_release("completed","receipt_only",_ms(now)))
            return _public(row)

    def fail(self,lease:Lease,*,retryable:bool):
        if type(retryable) is not bool:
            _fail("RETRY_FLAG_INVALID")
        with self._transaction() as (db,now):
            row=self._owned(db,lease,now)
            retry=retryable and row["attempt"]<MAX_ATTEMPTS
            ms=_ms(now)
            row=_transition(db,row,now,"attempt_failed",**_release(
                "queued" if retry else "failed","retry_scheduled" if retry else "worker_failed",
                ms+15000*2**(row["attempt"]-1) if retry else ms))
            return _public(row)

    def cancel(self,tenant,job_id):
        with self._transaction() as (db,now):
            self._expire(db,now,tenant)
            row=_row(db,tenant,job_id)
            if row["state"] in TERMINAL or row["state"]=="cancel_requested":
                return _public(row)
            changes={"state":"cancel_requested","reason":"cancel_requested"} if row["state"]=="running" else _release("canceled","cancel_before_claim",_ms(now))
            return _public(_transition(db,row,now,"cancel_requested",**changes))

    def acknowledge_cancel(self,lease:Lease):
        """Trusted worker attests execution stopped; no subprocess kill here."""
        with self._transaction() as (db,now):
            row=self._owned(db,lease,now,cancel=True)
            return _public(_transition(db,row,now,"cancel_acknowledged",
                **_release("canceled","worker_acknowledged",_ms(now))))

    def reconcile_invalidated(self,tenant):
        """Explicit maintenance tick: cancel pending work on tombstones/expiry.

        No deletion or cancellation on transient missing/stale authority.
        Current rights are independently checked at claim/heartbeat/finish.
        """
        with self._transaction() as (db,now):
            self._expire(db,now,tenant)
            _,_,by_id=_load(db,tenant)
            rows=db.execute(select(jobs).where(jobs.c.tenant_id==tenant,
                jobs.c.state.in_(("queued","running")))).mappings().all()
            changed=[]
            for row in rows:
                spec=_spec(row)
                if spec.object_id not in by_id:
                    _fail("INPUT_NOT_FOUND")
                node,ref=by_id[spec.object_id]
                if node["state"]=="active" and ref.retain_until>now:
                    continue
                changes={"state":"cancel_requested","reason":"input_invalidated"} if row["state"]=="running" else _release("canceled","input_invalidated",_ms(now))
                _transition(db,dict(row),now,"input_invalidated",**changes)
                changed.append(row["job_id"])
            return {"status":"reconciled","changed":sorted(changed),"media_enabled":False}

    def status(self,tenant,job_id):
        # Read only: expose expiration separately; scheduling tick advances it.
        with self.index.engine.connect() as db:
            row=_row(db,tenant,job_id)
            return {**_public(row),"lease_expired":row["state"] in ACTIVE and _ms(now_utc())>=row["lease_ms"]}
