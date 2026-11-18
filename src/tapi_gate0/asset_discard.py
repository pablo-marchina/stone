"""A02.4 offline discard worker for indexed, permanently invalidated envelopes.

No operational CLI, automatic scheduling or arbitrary paths. Trusted host
supplies the existing vault and index, and stops all vault writers/readers.
This removes one directory entry, NOT secure erasure of backups or SSD blocks.
No plaintext is decrypted. DB and filesystem cannot commit atomically:
an interrupted deletion can be reconciled as already absent on retry.
"""
import json
import os
import stat
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select,insert
from .asset_rights import AssetRightsDenied
from .asset_lineage import RetainedAssetRef
from .asset_lineage_index import _load
from .asset_vault import VERSION,OVERHEAD,_binding_fields,AssetVault
from .sa_store import domain_events,outbox
from .storage import now_utc


def _fail(code):
    raise AssetRightsDenied("ASSET_DISCARD_"+code)


def _regular(info):
    return (stat.S_ISREG(info.st_mode) and info.st_nlink==1 and
        not getattr(info,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400))


def _inspect(vault,ref):
    """Check exact envelope entry, never follow links or decrypt data."""
    aad=_binding_fields(ref.issuer_id,ref.issuer_key_sha256,ref.grant_id,ref.target,ref.mime)
    if sha256(aad).hexdigest()!=ref.object_id:
        _fail("OBJECT_BINDING")
    path=vault._path(aad)
    try:
        info=path.lstat()
    except FileNotFoundError:
        return path,None
    if not _regular(info) or path.resolve()!=path:
        _fail("UNSAFE_OBJECT")
    if info.st_size!=ref.byte_count+OVERHEAD:
        _fail("ENVELOPE_SIZE")
    with os.fdopen(os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_BINARY",0)),"rb") as stream:
        actual=os.fstat(stream.fileno())
        if not _regular(actual) or not os.path.samestat(info,actual) or actual.st_size!=info.st_size:
            _fail("OBJECT_CHANGED")
        if stream.read(len(VERSION))!=VERSION:
            _fail("ENVELOPE_HEADER")
    return path,info


def discard_invalidated(index,vault:AssetVault,tenant,object_id,*,all_vault_io_stopped:bool):
    """Discard exactly one invalidated root, retain durable audit/tombstone.

    Only a trusted administrative caller may invoke this function. No
    permission to read revoked content is needed or granted by this cleanup.
    Caller must ensure all vault I/O stopped and correct vault root. A
    recorded receipt is not proof of secure physical erasure.
    """
    if all_vault_io_stopped is not True:
        _fail("STOPPED_IO_REQUIRED")
    if not isinstance(vault,AssetVault):
        _fail("VAULT_REQUIRED")
    with index._transaction() as db:
        _,_,by_id=_load(db,tenant)
        if object_id not in by_id:
            _fail("UNKNOWN_OBJECT")
        row,ref=by_id[object_id]
        if not isinstance(ref,RetainedAssetRef) or row["state"]!="invalidated":
            _fail("TOMBSTONE_REQUIRED")
        events=db.execute(select(domain_events.c.aggregate_version,domain_events.c.event_type,
            domain_events.c.payload).where(domain_events.c.tenant_id==tenant,
            domain_events.c.aggregate_type=="asset_lineage",
            domain_events.c.aggregate_id==object_id).order_by(domain_events.c.aggregate_version)).mappings().all()
        expected=[(1,"asset_lineage.registered"),(2,"asset_lineage.invalidated")]
        actual=[(e["aggregate_version"],e["event_type"]) for e in events]
        if actual not in (expected,expected+[(3,"asset_lineage.discarded")]):
            _fail("AUDIT_CHAIN_INVALID")
        path,info=_inspect(vault,ref)
        if len(events)==3:
            if info is not None:
                _fail("OBJECT_REAPPEARED")
            return {"status":"ALREADY_RECORDED","object_id":object_id,
                "directory_entry_removed":False,"object_absent":True,
                "secure_erasure_verified":False,"media_enabled":False}
        if info is not None:
            current=path.lstat()
            if not _regular(current) or not os.path.samestat(info,current) or current.st_size!=info.st_size:
                _fail("OBJECT_CHANGED")
            path.unlink()
        # An absent file after a crash is NOT evidence that this invocation
        # deleted it. Preserve that distinction in the durable receipt.
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            _fail("OBJECT_REAPPEARED")
        outcome="removed" if info is not None else "already_absent"
        seq=db.execute(insert(domain_events).values(event_id=str(uuid4()),tenant_id=tenant,
            aggregate_type="asset_lineage",aggregate_id=object_id,aggregate_version=3,
            event_type="asset_lineage.discarded",occurred_at=now_utc().isoformat(),
            payload=json.dumps({"outcome":outcome,"secure_erasure_verified":False,
                "media_enabled":False}))).inserted_primary_key[0]
        db.execute(insert(outbox).values(seq=seq,attempts=0,dead_letter=0))
        return {"status":"DISCARD_RECORDED","object_id":object_id,
            "directory_entry_removed":info is not None,"object_absent":True,
            "secure_erasure_verified":False,"media_enabled":False}
