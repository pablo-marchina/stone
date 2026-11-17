"""A02.4 durable private lineage index and monotonic logical invalidation.

Trusted-host SQLite library, no HTTP/worker/processor integration. Metadata
only; does not store derivative payloads or grant rights. All mutations
serialize via BEGIN IMMEDIATE. A registered reference is not proof that
an encrypted file exists or that a derivative is valid.
"""
from contextlib import contextmanager
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import (Table,Column,String,Text,ForeignKeyConstraint,CheckConstraint,
                        select,insert,update)
from .sa_store import metadata,domain_events,outbox
from .asset_lineage import RetainedAssetRef,DerivedArtifactRef,invalidation_plan
from .asset_rights import Permission,AssetRightsDenied
from .asset_rights_registry import (_scope,_load_head,_source_bound,_hash,_effective_anchor,
                                    grants,SignedGrant,decide_asset)
from .storage import now_utc

NAME="asset_lineage_nodes"
nodes=Table(NAME,metadata,
    Column("tenant_id",String(128),primary_key=True),
    Column("node_id",String(128),primary_key=True),
    Column("kind",String(32),nullable=False),
    Column("payload",Text,nullable=False),
    Column("state",String(16),nullable=False),
    Column("invalidated_at",String(40)),
    ForeignKeyConstraint(["tenant_id"],["tenants.tenant_id"]),
    CheckConstraint("kind IN ('asset','derived')",name="ck_lineage_kind"),
    CheckConstraint("(state='active' AND invalidated_at IS NULL) OR "
                    "(state='invalidated' AND invalidated_at IS NOT NULL)",name="ck_lineage_state"))


def _fail(code):
    raise AssetRightsDenied("ASSET_INDEX_"+code)


def _event(db,tenant,node_id,kind,reason):
    seq=db.execute(insert(domain_events).values(event_id=str(uuid4()),tenant_id=tenant,
        aggregate_type="asset_lineage",aggregate_id=node_id,
        aggregate_version=1 if kind=="registered" else 2,
        event_type="asset_lineage."+kind,occurred_at=now_utc().isoformat(),
        payload=json.dumps({"reason":reason,"media_enabled":False}))).inserted_primary_key[0]
    db.execute(insert(outbox).values(seq=seq,attempts=0,dead_letter=0))


def _load(db,tenant):
    rows=db.execute(select(nodes).where(nodes.c.tenant_id==tenant).limit(20001)).mappings().all()
    if len(rows)>20000:
        _fail("LOCAL_LIMIT")
    assets,derived=[],[]
    by_id={}
    for row in rows:
        if row["kind"]=="asset":
            ref=RetainedAssetRef.model_validate_json(row["payload"])
            ident=ref.object_id
            if ref.target.tenant_id!=tenant:
                _fail("TENANT_MISMATCH")
            assets.append(ref)
        elif row["kind"]=="derived":
            ref=DerivedArtifactRef.model_validate_json(row["payload"])
            ident=ref.artifact_id
            if ref.tenant_id!=tenant:
                _fail("TENANT_MISMATCH")
            derived.append(ref)
        else:
            _fail("INVALID_KIND")
        if ident!=row["node_id"] or row["state"] not in ("active","invalidated"):
            _fail("INDEX_CORRUPT")
        by_id[ident]=(row,ref)
    # Reject malformed graph even when there is no requested invalidation.
    invalidation_plan(tenant,assets,derived,invalid_asset_ids=set(),
                      invalid_artifact_ids=set(),now=now_utc())
    return assets,derived,by_id


def _grant(db,anchor,ref,now,permission):
    target=ref.target
    key=_scope(anchor,target.tenant_id,target.platform)
    if ref.issuer_id!=anchor.issuer_id or ref.issuer_key_sha256!=sha256(anchor.public_key).hexdigest():
        _fail("ISSUER_MISMATCH")
    head,state=_load_head(db,key,anchor)
    if not _source_bound(db,target,now):
        _fail("SOURCE_DENIED")
    row=db.execute(select(grants).where(*(grants.c[k]==v for k,v in key.items()),
        grants.c.grant_id==ref.grant_id)).mappings().one_or_none()
    if row is None:
        _fail("GRANT_NOT_FOUND")
    grant=SignedGrant.model_validate_json(row["payload"])
    if (_hash(grant.claims)!=row["claims_sha256"] or grant.claims.grant_id!=ref.grant_id
        or grant.claims.target!=target or row["asset_id"]!=target.asset_id
        or row["content_id"]!=target.content_id):
        _fail("GRANT_CORRUPT")
    if ref.retain_until>min(grant.claims.retain_until,grant.claims.expires_at) or ref.retained_at<grant.claims.not_before:
        _fail("RETENTION_OUTSIDE_GRANT")
    decision=decide_asset(authority=_effective_anchor(anchor,head),grant=grant,
        revocations=state,target=target,permission=permission,now=now)
    if not decision.permitted:
        raise AssetRightsDenied(decision.code)


def _ancestors(by_id,ident,now):
    todo=[ident]
    seen=set()
    roots=[]
    while todo:
        key=todo.pop()
        if key in seen:
            continue
        seen.add(key)
        if key not in by_id:
            _fail("UNKNOWN_NODE")
        row,ref=by_id[key]
        if row["state"]!="active" or ref.retain_until<=now:
            _fail("INACTIVE_ANCESTOR")
        if isinstance(ref,RetainedAssetRef):
            if ref.retained_at>now:
                _fail("FUTURE_NODE")
            roots.append(ref)
        else:
            if ref.created_at>now:
                _fail("FUTURE_NODE")
            todo.extend(ref.parent_ids)
    return roots


class AssetLineageIndex:
    def __init__(self,engine):
        if engine.dialect.name!="sqlite":
            _fail("SQLITE_ONLY")
        self.engine=engine

    @contextmanager
    def _transaction(self):
        with self.engine.connect() as db:
            db.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def _insert(self,db,tenant,ident,kind,ref,by_id):
        if ident in by_id:
            row,old=by_id[ident]
            if old!=ref or row["kind"]!=kind:
                _fail("ID_CONFLICT")
            if row["state"]!="active":
                _fail("TOMBSTONE")
            return False
        if len(by_id)>=20000:
            _fail("LOCAL_LIMIT")
        db.execute(insert(nodes).values(tenant_id=tenant,node_id=ident,kind=kind,
            payload=ref.model_dump_json(),state="active"))
        _event(db,tenant,ident,"registered",kind)
        return True

    def register_retained(self,anchor,ref:RetainedAssetRef,*,purpose="research_analysis"):
        """Register trusted metadata only, not a storage receipt or byte proof."""
        tenant=ref.target.tenant_id
        with self._transaction() as db:
            now=now_utc()
            if not ref.retained_at<=now<ref.retain_until:
                _fail("INACTIVE_NODE")
            _grant(db,anchor,ref,now,Permission(operation="retain",purpose=purpose,field=ref.target.media_kind))
            _,_,by_id=_load(db,tenant)
            return self._insert(db,tenant,ref.object_id,"asset",ref,by_id)

    def register_derived(self,ref:DerivedArtifactRef,*,resolve_anchor,purpose="research_analysis"):
        """Metadata-only registration, all roots must authorize exact derivation.

        resolve_anchor is trusted host code accepting a RetainedAssetRef.
        No inference is run; actual payload binding remains a future PEP.
        """
        with self._transaction() as db:
            now=now_utc()
            if not ref.created_at<=now<ref.retain_until:
                _fail("INACTIVE_NODE")
            assets,derived,by_id=_load(db,ref.tenant_id)
            if ref.artifact_id in by_id:
                old=by_id[ref.artifact_id][1]
                if old!=ref:
                    _fail("ID_CONFLICT")
            else:
                invalidation_plan(ref.tenant_id,assets,derived+[ref],invalid_asset_ids=set(),
                                  invalid_artifact_ids=set(),now=now)
            field=ref.kind
            # Ranking/index/run nodes require the underlying rubric evidence
            # permission; no claim of permission to expose their payloads.
            if field in ("ranking_reference","retrieval_index","analysis_run"):
                field="rubric_evidence"
            unique_roots={root.object_id:root for parent in ref.parent_ids for root in _ancestors(by_id,parent,now)}
            for root in unique_roots.values():
                anchor=resolve_anchor(root)
                _grant(db,anchor,root,now,Permission(operation="retain",purpose=purpose,field=root.target.media_kind))
                _grant(db,anchor,root,now,Permission(operation="derive",purpose=purpose,field=field))
            return self._insert(db,ref.tenant_id,ref.artifact_id,"derived",ref,by_id)

    def _invalidate(self,db,tenant,assets,derived,by_id,*,object_ids=(),artifact_ids=(),now):
        roots={a.object_id for a in assets}
        artifacts={a.artifact_id for a in derived}
        requested=set(object_ids)|set(artifact_ids)
        if not set(object_ids)<=roots or not set(artifact_ids)<=artifacts:
            _fail("UNKNOWN_NODE")
        affected=requested|{k for k,(row,ref) in by_id.items()
            if row["state"]=="invalidated" or ref.retain_until<=now}
        children={}
        for item in derived:
            for parent in item.parent_ids:
                children.setdefault(parent,[]).append(item.artifact_id)
        todo=list(affected)
        while todo:
            for child in children.get(todo.pop(),()):
                if child not in affected:
                    affected.add(child)
                    todo.append(child)
        changed=[]
        for ident in sorted(affected):
            if by_id[ident][0]["state"]=="active":
                db.execute(update(nodes).where(nodes.c.tenant_id==tenant,nodes.c.node_id==ident,
                    nodes.c.state=="active").values(state="invalidated",invalidated_at=now.isoformat()))
                _event(db,tenant,ident,"invalidated","requested_or_ancestor_or_expired")
                changed.append(ident)
        return {"status":"LOGICAL_INVALIDATION_APPLIED","newly_invalidated":changed,
                "affected_objects":sorted(affected&roots),"affected_artifacts":sorted(affected&artifacts),
                "filesystem_mutated":False,"media_enabled":False}

    def invalidate(self,tenant,*,object_ids=(),artifact_ids=()):
        """Trusted administrative invalidation and expiry sweep, no deletion."""
        with self._transaction() as db:
            now=now_utc()
            assets,derived,by_id=_load(db,tenant)
            return self._invalidate(db,tenant,assets,derived,by_id,
                object_ids=object_ids,artifact_ids=artifact_ids,now=now)

    def reconcile_signed_revocations(self,anchor,tenant,platform):
        """Apply the current signed registry head to its exact issuer scope.

        Registry advancement is deliberately independent: an index failure
        cannot roll back a revocation. Every preflight rechecks registry
        rights even before reconciliation. Stale heads deny preflight;
        no destructive action is taken merely because an anchor is absent.
        """
        with self._transaction() as db:
            now=now_utc()
            key=_scope(anchor,tenant,platform)
            _,state=_load_head(db,key,anchor)
            rv=state.claims
            if not rv.issued_at<=now<rv.valid_until:
                _fail("REVOCATION_STALE")
            assets,derived,by_id=_load(db,tenant)
            revoked_sources={(s.tenant_id,s.platform,s.source_account_id) for s in rv.revoked_sources}
            affected=[a.object_id for a in assets
                if a.issuer_id==anchor.issuer_id and a.target.platform==platform
                and a.issuer_key_sha256==sha256(anchor.public_key).hexdigest()
                and (a.grant_id in rv.revoked_grant_ids or a.target.asset_id in rv.revoked_asset_ids
                    or (tenant,platform,a.target.source_account_id) in revoked_sources)]
            return self._invalidate(db,tenant,assets,derived,by_id,object_ids=affected,now=now)

    def preflight(self,tenant,ident,*,resolve_anchor,permission:Permission):
        """Recheck every root at read boundary. Returns no payload or credential.

        This is only a preflight, not an enforcement lock spanning inference.
        A stale/missing authority denies without permanently deleting data.
        """
        with self._transaction() as db:
            now=now_utc()
            _,_,by_id=_load(db,tenant)
            for root in _ancestors(by_id,ident,now):
                anchor=resolve_anchor(root)
                _grant(db,anchor,root,now,Permission(operation="retain",purpose=permission.purpose,
                    field=root.target.media_kind))
                _grant(db,anchor,root,now,permission)
            return {"status":"PREFLIGHT_ALLOWED","payload_returned":False,"media_enabled":False}
