"""A02 encrypted derivative staging, trusted SQLite host only.

Opaque bytes are not scientifically validated. No API, model adapter,
display/export/publish, or operational key provisioning. SQLite transaction
binds ciphertext, lineage, job receipt and audit. Keys stay outside SQLite.
Deletion removes the live ciphertext value, not backups/WAL/SSD blocks.
"""
import json
import os
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import (Table,Column,String,Integer,LargeBinary,ForeignKeyConstraint,
    UniqueConstraint,CheckConstraint,select,insert,update,func)
from .sa_store import metadata,domain_events,outbox
from .asset_jobs import (AssetJobQueue,Lease,OUTPUT,_spec,_row,_check_rights,
                          _transition,_release,_public,_ms)
from .asset_lineage import DerivedArtifactRef,invalidation_plan
from .asset_lineage_index import _load,_ancestors,_grant
from .asset_rights import AssetRightsDenied,Permission
from .asset_vault import _crypto
from .storage import now_utc

MAX_OUTPUT=1_000_000
MAX_TENANT_BYTES=100_000_000
MAX_GLOBAL_BYTES=500_000_000
OVERHEAD=28

payloads=Table("asset_derived_payloads",metadata,
    Column("tenant_id",String(128),primary_key=True),
    Column("artifact_id",String(128),primary_key=True),
    Column("job_id",String(128),nullable=False),
    Column("key_id",String(64),nullable=False),
    Column("byte_count",Integer,nullable=False),
    Column("attempt",Integer,nullable=False),
    Column("envelope",LargeBinary),
    Column("purged_at",String(40)),
    ForeignKeyConstraint(["tenant_id","artifact_id"],["asset_lineage_nodes.tenant_id","asset_lineage_nodes.node_id"]),
    ForeignKeyConstraint(["tenant_id","job_id"],["asset_processing_jobs.tenant_id","asset_processing_jobs.job_id"]),
    UniqueConstraint("tenant_id","job_id",name="uq_asset_payload_job"),
    CheckConstraint("byte_count BETWEEN 1 AND 1000000 AND attempt BETWEEN 1 AND 3",name="ck_asset_payload_bounds"),
    CheckConstraint("(envelope IS NOT NULL AND purged_at IS NULL AND length(envelope)=byte_count+28) OR (envelope IS NULL AND purged_at IS NOT NULL)",name="ck_asset_payload_state"))


def _deny(code):
    raise AssetRightsDenied("ASSET_PAYLOAD_"+code)


def _aad(ref,spec,attempt,key_id,parent):
    return json.dumps({"schema":"asset-derived-payload.v1","ref":ref.model_dump(mode="json"),
        "spec":spec.model_dump(mode="json"),"attempt":attempt,"key_id":key_id,
        "parent":parent.model_dump(mode="json")},sort_keys=True,separators=(",",":"),
        ensure_ascii=False).encode()


def _extra(db,queue,spec,parent,now,*,read=False):
    anchor=queue.resolve_anchor(parent)
    field=OUTPUT[spec.processor]
    _grant(db,anchor,parent,now,Permission(operation="retain",purpose=spec.purpose,field=field))
    if read:
        _grant(db,anchor,parent,now,Permission(operation="process",purpose=spec.purpose,field=field))


def _artifact_id(spec,digest):
    return "artifact."+sha256((spec.job_id+":"+digest).encode()).hexdigest()


class DerivedPayloadStore:
    def __init__(self,queue:AssetJobQueue,key:bytes):
        if not isinstance(queue,AssetJobQueue):
            _deny("QUEUE_REQUIRED")
        if type(key) is not bytes or len(key)!=32:
            _deny("KEY_INVALID")
        aes,invalid_tag=_crypto()
        self.queue=queue
        self._cipher=aes(key)
        self._invalid_tag=invalid_tag
        # Domain-separated fingerprint, not a key or authorization credential.
        self.key_id=sha256(b"asset-derived-key.v1:"+key).hexdigest()

    def finish(self,lease:Lease,*,payload:bytes):
        """Persist encrypted output, requires explicit retain of derived field."""
        if type(payload) is not bytes or not 0<len(payload)<=MAX_OUTPUT:
            _deny("SIZE_INVALID")
        digest=sha256(payload).hexdigest()
        q=self.queue
        with q._transaction() as (db,now):
            row=q._owned(db,lease,now)
            spec=_spec(row)
            parent=_check_rights(db,spec,q.resolve_anchor,now)
            _extra(db,q,spec,parent,now)
            assets,derived,by_id=_load(db,spec.tenant_id)
            ident=_artifact_id(spec,digest)
            ref=DerivedArtifactRef(tenant_id=spec.tenant_id,artifact_id=ident,
                kind=OUTPUT[spec.processor],payload_sha256=digest,parent_ids=(spec.object_id,),
                run_id=spec.job_id,method_version=spec.method_version,created_at=now,
                retain_until=parent.retain_until)
            if ident in by_id:
                _deny("REFERENCE_CONFLICT")
            invalidation_plan(spec.tenant_id,assets,derived+[ref],invalid_asset_ids=set(),
                invalid_artifact_ids=set(),now=now)
            size=func.coalesce(func.sum(func.length(payloads.c.envelope)),0)
            total=db.scalar(select(size))
            tenant_total=db.scalar(select(size).where(payloads.c.tenant_id==spec.tenant_id))
            if total+len(payload)+OVERHEAD>MAX_GLOBAL_BYTES or tenant_total+len(payload)+OVERHEAD>MAX_TENANT_BYTES:
                _deny("STORAGE_QUOTA")
            nonce=os.urandom(12)
            envelope=nonce+self._cipher.encrypt(nonce,payload,_aad(ref,spec,lease.attempt,self.key_id,parent))
            q.index._insert(db,spec.tenant_id,ident,"derived",ref,by_id,spec.purpose)
            db.execute(insert(payloads).values(tenant_id=spec.tenant_id,artifact_id=ident,
                job_id=spec.job_id,key_id=self.key_id,byte_count=len(payload),attempt=lease.attempt,envelope=envelope))
            fresh=now_utc()
            if fresh<now:
                _deny("CLOCK_REGRESSION")
            q._owned(db,lease,fresh)
            current=_check_rights(db,spec,q.resolve_anchor,fresh)
            if current!=parent:
                _deny("PARENT_CHANGED")
            _extra(db,q,spec,current,fresh)
            row=_transition(db,row,fresh,"payload_recorded",receipt_sha256=digest,
                **_release("completed","encrypted_payload",_ms(fresh)))
            return {**_public(row),"artifact_id":ident,"payload_persisted":True,
                "scientific_evidence":False,"media_enabled":False}

    def read_for_processing(self,tenant,artifact_id,*,purpose):
        """Trusted in-process read only; requires retain + process of output."""
        q=self.queue
        with q._transaction() as (db,now):
            _,_,by_id=_load(db,tenant)
            if artifact_id not in by_id or not isinstance(by_id[artifact_id][1],DerivedArtifactRef):
                _deny("UNKNOWN_ARTIFACT")
            ref=by_id[artifact_id][1]
            roots=_ancestors(by_id,artifact_id,now,purpose)
            if len(roots)!=1 or ref.parent_ids!=(roots[0].object_id,):
                _deny("LINEAGE_MISMATCH")
            item=db.execute(select(payloads).where(payloads.c.tenant_id==tenant,
                payloads.c.artifact_id==artifact_id)).mappings().one_or_none()
            if item is None or item["envelope"] is None:
                _deny("UNAVAILABLE")
            row=_row(db,tenant,item["job_id"])
            spec=_spec(row)
            if (row["state"]!="completed" or row["reason"]!="encrypted_payload" or
                row["receipt_sha256"]!=ref.payload_sha256 or row["attempt"]!=item["attempt"] or
                spec.purpose!=purpose or ref.run_id!=spec.job_id or ref.method_version!=spec.method_version or
                ref.kind!=OUTPUT[spec.processor] or ref.parent_ids!=(spec.object_id,) or
                artifact_id!=_artifact_id(spec,ref.payload_sha256)):
                _deny("RECEIPT_MISMATCH")
            parent=_check_rights(db,spec,q.resolve_anchor,now)
            _extra(db,q,spec,parent,now,read=True)
            if item["key_id"]!=self.key_id:
                _deny("KEY_MISMATCH")
            envelope=item["envelope"]
            if not 0<item["byte_count"]<=MAX_OUTPUT or len(envelope)!=item["byte_count"]+OVERHEAD:
                _deny("ENVELOPE_INVALID")
            try:
                data=self._cipher.decrypt(envelope[:12],envelope[12:],
                    _aad(ref,spec,item["attempt"],self.key_id,parent))
            except (self._invalid_tag,ValueError):
                _deny("AUTHENTICATION_FAILED")
            if len(data)!=item["byte_count"] or sha256(data).hexdigest()!=ref.payload_sha256:
                _deny("DIGEST_MISMATCH")
            fresh=now_utc()
            if fresh<now:
                _deny("CLOCK_REGRESSION")
            _ancestors(by_id,artifact_id,fresh,purpose)
            current=_check_rights(db,spec,q.resolve_anchor,fresh)
            if current!=parent:
                _deny("PARENT_CHANGED")
            _extra(db,q,spec,current,fresh,read=True)
            return data

    def purge_invalidated(self,tenant,artifact_id):
        """Trusted cleanup of one tombstoned payload; keep metadata and audit."""
        q=self.queue
        with q._transaction() as (db,now):
            _,_,by_id=_load(db,tenant)
            if artifact_id not in by_id or not isinstance(by_id[artifact_id][1],DerivedArtifactRef):
                _deny("UNKNOWN_ARTIFACT")
            if by_id[artifact_id][0]["state"]!="invalidated":
                _deny("TOMBSTONE_REQUIRED")
            row=db.execute(select(payloads.c.purged_at).where(payloads.c.tenant_id==tenant,
                payloads.c.artifact_id==artifact_id)).mappings().one_or_none()
            if row is None:
                _deny("UNAVAILABLE")
            if row["purged_at"] is not None:
                return {"status":"ALREADY_PURGED","secure_erasure_verified":False}
            db.execute(update(payloads).where(payloads.c.tenant_id==tenant,
                payloads.c.artifact_id==artifact_id).values(envelope=None,purged_at=now.isoformat()))
            seq=db.execute(insert(domain_events).values(event_id=str(uuid4()),tenant_id=tenant,
                aggregate_type="asset_derived_payload",aggregate_id=artifact_id,aggregate_version=1,
                event_type="asset_derived_payload.purged",occurred_at=now.isoformat(),
                payload=json.dumps({"secure_erasure_verified":False,"media_enabled":False}))).inserted_primary_key[0]
            db.execute(insert(outbox).values(seq=seq,attempts=0,dead_letter=0))
            return {"status":"PURGED","secure_erasure_verified":False}
