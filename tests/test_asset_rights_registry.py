from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update, func
from alembic import command
from alembic.config import Config

from tapi_gate0.asset_rights import (AssetIdentity, Permission, GrantClaims, SignedGrant,
    RevocationClaims, SignedRevocations, TrustedAuthority, AssetRightsDenied, signed_bytes)
from tapi_gate0.asset_rights_registry import AssetRightsRegistry, authorities, revocations, grants
from tapi_gate0.asset_lineage_index import AssetLineageIndex, nodes
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


@pytest.mark.parametrize('lineage',[False,True])
def test_migration_rehearsal_preserves_disposable_backup(tmp_path,monkeypatch,lineage):
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
    command.upgrade(config,drill.NEW if lineage else drill.OLD)
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
    result=drill.rehearsal(tmp_path,db.name,digest,TENANT,lineage=lineage)
    assert result["status"]=="A02_MIGRATION_REHEARSAL_VERIFIED"
    assert result["backup_unchanged"] and result["empty_downgrade_verified"]
    if lineage:
        assert result["to_revision"]=="0014_asset_lineage"
        assert result["new_empty_tables"]==["asset_lineage_nodes"]
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


def test_vault_with_real_signed_registry_and_revocation(registry,tmp_path):
    from tapi_gate0.asset_vault import AssetVault
    f=registry
    data=b"\x00\x00\x00\x0cftypisom"
    target=f.target.model_copy(update={"sha256":sha256(data).hexdigest()})
    retention=Permission(operation="retain",purpose="research_analysis",field="video")
    f.svc.provision(f.anchor,TENANT,"instagram",f.rv)
    f.svc.register_grant(f.anchor,f.grant(target=target,permissions=(retention,PERMISSION)),
        verified_approval_digest="b"*64)
    root=tmp_path/"vault"
    root.mkdir(mode=0o700)
    vault=AssetVault(root,b"v"*32,f.svc)
    kwargs={"mime":"video/mp4","purpose":"research_analysis"}
    assert vault.retain(f.anchor,"grant.fixture",target,data=data,**kwargs)["status"]=="retained"
    assert vault.read_for_processing(f.anchor,"grant.fixture",target,**kwargs)==data
    revoked=f.state(2,revoked_asset_ids=(target.asset_id,))
    f.svc.advance(f.anchor,TENANT,"instagram",revoked)
    with pytest.raises(AssetRightsDenied,match="ROLLBACK"):
        vault.read_for_processing(f.anchor,"grant.fixture",target,**kwargs)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        vault.read_for_processing(f.pin(revoked),"grant.fixture",target,**kwargs)
    assert len(list(root.iterdir()))==1  # Physical purge remains separate.


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
def discard_fixture(registry,tmp_path):
    from tapi_gate0.asset_vault import AssetVault
    from tapi_gate0.asset_discard import discard_invalidated
    f=registry
    data=b"\x00\x00\x00\x0cftypisom"
    target=f.target.model_copy(update={"sha256":sha256(data).hexdigest()})
    retention=Permission(operation="retain",purpose="research_analysis",field="video")
    f.svc.provision(f.anchor,TENANT,"instagram",f.rv)
    f.svc.register_grant(f.anchor,f.grant(target=target,permissions=(retention,PERMISSION)),
        verified_approval_digest="b"*64)
    root=tmp_path/"discard-vault";root.mkdir(mode=0o700)
    vault=AssetVault(root,b"v"*32,f.svc)
    vault.retain(f.anchor,"grant.fixture",target,mime="video/mp4",purpose="research_analysis",data=data)
    now=now_utc()
    ref=RetainedAssetRef(target=target,issuer_id=f.anchor.issuer_id,
        issuer_key_sha256=sha256(f.anchor.public_key).hexdigest(),grant_id="grant.fixture",
        mime="video/mp4",object_id=expected_object_id(f.anchor,"grant.fixture",target,"video/mp4"),
        byte_count=len(data),retained_at=now,retain_until=now+timedelta(minutes=20))
    index=AssetLineageIndex(f.engine)
    index.register_retained(f.anchor,ref)
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
