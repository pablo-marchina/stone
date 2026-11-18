from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import sys
import struct

import pytest
from sqlalchemy import select, update, func
from alembic import command
from alembic.config import Config

from tapi_gate0.asset_rights import (AssetIdentity, Permission, GrantClaims, SignedGrant,
    RevocationClaims, SignedRevocations, TrustedAuthority, AssetRightsDenied, signed_bytes)
from tapi_gate0.asset_rights_registry import AssetRightsRegistry, authorities, revocations, grants
from tapi_gate0.asset_lineage_index import AssetLineageIndex, nodes
from tapi_gate0.asset_jobs import AssetJobQueue, JobSpec, jobs, attempts
from tapi_gate0.asset_derived_payloads import DerivedPayloadStore, payloads
from tapi_gate0.asset_lineage import RetainedAssetRef, DerivedArtifactRef, expected_object_id
from tapi_gate0.connectors import NormalizedItem, Platform
from tapi_gate0.domain import MediaType
from tapi_gate0.ingestion import IngestionStore, GrantCreate, source_grants, ingestion_records
from tapi_gate0.sa_store import SqlDomainStore, engine_for, domain_events, outbox
from tapi_gate0.storage import now_utc

TENANT="rights-fixture"
ACCOUNT="17841400011122233"
ITEM="17900000000011111"
PERMISSION=Permission(operation="process",purpose="research_analysis",field="video")


@pytest.fixture
def registry(tmp_path):
    crypto=pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    private=crypto.Ed25519PrivateKey.generate()
    engine=engine_for("sqlite:///"+str(tmp_path/"registry.sqlite3"))
    domain=SqlDomainStore(engine)
    domain.initialize()
    domain.create_tenant(TENANT,"Fixture")
    store=IngestionStore(engine)
    now=now_utc()
    store.grant(TENANT,"fixture-operator",GrantCreate(platform=Platform.INSTAGRAM,
        source_account_id=ACCOUNT,approval_reference="fixture-only-metadata-grant",
        expires_at=now+timedelta(days=1)))
    with engine.begin() as db:
        db.execute(update(source_grants).where(source_grants.c.tenant_id==TENANT)
            .values(technical_verified_at=now_utc().isoformat()))
    item=NormalizedItem(platform=Platform.INSTAGRAM,source_account_id=ACCOUNT,
        source_item_id=ITEM,creator_handle="fixture",media_type=MediaType.REELS,
        source_url="https://www.instagram.com/p/Fixture123/",
        published_at=now-timedelta(days=30),caption="Fixture.",
        likes=1,comments=0,follower_count=100,
        denominator_quality="observed_current_only",metadata_only=True)
    store._persist_item(TENANT,item)
    with engine.connect() as db:
        cid=db.scalar(select(ingestion_records.c.content_id).where(ingestion_records.c.tenant_id==TENANT))
    target=AssetIdentity(tenant_id=TENANT,platform="instagram",source_account_id=ACCOUNT,
        source_item_id=ITEM,content_id=cid,asset_id="asset.fixture",media_kind="video",sha256="a"*64)
    now=now_utc()
    def state(revision=1,**changes):
        claims=RevocationClaims(**(dict(issuer_id="fixture-issuer",revision=revision,
            issued_at=now-timedelta(seconds=1),valid_until=now+timedelta(minutes=10),
            revoked_grant_ids=(),revoked_asset_ids=())|changes))
        return SignedRevocations(claims=claims,signature=private.sign(signed_bytes(claims)).hex())
    def anchor(rv):
        return TrustedAuthority("fixture-issuer",private.public_key().public_bytes_raw(),
            frozenset({(TENANT,"instagram")}),rv.claims.revision,sha256(signed_bytes(rv.claims)).hexdigest())
    def grant(**changes):
        claims=GrantClaims(**(dict(issuer_id="fixture-issuer",grant_id="grant.fixture",target=target,
            approval_evidence_sha256="b"*64,issued_at=now-timedelta(minutes=10),
            not_before=now-timedelta(minutes=5),expires_at=now+timedelta(hours=1),
            retain_until=now+timedelta(hours=1),permissions=(PERMISSION,))|changes))
        return SignedGrant(claims=claims,signature=private.sign(signed_bytes(claims)).hex())
    rv=state()
    svc=AssetRightsRegistry(engine)
    try:
        yield SimpleNamespace(engine=engine,svc=svc,rv=rv,anchor=anchor(rv),state=state,
            pin=anchor,grant=grant,target=target,store=store)
    finally:
        engine.dispose()


def register(f):
    f.svc.provision(f.anchor,TENANT,"instagram",f.rv)
    assert f.svc.register_grant(f.anchor,f.grant(),verified_approval_digest="b"*64)


def test_registry_default_deny_and_transactional_registration(registry):
    f=registry
    assert not f.svc.decide(None,"grant.fixture",f.target,PERMISSION).permitted
    assert not f.svc.decide(f.anchor,"grant.fixture",f.target,PERMISSION).permitted
    register(f)
    assert f.svc.decide(f.anchor,"grant.fixture",f.target,PERMISSION).permitted
    assert f.svc.register_grant(f.anchor,f.grant(),verified_approval_digest="b"*64) is False
    with f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(grants))==1
        seqs=db.scalars(select(domain_events.c.seq).where(domain_events.c.aggregate_type=="asset_rights")).all()
        assert len(seqs)==2
        assert db.scalar(select(func.count()).select_from(outbox).where(outbox.c.seq.in_(seqs)))==2


def test_registry_rejects_approval_mismatch_and_source_identity(registry):
    f=registry
    f.svc.provision(f.anchor,TENANT,"instagram",f.rv)
    with pytest.raises(AssetRightsDenied,match="APPROVAL_MISMATCH"):
        f.svc.register_grant(f.anchor,f.grant(),verified_approval_digest="c"*64)
    bad=f.grant(target=f.target.model_copy(update={"source_item_id":"wrong"}))
    with pytest.raises(AssetRightsDenied,match="SOURCE_DENIED"):
        f.svc.register_grant(f.anchor,bad,verified_approval_digest="b"*64)
    assert not f.svc.decide(f.anchor,"grant.fixture",f.target,PERMISSION).permitted


def test_registry_revocation_cumulative_and_exact_external_pin(registry):
    f=registry
    register(f)
    rv2=f.state(2,revoked_grant_ids=("grant.fixture",))
    assert f.svc.advance(f.anchor,TENANT,"instagram",rv2)
    assert f.svc.decide(f.anchor,"grant.fixture",f.target,PERMISSION).code=="ASSET_REGISTRY_ROLLBACK"
    pin2=f.pin(rv2)
    assert f.svc.decide(pin2,"grant.fixture",f.target,PERMISSION).code=="ASSET_RIGHTS_REVOKED"
    assert f.svc.advance(pin2,TENANT,"instagram",rv2) is False
    with pytest.raises(AssetRightsDenied,match="REVOCATION_REMOVAL"):
        f.svc.advance(pin2,TENANT,"instagram",f.state(3))
    with pytest.raises(AssetRightsDenied,match="REVISION_NOT_MONOTONIC"):
        f.svc.advance(pin2,TENANT,"instagram",f.state(2,revoked_asset_ids=("asset.fixture",)))
    with f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(revocations))==2


def test_registry_source_revocation_and_db_tampering(registry):
    f=registry
    register(f)
    with f.engine.begin() as db:
        db.execute(update(source_grants).where(source_grants.c.tenant_id==TENANT).values(enabled=0))
    assert f.svc.decide(f.anchor,"grant.fixture",f.target,PERMISSION).code=="ASSET_REGISTRY_SOURCE_DENIED"
    with f.engine.begin() as db:
        db.execute(update(source_grants).where(source_grants.c.tenant_id==TENANT).values(enabled=1))
        db.execute(update(grants).values(claims_sha256="0"*64))
    assert f.svc.decide(f.anchor,"grant.fixture",f.target,PERMISSION).code=="ASSET_REGISTRY_GRANT_CORRUPT"


def test_registry_wrong_key_and_tenant_denied(registry):
    f=registry
    register(f)
    assert not f.svc.decide(replace(f.anchor,public_key=b"x"*32),"grant.fixture",f.target,PERMISSION).permitted
    assert not f.svc.decide(f.anchor,"grant.fixture",f.target.model_copy(update={"tenant_id":"other"}),PERMISSION).permitted
    assert not f.svc.decide(f.anchor,"grant.fixture",f.target,Permission(
        operation="display",purpose="research_analysis",field="video")).permitted


@pytest.mark.parametrize('mode',[0,1,2,3],ids=['0013','0014','0015','0016'])
def test_migration_rehearsal_preserves_disposable_backup(tmp_path,monkeypatch,mode):
    lineage=mode==1
    jobs_mode=mode==2
    payload_mode=mode==3
    from scripts import a02_migration_rehearsal as drill
    from tapi_gate0.discovery_backup import _sha256
    root=Path(__file__).resolve().parents[1]
    # Actual Alembic chain, with a private disposable database only.
    private=tmp_path/"artifacts"/"private"
    private.mkdir(parents=True)
    db=private/"fixture.sqlite3"
    monkeypatch.setenv("TAPI_DATABASE_URL","sqlite:///"+str(db))
    config=Config(str(root/"alembic.ini"))
    config.set_main_option("script_location",str(root/"migrations"))
    command.upgrade(config,'0015_asset_jobs' if payload_mode else '0014_asset_lineage' if jobs_mode else drill.NEW if lineage else drill.OLD)
    engine=engine_for("sqlite:///"+str(db))
    SqlDomainStore(engine).create_tenant(TENANT,"Fixture")
    engine.dispose()
    # Rehearsal root needs repo files; use temporary private dir via narrow
    # test patch of the subprocess root by running with copied migration files.
    import shutil
    shutil.copytree(root/"migrations",tmp_path/"migrations")
    shutil.copy2(root/"alembic.ini",tmp_path/"alembic.ini")
    shutil.copytree(root/"src",tmp_path/"src")
    digest=_sha256(db)
    result=drill.rehearsal(tmp_path,db.name,digest,TENANT,lineage=lineage,jobs=jobs_mode,payloads=payload_mode)
    assert result["status"]=="A02_MIGRATION_REHEARSAL_VERIFIED"
    assert result["backup_unchanged"] and result["empty_downgrade_verified"]
    if lineage:
        assert result["to_revision"]=="0014_asset_lineage"
        assert result["new_empty_tables"]==["asset_lineage_nodes"]
    if jobs_mode:
        assert result["to_revision"]=="0015_asset_jobs"
        assert result["new_empty_tables"]==["asset_processing_attempts","asset_processing_jobs"]
    if payload_mode:
        assert result["to_revision"]=="0016_asset_derived_payloads"
        assert result["new_empty_tables"]==["asset_derived_payloads"]
    assert _sha256(db)==digest
    with pytest.raises(ValueError,match="BACKUP_MISMATCH"):
        drill.rehearsal(tmp_path,db.name,"0"*64,TENANT)


def test_nonempty_registry_downgrade_refused(tmp_path,monkeypatch):
    from sqlalchemy import insert, inspect
    from tapi_gate0.sa_store import tenants
    root=Path(__file__).resolve().parents[1]
    url="sqlite:///"+str(tmp_path/"downgrade.sqlite3")
    monkeypatch.setenv("TAPI_DATABASE_URL",url)
    cfg=Config(str(root/"alembic.ini"))
    cfg.set_main_option("script_location",str(root/"migrations"))
    command.upgrade(cfg,"0013_asset_rights_registry")
    engine=engine_for(url)
    try:
        with engine.begin() as db:
            db.execute(insert(tenants).values(tenant_id=TENANT,name="Fixture"))
            db.execute(insert(authorities).values(tenant_id=TENANT,platform="instagram",
                issuer_id="fixture",key_sha256="a"*64,revision=1,claims_sha256="b"*64))
        with pytest.raises(RuntimeError,match="DOWNGRADE_NONEMPTY"):
            command.downgrade(cfg,"0012_bd_history_checkpoints")
        assert "asset_rights_authorities" in inspect(engine).get_table_names()
        with engine.connect() as db:
            assert db.scalar(select(func.count()).select_from(authorities))==1
    finally:
        engine.dispose()


def test_vault_with_real_signed_registry_and_revocation(discard_fixture):
    q=discard_fixture
    f=q.f
    from tapi_gate0.asset_vault import AssetVault
    primitive=AssetVault(q.path.parent,b"v"*32,f.svc)
    kwargs={"mime":"video/mp4","purpose":"research_analysis"}
    data=b"\x00\x00\x00\x0cftypisom"
    with pytest.raises(AssetRightsDenied,match="INDEX_REQUIRED"):
        primitive.retain(f.anchor,"grant.fixture",q.ref.target,data=data,**kwargs)
    with pytest.raises(AssetRightsDenied,match="INDEX_REQUIRED"):
        primitive.read_for_processing(f.anchor,"grant.fixture",q.ref.target,**kwargs)
    assert q.vault.read_indexed(f.anchor,TENANT,q.ref.object_id,purpose="research_analysis")==data
    revoked=f.state(2,revoked_asset_ids=(q.ref.target.asset_id,))
    f.svc.advance(f.anchor,TENANT,"instagram",revoked)
    with pytest.raises(AssetRightsDenied,match="ROLLBACK"):
        q.vault.read_indexed(f.anchor,TENANT,q.ref.object_id,purpose="research_analysis")
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        q.vault.read_indexed(f.pin(revoked),TENANT,q.ref.object_id,purpose="research_analysis")
    assert q.path.exists()


def indexed(f):
    retain=Permission(operation="retain",purpose="research_analysis",field="video")
    derive=Permission(operation="derive",purpose="research_analysis",field="rubric_evidence")
    f.svc.provision(f.anchor,TENANT,"instagram",f.rv)
    f.svc.register_grant(f.anchor,f.grant(permissions=(retain,derive,PERMISSION)),
        verified_approval_digest="b"*64)
    now=now_utc()
    ref=RetainedAssetRef(target=f.target,issuer_id=f.anchor.issuer_id,
        issuer_key_sha256=sha256(f.anchor.public_key).hexdigest(),grant_id="grant.fixture",
        mime="video/mp4",object_id=expected_object_id(f.anchor,"grant.fixture",f.target,"video/mp4"),
        byte_count=12,retained_at=now,retain_until=now+timedelta(minutes=20))
    index=AssetLineageIndex(f.engine)
    def derived(id,parents):
        return DerivedArtifactRef(tenant_id=TENANT,artifact_id=id,kind="rubric_evidence",
            payload_sha256="d"*64,parent_ids=tuple(parents),run_id="run.fixture",method_version="v1",
            created_at=now,retain_until=now+timedelta(minutes=10))
    x=derived("x",[ref.object_id])
    y=derived("y",["x"])
    return index,ref,x,y,derive


def test_lineage_index_signed_revocation_preflight_and_persistent_cascade(registry):
    f=registry
    index,ref,x,y,derive=indexed(f)
    resolve=lambda root:f.anchor
    assert index.register_retained(f.anchor,ref)
    assert not index.register_retained(f.anchor,ref)
    assert index.register_derived(x,resolve_anchor=resolve)
    assert index.register_derived(y,resolve_anchor=resolve)
    assert index.preflight(TENANT,"y",resolve_anchor=resolve,permission=derive)["status"]=="PREFLIGHT_ALLOWED"
    rv=f.state(2,revoked_grant_ids=("grant.fixture",))
    f.svc.advance(f.anchor,TENANT,"instagram",rv)
    pin=f.pin(rv)
    with pytest.raises(AssetRightsDenied,match="ROLLBACK"):
        index.preflight(TENANT,"y",resolve_anchor=resolve,permission=derive)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        index.preflight(TENANT,"y",resolve_anchor=lambda root:pin,permission=derive)
    # Reconciliation remains separate from registry advance; stale pin
    # never authorizes a destructive action or revives a node.
    with pytest.raises(AssetRightsDenied,match="ROLLBACK"):
        index.reconcile_signed_revocations(f.anchor,TENANT,"instagram")
    result=index.reconcile_signed_revocations(pin,TENANT,"instagram")
    assert result["newly_invalidated"]==sorted([ref.object_id,"x","y"])
    assert result["affected_artifacts"]==["x","y"]
    assert not result["filesystem_mutated"]
    assert index.reconcile_signed_revocations(pin,TENANT,"instagram")["newly_invalidated"]==[]
    with pytest.raises(AssetRightsDenied,match="INACTIVE_ANCESTOR"):
        index.preflight(TENANT,"y",resolve_anchor=lambda root:pin,permission=derive)
    with f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(nodes).where(nodes.c.state=="invalidated"))==3
        seqs=db.scalars(select(domain_events.c.seq).where(domain_events.c.aggregate_type=="asset_lineage")).all()
        assert len(seqs)==6
        assert db.scalar(select(func.count()).select_from(outbox).where(outbox.c.seq.in_(seqs)))==6


def test_lineage_index_rejects_unregistered_parent_wrong_scope_and_tombstone(registry):
    f=registry
    index,ref,x,y,derive=indexed(f)
    resolve=lambda root:f.anchor
    with pytest.raises(ValueError,match="PARENT_MISSING"):
        index.register_derived(x,resolve_anchor=resolve)
    index.register_retained(f.anchor,ref)
    with pytest.raises(AssetRightsDenied,match="SCOPE_MISMATCH"):
        index.register_derived(x.model_copy(update={"kind":"ocr"}),resolve_anchor=resolve)
    with pytest.raises(AssetRightsDenied,match="RETENTION_OUTSIDE_GRANT"):
        index.register_retained(f.anchor,ref.model_copy(update={"retain_until":now_utc()+timedelta(days=2)}))
    index.register_derived(x,resolve_anchor=resolve)
    with pytest.raises(AssetRightsDenied,match="FIELD_MISMATCH"):
        index.preflight(TENANT,"x",resolve_anchor=resolve,permission=PERMISSION)
    with pytest.raises(AssetRightsDenied,match="PURPOSE_MISMATCH"):
        index.preflight(TENANT,"x",resolve_anchor=resolve,permission=derive.model_copy(update={"purpose":"studio_creation"}))
    with pytest.raises(AssetRightsDenied,match="UNKNOWN_NODE"):
        index.preflight("other","x",resolve_anchor=resolve,permission=derive)
    index.invalidate(TENANT,artifact_ids=["x"])
    with pytest.raises(AssetRightsDenied,match="TOMBSTONE"):
        index.register_derived(x,resolve_anchor=resolve)
    with pytest.raises(AssetRightsDenied,match="INACTIVE_ANCESTOR"):
        index.register_derived(y,resolve_anchor=resolve)
    assert index.preflight(TENANT,ref.object_id,resolve_anchor=resolve,permission=PERMISSION)["status"]=="PREFLIGHT_ALLOWED"


def test_lineage_index_expiry_and_source_denial(registry,monkeypatch):
    from tapi_gate0 import asset_lineage_index as module
    f=registry
    index,ref,x,y,derive=indexed(f)
    index.register_retained(f.anchor,ref)
    index.register_derived(x,resolve_anchor=lambda root:f.anchor)
    index.register_derived(y,resolve_anchor=lambda root:f.anchor)
    with f.engine.begin() as db:
        db.execute(update(source_grants).where(source_grants.c.tenant_id==TENANT).values(enabled=0))
    with pytest.raises(AssetRightsDenied,match="SOURCE_DENIED"):
        index.preflight(TENANT,"y",resolve_anchor=lambda root:f.anchor,permission=derive)
    monkeypatch.setattr(module,"now_utc",lambda:x.retain_until)
    result=index.invalidate(TENANT)
    assert result["newly_invalidated"]==["x","y"]
    assert result["affected_objects"]==[]


def test_nonempty_lineage_downgrade_refused(tmp_path,monkeypatch):
    from sqlalchemy import insert, inspect
    from tapi_gate0.sa_store import tenants
    root=Path(__file__).resolve().parents[1]
    url="sqlite:///"+str(tmp_path/"lineage.sqlite3")
    monkeypatch.setenv("TAPI_DATABASE_URL",url)
    cfg=Config(str(root/"alembic.ini"))
    cfg.set_main_option("script_location",str(root/"migrations"))
    command.upgrade(cfg,"0014_asset_lineage")
    engine=engine_for(url)
    try:
        with engine.begin() as db:
            db.execute(insert(tenants).values(tenant_id=TENANT,name="Fixture"))
            db.execute(insert(nodes).values(tenant_id=TENANT,node_id="tombstone",
                kind="derived",purpose="research_analysis",payload="{}",
                state="invalidated",invalidated_at=now_utc().isoformat()))
        with pytest.raises(RuntimeError,match="ASSET_LINEAGE_DOWNGRADE_NONEMPTY"):
            command.downgrade(cfg,"0013_asset_rights_registry")
        assert "asset_lineage_nodes" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


@pytest.fixture
def discard_fixture(registry,tmp_path,request):
    from tapi_gate0.asset_indexed_vault import IndexedAssetVault
    from tapi_gate0.asset_discard import discard_invalidated
    f=registry
    data=b"\x00\x00\x00\x0cftypisom"
    requested=getattr(request,"param",())
    temporal_cases=[x.removeprefix("temporal_") for x in requested if x.startswith("temporal_")]
    if temporal_cases:
        from tapi_gate0.asset_temporal_fixture import fixture
        assert len(temporal_cases)==1
        data,_=fixture(temporal_cases[0])
    target=f.target.model_copy(update={"sha256":sha256(data).hexdigest()})
    retention=Permission(operation="retain",purpose="research_analysis",field="video")
    f.svc.provision(f.anchor,TENANT,"instagram",f.rv)
    extra=tuple(Permission(operation=op,purpose="research_analysis",field="visual_features")
        for op in requested if op!="all_processors" and not op.startswith("temporal_"))
    if "all_processors" in requested:
        extra+=tuple(Permission(operation=op,purpose="research_analysis",field=field)
            for field in ("transcript","ocr") for op in ("derive","retain","process"))
    f.svc.register_grant(f.anchor,f.grant(target=target,permissions=(retention,PERMISSION,Permission(operation="derive",purpose="research_analysis",field="visual_features"),*extra)),
        verified_approval_digest="b"*64)
    root=tmp_path/"discard-vault";root.mkdir(mode=0o700)
    now=now_utc()
    ref=RetainedAssetRef(target=target,issuer_id=f.anchor.issuer_id,
        issuer_key_sha256=sha256(f.anchor.public_key).hexdigest(),grant_id="grant.fixture",
        mime="video/mp4",object_id=expected_object_id(f.anchor,"grant.fixture",target,"video/mp4"),
        byte_count=len(data),retained_at=now,retain_until=now+timedelta(minutes=20))
    index=AssetLineageIndex(f.engine)
    vault=IndexedAssetVault(root,b"v"*32,f.svc,index)
    assert vault.retain_indexed(f.anchor,ref,purpose="research_analysis",data=data)["status"]=="retained"
    def discard(tenant=TENANT,stopped=True):
        return discard_invalidated(index,vault,tenant,ref.object_id,all_vault_io_stopped=stopped)
    return SimpleNamespace(f=f,index=index,ref=ref,path=root/(ref.object_id+".enc"),discard=discard,vault=vault)


def test_discard_requires_tombstone_exact_tenant_and_stopped_io(discard_fixture):
    q=discard_fixture
    for tenant,stopped,code in [(TENANT,False,"STOPPED_IO_REQUIRED"),
                                ("other",True,"UNKNOWN_OBJECT"),(TENANT,True,"TOMBSTONE_REQUIRED")]:
        with pytest.raises(AssetRightsDenied,match=code):
            q.discard(tenant,stopped)
    assert q.path.exists()


def test_discard_revoked_object_idempotent_receipt_and_no_reactivation(discard_fixture):
    q=discard_fixture
    rv=q.f.state(2,revoked_asset_ids=(q.ref.target.asset_id,))
    q.f.svc.advance(q.f.anchor,TENANT,"instagram",rv)
    q.index.reconcile_signed_revocations(q.f.pin(rv),TENANT,"instagram")
    envelope=q.path.read_bytes()
    result=q.discard()
    assert result["directory_entry_removed"] and result["object_absent"]
    assert not result["secure_erasure_verified"] and not q.path.exists()
    assert q.discard()["status"]=="ALREADY_RECORDED"
    with q.f.engine.connect() as db:
        row=db.execute(select(nodes).where(nodes.c.node_id==q.ref.object_id)).mappings().one()
        assert row["state"]=="invalidated"
        seqs=db.scalars(select(domain_events.c.seq).where(domain_events.c.aggregate_type=="asset_lineage")).all()
        assert len(seqs)==3
        assert db.scalar(select(func.count()).select_from(outbox).where(outbox.c.seq.in_(seqs)))==3
    q.path.write_bytes(envelope)
    with pytest.raises(AssetRightsDenied,match="OBJECT_REAPPEARED"):
        q.discard()
    assert q.path.exists()


def test_discard_rejects_corrupt_envelope_and_hardlink(discard_fixture):
    import os
    q=discard_fixture
    q.index.invalidate(TENANT,object_ids=[q.ref.object_id])
    envelope=q.path.read_bytes()
    q.path.write_bytes(b"X"*len(envelope))
    with pytest.raises(AssetRightsDenied,match="ENVELOPE_HEADER"):
        q.discard()
    q.path.write_bytes(envelope)
    link=q.path.parent/"other.enc"
    os.link(q.path,link)
    with pytest.raises(AssetRightsDenied,match="UNSAFE_OBJECT"):
        q.discard()
    assert q.path.exists() and link.exists()
    link.unlink()
    assert q.discard()["directory_entry_removed"]
    # Administrative invalidation is permanent even when the grant itself
    # is still active; an index registration cannot revive the tombstone.
    with pytest.raises(AssetRightsDenied,match="TOMBSTONE"):
        q.index.register_retained(q.f.anchor,q.ref)


def test_discard_retry_after_file_removed_before_receipt(discard_fixture,monkeypatch):
    from tapi_gate0 import asset_discard
    q=discard_fixture
    q.index.invalidate(TENANT,object_ids=[q.ref.object_id])
    real=asset_discard.insert
    def fail(table):
        if table is domain_events:
            raise RuntimeError("fixture crash before receipt")
        return real(table)
    with monkeypatch.context() as m:
        m.setattr(asset_discard,"insert",fail)
        with pytest.raises(RuntimeError,match="fixture crash"):
            q.discard()
    assert not q.path.exists()
    result=q.discard()
    assert result["status"]=="DISCARD_RECORDED" and not result["directory_entry_removed"]
    with q.f.engine.connect() as db:
        import json
        payload=db.scalar(select(domain_events.c.payload).where(domain_events.c.aggregate_type=="asset_lineage",
            domain_events.c.aggregate_id==q.ref.object_id,domain_events.c.aggregate_version==3))
        assert json.loads(payload)["outcome"]=="already_absent"


def test_indexed_vault_admin_tombstone_denies_read_and_retain(discard_fixture):
    q=discard_fixture
    data=b"\x00\x00\x00\x0cftypisom"
    q.index.invalidate(TENANT,object_ids=[q.ref.object_id])
    with pytest.raises(AssetRightsDenied,match="INACTIVE_ANCESTOR"):
        q.vault.read_indexed(q.f.anchor,TENANT,q.ref.object_id,purpose="research_analysis")
    q.discard()
    with pytest.raises(AssetRightsDenied,match="TOMBSTONE"):
        q.vault.retain_indexed(q.f.anchor,q.ref,purpose="research_analysis",data=data)
    assert not q.path.exists()


def test_indexed_vault_exact_ref_purpose_and_tenant(discard_fixture):
    q=discard_fixture
    data=b"\x00\x00\x00\x0cftypisom"
    assert q.vault.retain_indexed(q.f.anchor,q.ref,purpose="research_analysis",data=data)["status"]=="already_retained"
    for tenant,ident,purpose,code in [
        ("other",q.ref.object_id,"research_analysis","UNKNOWN_OBJECT"),
        (TENANT,"absent","research_analysis","UNKNOWN_OBJECT"),
        (TENANT,q.ref.object_id,"studio_creation","PURPOSE_MISMATCH")]:
        with pytest.raises(AssetRightsDenied,match=code):
            q.vault.read_indexed(q.f.anchor,tenant,ident,purpose=purpose)
    with pytest.raises(AssetRightsDenied,match="BYTE_COUNT_MISMATCH"):
        q.vault.retain_indexed(q.f.anchor,q.ref,purpose="research_analysis",data=data+b"x")


def test_indexed_vault_missing_bytes_retry_and_metadata_binding(discard_fixture):
    q=discard_fixture
    data=b"\x00\x00\x00\x0cftypisom"
    q.path.unlink()
    with pytest.raises(AssetRightsDenied,match="OBJECT_UNAVAILABLE"):
        q.vault.read_indexed(q.f.anchor,TENANT,q.ref.object_id,purpose="research_analysis")
    assert q.vault.retain_indexed(q.f.anchor,q.ref,purpose="research_analysis",data=data)["status"]=="retained"
    assert q.vault.read_indexed(q.f.anchor,TENANT,q.ref.object_id,purpose="research_analysis")==data
    with pytest.raises(AssetRightsDenied,match="ID_CONFLICT"):
        q.vault.retain_indexed(q.f.anchor,q.ref.model_copy(update={"retain_until":q.ref.retain_until-timedelta(seconds=1)}),
            purpose="research_analysis",data=data)


def test_indexed_vault_expiry_during_io_withholds_bytes(discard_fixture,monkeypatch):
    from tapi_gate0 import asset_indexed_vault as module
    q=discard_fixture
    real=q.vault._read
    def expire(*args):
        result=real(*args)
        monkeypatch.setattr(module,"now_utc",lambda:q.ref.retain_until)
        return result
    monkeypatch.setattr(q.vault,"_read",expire)
    with pytest.raises(AssetRightsDenied,match="INACTIVE_OBJECT"):
        q.vault.read_indexed(q.f.anchor,TENANT,q.ref.object_id,purpose="research_analysis")


def test_indexed_vault_reservation_survives_failed_publish(discard_fixture,monkeypatch):
    q=discard_fixture
    q.path.unlink()
    data=b"\x00\x00\x00\x0cftypisom"
    def fail(*args,**kwargs):
        raise OSError("fixture publish failure")
    with monkeypatch.context() as m:
        m.setattr("tapi_gate0.asset_vault.os.link",fail)
        with pytest.raises(OSError,match="fixture publish failure"):
            q.vault.retain_indexed(q.f.anchor,q.ref,purpose="research_analysis",data=data)
    assert not list(q.path.parent.iterdir())
    with q.f.engine.connect() as db:
        row=db.execute(select(nodes).where(nodes.c.tenant_id==TENANT,nodes.c.node_id==q.ref.object_id)).mappings().one()
        assert row["state"]=="active"
        assert db.scalar(select(func.count()).select_from(domain_events).where(
            domain_events.c.tenant_id==TENANT,domain_events.c.aggregate_type=="asset_lineage",
            domain_events.c.aggregate_id==q.ref.object_id))==1
    with pytest.raises(AssetRightsDenied,match="OBJECT_UNAVAILABLE"):
        q.vault.read_indexed(q.f.anchor,TENANT,q.ref.object_id,purpose="research_analysis")
    assert q.vault.retain_indexed(q.f.anchor,q.ref,purpose="research_analysis",data=data)["status"]=="retained"


@pytest.fixture
def queue_fixture(discard_fixture):
    q=discard_fixture
    queue=AssetJobQueue(q.index,resolve_anchor=lambda ref:q.f.anchor)
    spec=JobSpec(tenant_id=TENANT,object_id=q.ref.object_id,purpose="research_analysis",
        processor="temporal",method_version="fixture-v1",configuration_sha256="a"*64)
    return SimpleNamespace(q=q,queue=queue,spec=spec)


def test_jobs_dedup_receipt_and_audit(queue_fixture):
    f=queue_fixture
    r=f.queue.enqueue(f.spec)
    assert r["state"]=="queued" and f.queue.enqueue(f.spec)==r
    result=f.queue.claim(TENANT,"worker-a")
    assert result["status"]=="claimed" and result["spec"]==f.spec
    lease=result["lease"]
    assert lease.attempt==1 and f.queue.claim(TENANT,"worker-b")["status"]=="busy"
    assert "fence" not in f.queue.status(TENANT,f.spec.job_id)
    finished=f.queue.finish(lease,"b"*64)
    assert finished["state"]=="completed" and finished["reason"]=="receipt_only"
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        f.queue.finish(lease,"b"*64)
    assert f.queue.enqueue(f.spec)["state"]=="completed"
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts))==1
        seqs=db.scalars(select(domain_events.c.seq).where(domain_events.c.aggregate_type=="asset_processing_job")).all()
        assert len(seqs)==3
        assert db.scalar(select(func.count()).select_from(outbox).where(outbox.c.seq.in_(seqs)))==3


def test_jobs_cancel_running_fences_completion_and_holds_slot(queue_fixture):
    f=queue_fixture
    f.queue.enqueue(f.spec)
    other=f.spec.model_copy(update={"method_version":"other"})
    f.queue.enqueue(other)
    lease=f.queue.claim(TENANT,"worker")["lease"]
    other_id=other.job_id if lease.job_id==f.spec.job_id else f.spec.job_id
    assert f.queue.cancel(TENANT,lease.job_id)["state"]=="cancel_requested"
    assert f.queue.claim(TENANT,"second")["status"]=="busy"
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        f.queue.finish(lease,"b"*64)
    assert f.queue.acknowledge_cancel(lease)["state"]=="canceled"
    assert f.queue.cancel(TENANT,other_id)["state"]=="canceled"
    assert f.queue.claim(TENANT,"second")["status"]=="empty"


def test_jobs_expired_leases_retry_then_exhaust(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_jobs as module
    f=queue_fixture
    clock=[now_utc()]
    monkeypatch.setattr(module,"now_utc",lambda:clock[0])
    f.queue.enqueue(f.spec)
    leases=[]
    for attempt in range(1,4):
        lease=f.queue.claim(TENANT,"worker")["lease"]
        assert lease.attempt==attempt
        if leases:
            assert lease.fence!=leases[-1].fence
            with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
                f.queue.finish(leases[-1],"b"*64)
        leases.append(lease)
        clock[0]+=timedelta(seconds=121)
        assert f.queue.status(TENANT,f.spec.job_id)["lease_expired"]
        with pytest.raises(AssetRightsDenied,match="LEASE_EXPIRED"):
            f.queue.heartbeat(lease)
        assert f.queue.claim(TENANT,"worker")["status"]=="empty"
        clock[0]+=timedelta(seconds=61)
    assert f.queue.status(TENANT,f.spec.job_id)["state"]=="failed"
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts))==3


def test_jobs_heartbeat_bounded_and_explicit_retry(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_jobs as module
    f=queue_fixture
    clock=[now_utc()]
    monkeypatch.setattr(module,"now_utc",lambda:clock[0])
    monkeypatch.setattr(module,"ATTEMPT_SECONDS",150)
    f.queue.enqueue(f.spec)
    lease=f.queue.claim(TENANT,"worker")["lease"]
    clock[0]+=timedelta(seconds=100)
    renewed=f.queue.heartbeat(lease)
    assert renewed.lease_ms==renewed.deadline_ms==lease.deadline_ms
    assert f.queue.fail(renewed,retryable=True)["state"]=="queued"
    assert f.queue.claim(TENANT,"worker")["status"]=="empty"
    clock[0]+=timedelta(seconds=16)
    fresh=f.queue.claim(TENANT,"worker")["lease"]
    assert fresh.attempt==2
    assert f.queue.fail(fresh,retryable=False)["state"]=="failed"


def test_jobs_quota_counts_attempts_not_completed_results(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_jobs as module
    f=queue_fixture
    monkeypatch.setattr(module,"MAX_DAILY_TENANT_ATTEMPTS",1)
    monkeypatch.setattr(module,"MAX_PENDING",1)
    f.queue.enqueue(f.spec)
    other=f.spec.model_copy(update={"method_version":"other"})
    with pytest.raises(AssetRightsDenied,match="QUEUE_QUOTA"):
        f.queue.enqueue(other)
    lease=f.queue.claim(TENANT,"worker")["lease"]
    f.queue.fail(lease,retryable=False)
    f.queue.enqueue(other)
    assert f.queue.claim(TENANT,"worker")["status"]=="quota"


def test_jobs_current_rights_and_reconciliation(queue_fixture):
    f=queue_fixture
    bad=f.spec.model_copy(update={"processor":"ocr"})
    with pytest.raises(AssetRightsDenied,match="SCOPE_MISMATCH"):
        f.queue.enqueue(bad)
    f.queue.enqueue(f.spec)
    lease=f.queue.claim(TENANT,"worker")["lease"]
    rv=f.q.f.state(2,revoked_asset_ids=(f.q.ref.target.asset_id,))
    f.q.f.svc.advance(f.q.f.anchor,TENANT,"instagram",rv)
    f.queue.resolve_anchor=lambda ref:f.q.f.pin(rv)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        f.queue.finish(lease,"b"*64)
    f.q.index.reconcile_signed_revocations(f.q.f.pin(rv),TENANT,"instagram")
    assert f.queue.reconcile_invalidated(TENANT)["changed"]==[f.spec.job_id]
    assert f.queue.status(TENANT,f.spec.job_id)["state"]=="cancel_requested"
    assert f.queue.acknowledge_cancel(lease)["state"]=="canceled"
    with pytest.raises(AssetRightsDenied,match="INACTIVE_ANCESTOR"):
        f.queue.enqueue(f.spec)


def test_jobs_wrong_tenant_and_clock_regression(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_jobs as module
    f=queue_fixture
    f.queue.enqueue(f.spec)
    with pytest.raises(AssetRightsDenied,match="NOT_FOUND"):
        f.queue.status("other",f.spec.job_id)
    with pytest.raises(AssetRightsDenied,match="INPUT_NOT_FOUND"):
        f.queue.enqueue(f.spec.model_copy(update={"tenant_id":"other"}))
    earlier=now_utc()-timedelta(seconds=10)
    monkeypatch.setattr(module,"now_utc",lambda:earlier)
    with pytest.raises(AssetRightsDenied,match="CLOCK_REGRESSION"):
        f.queue.claim(TENANT,"worker")


def test_jobs_revoked_queued_input_never_reserves_attempt(queue_fixture):
    f=queue_fixture
    f.queue.enqueue(f.spec)
    rv=f.q.f.state(2,revoked_grant_ids=("grant.fixture",))
    f.q.f.svc.advance(f.q.f.anchor,TENANT,"instagram",rv)
    f.queue.resolve_anchor=lambda ref:f.q.f.pin(rv)
    assert f.queue.claim(TENANT,"worker")["status"]=="rights_blocked"
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts))==0
    f.q.index.reconcile_signed_revocations(f.q.f.pin(rv),TENANT,"instagram")
    assert f.queue.reconcile_invalidated(TENANT)["changed"]==[f.spec.job_id]
    assert f.queue.status(TENANT,f.spec.job_id)["state"]=="canceled"


def test_jobs_cancel_lease_expiry_and_restart(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_jobs as module
    f=queue_fixture
    clock=[now_utc()]
    monkeypatch.setattr(module,"now_utc",lambda:clock[0])
    f.queue.enqueue(f.spec)
    lease=f.queue.claim(TENANT,"worker")["lease"]
    f.queue.cancel(TENANT,f.spec.job_id)
    restarted=AssetJobQueue(AssetLineageIndex(f.q.f.engine),resolve_anchor=lambda ref:f.q.f.anchor)
    assert restarted.claim(TENANT,"worker2")["status"]=="busy"
    clock[0]+=timedelta(seconds=121)
    assert restarted.claim(TENANT,"worker2")["status"]=="empty"
    assert restarted.status(TENANT,f.spec.job_id)["state"]=="canceled"
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        restarted.acknowledge_cancel(lease)


def test_nonempty_job_migration_downgrade_refused(tmp_path,monkeypatch):
    from sqlalchemy import insert,inspect
    from tapi_gate0.sa_store import tenants
    root=Path(__file__).resolve().parents[1]
    url="sqlite:///"+str(tmp_path/"jobs.sqlite3")
    monkeypatch.setenv("TAPI_DATABASE_URL",url)
    cfg=Config(str(root/"alembic.ini"))
    cfg.set_main_option("script_location",str(root/"migrations"))
    command.upgrade(cfg,"0015_asset_jobs")
    engine=engine_for(url)
    try:
        with engine.begin() as db:
            db.execute(insert(tenants).values(tenant_id=TENANT,name="Fixture"))
            db.execute(insert(nodes).values(tenant_id=TENANT,node_id="a"*64,kind="asset",
                purpose="research_analysis",payload="{}",state="active"))
            spec=JobSpec(tenant_id=TENANT,object_id="a"*64,purpose="research_analysis",
                processor="temporal",method_version="v1",configuration_sha256="b"*64)
            db.execute(insert(jobs).values(tenant_id=TENANT,job_id=spec.job_id,
                object_id=spec.object_id,spec=spec.model_dump_json(),state="queued",
                attempt=0,version=1,created_ms=0,updated_ms=0,available_ms=0))
        with pytest.raises(RuntimeError,match="ASSET_JOBS_DOWNGRADE_NONEMPTY"):
            command.downgrade(cfg,"0014_asset_lineage")
        assert {"asset_processing_jobs","asset_processing_attempts"}<=set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_jobs_fenced_reference_atomic_commit(queue_fixture):
    f=queue_fixture
    f.queue.enqueue(f.spec)
    lease=f.queue.claim(TENANT,"worker")["lease"]
    data=b"synthetic metadata output"
    result=f.queue.finish_reference(lease,payload=data)
    assert result["state"]=="completed" and result["reason"]=="reference_only"
    assert not result["payload_persisted"] and not result["scientific_evidence"]
    with f.q.f.engine.connect() as db:
        ref=DerivedArtifactRef.model_validate_json(db.scalar(select(nodes.c.payload).where(
            nodes.c.tenant_id==TENANT,nodes.c.node_id==result["artifact_id"])))
        assert ref.payload_sha256==sha256(data).hexdigest()==result["receipt_sha256"]
        assert ref.parent_ids==(f.spec.object_id,) and ref.run_id==f.spec.job_id
        assert ref.kind=="visual_features" and ref.method_version==f.spec.method_version
        assert ref.retain_until==f.q.ref.retain_until
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        f.queue.finish_reference(lease,payload=data)
    f.q.index.invalidate(TENANT,object_ids=[f.spec.object_id])
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(nodes.c.state).where(nodes.c.tenant_id==TENANT,
            nodes.c.node_id==ref.artifact_id))=="invalidated"


def test_jobs_reference_rolls_back_on_late_rights_denial(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_jobs as module
    f=queue_fixture
    f.queue.enqueue(f.spec)
    lease=f.queue.claim(TENANT,"worker")["lease"]
    original=module._check_rights
    calls=[]
    def fail_second(*args):
        calls.append(1)
        if len(calls)==2:
            raise AssetRightsDenied("fixture late denial")
        return original(*args)
    monkeypatch.setattr(module,"_check_rights",fail_second)
    with pytest.raises(AssetRightsDenied,match="late denial"):
        f.queue.finish_reference(lease,payload=b"fixture")
    assert f.queue.status(TENANT,f.spec.job_id)["state"]=="running"
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(nodes).where(nodes.c.kind=="derived"))==0
        assert db.scalar(select(func.count()).select_from(domain_events).where(
            domain_events.c.aggregate_type=="asset_lineage"))==1


def test_jobs_reference_denies_wrong_size_and_revoked_input(queue_fixture):
    f=queue_fixture
    f.queue.enqueue(f.spec)
    lease=f.queue.claim(TENANT,"worker")["lease"]
    with pytest.raises(AssetRightsDenied,match="OUTPUT_SIZE_INVALID"):
        f.queue.finish_reference(lease,payload=b"")
    rv=f.q.f.state(2,revoked_asset_ids=(f.q.ref.target.asset_id,))
    f.q.f.svc.advance(f.q.f.anchor,TENANT,"instagram",rv)
    f.queue.resolve_anchor=lambda ref:f.q.f.pin(rv)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        f.queue.finish_reference(lease,payload=b"fixture")
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(nodes).where(nodes.c.kind=="derived"))==0


def _probe_job(f):
    from tapi_gate0 import asset_supervisor as supervisor
    spec=f.spec.model_copy(update={"method_version":supervisor.METHOD,
        "configuration_sha256":supervisor.configuration_sha256()})
    f.queue.enqueue(spec)
    return spec,f.queue.claim(TENANT,"worker")["lease"]


def test_supervisor_real_synthetic_child_receipt(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_supervisor as supervisor
    f=queue_fixture
    monkeypatch.setenv("TAPI_SUPERVISOR_TEST_SECRET","fixture-not-forwarded")
    original=supervisor.subprocess.Popen
    seen=[]
    def start(*args,**kwargs):
        assert "TAPI_SUPERVISOR_TEST_SECRET" not in kwargs["env"]
        assert "TAPI_DATABASE_URL" not in kwargs["env"]
        assert kwargs["shell"] is False
        process=original(*args,**kwargs)
        seen.append(process)
        return process
    monkeypatch.setattr(supervisor.subprocess,"Popen",start)
    spec,lease=_probe_job(f)
    result=supervisor.run_fixture_probe(f.queue,f.q.vault,lease)
    assert result["state"]=="completed" and result["synthetic_probe"]
    assert result["receipt_sha256"]==sha256(supervisor.EXPECTED).hexdigest()
    assert not result["scientific_evidence"] and not result["payload_persisted"]
    assert len(seen)==1 and seen[0].poll()==0
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(nodes).where(nodes.c.kind=="derived"))==0


def test_supervisor_rejects_nonprobe_before_read_or_spawn(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_supervisor as supervisor
    f=queue_fixture
    f.queue.enqueue(f.spec)
    lease=f.queue.claim(TENANT,"worker")["lease"]
    def unexpected(*args,**kwargs):
        pytest.fail("must not read or spawn")
    monkeypatch.setattr(f.q.vault,"read_indexed",unexpected)
    monkeypatch.setattr(supervisor.subprocess,"Popen",unexpected)
    with pytest.raises(AssetRightsDenied,match="FIXTURE_ONLY"):
        supervisor.run_fixture_probe(f.queue,f.q.vault,lease)


def test_supervisor_timeout_kills_child_and_withholds_receipt(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_supervisor as supervisor
    f=queue_fixture
    monkeypatch.setattr(supervisor,"_CHILD","import time; time.sleep(30)")
    monkeypatch.setattr(supervisor,"TIMEOUT_SECONDS",0.5)
    original=supervisor.subprocess.Popen
    seen=[]
    def start(*args,**kwargs):
        process=original(*args,**kwargs);seen.append(process);return process
    monkeypatch.setattr(supervisor.subprocess,"Popen",start)
    spec,lease=_probe_job(f)
    with pytest.raises(AssetRightsDenied,match="TIMEOUT"):
        supervisor.run_fixture_probe(f.queue,f.q.vault,lease)
    assert len(seen)==1 and seen[0].poll() is not None
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None


def test_supervisor_cancel_during_child_kills_and_fences(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_supervisor as supervisor
    f=queue_fixture
    monkeypatch.setattr(supervisor,"_CHILD","import time; time.sleep(30)")
    original=supervisor.subprocess.Popen
    seen=[]
    spec,lease=_probe_job(f)
    def start(*args,**kwargs):
        process=original(*args,**kwargs);seen.append(process)
        f.queue.cancel(TENANT,spec.job_id)
        return process
    monkeypatch.setattr(supervisor.subprocess,"Popen",start)
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        supervisor.run_fixture_probe(f.queue,f.q.vault,lease)
    assert len(seen)==1 and seen[0].poll() is not None
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None
    assert f.queue.acknowledge_cancel(lease)["state"]=="canceled"


def test_supervisor_revocation_during_child_kills_and_withholds_receipt(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_supervisor as supervisor
    f=queue_fixture
    monkeypatch.setattr(supervisor,"_CHILD","import time; time.sleep(30)")
    original=supervisor.subprocess.Popen
    seen=[]
    spec,lease=_probe_job(f)
    rv=f.q.f.state(2,revoked_asset_ids=(f.q.ref.target.asset_id,))
    def start(*args,**kwargs):
        process=original(*args,**kwargs);seen.append(process)
        f.q.f.svc.advance(f.q.f.anchor,TENANT,"instagram",rv)
        f.queue.resolve_anchor=lambda ref:f.q.f.pin(rv)
        return process
    monkeypatch.setattr(supervisor.subprocess,"Popen",start)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        supervisor.run_fixture_probe(f.queue,f.q.vault,lease)
    assert len(seen)==1 and seen[0].poll() is not None
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None
    f.q.index.reconcile_signed_revocations(f.q.f.pin(rv),TENANT,"instagram")
    assert f.queue.reconcile_invalidated(TENANT)["changed"]==[spec.job_id]
    assert f.queue.acknowledge_cancel(lease)["state"]=="canceled"


def _payload_job(f):
    f.queue.enqueue(f.spec)
    return f.queue.claim(TENANT,"worker")["lease"]


def test_payload_requires_explicit_derived_retention(queue_fixture):
    f=queue_fixture
    lease=_payload_job(f)
    store=DerivedPayloadStore(f.queue,b"d"*32)
    with pytest.raises(AssetRightsDenied,match="SCOPE_MISMATCH"):
        store.finish(lease,payload=b"fixture")
    assert f.queue.status(TENANT,f.spec.job_id)["state"]=="running"
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==0


@pytest.mark.parametrize("discard_fixture",[("retain",)],indirect=True)
def test_payload_retention_does_not_authorize_read(queue_fixture):
    f=queue_fixture
    store=DerivedPayloadStore(f.queue,b"d"*32)
    result=store.finish(_payload_job(f),payload=b"fixture")
    assert result["payload_persisted"]
    with pytest.raises(AssetRightsDenied,match="SCOPE_MISMATCH"):
        store.read_for_processing(TENANT,result["artifact_id"],purpose="research_analysis")


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
def test_payload_atomic_encryption_read_and_binding(queue_fixture):
    f=queue_fixture
    store=DerivedPayloadStore(f.queue,b"d"*32)
    data=b"private synthetic derivative"
    lease=_payload_job(f)
    result=store.finish(lease,payload=data)
    ident=result["artifact_id"]
    assert result["state"]=="completed" and result["reason"]=="encrypted_payload"
    assert result["receipt_sha256"]==sha256(data).hexdigest()
    assert not result["scientific_evidence"] and not result["media_enabled"]
    with f.q.f.engine.connect() as db:
        envelope=db.scalar(select(payloads.c.envelope))
        ref=DerivedArtifactRef.model_validate_json(db.scalar(select(nodes.c.payload).where(nodes.c.node_id==ident)))
        assert len(envelope)==len(data)+28 and data not in envelope
        assert ref.parent_ids==(f.spec.object_id,) and ref.payload_sha256==result["receipt_sha256"]
    assert store.read_for_processing(TENANT,ident,purpose="research_analysis")==data
    with pytest.raises(AssetRightsDenied,match="KEY_MISMATCH"):
        DerivedPayloadStore(f.queue,b"x"*32).read_for_processing(TENANT,ident,purpose="research_analysis")
    with pytest.raises(AssetRightsDenied,match="PURPOSE_MISMATCH"):
        store.read_for_processing(TENANT,ident,purpose="studio_creation")
    with pytest.raises(AssetRightsDenied,match="UNKNOWN_ARTIFACT"):
        store.read_for_processing("other",ident,purpose="research_analysis")
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        store.finish(lease,payload=data)
    with f.q.f.engine.begin() as db:
        db.execute(update(payloads).values(envelope=envelope[:-1]+bytes([envelope[-1]^1])))
    with pytest.raises(AssetRightsDenied,match="AUTHENTICATION_FAILED"):
        store.read_for_processing(TENANT,ident,purpose="research_analysis")


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
def test_payload_late_denial_rolls_back_all_records(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_derived_payloads as module
    f=queue_fixture
    store=DerivedPayloadStore(f.queue,b"d"*32)
    lease=_payload_job(f)
    original=module._extra
    calls=[]
    def deny(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:
            raise AssetRightsDenied("fixture late denial")
        return original(*args,**kwargs)
    monkeypatch.setattr(module,"_extra",deny)
    with pytest.raises(AssetRightsDenied,match="late denial"):
        store.finish(lease,payload=b"fixture")
    assert f.queue.status(TENANT,f.spec.job_id)["state"]=="running"
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==0
        assert db.scalar(select(func.count()).select_from(nodes).where(nodes.c.kind=="derived"))==0
        assert db.scalar(select(func.count()).select_from(domain_events).where(domain_events.c.aggregate_type=="asset_lineage"))==1


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
def test_payload_revocation_and_purge_idempotent(queue_fixture):
    f=queue_fixture
    store=DerivedPayloadStore(f.queue,b"d"*32)
    result=store.finish(_payload_job(f),payload=b"fixture")
    ident=result["artifact_id"]
    with pytest.raises(AssetRightsDenied,match="TOMBSTONE_REQUIRED"):
        store.purge_invalidated(TENANT,ident)
    rv=f.q.f.state(2,revoked_asset_ids=(f.q.ref.target.asset_id,))
    f.q.f.svc.advance(f.q.f.anchor,TENANT,"instagram",rv)
    f.queue.resolve_anchor=lambda ref:f.q.f.pin(rv)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        store.read_for_processing(TENANT,ident,purpose="research_analysis")
    f.q.index.reconcile_signed_revocations(f.q.f.pin(rv),TENANT,"instagram")
    with pytest.raises(AssetRightsDenied,match="INACTIVE_ANCESTOR"):
        store.read_for_processing(TENANT,ident,purpose="research_analysis")
    assert store.purge_invalidated(TENANT,ident)=={"status":"PURGED","secure_erasure_verified":False}
    assert store.purge_invalidated(TENANT,ident)["status"]=="ALREADY_PURGED"
    with f.q.f.engine.connect() as db:
        row=db.execute(select(payloads)).mappings().one()
        assert row["envelope"] is None and row["purged_at"]
        seqs=db.scalars(select(domain_events.c.seq).where(domain_events.c.aggregate_type=="asset_derived_payload")).all()
        assert len(seqs)==1
        assert db.scalar(select(func.count()).select_from(outbox).where(outbox.c.seq.in_(seqs)))==1
        assert db.scalar(select(nodes.c.state).where(nodes.c.node_id==ident))=="invalidated"


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
def test_payload_quota_and_invalid_size(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_derived_payloads as module
    f=queue_fixture
    store=DerivedPayloadStore(f.queue,b"d"*32)
    lease=_payload_job(f)
    with pytest.raises(AssetRightsDenied,match="SIZE_INVALID"):
        store.finish(lease,payload=b"")
    monkeypatch.setattr(module,"MAX_TENANT_BYTES",30)
    with pytest.raises(AssetRightsDenied,match="STORAGE_QUOTA"):
        store.finish(lease,payload=b"fixture")
    assert f.queue.status(TENANT,f.spec.job_id)["state"]=="running"
    monkeypatch.setattr(module,"MAX_TENANT_BYTES",100)
    assert store.finish(lease,payload=b"fixture")["payload_persisted"]


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
def test_payload_reference_only_is_not_readable(queue_fixture):
    f=queue_fixture
    store=DerivedPayloadStore(f.queue,b"d"*32)
    result=f.queue.finish_reference(_payload_job(f),payload=b"fixture")
    with pytest.raises(AssetRightsDenied,match="UNAVAILABLE"):
        store.read_for_processing(TENANT,result["artifact_id"],purpose="research_analysis")


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
def test_payload_ciphertext_cannot_be_substituted_between_jobs(queue_fixture):
    f=queue_fixture
    store=DerivedPayloadStore(f.queue,b"d"*32)
    first=store.finish(_payload_job(f),payload=b"same synthetic bytes")
    second_spec=f.spec.model_copy(update={"method_version":"fixture-v2"})
    f.queue.enqueue(second_spec)
    second=store.finish(f.queue.claim(TENANT,"worker")["lease"],payload=b"same synthetic bytes")
    assert first["artifact_id"]!=second["artifact_id"]
    with f.q.f.engine.begin() as db:
        envelope=db.scalar(select(payloads.c.envelope).where(payloads.c.artifact_id==first["artifact_id"]))
        db.execute(update(payloads).where(payloads.c.artifact_id==second["artifact_id"]).values(envelope=envelope))
    with pytest.raises(AssetRightsDenied,match="AUTHENTICATION_FAILED"):
        store.read_for_processing(TENANT,second["artifact_id"],purpose="research_analysis")
    assert store.read_for_processing(TENANT,first["artifact_id"],purpose="research_analysis")==b"same synthetic bytes"


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
def test_payload_nonempty_downgrade_refused_even_after_purge(queue_fixture,monkeypatch):
    # The disposable registry fixture already has the current metadata schema.
    # Stamp its revision only to exercise the actual downgrade guard.
    f=queue_fixture
    store=DerivedPayloadStore(f.queue,b"d"*32)
    result=store.finish(_payload_job(f),payload=b"fixture")
    f.q.index.invalidate(TENANT,artifact_ids=[result["artifact_id"]])
    store.purge_invalidated(TENANT,result["artifact_id"])
    root=Path(__file__).resolve().parents[1]
    url=f.q.f.engine.url.render_as_string(hide_password=False)
    monkeypatch.setenv("TAPI_DATABASE_URL",url)
    cfg=Config(str(root/"alembic.ini"))
    cfg.set_main_option("script_location",str(root/"migrations"))
    command.stamp(cfg,"0016_asset_derived_payloads")
    with pytest.raises(RuntimeError,match="ASSET_PAYLOAD_DOWNGRADE_NONEMPTY"):
        command.downgrade(cfg,"0015_asset_jobs")
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==1


_WINDOWS_JOB = pytest.mark.skipif(sys.platform!="win32" or struct.calcsize("P")!=8,
    reason="requires native Windows x64 Job Objects")


def _windows_probe_job(f):
    from tapi_gate0 import asset_supervisor as s
    spec=f.spec.model_copy(update={"method_version":s.WINDOWS_METHOD,
        "configuration_sha256":s.windows_configuration_sha256()})
    f.queue.enqueue(spec)
    return spec,f.queue.claim(TENANT,"worker")["lease"]


@_WINDOWS_JOB
def test_windows_supervisor_fenced_receipt(queue_fixture):
    from tapi_gate0 import asset_supervisor as s
    f=queue_fixture
    spec,lease=_windows_probe_job(f)
    result=s.run_fixture_probe_windows(f.queue,f.q.vault,lease)
    assert result["state"]=="completed" and result["supervisor"]=="windows_job_v2"
    assert result["kernel_job_limits_verified"] and result["tree_empty_verified"]
    assert result["receipt_sha256"]==sha256(s.EXPECTED).hexdigest()
    assert not result["payload_persisted"] and not result["scientific_evidence"]
    assert not result["media_enabled"] and result["model_calls"]==0


@_WINDOWS_JOB
def test_windows_supervisor_cancel_before_input(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_supervisor as s
    f=queue_fixture
    spec,lease=_windows_probe_job(f)
    original=s.windows.subprocess.Popen
    seen=[]
    def spawn(*a,**k):
        p=original(*a,**k);seen.append(p)
        f.queue.cancel(TENANT,spec.job_id)
        return p
    monkeypatch.setattr(s.windows.subprocess,"Popen",spawn)
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        s.run_fixture_probe_windows(f.queue,f.q.vault,lease)
    assert len(seen)==1 and seen[0].poll() is not None
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None
    assert f.queue.acknowledge_cancel(lease)["state"]=="canceled"


@_WINDOWS_JOB
def test_windows_supervisor_revocation_before_input(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_supervisor as s
    f=queue_fixture
    spec,lease=_windows_probe_job(f)
    rv=f.q.f.state(2,revoked_asset_ids=(f.q.ref.target.asset_id,))
    original=s.windows.subprocess.Popen
    seen=[]
    def spawn(*a,**k):
        p=original(*a,**k);seen.append(p)
        f.q.f.svc.advance(f.q.f.anchor,TENANT,"instagram",rv)
        f.queue.resolve_anchor=lambda ref:f.q.f.pin(rv)
        return p
    monkeypatch.setattr(s.windows.subprocess,"Popen",spawn)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        s.run_fixture_probe_windows(f.queue,f.q.vault,lease)
    assert len(seen)==1 and seen[0].poll() is not None
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None
    f.q.index.reconcile_signed_revocations(f.q.f.pin(rv),TENANT,"instagram")
    assert f.queue.reconcile_invalidated(TENANT)["changed"]==[spec.job_id]
    assert f.queue.acknowledge_cancel(lease)["state"]=="canceled"


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("retain","process","all_processors")],indirect=True)
@pytest.mark.parametrize("processor",["asr_vad","ocr","temporal","vlm"])
def test_typed_fixture_windows_encrypted_abstention(queue_fixture,processor):
    from tapi_gate0 import asset_processor_fixture as a
    from tapi_gate0.asset_processor_results import decode,validate_binding
    f=queue_fixture
    spec=f.spec.model_copy(update={"processor":processor,"method_version":a.METHOD,
        "configuration_sha256":a.configuration_sha256(processor)})
    f.queue.enqueue(spec)
    lease=f.queue.claim(TENANT,"worker")["lease"]
    store=DerivedPayloadStore(f.queue,b"d"*32)
    receipt=a.run_typed_fixture_windows(f.queue,f.q.vault,store,lease)
    assert receipt["state"]=="completed" and receipt["payload_persisted"]
    assert receipt["result_state"]=="abstained" and receipt["model_calls"]==0
    assert not receipt["scientific_evidence"] and not receipt["canonical_rubric"]
    assert not receipt["media_enabled"]
    payload=store.read_for_processing(TENANT,receipt["artifact_id"],purpose=spec.purpose)
    result=decode(payload)
    assert validate_binding(result,spec=spec,ref=f.q.ref,lease=lease)==result
    assert result.result.processor==processor and result.result.reason=="fixture_header_only"
    with f.q.f.engine.connect() as db:
        envelope=db.scalar(select(payloads.c.envelope))
        assert payload not in envelope and len(envelope)==len(payload)+28
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        a.run_typed_fixture_windows(f.queue,f.q.vault,store,lease)


@_WINDOWS_JOB
def test_typed_fixture_missing_derived_retain_withholds_payload(queue_fixture):
    from tapi_gate0 import asset_processor_fixture as a
    f=queue_fixture
    spec=f.spec.model_copy(update={"method_version":a.METHOD,
        "configuration_sha256":a.configuration_sha256("temporal")})
    f.queue.enqueue(spec)
    lease=f.queue.claim(TENANT,"worker")["lease"]
    with pytest.raises(AssetRightsDenied,match="SCOPE_MISMATCH"):
        a.run_typed_fixture_windows(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease)
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==0


@_WINDOWS_JOB
def test_typed_fixture_rejects_configuration_before_spawn(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_processor_fixture as a
    f=queue_fixture
    spec=f.spec.model_copy(update={"method_version":a.METHOD,
        "configuration_sha256":a.configuration_sha256("ocr")})
    f.queue.enqueue(spec)
    lease=f.queue.claim(TENANT,"worker")["lease"]
    def unexpected(*args,**kwargs):
        pytest.fail("must not spawn for mismatched config")
    monkeypatch.setattr(a.windows,"_run_trusted_fixture",unexpected)
    with pytest.raises(AssetRightsDenied,match="FIXTURE_ONLY"):
        a.run_typed_fixture_windows(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease)


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
def test_typed_fixture_late_cancel_withholds_payload(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_processor_fixture as a
    f=queue_fixture
    spec=f.spec.model_copy(update={"method_version":a.METHOD,
        "configuration_sha256":a.configuration_sha256("temporal")})
    f.queue.enqueue(spec)
    lease=f.queue.claim(TENANT,"worker")["lease"]
    original=a.windows._run_trusted_fixture
    def late(*args,**kwargs):
        result=original(*args,**kwargs)
        f.queue.cancel(TENANT,spec.job_id)
        return result
    monkeypatch.setattr(a.windows,"_run_trusted_fixture",late)
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        a.run_typed_fixture_windows(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease)
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==0
    assert f.queue.acknowledge_cancel(lease)["state"]=="canceled"


def _temporal_job(f,case):
    from tapi_gate0 import asset_temporal_fixture as a
    config,_=a.plan(case)
    spec=f.spec.model_copy(update={"method_version":a.METHOD,
        "configuration_sha256":config["configuration_sha256"]})
    f.queue.enqueue(spec)
    return spec,f.queue.claim(TENANT,"worker")["lease"]


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture,case,times",[
    (("retain","process","temporal_static"),"static",[]),
    (("retain","process","temporal_one"),"one",[2000]),
    (("retain","process","temporal_two"),"two",[1000,2000]),
],indirect=["discard_fixture"])
def test_real_temporal_fixture_encrypted_measurement(queue_fixture,case,times):
    from tapi_gate0 import asset_temporal_fixture as a
    from tapi_gate0.asset_processor_results import decode,validate_binding
    f=queue_fixture
    spec,lease=_temporal_job(f,case)
    store=DerivedPayloadStore(f.queue,b"d"*32)
    receipt=a.run_temporal_fixture_windows(f.queue,f.q.vault,store,lease)
    assert receipt["state"]=="completed" and receipt["payload_persisted"]
    assert receipt["result_state"]=="observed" and receipt["fixture_case"]==case
    assert receipt["kernel_job_limits_verified"] and receipt["tree_empty_verified"]
    assert receipt["model_calls"]==0 and not receipt["media_enabled"]
    assert not receipt["scientific_evidence"] and not receipt["canonical_rubric"]
    payload=store.read_for_processing(TENANT,receipt["artifact_id"],purpose=spec.purpose)
    result=decode(payload)
    assert validate_binding(result,spec=spec,ref=f.q.ref,lease=lease)==result
    assert result.origin=="adapter_candidate" and result.result.samples==12
    assert [x.current.time_ms for x in result.result.candidates]==times
    assert receipt["receipt_sha256"]==sha256(payload).hexdigest()
    with f.q.f.engine.connect() as db:
        envelope=db.scalar(select(payloads.c.envelope))
        assert len(envelope)==len(payload)+28 and payload not in envelope


@_WINDOWS_JOB
def test_real_temporal_fixture_rejects_header_before_spawn(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_temporal_fixture as a
    f=queue_fixture
    spec,lease=_temporal_job(f,"static")
    monkeypatch.setattr(a.windows,"_run_exact_fixture",lambda *x,**y:pytest.fail("must not spawn"))
    with pytest.raises(AssetRightsDenied,match="TEMPORAL_FIXTURE_ONLY"):
        a.run_temporal_fixture_windows(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease)


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("temporal_one",)],indirect=True)
def test_real_temporal_fixture_requires_derived_retention(queue_fixture):
    from tapi_gate0 import asset_temporal_fixture as a
    f=queue_fixture
    spec,lease=_temporal_job(f,"one")
    with pytest.raises(AssetRightsDenied,match="SCOPE_MISMATCH"):
        a.run_temporal_fixture_windows(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease)
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==0


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("retain","process","temporal_two")],indirect=True)
def test_real_temporal_fixture_late_cancel_no_receipt(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_temporal_fixture as a
    f=queue_fixture
    spec,lease=_temporal_job(f,"two")
    original=a.windows._run_exact_fixture
    def late(*args,**kwargs):
        output=original(*args,**kwargs)
        f.queue.cancel(TENANT,spec.job_id)
        return output
    monkeypatch.setattr(a.windows,"_run_exact_fixture",late)
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        a.run_temporal_fixture_windows(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease)
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==0
    assert f.queue.acknowledge_cancel(lease)["state"]=="canceled"
