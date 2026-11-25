"""A02.4 indexed byte-access PEP for a trusted host, SQLite only.

Reserve metadata durably before publishing an envelope. A missing envelope
after a failed/crashed write is not a completed retention. All indexed byte
access serializes against revocation/index mutations using BEGIN IMMEDIATE
and verifies current rights before and after I/O. No HTTP or media adapter.
Python-private primitives are not a sandbox against trusted process code.
"""
from .asset_vault import AssetVault,_validate
from .asset_lineage import RetainedAssetRef
from .asset_lineage_index import AssetLineageIndex,_load,_grant,_ancestors
from .asset_rights_registry import AssetRightsRegistry
from .asset_rights import AssetRightsDenied,Permission
from .storage import now_utc


def _fail(code):
    raise AssetRightsDenied("INDEXED_VAULT_"+code)


class IndexedAssetVault(AssetVault):
    def __init__(self,root,key,registry,index):
        if not isinstance(registry,AssetRightsRegistry) or not isinstance(index,AssetLineageIndex):
            _fail("REGISTRY_AND_INDEX_REQUIRED")
        if registry.engine is not index.engine:
            _fail("ENGINE_MISMATCH")
        super().__init__(root,key,registry)
        self._index=index

    def _ref(self,db,tenant,ident,purpose):
        _,_,by_id=_load(db,tenant)
        if ident not in by_id:
            _fail("UNKNOWN_OBJECT")
        row,ref=by_id[ident]
        if not isinstance(ref,RetainedAssetRef):
            _fail("ROOT_REQUIRED")
        _ancestors(by_id,ident,now_utc(),purpose)
        return ref

    def _check(self,db,anchor,ref,purpose,*,process=False):
        now=now_utc()
        if not ref.retained_at<=now<ref.retain_until:
            _fail("INACTIVE_OBJECT")
        _grant(db,anchor,ref,now,Permission(operation="retain",purpose=purpose,field=ref.target.media_kind))
        if process:
            _grant(db,anchor,ref,now,Permission(operation="process",purpose=purpose,field=ref.target.media_kind))

    def retain_indexed(self,anchor,ref:RetainedAssetRef,*,purpose,data:bytes):
        # Check metadata and rights before publishing anything. Registration
        # is a reservation, not evidence that bytes exist; a failed write
        # can be retried with the exact same ref, never a tombstoned one.
        ref=RetainedAssetRef.model_validate(ref.model_dump())
        if type(data) is not bytes or len(data)!=ref.byte_count:
            _fail("BYTE_COUNT_MISMATCH")
        _validate(data,ref.target,ref.mime)
        self._index.register_retained(anchor,ref,purpose=purpose)
        with self._index._transaction() as db:
            stored=self._ref(db,ref.target.tenant_id,ref.object_id,purpose)
            if stored!=ref:
                _fail("REFERENCE_MISMATCH")
            result=self._retain_checked(anchor,ref.grant_id,ref.target,mime=ref.mime,data=data,
                check=lambda:self._check(db,anchor,stored,purpose))
        return {**result,"object_id":ref.object_id,"indexed":True,"media_enabled":False}

    def read_indexed(self,anchor,tenant,object_id,*,purpose):
        # Caller supplies an opaque ID, not a path or alternative metadata.
        with self._index._transaction() as db:
            ref=self._ref(db,tenant,object_id,purpose)
            data=self._read_checked(anchor,ref.grant_id,ref.target,mime=ref.mime,
                check=lambda:self._check(db,anchor,ref,purpose,process=True))
            if len(data)!=ref.byte_count:
                _fail("BYTE_COUNT_MISMATCH")
        return data
