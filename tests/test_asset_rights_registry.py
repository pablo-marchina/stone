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
from tapi_gate0.agent_graph_checkpoints import AgentCheckpointDenied, agent_graph_events, agent_graph_runs
from tapi_gate0.agent_graph_protected_av_dec008 import (
    ProtectedAVReviewPlan, ProtectedAVReviewDenied,
    execute_protected_av_review_step, execute_protected_av_review,
)

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
    ocr_cases=[x.removeprefix("ocr_") for x in requested if x.startswith("ocr_")]
    media_kind="video"
    mime="video/mp4"
    output_field="visual_features"
    if ocr_cases:
        from tapi_gate0.asset_ocr_fixture import fixture
        assert len(ocr_cases)==1 and not temporal_cases
        data,_=fixture(ocr_cases[0])
        media_kind,mime,output_field="image","image/png","ocr"
    asr_cases=[x.removeprefix("asr_") for x in requested if x.startswith("asr_")]
    if asr_cases:
        import os
        if not os.environ.get("TAPI_ASR_TEST_MODEL_DIR"):
            pytest.skip("explicit TAPI_ASR_TEST_MODEL_DIR required")
        from tapi_gate0.asset_asr_fixture import fixture
        assert len(asr_cases)==1 and not temporal_cases and not ocr_cases
        data,_=fixture(asr_cases[0])
        media_kind,mime,output_field="audio","audio/wav","transcript"
    vlm_cases=[x.removeprefix("vlm_") for x in requested if x.startswith("vlm_")]
    if vlm_cases:
        import os
        if not os.environ.get("TAPI_VLM_TEST_MODEL_DIR") or not os.environ.get("TAPI_VLM_TEST_SERVER_EXE"):
            pytest.skip("explicit VLM model and server opt-ins required")
        from tapi_gate0.asset_vlm_fixture import fixture
        assert len(vlm_cases)==1 and not temporal_cases and not ocr_cases and not asr_cases
        data,_=fixture(vlm_cases[0])
        media_kind,mime,output_field="image","image/png","visual_features"
    shared_cases=[x.removeprefix("shared_av_") for x in requested if x.startswith("shared_av_")]
    if shared_cases:
        from tapi_gate0.asset_shared_av_fixture import prepare
        assert len(shared_cases)==1 and not (temporal_cases or ocr_cases or asr_cases or vlm_cases)
        data=prepare(shared_cases[0]).data
        media_kind,mime,output_field="video","video/mp4","visual_features"
    target=f.target.model_copy(update={"sha256":sha256(data).hexdigest(),"media_kind":media_kind})
    retention=Permission(operation="retain",purpose="research_analysis",field=media_kind)
    processing=Permission(operation="process",purpose="research_analysis",field=media_kind)
    f.svc.provision(f.anchor,TENANT,"instagram",f.rv)
    extra=tuple(Permission(operation=op,purpose="research_analysis",field=output_field)
        for op in requested if op not in ("all_processors","bundle_visual","bundle_rubric","shared_modalities","shared_audio_only","shared_image_only") and not op.startswith(("temporal_","ocr_","asr_","vlm_","shared_av_")))
    for field in ("audio","image"):
        if "shared_modalities" in requested or "shared_"+field+"_only" in requested:
            extra+=(Permission(operation="process",purpose="research_analysis",field=field),)
    if "bundle_rubric" in requested:
        extra+=(Permission(operation="derive",purpose="research_analysis",field="rubric_evidence"),)
    if "bundle_visual" in requested:
        assert ocr_cases
        extra+=tuple(Permission(operation=op,purpose="research_analysis",field="visual_features")
            for op in ("derive","retain","process"))
    if "all_processors" in requested:
        assert not ocr_cases
        extra+=tuple(Permission(operation=op,purpose="research_analysis",field=field)
            for field in ("transcript","ocr") for op in ("derive","retain","process"))
    f.svc.register_grant(f.anchor,f.grant(target=target,permissions=(retention,processing,Permission(operation="derive",purpose="research_analysis",field=output_field),*extra)),
        verified_approval_digest="b"*64)
    root=tmp_path/"discard-vault";root.mkdir(mode=0o700)
    now=now_utc()
    ref=RetainedAssetRef(target=target,issuer_id=f.anchor.issuer_id,
        issuer_key_sha256=sha256(f.anchor.public_key).hexdigest(),grant_id="grant.fixture",
        mime=mime,object_id=expected_object_id(f.anchor,"grant.fixture",target,mime),
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


def _ocr_job(f,case):
    import os
    from tapi_gate0 import asset_ocr_fixture as a
    directory=os.environ.get("TAPI_OCR_TEST_TESSDATA")
    if not directory:
        pytest.skip("explicit TAPI_OCR_TEST_TESSDATA required")
    directory=Path(directory)
    config,_=a.plan(case,directory)
    spec=f.spec.model_copy(update={"processor":"ocr","method_version":a.METHOD,
        "configuration_sha256":config["configuration_sha256"]})
    f.queue.enqueue(spec)
    return spec,f.queue.claim(TENANT,"worker")["lease"],directory


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture,case,words",[
    (("retain","process","ocr_sales"),"sales",("Organize","suas","vendas")),
    (("retain","process","ocr_cta"),"cta",("Salve","para","revisar","depois")),
    (("retain","process","ocr_blank"),"blank",()),
],indirect=["discard_fixture"])
def test_real_ocr_fixture_encrypted_result(queue_fixture,case,words):
    from tapi_gate0 import asset_ocr_fixture as a
    from tapi_gate0.asset_processor_results import decode,validate_binding
    f=queue_fixture
    spec,lease,directory=_ocr_job(f,case)
    store=DerivedPayloadStore(f.queue,b"d"*32)
    receipt=a.run_ocr_fixture_windows(f.queue,f.q.vault,store,lease,tessdata_dir=directory)
    assert receipt["state"]=="completed" and receipt["payload_persisted"]
    assert receipt["fixture_case"]==case and receipt["model_calls"]==1
    assert receipt["kernel_job_limits_verified"] and receipt["tree_empty_verified"]
    assert not receipt["media_enabled"] and not receipt["scientific_evidence"]
    assert not receipt["canonical_rubric"]
    payload=store.read_for_processing(TENANT,receipt["artifact_id"],purpose=spec.purpose)
    result=decode(payload)
    assert validate_binding(result,spec=spec,ref=f.q.ref,lease=lease)==result
    assert result.origin=="adapter_candidate"
    if words:
        assert result.result.state=="observed"
        assert tuple(w.text for w in result.result.words)==words
        assert result.result.frame.frame_sha256==f.q.ref.target.sha256
    else:
        assert result.result.state=="abstained" and result.result.reason=="no_observable_signal"
    assert receipt["receipt_sha256"]==sha256(payload).hexdigest()
    with f.q.f.engine.connect() as db:
        envelope=db.scalar(select(payloads.c.envelope))
        assert len(envelope)==len(payload)+28 and payload not in envelope


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("ocr_sales",)],indirect=True)
def test_real_ocr_fixture_requires_derived_retention(queue_fixture):
    from tapi_gate0 import asset_ocr_fixture as a
    f=queue_fixture
    spec,lease,directory=_ocr_job(f,"sales")
    with pytest.raises(AssetRightsDenied,match="SCOPE_MISMATCH"):
        a.run_ocr_fixture_windows(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease,tessdata_dir=directory)
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==0


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("retain","process","ocr_sales")],indirect=True)
def test_real_ocr_fixture_config_mismatch_before_spawn(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_ocr_fixture as a
    f=queue_fixture
    spec,lease,directory=_ocr_job(f,"cta")
    monkeypatch.setattr(a.windows,"_run_bounded_fixture",lambda *x,**y:pytest.fail("must not spawn"))
    with pytest.raises(AssetRightsDenied,match="OCR_FIXTURE_CONFIG"):
        a.run_ocr_fixture_windows(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease,tessdata_dir=directory)


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("retain","process","ocr_cta")],indirect=True)
def test_real_ocr_fixture_late_cancel_no_payload(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_ocr_fixture as a
    f=queue_fixture
    spec,lease,directory=_ocr_job(f,"cta")
    original=a.windows._run_bounded_fixture
    def late(*args,**kwargs):
        output=original(*args,**kwargs)
        f.queue.cancel(TENANT,spec.job_id)
        return output
    monkeypatch.setattr(a.windows,"_run_bounded_fixture",late)
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        a.run_ocr_fixture_windows(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease,tessdata_dir=directory)
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==0
    assert f.queue.acknowledge_cancel(lease)["state"]=="canceled"


def _asr_job(f,case):
    import os
    from tapi_gate0 import asset_asr_fixture as a
    directory=os.environ.get("TAPI_ASR_TEST_MODEL_DIR")
    if not directory:
        pytest.skip("explicit TAPI_ASR_TEST_MODEL_DIR required")
    directory=Path(directory)
    config,_=a.plan(case,directory)
    spec=f.spec.model_copy(update={"processor":"asr_vad","method_version":a.METHOD,
        "configuration_sha256":config["configuration_sha256"]})
    f.queue.enqueue(spec)
    return spec,f.queue.claim(TENANT,"worker")["lease"],directory


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture,case",[
    (("retain","process","asr_inventory"),"inventory"),
    (("retain","process","asr_silence"),"silence"),
    (("retain","process","asr_tone"),"tone"),
],indirect=["discard_fixture"])
def test_real_asr_fixture_encrypted_result(queue_fixture,case):
    import json
    from tapi_gate0 import asset_asr_fixture as a
    from tapi_gate0.asset_processor_results import decode,validate_binding
    f=queue_fixture
    spec,lease,directory=_asr_job(f,case)
    store=DerivedPayloadStore(f.queue,b"d"*32)
    receipt=a.run_asr_fixture_windows(f.queue,f.q.vault,store,lease,case=case,model_dir=directory)
    assert receipt["state"]=="completed" and receipt["payload_persisted"]
    assert receipt["fixture_case"]==case and receipt["kernel_job_limits_verified"] and receipt["tree_empty_verified"]
    assert not receipt["media_enabled"] and not receipt["scientific_evidence"] and not receipt["canonical_rubric"]
    payload=store.read_for_processing(TENANT,receipt["artifact_id"],purpose=spec.purpose)
    result=decode(payload)
    assert validate_binding(result,spec=spec,ref=f.q.ref,lease=lease)==result
    assert result.origin=="adapter_candidate"
    quality=receipt["quality"]
    if case=="inventory":
        assert result.result.state=="observed" and quality["asr_calls"]==1 and quality["vad_calls"]==1
        assert quality["wer"]<=0.50 and quality["vad_iou"]>=0.60
    else:
        assert result.result.state=="abstained" and quality["asr_calls"]==0
        assert quality["vad_calls"]==int(case=="tone")
    resources=receipt["resources"]
    assert 0<resources["peak_job_commit_bytes"]<=a.LIMITS.memory_mib*1024*1024
    assert 0<=resources["cpu_user_ms"]<=240000 and resources["wall_ms"]>0
    assert receipt["receipt_sha256"]==sha256(payload).hexdigest()
    with f.q.f.engine.connect() as db:
        envelope=db.scalar(select(payloads.c.envelope))
        assert len(envelope)==len(payload)+28 and payload not in envelope
    print("ASR_FIXTURE_METRICS "+json.dumps({"case":case,"quality":quality,"resources":resources},sort_keys=True))


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("asr_silence",)],indirect=True)
def test_real_asr_fixture_requires_derived_retention(queue_fixture):
    from tapi_gate0 import asset_asr_fixture as a
    f=queue_fixture
    spec,lease,directory=_asr_job(f,"silence")
    with pytest.raises(AssetRightsDenied,match="SCOPE_MISMATCH"):
        a.run_asr_fixture_windows(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease,case="silence",model_dir=directory)
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==0


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("retain","process","asr_silence")],indirect=True)
def test_real_asr_fixture_config_mismatch_before_spawn(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_asr_fixture as a
    f=queue_fixture
    spec,lease,directory=_asr_job(f,"tone")
    monkeypatch.setattr(a.windows,"_run_model_fixture",lambda *x,**y:pytest.fail("must not spawn"))
    with pytest.raises(AssetRightsDenied,match="ASR_FIXTURE_ONLY"):
        a.run_asr_fixture_windows(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease,case="tone",model_dir=directory)


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("retain","process","asr_silence")],indirect=True)
def test_real_asr_fixture_late_cancel_no_payload(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_asr_fixture as a
    f=queue_fixture
    spec,lease,directory=_asr_job(f,"silence")
    original=a.windows._run_model_fixture
    def late(*args,**kwargs):
        output=original(*args,**kwargs)
        f.queue.cancel(TENANT,spec.job_id)
        return output
    monkeypatch.setattr(a.windows,"_run_model_fixture",late)
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        a.run_asr_fixture_windows(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease,case="silence",model_dir=directory)
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==0
    assert f.queue.acknowledge_cancel(lease)["state"]=="canceled"


def _vlm_job(f,case):
    import os
    from tapi_gate0 import asset_vlm_fixture as a
    model,server=(os.environ.get(k) for k in ("TAPI_VLM_TEST_MODEL_DIR","TAPI_VLM_TEST_SERVER_EXE"))
    if not model or not server:
        pytest.skip("explicit VLM model and server opt-ins required")
    model,server=Path(model),Path(server)
    config,_=a.plan(case,model,server)
    spec=f.spec.model_copy(update={"processor":"vlm","method_version":a.METHOD,
        "configuration_sha256":config["configuration_sha256"]})
    f.queue.enqueue(spec)
    return spec,f.queue.claim(TENANT,"worker")["lease"],model,server


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture,case,scene",[
    (("retain","process","vlm_sales"),"sales","text_card"),
    (("retain","process","vlm_geometry"),"geometry","geometry"),
    (("retain","process","vlm_blank"),"blank","blank"),
],indirect=["discard_fixture"])
def test_real_vlm_fixture_encrypted_result(queue_fixture,case,scene):
    import json
    from tapi_gate0 import asset_vlm_fixture as a,asset_windows_job as w
    from tapi_gate0.asset_processor_results import decode,validate_binding
    f=queue_fixture
    spec,lease,model,server=_vlm_job(f,case)
    store=DerivedPayloadStore(f.queue,b"d"*32)
    receipt=a.run_vlm_fixture_windows(f.queue,f.q.vault,store,lease,case=case,model_dir=model,server_exe=server)
    assert receipt["state"]=="completed" and receipt["payload_persisted"]
    assert receipt["fixture_case"]==case and receipt["model_calls"]==int(case!="blank")
    assert receipt["kernel_job_limits_verified"] and receipt["tree_empty_verified"]
    assert not receipt["media_enabled"] and not receipt["scientific_evidence"] and not receipt["canonical_rubric"]
    payload=store.read_for_processing(TENANT,receipt["artifact_id"],purpose=spec.purpose)
    result=decode(payload)
    assert validate_binding(result,spec=spec,ref=f.q.ref,lease=lease)==result
    assert result.origin=="adapter_candidate" and result.result.scene==scene
    assert result.result.text_present==("yes" if scene=="text_card" else "no")
    assert result.result.frame.frame_sha256==f.q.ref.target.sha256
    assert receipt["receipt_sha256"]==sha256(payload).hexdigest()
    resources=receipt["resources"]
    assert 0<resources["peak_job_commit_bytes"]<=w.VlmFixtureLimits().memory_mib*1024*1024
    assert 0<=resources["cpu_user_ms"]<=240000 and resources["wall_ms"]>0
    with f.q.f.engine.connect() as db:
        envelope=db.scalar(select(payloads.c.envelope))
        assert len(envelope)==len(payload)+28 and payload not in envelope
    print("VLM_FIXTURE_METRICS "+json.dumps({"case":case,"scene":scene,"model_calls":receipt["model_calls"],"resources":resources},sort_keys=True))


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("vlm_blank",)],indirect=True)
def test_real_vlm_fixture_requires_derived_retention(queue_fixture):
    from tapi_gate0 import asset_vlm_fixture as a
    f=queue_fixture
    spec,lease,model,server=_vlm_job(f,"blank")
    with pytest.raises(AssetRightsDenied,match="SCOPE_MISMATCH"):
        a.run_vlm_fixture_windows(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease,case="blank",model_dir=model,server_exe=server)
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==0


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("retain","process","vlm_blank")],indirect=True)
def test_real_vlm_fixture_wrong_config_before_spawn(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_vlm_fixture as a,asset_windows_job as w
    f=queue_fixture
    spec,lease,model,server=_vlm_job(f,"sales")
    monkeypatch.setattr(w,"_run_vlm_fixture",lambda *x,**y:pytest.fail("must not spawn"))
    with pytest.raises(AssetRightsDenied,match="VLM_FIXTURE_ONLY"):
        a.run_vlm_fixture_windows(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease,case="sales",model_dir=model,server_exe=server)


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("retain","process","vlm_blank")],indirect=True)
def test_real_vlm_fixture_late_cancel_no_payload(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_vlm_fixture as a,asset_windows_job as w
    f=queue_fixture
    spec,lease,model,server=_vlm_job(f,"blank")
    original=w._run_vlm_fixture
    def late(*args,**kwargs):
        output=original(*args,**kwargs)
        f.queue.cancel(TENANT,spec.job_id)
        return output
    monkeypatch.setattr(w,"_run_vlm_fixture",late)
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        a.run_vlm_fixture_windows(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease,case="blank",model_dir=model,server_exe=server)
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==0
    assert f.queue.acknowledge_cancel(lease)["state"]=="canceled"


def _reconcile_revocation(f):
    rv=f.q.f.state(2,revoked_asset_ids=(f.q.ref.target.asset_id,))
    f.q.f.svc.advance(f.q.f.anchor,TENANT,"instagram",rv)
    anchor=f.q.f.pin(rv)
    f.queue.resolve_anchor=lambda ref:anchor
    return anchor


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
def test_maintenance_signed_cascade_and_bounded_cleanup(queue_fixture):
    from tapi_gate0.asset_reconcile import reconcile_tenant,cleanup_tenant
    f=queue_fixture
    store=DerivedPayloadStore(f.queue,b"d"*32)
    receipt=store.finish(_payload_job(f),payload=b"fixture")
    other=f.spec.model_copy(update={"method_version":"other"})
    f.queue.enqueue(other)
    anchor=_reconcile_revocation(f)
    result=reconcile_tenant(f.queue,TENANT,scopes=((anchor,"instagram"),))
    assert result["newly_invalidated"]==2 and result["signed_revoked_roots"]==1
    assert result["roots_covered"]==1 and result["roots_uncovered"]==0
    assert result["queued_canceled"]==1 and f.queue.status(TENANT,other.job_id)["state"]=="canceled"
    assert f.queue.status(TENANT,f.spec.job_id)["state"]=="completed"
    assert f.q.path.exists() and not result["filesystem_mutated"]
    with pytest.raises(AssetRightsDenied,match="INACTIVE_ANCESTOR"):
        store.read_for_processing(TENANT,receipt["artifact_id"],purpose=f.spec.purpose)
    first=cleanup_tenant(f.queue,f.q.vault,store,TENANT,all_io_stopped=True,limit=1)
    assert first["payloads_purged"]==1 and first["remaining_at_snapshot"]==1 and f.q.path.exists()
    second=cleanup_tenant(f.queue,f.q.vault,store,TENANT,all_io_stopped=True,limit=1)
    assert second["root_entries_removed"]==1 and second["remaining_at_snapshot"]==0 and not f.q.path.exists()
    assert not second["secure_erasure_verified"]
    assert cleanup_tenant(f.queue,f.q.vault,store,TENANT,all_io_stopped=True)["selected"]==0
    assert reconcile_tenant(f.queue,TENANT,scopes=((anchor,"instagram"),))["newly_invalidated"]==0
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads).where(payloads.c.envelope.is_(None)))==1
        assert db.scalar(select(func.count()).select_from(domain_events).where(domain_events.c.event_type=="asset_derived_payload.purged"))==1
        assert db.scalar(select(func.count()).select_from(domain_events).where(domain_events.c.event_type=="asset_lineage.discarded"))==1


def test_maintenance_running_cancel_requires_ack(queue_fixture):
    from tapi_gate0.asset_reconcile import reconcile_tenant,cleanup_tenant
    f=queue_fixture
    lease=_payload_job(f)
    anchor=_reconcile_revocation(f)
    result=reconcile_tenant(f.queue,TENANT,scopes=((anchor,"instagram"),))
    assert result["running_cancel_requested"]==1 and result["cancel_requested_pending"]==1
    assert not result["workers_stopped_verified"]
    store=DerivedPayloadStore(f.queue,b"d"*32)
    with pytest.raises(AssetRightsDenied,match="ACTIVE_LEASES"):
        cleanup_tenant(f.queue,f.q.vault,store,TENANT,all_io_stopped=True)
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        f.queue.finish(lease,"b"*64)
    assert f.queue.acknowledge_cancel(lease)["state"]=="canceled"
    assert cleanup_tenant(f.queue,f.q.vault,store,TENANT,all_io_stopped=True)["root_entries_removed"]==1


def test_maintenance_expired_revoked_running_never_requeues(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_jobs as j
    from tapi_gate0.asset_reconcile import reconcile_tenant
    f=queue_fixture
    lease=_payload_job(f)
    anchor=_reconcile_revocation(f)
    future=now_utc()+timedelta(seconds=121)
    monkeypatch.setattr(j,"now_utc",lambda:future)
    result=reconcile_tenant(f.queue,TENANT,scopes=((anchor,"instagram"),))
    assert result["running_cancel_requested"]==1 and result["expired_leases_reconciled"]==1
    assert result["cancel_requested_pending"]==0
    status=f.queue.status(TENANT,lease.job_id)
    assert status["state"]=="canceled" and status["reason"]=="cancel_lease_expired"
    assert f.q.path.exists()


def test_maintenance_expired_live_job_requeues(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_jobs as j
    from tapi_gate0.asset_reconcile import reconcile_tenant
    f=queue_fixture
    lease=_payload_job(f)
    future=now_utc()+timedelta(seconds=121)
    monkeypatch.setattr(j,"now_utc",lambda:future)
    result=reconcile_tenant(f.queue,TENANT)
    assert result["expired_leases_reconciled"]==1 and result["newly_invalidated"]==0
    status=f.queue.status(TENANT,lease.job_id)
    assert status["state"]=="queued" and status["reason"]=="lease_expired" and status["attempt"]==1
    assert status["available_ms"]>j._ms(future)
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        f.queue.finish(lease,"b"*64)


def test_maintenance_ttl_without_authority(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_jobs as j
    from tapi_gate0.asset_reconcile import reconcile_tenant
    f=queue_fixture
    f.queue.enqueue(f.spec)
    future=f.q.ref.retain_until+timedelta(seconds=1)
    monkeypatch.setattr(j,"now_utc",lambda:future)
    result=reconcile_tenant(f.queue,TENANT)
    assert result["roots_uncovered"]==1 and result["scopes_verified"]==0
    assert result["newly_invalidated"]==1 and result["queued_canceled"]==1
    assert f.q.path.exists()


def test_maintenance_missing_or_stale_authority_not_revocation(queue_fixture):
    from tapi_gate0.asset_reconcile import reconcile_tenant,cleanup_tenant
    f=queue_fixture
    f.queue.enqueue(f.spec)
    anchor=_reconcile_revocation(f)
    with pytest.raises(AssetRightsDenied,match="ROLLBACK"):
        reconcile_tenant(f.queue,TENANT,scopes=((f.q.f.anchor,"instagram"),))
    with pytest.raises(AssetRightsDenied,match="DUPLICATE_SCOPE"):
        reconcile_tenant(f.queue,TENANT,scopes=((anchor,"instagram"),(anchor,"instagram")))
    result=reconcile_tenant(f.queue,TENANT)
    assert result["newly_invalidated"]==0 and result["roots_uncovered"]==1
    assert f.queue.status(TENANT,f.spec.job_id)["state"]=="queued"
    store=DerivedPayloadStore(f.queue,b"d"*32)
    assert cleanup_tenant(f.queue,f.q.vault,store,TENANT,all_io_stopped=True)["selected"]==0
    assert f.q.path.exists()
    assert f.queue.claim(TENANT,"worker")["status"]=="rights_blocked"


def test_maintenance_rollback_when_job_transition_fails(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_reconcile as m
    f=queue_fixture
    f.queue.enqueue(f.spec)
    anchor=_reconcile_revocation(f)
    def fail(*args,**kwargs):
        raise RuntimeError("fixture transition failure")
    monkeypatch.setattr(m,"_transition",fail)
    with pytest.raises(RuntimeError,match="fixture transition"):
        m.reconcile_tenant(f.queue,TENANT,scopes=((anchor,"instagram"),))
    assert f.queue.status(TENANT,f.spec.job_id)["state"]=="queued"
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(nodes.c.state).where(nodes.c.node_id==f.q.ref.object_id))=="active"
        assert db.scalar(select(func.count()).select_from(domain_events).where(domain_events.c.event_type=="asset_lineage.invalidated"))==0
    # The separately committed signed head still blocks claim.
    assert f.queue.claim(TENANT,"worker")["status"]=="rights_blocked"


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
def test_maintenance_cleanup_resume_after_partial_commit(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_reconcile as m
    f=queue_fixture
    store=DerivedPayloadStore(f.queue,b"d"*32)
    store.finish(_payload_job(f),payload=b"fixture")
    anchor=_reconcile_revocation(f)
    m.reconcile_tenant(f.queue,TENANT,scopes=((anchor,"instagram"),))
    def fail(*args,**kwargs):
        raise RuntimeError("fixture discard failure")
    with monkeypatch.context() as patch:
        patch.setattr(m,"discard_invalidated",fail)
        with pytest.raises(RuntimeError,match="fixture discard"):
            m.cleanup_tenant(f.queue,f.q.vault,store,TENANT,all_io_stopped=True)
    assert f.q.path.exists()
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads).where(payloads.c.envelope.is_(None)))==1
    result=m.cleanup_tenant(f.queue,f.q.vault,store,TENANT,all_io_stopped=True)
    assert result["payloads_purged"]==0 and result["root_entries_removed"]==1


def test_maintenance_cleanup_requires_attestation_and_exact_host(queue_fixture):
    from tapi_gate0.asset_reconcile import cleanup_tenant,reconcile_tenant
    f=queue_fixture
    store=DerivedPayloadStore(f.queue,b"d"*32)
    anchor=_reconcile_revocation(f)
    reconcile_tenant(f.queue,TENANT,scopes=((anchor,"instagram"),))
    with pytest.raises(AssetRightsDenied,match="STOPPED_IO_REQUIRED"):
        cleanup_tenant(f.queue,f.q.vault,store,TENANT,all_io_stopped=1)
    with pytest.raises(AssetRightsDenied,match="BATCH_INVALID"):
        cleanup_tenant(f.queue,f.q.vault,store,TENANT,all_io_stopped=True,limit=101)
    other=AssetJobQueue(f.q.index,resolve_anchor=f.queue.resolve_anchor)
    with pytest.raises(AssetRightsDenied,match="HOST_MISMATCH"):
        cleanup_tenant(f.queue,f.q.vault,DerivedPayloadStore(other,b"d"*32),TENANT,all_io_stopped=True)
    with pytest.raises(AssetRightsDenied,match="TENANT_UNKNOWN"):
        reconcile_tenant(f.queue,"other")
    assert f.q.path.exists()


def _bundle_finish(f, store, result, *, method="bundle-test-v1", mutate=None, noncanonical=False):
    from tapi_gate0.asset_processor_results import ProcessorResult, encode
    spec = f.spec.model_copy(update={"processor":result.processor,"method_version":method})
    f.queue.enqueue(spec)
    lease = f.queue.claim(TENANT,"worker")['lease']
    assert lease.job_id == spec.job_id
    envelope = ProcessorResult(tenant_id=spec.tenant_id,job_id=spec.job_id,
        object_id=spec.object_id,input_sha256=f.q.ref.target.sha256,attempt=lease.attempt,
        purpose=spec.purpose,method_version=spec.method_version,
        configuration_sha256=spec.configuration_sha256,
        origin="synthetic_fixture" if getattr(result,"reason",None)=="fixture_header_only" else "adapter_candidate",
        result=result)
    if mutate is not None:
        envelope = envelope.model_copy(update=mutate)
    data = encode(envelope)
    if noncanonical:
        data = b" " + data
    return store.finish(lease,payload=data)["artifact_id"]


def _bundle_read(f,store,ids,**kwargs):
    from tapi_gate0.asset_candidate_evidence import assemble_candidate_bundle
    return assemble_candidate_bundle(store,kwargs.get("tenant",TENANT),
        kwargs.get("object_id",f.q.ref.object_id),ids,purpose=kwargs.get("purpose",f.spec.purpose))


@pytest.mark.parametrize("discard_fixture",[("retain","process","all_processors")],indirect=True)
def test_candidate_bundle_four_header_abstentions(queue_fixture):
    from tapi_gate0.asset_processor_results import Abstention
    f=queue_fixture
    store=DerivedPayloadStore(f.queue,b"d"*32)
    ids=[_bundle_finish(f,store,Abstention(processor=p,reason="fixture_header_only"))
         for p in ("vlm","ocr","temporal","asr_vad")]
    with f.q.f.engine.connect() as db:
        events=db.scalar(select(func.count()).select_from(domain_events))
    bundle=_bundle_read(f,store,ids)
    assert bundle.coverage()=={p:"abstained" for p in ("asr_vad","ocr","temporal","vlm")}
    assert bundle.object_id==f.q.ref.object_id and bundle.content_id==f.q.ref.target.content_id
    assert bundle.input_sha256==f.q.ref.target.sha256
    assert not bundle.canonical_rubric and not bundle.scientific_evidence and bundle.calibrated_probability is None
    assert bundle.fingerprint()==_bundle_read(f,store,list(reversed(ids))).fingerprint()
    assert [e.observation.result.processor for e in bundle.entries]==["asr_vad","ocr","temporal","vlm"]
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(domain_events))==events
        assert db.scalar(select(func.count()).select_from(payloads))==4


@pytest.mark.parametrize("discard_fixture",[("retain","process","ocr_sales","bundle_visual")],indirect=True)
def test_candidate_bundle_same_image_distinct_modalities(queue_fixture):
    from tapi_gate0.asset_processor_results import Frame,OCR,Word,VLM
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    frame=Frame(time_ms=0,frame_sha256=f.q.ref.target.sha256,timeline="image")
    ocr=_bundle_finish(f,store,OCR(frame=frame,width=960,height=540,
        words=(Word(text="Organize",box_px=(10,20,100,30),confidence_raw=96.0),)))
    vlm=_bundle_finish(f,store,VLM(frame=frame,scene="text_card",text_present="yes"))
    bundle=_bundle_read(f,store,[vlm,ocr])
    assert bundle.coverage()=={"asr_vad":"not_applicable","ocr":"observed","temporal":"not_applicable","vlm":"observed"}
    assert bundle.entries[0].observation.result.frame==bundle.entries[1].observation.result.frame
    assert _bundle_read(f,store,[ocr]).coverage()["vlm"]=="missing"
    assert _bundle_read(f,store,[ocr]).fingerprint()!=bundle.fingerprint()


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
def test_candidate_bundle_rejects_selection_and_duplicate_processor(queue_fixture):
    from tapi_gate0.asset_processor_results import Abstention
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    r=Abstention(processor="temporal",reason="no_observable_signal")
    x=_bundle_finish(f,store,r)
    y=_bundle_finish(f,store,r,method="bundle-test-v2")
    for ids in ([],[x,x],[x]*5,["../wrong"]):
        with pytest.raises(AssetRightsDenied,match="ARTIFACT_SELECTION"):
            _bundle_read(f,store,ids)
    with pytest.raises(AssetRightsDenied,match="BUNDLE_CONTRACT"):
        _bundle_read(f,store,[x,y])
    with pytest.raises(AssetRightsDenied,match="ROOT_UNKNOWN"):
        _bundle_read(f,store,[x],tenant="other")
    with pytest.raises(AssetRightsDenied,match="PURPOSE_MISMATCH"):
        _bundle_read(f,store,[x],purpose="studio_creation")


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
@pytest.mark.parametrize("mutate",[{"attempt":2},{"configuration_sha256":"c"*64},{"input_sha256":"e"*64}])
def test_candidate_bundle_rejects_authenticated_wrong_binding(queue_fixture,mutate):
    from tapi_gate0.asset_processor_results import Abstention
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    ident=_bundle_finish(f,store,Abstention(processor="temporal",reason="no_observable_signal"),mutate=mutate)
    # AEAD authenticates these bytes but cannot establish their semantic binding.
    assert store.read_for_processing(TENANT,ident,purpose=f.spec.purpose)
    with pytest.raises(AssetRightsDenied,match="PROCESSOR_CONTRACT"):
        _bundle_read(f,store,[ident])


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
@pytest.mark.parametrize("opaque",[False,True])
def test_candidate_bundle_rejects_noncanonical_or_opaque_bytes(queue_fixture,opaque):
    from tapi_gate0.asset_processor_results import Abstention
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    if opaque:
        ident=store.finish(_payload_job(f),payload=b"not a processor envelope")["artifact_id"]
    else:
        ident=_bundle_finish(f,store,Abstention(processor="temporal",reason="no_observable_signal"),noncanonical=True)
    with pytest.raises(AssetRightsDenied,match="PROCESSOR_CONTRACT|NONCANONICAL_PROCESSOR_PAYLOAD"):
        _bundle_read(f,store,[ident])


@pytest.mark.parametrize("discard_fixture",[("retain","process","ocr_sales")],indirect=True)
@pytest.mark.parametrize("timeline,digest",[("image","e"*64),("resampled_uniform",None)])
def test_candidate_bundle_rejects_wrong_frame(queue_fixture,timeline,digest):
    from tapi_gate0.asset_processor_results import Frame,OCR,Word
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    frame=Frame(time_ms=0,frame_sha256=digest or f.q.ref.target.sha256,timeline=timeline)
    ident=_bundle_finish(f,store,OCR(frame=frame,width=960,height=540,
        words=(Word(text="Organize",box_px=(10,20,100,30)),)))
    with pytest.raises(AssetRightsDenied,match="BUNDLE_CONTRACT"):
        _bundle_read(f,store,[ident])


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
def test_candidate_bundle_rejects_same_content_and_digest_different_root(queue_fixture,monkeypatch):
    from tapi_gate0.asset_processor_results import Abstention
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    ident=_bundle_finish(f,store,Abstention(processor="temporal",reason="no_observable_signal"))
    q=f.q
    retention=Permission(operation="retain",purpose="research_analysis",field="video")
    other=q.f.grant(grant_id="grant.other",target=q.ref.target,permissions=(retention,))
    q.f.svc.register_grant(q.f.anchor,other,verified_approval_digest="b"*64)
    ref=q.ref.model_copy(update={"grant_id":"grant.other",
        "object_id":expected_object_id(q.f.anchor,"grant.other",q.ref.target,q.ref.mime)})
    assert q.index.register_retained(q.f.anchor,ref,purpose="research_analysis")
    monkeypatch.setattr(store,"_read_in_transaction",lambda *a,**k:pytest.fail("must reject before decrypt"))
    with pytest.raises(AssetRightsDenied,match="ROOT_MISMATCH"):
        _bundle_read(f,store,[ident],object_id=ref.object_id)


@pytest.mark.parametrize("discard_fixture",[("retain",)],indirect=True)
def test_candidate_bundle_requires_derived_process(queue_fixture):
    from tapi_gate0.asset_processor_results import Abstention
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    ident=_bundle_finish(f,store,Abstention(processor="temporal",reason="no_observable_signal"))
    with pytest.raises(AssetRightsDenied,match="SCOPE_MISMATCH"):
        _bundle_read(f,store,[ident])


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
def test_candidate_bundle_rechecks_revocation_and_tombstone(queue_fixture):
    from tapi_gate0.asset_processor_results import Abstention
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    ident=_bundle_finish(f,store,Abstention(processor="temporal",reason="no_observable_signal"))
    assert _bundle_read(f,store,[ident]).entries
    rv=f.q.f.state(2,revoked_asset_ids=(f.q.ref.target.asset_id,))
    f.q.f.svc.advance(f.q.f.anchor,TENANT,"instagram",rv)
    f.queue.resolve_anchor=lambda ref:f.q.f.pin(rv)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        _bundle_read(f,store,[ident])
    f.q.index.reconcile_signed_revocations(f.q.f.pin(rv),TENANT,"instagram")
    store.purge_invalidated(TENANT,ident)
    with pytest.raises(AssetRightsDenied,match="INACTIVE_ANCESTOR"):
        _bundle_read(f,store,[ident])


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
def test_candidate_bundle_final_expiry_check(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_candidate_evidence as module
    from tapi_gate0.asset_processor_results import Abstention
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    ident=_bundle_finish(f,store,Abstention(processor="temporal",reason="no_observable_signal"))
    monkeypatch.setattr(module,"now_utc",lambda:f.q.ref.retain_until+timedelta(seconds=1))
    with pytest.raises(AssetRightsDenied,match="INACTIVE_ANCESTOR"):
        _bundle_read(f,store,[ident])


@pytest.mark.parametrize("discard_fixture",[("retain","process")],indirect=True)
def test_candidate_bundle_rejects_tampered_ciphertext(queue_fixture):
    from tapi_gate0.asset_processor_results import Abstention
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    ident=_bundle_finish(f,store,Abstention(processor="temporal",reason="no_observable_signal"))
    with f.q.f.engine.begin() as db:
        item=db.scalar(select(payloads.c.envelope).where(payloads.c.artifact_id==ident))
        db.execute(update(payloads).where(payloads.c.artifact_id==ident).values(envelope=item[:-1]+bytes([item[-1]^1])))
    with pytest.raises(AssetRightsDenied,match="AUTHENTICATION_FAILED"):
        _bundle_read(f,store,[ident])


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("retain","process","ocr_blank","bundle_visual")],indirect=True)
def test_candidate_bundle_real_blank_ocr_and_vlm(queue_fixture):
    from tapi_gate0 import asset_ocr_fixture as o, asset_vlm_fixture as v
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    assert o.fixture("blank")[0]==v.fixture("blank")[0]
    spec,lease,directory=_ocr_job(f,"blank")
    ocr=o.run_ocr_fixture_windows(f.queue,f.q.vault,store,lease,tessdata_dir=directory)
    spec,lease,model,server=_vlm_job(f,"blank")
    vlm=v.run_vlm_fixture_windows(f.queue,f.q.vault,store,lease,case="blank",model_dir=model,server_exe=server)
    assert vlm["model_calls"]==0 and ocr["model_calls"]==1
    bundle=_bundle_read(f,store,[ocr["artifact_id"],vlm["artifact_id"]])
    assert bundle.coverage()=={"asr_vad":"not_applicable","ocr":"abstained","temporal":"not_applicable","vlm":"observed"}
    assert bundle.entries[0].observation.result.reason=="no_observable_signal"
    assert bundle.entries[1].observation.result.scene=="blank"
    assert bundle.entries[1].observation.result.frame.frame_sha256==bundle.input_sha256
    assert not bundle.canonical_rubric and not bundle.scientific_evidence


def _s1_decisions(f,store,ids,**kwargs):
    from tapi_gate0.asset_candidate_fusion import evaluate_candidate_bundle
    result=evaluate_candidate_bundle(store,kwargs.get("tenant",TENANT),f.q.ref.object_id,ids,purpose=f.spec.purpose)
    return result,{d.field_id:d for d in result.fields}


def _s1_image(f,store,words,*,visual=None,boxes=None):
    from tapi_gate0.asset_processor_results import Frame, OCR, Word, VLM
    frame=Frame(time_ms=0,frame_sha256=f.q.ref.target.sha256,timeline="image")
    boxes=boxes or [(10+i*110,20,100,30) for i in range(len(words))]
    ident=_bundle_finish(f,store,OCR(frame=frame,width=960,height=540,
        words=tuple(Word(text=w,box_px=b) for w,b in zip(words,boxes))))
    ids=[ident]
    if visual:
        ids.append(_bundle_finish(f,store,VLM(frame=frame,scene=visual,
            text_present="yes" if visual=="text_card" else "no")))
    return ids


@pytest.mark.parametrize("discard_fixture", [("retain","process","ocr_sales","bundle_visual","bundle_rubric")],indirect=True)
def test_candidate_fusion_topic_cta_and_provenance(queue_fixture):
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    ids=_s1_image(f,store,("Salve","este","post.","Organize","suas","vendas."),visual="text_card")
    with f.q.f.engine.connect() as db:
        count=db.scalar(select(func.count()).select_from(domain_events))
    result,d=_s1_decisions(f,store,ids)
    assert d["tema_principal"].value=="vendas" and d["tipo_cta"].value=="salvar"
    assert d["tem_cta"].value is True and d["texto_na_tela"].value is True
    assert sum(x.state=="candidate" for x in d.values())==4
    assert sum(x.state=="not_assessed" for x in d.values())==16
    assert all(not x.value is False for x in d.values())
    assert d["tipo_cta"].supports[0].artifact_id==ids[0]
    assert d["tipo_cta"].supports[0].word_indices==tuple(range(6))
    assert d["tipo_cta"].supports[0].text_sha256==sha256("Salve este post. Organize suas vendas.".encode()).hexdigest()
    assert result.evidence_fingerprint==_bundle_read(f,store,ids).fingerprint()
    assert result==_s1_decisions(f,store,list(reversed(ids)))[0]
    assert not result.scientific_evidence and not result.canonical_rubric and result.calibrated_probability is None
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(domain_events))==count


@pytest.mark.parametrize("discard_fixture", [("retain","process","ocr_sales","bundle_visual","bundle_rubric")],indirect=True)
def test_candidate_fusion_same_frame_conflict(queue_fixture):
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    ids=_s1_image(f,store,("Organize","suas","vendas"),visual="geometry")
    _,d=_s1_decisions(f,store,ids)
    for k in ("tema_principal","tipo_cta","tem_cta","texto_na_tela"):
        assert d[k].state=="abstained" and d[k].value is None
        assert {s.artifact_id for s in d[k].vetoes}==set(ids)


@pytest.mark.parametrize("discard_fixture", [("retain","process","ocr_sales","bundle_rubric")],indirect=True)
@pytest.mark.parametrize("words,boxes",[
    (("Salve","este","post"),[(10,10,80,20),(10,60,80,20),(100,60,80,20)]),
    (("Salve","este","post"),[(10,10,80,20),(400,10,80,20),(490,10,80,20)]),
    (("Salve","para","revisar"),None),
    (("Não","salve","este","post"),None),
])
def test_candidate_fusion_no_unsupported_cta(queue_fixture,words,boxes):
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    _,d=_s1_decisions(f,store,_s1_image(f,store,words,boxes=boxes))
    assert d["tipo_cta"].value is None and d["tem_cta"].value is None
    assert d["texto_na_tela"].value is True


@pytest.mark.parametrize("discard_fixture", [("retain","process","ocr_sales","bundle_visual","bundle_rubric")],indirect=True)
def test_candidate_fusion_vlm_only_never_promotes_text(queue_fixture):
    from tapi_gate0.asset_processor_results import Frame,VLM
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    ident=_bundle_finish(f,store,VLM(frame=Frame(time_ms=0,frame_sha256=f.q.ref.target.sha256,timeline="image"),
        scene="text_card",text_present="yes"))
    _,d=_s1_decisions(f,store,[ident])
    assert d["texto_na_tela"].state=="abstained" and all(x.value is None for x in d.values())


@pytest.mark.parametrize("discard_fixture", [("retain","process","all_processors","bundle_rubric")],indirect=True)
def test_candidate_fusion_audio_separate_segments_and_temporal_not_score(queue_fixture):
    from tapi_gate0.asset_processor_results import ASR,Speech,Interval,Temporal
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    a=_bundle_finish(f,store,ASR(duration_ms=3000,segments=(
        Speech(start_ms=0,end_ms=1000,text="Clique no link"),
        Speech(start_ms=1000,end_ms=2000,text="na bio"),
        Speech(start_ms=2000,end_ms=3000,text="Controle o estoque.")),
        vad=(Interval(start_ms=0,end_ms=3000),)))
    t=_bundle_finish(f,store,Temporal(samples=12,threshold=0.5,candidates=()))
    _,d=_s1_decisions(f,store,[a,t])
    assert d["tema_principal"].value=="gestão"
    assert d["tema_principal"].supports[0].segment_index==2
    assert d["tipo_cta"].value is None and d["ritmo_cortes_0a10"].state=="not_assessed"
    assert d["hook_primeiros_3s"].state=="not_assessed"


@pytest.mark.parametrize("discard_fixture", [("retain","process","all_processors","bundle_rubric")],indirect=True)
def test_candidate_fusion_cross_modality_cta_conflict(queue_fixture):
    from tapi_gate0.asset_processor_results import ASR,Speech,Interval,OCR,Frame,Word
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    a=_bundle_finish(f,store,ASR(duration_ms=2000,
        segments=(Speech(start_ms=0,end_ms=2000,text="Comente sua dúvida."),),
        vad=(Interval(start_ms=0,end_ms=2000),)))
    o=_bundle_finish(f,store,OCR(frame=Frame(time_ms=1000,frame_sha256="a"*64,timeline="resampled_uniform"),
        width=960,height=540,words=tuple(Word(text=w,box_px=(10+i*110,10,100,30))
        for i,w in enumerate(("Salve","este","post.")))))
    _,d=_s1_decisions(f,store,[a,o])
    assert d["tipo_cta"].state=="abstained" and d["tem_cta"].value is None
    assert {x.artifact_id for x in d["tipo_cta"].vetoes}=={a,o}
    assert d["texto_na_tela"].value is True


@pytest.mark.parametrize("discard_fixture", [("retain","process","ocr_sales")],indirect=True)
def test_candidate_fusion_requires_rubric_permission_before_decrypt(queue_fixture,monkeypatch):
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    ids=_s1_image(f,store,("Organize","suas","vendas"))
    monkeypatch.setattr(store,"_read_in_transaction",lambda *a,**k:pytest.fail("must deny before decrypt"))
    with pytest.raises(AssetRightsDenied,match="SCOPE_MISMATCH"):
        _s1_decisions(f,store,ids)


@pytest.mark.parametrize("discard_fixture", [("retain","process","ocr_sales","bundle_rubric")],indirect=True)
def test_candidate_fusion_final_expiry_and_revocation(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_candidate_evidence as b
    f=queue_fixture;store=DerivedPayloadStore(f.queue,b"d"*32)
    ids=_s1_image(f,store,("Organize","suas","vendas"))
    assert _s1_decisions(f,store,ids)[1]["tema_principal"].value=="vendas"
    with monkeypatch.context() as m:
        m.setattr(b,"now_utc",lambda:f.q.ref.retain_until+timedelta(seconds=1))
        with pytest.raises(AssetRightsDenied,match="INACTIVE_ANCESTOR"):
            _s1_decisions(f,store,ids)
    rv=f.q.f.state(2,revoked_asset_ids=(f.q.ref.target.asset_id,))
    f.q.f.svc.advance(f.q.f.anchor,TENANT,"instagram",rv)
    f.queue.resolve_anchor=lambda ref:f.q.f.pin(rv)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        _s1_decisions(f,store,ids)


# A02.7 — explicit fixture orchestration.
def _pipeline(f,**kwargs):
    from tapi_gate0.asset_fixture_pipeline import FixturePipeline
    return FixturePipeline(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),
        tenant=TENANT,object_id=f.q.ref.object_id,purpose=f.spec.purpose,**kwargs)


@pytest.mark.parametrize("discard_fixture",[("retain","process","all_processors","bundle_rubric")],indirect=True)
def test_fixture_pipeline_targeted_claim_and_resume(queue_fixture,monkeypatch):
    from tapi_gate0.asset_fixture_pipeline import FixturePipeline
    from tapi_gate0.asset_processor_results import ProcessorResult,Abstention,encode
    f=queue_fixture
    pipe=_pipeline(f,mode="header",case="header")
    unrelated=f.spec.model_copy(update={"method_version":"unrelated"})
    f.queue.enqueue(unrelated)
    # Real queue/store/fusion, synthetic substitute for native adapter.
    def fake_dispatch(self,lease,spec):
        assert spec.job_id==lease.job_id
        r=ProcessorResult(tenant_id=spec.tenant_id,job_id=spec.job_id,
            object_id=spec.object_id,input_sha256=f.q.ref.target.sha256,attempt=lease.attempt,
            purpose=spec.purpose,method_version=spec.method_version,
            configuration_sha256=spec.configuration_sha256,origin="synthetic_fixture",
            result=Abstention(processor=spec.processor,reason="fixture_header_only"))
        return {**self.store.finish(lease,payload=encode(r)),"model_calls":0}
    monkeypatch.setattr(FixturePipeline,"_dispatch",fake_dispatch)
    assert pipe.step("worker")["status"]=="processed"
    pipe=_pipeline(f,mode="header",case="header",expected_plan=pipe.plan.fingerprint)
    with pytest.raises(AssetRightsDenied,match="PLAN_CHANGED"):
        _pipeline(f,mode="header",case="header",expected_plan="0"*64)
    for _ in range(3):
        assert pipe.step("worker")["status"]=="processed"
    result=pipe.step("worker")
    assert result["status"]=="candidate_complete" and len(result["artifact_ids"])==4
    assert sum(x.state=="abstained" for x in result["decisions"].fields)==4
    assert sum(x.state=="not_assessed" for x in result["decisions"].fields)==16
    assert pipe.step("worker")==result
    assert f.queue.status(TENANT,unrelated.job_id)["attempt"]==0
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts))==4


@pytest.mark.parametrize("discard_fixture",[("retain","process","all_processors","bundle_rubric")],indirect=True)
def test_fixture_pipeline_failure_and_cancel_hold_fence(queue_fixture,monkeypatch):
    from tapi_gate0.asset_fixture_pipeline import FixturePipeline
    f=queue_fixture
    pipe=_pipeline(f,mode="header",case="header")
    def failure(*_):
        raise RuntimeError("fixture interruption")
    monkeypatch.setattr(FixturePipeline,"_dispatch",failure)
    with pytest.raises(RuntimeError,match="interruption"):
        pipe.step("worker")
    spec=pipe.plan.specs[0]
    assert f.queue.status(TENANT,spec.job_id)["state"]=="running"
    assert pipe.step("worker")["status"]=="busy"
    f.queue.cancel(TENANT,spec.job_id)
    assert pipe.step("worker")["status"]=="blocked"
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==0


@pytest.mark.parametrize("discard_fixture",[("retain","process","all_processors","bundle_rubric")],indirect=True)
def test_fixture_pipeline_invalidated_after_plan(queue_fixture):
    f=queue_fixture
    pipe=_pipeline(f,mode="header",case="header")
    f.q.index.invalidate(TENANT,object_ids=[f.q.ref.object_id])
    with pytest.raises(AssetRightsDenied):
        pipe.step("worker")
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts))==0


@pytest.mark.parametrize("discard_fixture",[("retain","process","all_processors")],indirect=True)
def test_fixture_pipeline_requires_fusion_rights_before_enqueue(queue_fixture):
    f=queue_fixture
    with pytest.raises(AssetRightsDenied,match="SCOPE_MISMATCH"):
        _pipeline(f,mode="header",case="header")
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts))==0


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("retain","process","all_processors","bundle_rubric")],indirect=True)
def test_fixture_pipeline_native_four_header_processors(queue_fixture):
    pipe=_pipeline(queue_fixture,mode="header",case="header")
    for _ in range(4):
        step=pipe.step("worker")
        assert step["status"]=="processed" and step["model_calls"]==0
    result=pipe.step("worker")
    assert result["status"]=="candidate_complete" and len(result["artifact_ids"])==4
    assert sum(x.state=="abstained" for x in result["decisions"].fields)==4


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[("retain","process","ocr_blank","bundle_visual","bundle_rubric")],indirect=True)
def test_fixture_pipeline_native_blank_pair(queue_fixture):
    import os
    paths=[os.environ.get(k) for k in ("TAPI_OCR_TEST_TESSDATA","TAPI_VLM_TEST_MODEL_DIR","TAPI_VLM_TEST_SERVER_EXE")]
    if not all(paths):
        pytest.skip("explicit OCR/VLM opt-ins required")
    pipe=_pipeline(queue_fixture,mode="image_pair",case="blank",
        tessdata_dir=paths[0],vlm_model_dir=paths[1],vlm_server_exe=paths[2])
    assert pipe.step("worker")["model_calls"]==1
    assert pipe.step("worker")["model_calls"]==0
    result=pipe.step("worker")
    assert result["status"]=="candidate_complete" and len(result["artifact_ids"])==2
    assert sum(x.state=="abstained" for x in result["decisions"].fields)==4


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture,mode,case",[
    (("retain","process","temporal_one","bundle_rubric"),"temporal","one"),
    (("retain","process","asr_inventory","bundle_rubric"),"asr","inventory"),
    (("retain","process","ocr_sales","bundle_rubric"),"ocr","sales"),
    (("retain","process","vlm_geometry","bundle_rubric"),"vlm","geometry"),
],indirect=["discard_fixture"])
def test_fixture_pipeline_native_single_adapter(queue_fixture,mode,case):
    import os
    opts={"temporal":(),"asr":(("asr_model_dir","TAPI_ASR_TEST_MODEL_DIR"),),
          "ocr":(("tessdata_dir","TAPI_OCR_TEST_TESSDATA"),),
          "vlm":(("vlm_model_dir","TAPI_VLM_TEST_MODEL_DIR"),
                 ("vlm_server_exe","TAPI_VLM_TEST_SERVER_EXE"))}
    paths={k:os.environ.get(env) for k,env in opts[mode]}
    if not all(paths.values()):
        pytest.skip("explicit native adapter opt-ins required")
    pipe=_pipeline(queue_fixture,mode=mode,case=case,**paths)
    step=pipe.step("worker")
    assert step["status"]=="processed"
    assert step["model_calls"]=={"temporal":0,"asr":2,"ocr":1,"vlm":1}[mode]
    result=pipe.step("worker")
    assert result["status"]=="candidate_complete"
    assert result["artifact_ids"]==(step["artifact_id"],)
    assert result["decisions"].canonical_rubric is False
    assert result["decisions"].scientific_evidence is False
    fields={x.field_id:x for x in result["decisions"].fields}
    if mode=="ocr":
        assert fields["tema_principal"].value=="vendas"
        assert fields["texto_na_tela"].value is True
    if mode in ("temporal","vlm"):
        assert all(x.value is None for x in fields.values())


@pytest.mark.parametrize("discard_fixture",[("retain","process","all_processors","bundle_rubric")],indirect=True)
def test_fixture_pipeline_expired_lease_requires_explicit_recovery(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_jobs as module
    from tapi_gate0.asset_fixture_pipeline import FixturePipeline
    f=queue_fixture
    clock=[now_utc()]
    monkeypatch.setattr(module,"now_utc",lambda:clock[0])
    pipe=_pipeline(f,mode="header",case="header")
    spec=pipe.plan.specs[0]
    f.queue.enqueue(spec)
    lease=f.queue.claim(TENANT,"worker",job_id=spec.job_id)["lease"]
    clock[0]+=timedelta(seconds=121)
    assert pipe.step("worker")["status"]=="recovery_required"
    assert f.queue.status(TENANT,spec.job_id)["state"]=="running"
    # In this fixture no child was launched. The trusted host explicitly
    # reconciles the expired lease and later confirms stopped execution.
    f.queue.reconcile_invalidated(TENANT)
    clock[0]+=timedelta(seconds=16)
    assert pipe.step("worker")["status"]=="recovery_required"
    with pytest.raises(AssetRightsDenied,match="STALE_LEASE"):
        f.queue.finish(lease,"b"*64)
    def fail(*_):
        raise RuntimeError("retry dispatched")
    monkeypatch.setattr(FixturePipeline,"_dispatch",fail)
    with pytest.raises(RuntimeError,match="retry dispatched"):
        pipe.step("worker",retry_stopped=True)
    assert f.queue.status(TENANT,spec.job_id)["attempt"]==2


@pytest.mark.parametrize("discard_fixture",[("retain","process","all_processors","bundle_rubric")],indirect=True)
def test_fixture_pipeline_signed_revocation_and_receipt_only(queue_fixture):
    f=queue_fixture
    pipe=_pipeline(f,mode="header",case="header")
    spec=pipe.plan.specs[0]
    f.queue.enqueue(spec)
    lease=f.queue.claim(TENANT,"worker",job_id=spec.job_id)["lease"]
    f.queue.finish(lease,"b"*64)
    with pytest.raises(AssetRightsDenied,match="RECEIPT_ONLY"):
        pipe.step("worker")
    rv=f.q.f.state(2,revoked_asset_ids=(f.q.ref.target.asset_id,))
    f.q.f.svc.advance(f.q.f.anchor,TENANT,"instagram",rv)
    f.queue.resolve_anchor=lambda ref:f.q.f.pin(rv)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        pipe.step("worker")
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts))==1
        assert db.scalar(select(func.count()).select_from(payloads))==0


# A02.7.2 — shared lossless video/PCM with the same retained root.
@pytest.mark.parametrize("discard_fixture",[(),("shared_audio_only",),("shared_image_only",)],indirect=True)
def test_shared_av_requires_both_modality_scopes(queue_fixture):
    from tapi_gate0.asset_processor_results import SHARED_AV_METHOD
    f=queue_fixture
    spec=f.spec.model_copy(update={"method_version":SHARED_AV_METHOD})
    with pytest.raises(AssetRightsDenied,match="SCOPE_MISMATCH"):
        f.queue.enqueue(spec)
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(jobs))==0


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture,case",[
    (("retain","process","all_processors","bundle_rubric","shared_modalities","shared_av_complementary"),"complementary"),
    (("retain","process","all_processors","bundle_rubric","shared_modalities","shared_av_audio_only"),"audio_only"),
],indirect=["discard_fixture"])
def test_shared_av_strict_quality_rejection_no_payload(queue_fixture,case):
    """Strict mode must reject low-quality ASR, never silently complete the bundle.

    The same cases in shared_av_partial are separately tested for typed
    abstention plus the coverage guard; strict and partial are distinct contracts.
    """
    import os
    from tapi_gate0.asset_asr_fixture import ASRFixtureQualityError
    f=queue_fixture
    paths={k:os.environ.get(v) for k,v in (
        ("tessdata_dir","TAPI_OCR_TEST_TESSDATA"),("asr_model_dir","TAPI_ASR_TEST_MODEL_DIR"),
        ("vlm_model_dir","TAPI_VLM_TEST_MODEL_DIR"),("vlm_server_exe","TAPI_VLM_TEST_SERVER_EXE"))}
    if not all(paths.values()):
        pytest.skip("explicit shared AV native opt-ins required")
    pipe=_pipeline(f,mode="shared_av",case=case,**paths)
    assert [pipe.step("worker")["processor"] for _ in range(2)]==["temporal","ocr"]
    with pytest.raises(ASRFixtureQualityError,match="ASR_FIXTURE_WER_GATE") as caught:
        pipe.step("worker")
    assert caught.value.quality["wer"]>0.50
    assert caught.value.quality["asr_calls"]==1
    # A failed strict ASR adapter may retain a fenced running lease for
    # explicit reconciliation, but cannot persist its result or start VLM.
    audio_job=pipe.plan.specs[2]
    row=f.queue.status(TENANT,audio_job.job_id)
    assert row["receipt_sha256"] is None and row["state"]=="running"
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==2
        assert db.scalar(select(func.count()).select_from(attempts))==3
        assert db.scalar(select(func.count()).select_from(jobs))==3


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture,case",[
    (("retain","process","all_processors","bundle_rubric","shared_modalities","shared_av_inventory"),"inventory"),
    (("retain","process","all_processors","bundle_rubric","shared_modalities","shared_av_silence"),"silence"),
    *((("retain","process","all_processors","bundle_rubric","shared_modalities","shared_av_"+case),case)
      for case in ("agreement","conflict","screen_only","tone_negative")),
],indirect=["discard_fixture"])
def test_shared_av_native_pipeline(queue_fixture,case):
    import os
    from tapi_gate0.asset_candidate_evidence import assemble_candidate_bundle
    from tapi_gate0.asset_candidate_fusion import evaluate_shared_av_ablation,evaluate_shared_av_coverage_guard
    from tapi_gate0.asset_shared_av_fixture import RECIPES
    f=queue_fixture
    paths={k:os.environ.get(v) for k,v in (
        ("tessdata_dir","TAPI_OCR_TEST_TESSDATA"),("asr_model_dir","TAPI_ASR_TEST_MODEL_DIR"),
        ("vlm_model_dir","TAPI_VLM_TEST_MODEL_DIR"),("vlm_server_exe","TAPI_VLM_TEST_SERVER_EXE"))}
    if not all(paths.values()):
        pytest.skip("explicit shared AV native opt-ins required")
    pipe=_pipeline(f,mode="shared_av",case=case,**paths)
    source=pipe._shared.source
    speech,screen=RECIPES[case]
    spoken=speech not in ("silence","tone")
    visible=screen=="sales"
    assert source.container_sha256==f.q.ref.target.sha256
    assert source.container_sha256!=source.frame_sha256!=source.frame_png_sha256
    artifacts=[]
    for processor in ("temporal","ocr","asr_vad","vlm"):
        step=pipe.step("worker")
        assert step["status"]=="processed" and step["processor"]==processor
        expected={"temporal":0,"ocr":1,"asr_vad":2 if spoken else int(speech=="tone"),
                  "vlm":int(visible)}
        assert step["model_calls"]==expected[processor]
        metrics=step["decode_resources"]
        assert 0<metrics["peak_job_commit_bytes"]<=512*1024*1024
        assert 0<=metrics["cpu_user_ms"]<=10000 and metrics["wall_ms"]>0
        if processor in ("asr_vad","vlm"):
            assert step["model_resources"]["wall_ms"]>0
        else:
            assert step["model_resources"] is None
        if processor=="ocr":
            assert 0<step["ocr_resources"]["peak_job_commit_bytes"]<=512*1024*1024
            assert step["ocr_resources"]["wall_ms"]>0
        else:
            assert step["ocr_resources"] is None
        assert step["step_wall_ms"]>=metrics["wall_ms"]
        if processor=="asr_vad":
            assert step["quality"]["asr_calls"]==int(spoken)
        import json
        print("SHARED_AV_METRICS "+json.dumps({key:step[key] for key in
            ("processor","model_calls","decode_resources","model_resources","ocr_resources","step_wall_ms","quality")},sort_keys=True))
        artifacts.append(step["artifact_id"])
    result=pipe.step("worker")
    assert result["status"]=="candidate_complete"
    assert result["artifact_ids"]==tuple(artifacts)
    bundle=assemble_candidate_bundle(pipe.store,TENANT,f.q.ref.object_id,artifacts,purpose=f.spec.purpose)
    assert bundle.fingerprint()==result["decisions"].evidence_fingerprint
    by={e.observation.result.processor:e.observation for e in bundle.entries}
    assert all(r.shared_av.source==source and r.input_sha256==source.container_sha256 for r in by.values())
    assert all(r.object_id==f.q.ref.object_id and not r.canonical_rubric for r in by.values())
    assert by["temporal"].result.samples==len(source.temporal_sample_sha256)
    assert [x.current.time_ms for x in by["temporal"].result.candidates]==([1000] if visible else [])
    assert by["vlm"].result.frame.time_ms==1000
    assert by["vlm"].result.frame.frame_sha256==source.frame_sha256
    assert by["vlm"].result.frame.timeline=="resampled_uniform"
    fields={x.field_id:x for x in result["decisions"].fields}
    assert by["asr_vad"].result.state==("observed" if spoken else "abstained")
    assert by["ocr"].result.state==("observed" if visible else "abstained")
    if spoken:
        assert by["asr_vad"].result.duration_ms==(source.pcm_samples*1000+15999)//16000
    if visible:
        assert by["ocr"].result.frame==by["vlm"].result.frame
        assert fields["texto_na_tela"].value is True
        assert any(x.frame_sha256==source.frame_sha256 for x in fields["texto_na_tela"].supports)
    else:
        assert fields["texto_na_tela"].value is None
    if not spoken and not visible:
        assert all(x.value is None for x in fields.values())

    # Independent from adapter integrity: report semantic matches/misses
    # against frozen authored expectations, not the recognized transcript.
    # Do not silently convert a semantic miss into an engineering PASS.
    oracle={
        "inventory":(None,None,None,True),
        "silence":(None,None,None,None),
        "agreement":("vendas",None,None,True),
        "conflict":(None,None,None,True),
        "complementary":("vendas","salvar",True,True),
        "audio_only":(None,"salvar",True,None),
        "screen_only":("vendas",None,None,True),
        "tone_negative":(None,None,None,None),
    }
    assessed=("tema_principal","tipo_cta","tem_cta","texto_na_tela")
    expected=dict(zip(assessed,oracle[case]))
    replay=evaluate_shared_av_ablation(pipe.store,TENANT,f.q.ref.object_id,artifacts,purpose=f.spec.purpose)
    assert len(replay["arms"])==15 and replay["source_fingerprint"]==bundle.fingerprint()
    assert not replay["inference_reexecuted"] and not replay["scientific_evidence"]
    assert replay["arms"]["asr_vad+ocr+temporal+vlm"]==result["decisions"]
    assert replay==evaluate_shared_av_ablation(pipe.store,TENANT,f.q.ref.object_id,list(reversed(artifacts)),purpose=f.spec.purpose)
    from itertools import combinations
    processors=("asr_vad","ocr","temporal","vlm")
    assert set(replay["arms"])=={"+".join(a) for n in range(1,5) for a in combinations(processors,n)}
    values={}
    for arm,decision in replay["arms"].items():
        subset=set(arm.split("+"))
        for field in decision.fields:
            assert all(s.processor in subset for s in (*field.supports,*field.vetoes))
        values[arm]={f.field_id:f.value for f in decision.fields if f.field_id in assessed}
    # Temporal currently adds no semantic features; test that this does not
    # falsely look like a gain. Its provenance/measurements remain useful.
    for arm,row in values.items():
        if "temporal" in arm and "+" in arm:
            assert row==values["+".join(p for p in arm.split("+") if p!="temporal")]
    full=values["asr_vad+ocr+temporal+vlm"]
    print("SHARED_AV_ABLATION "+json.dumps({"case":case,"expected":expected,"arms":values,
        "full_wrong_nonabstained":sum(full[k] is not None and full[k]!=expected[k] for k in assessed),
        "full_missed_candidates":sum(expected[k] is not None and full[k] is None for k in assessed),
        "full_exact_match":full==expected,"reference_kind":"authored_fixture_not_independent_gold"},
        ensure_ascii=False,sort_keys=True))
    guard=evaluate_shared_av_coverage_guard(pipe.store,TENANT,f.q.ref.object_id,artifacts,purpose=f.spec.purpose)
    assert guard["baseline"]==result["decisions"] and not guard["policy_promoted"]
    guarded={f.field_id:f.value for f in guard["guarded"].fields if f.field_id in assessed}
    assert all(guarded[k] in (None,full[k]) for k in assessed)
    print("SHARED_AV_COVERAGE_GUARD "+json.dumps({"case":case,"expected":expected,
        "baseline":full,"guarded":guarded,"coverage":guard["coverage_details"],
        "suppressed_fields":guard["suppressed_fields"],
        "guarded_wrong_nonabstained":sum(guarded[k] is not None and guarded[k]!=expected[k] for k in assessed),
        "guarded_missed_candidates":sum(expected[k] is not None and guarded[k] is None for k in assessed),
        "guarded_exact_match":guarded==expected,"policy_promoted":False},ensure_ascii=False,sort_keys=True))
    assert pipe.step("worker")==result
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts))==4
        assert db.scalar(select(func.count()).select_from(payloads))==4
    print("SHARED_AV_SOURCE "+source.model_dump_json())


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[
    ("retain","process","all_processors","bundle_rubric","shared_modalities","shared_av_silence")
],indirect=True)
def test_shared_av_rejects_forged_recipe_before_spawn(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_shared_av_fixture as shared
    f=queue_fixture
    fixture=shared.prepare("silence")
    binding,_,_=shared.plan(fixture,"temporal",(None,None,None,None))
    spec=f.spec.model_copy(update={"method_version":shared.METHOD,
        "configuration_sha256":binding.configuration("temporal")})
    f.queue.enqueue(spec)
    lease=f.queue.claim(TENANT,"worker",job_id=spec.job_id)["lease"]
    forged=replace(fixture,decoder_code=fixture.decoder_code+"\nraise SystemExit(0)\n")
    monkeypatch.setattr(shared.windows,"_run_fixture_output",lambda *a,**k:pytest.fail("must deny before spawn"))
    with pytest.raises(AssetRightsDenied,match="FIXTURE_RECIPE_CHANGED"):
        shared.run(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease,
            fixture=forged,paths=(None,None,None,None))
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==0


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture",[
    ("retain","process","all_processors","bundle_rubric","shared_modalities","shared_av_silence")
],indirect=True)
def test_shared_av_rechecks_revocation_between_decode_and_finish(queue_fixture,monkeypatch):
    from tapi_gate0 import asset_shared_av_fixture as shared
    f=queue_fixture
    fixture=shared.prepare("silence")
    binding,_,_=shared.plan(fixture,"temporal",(None,None,None,None))
    spec=f.spec.model_copy(update={"method_version":shared.METHOD,
        "configuration_sha256":binding.configuration("temporal")})
    f.queue.enqueue(spec)
    lease=f.queue.claim(TENANT,"worker",job_id=spec.job_id)["lease"]
    real=shared.windows._run_fixture_output
    def revoke_after_decode(*a,**kw):
        result=real(*a,**kw)
        rv=f.q.f.state(2,revoked_asset_ids=(f.q.ref.target.asset_id,))
        f.q.f.svc.advance(f.q.f.anchor,TENANT,"instagram",rv)
        f.queue.resolve_anchor=lambda ref:f.q.f.pin(rv)
        return result
    monkeypatch.setattr(shared.windows,"_run_fixture_output",revoke_after_decode)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        shared.run(f.queue,f.q.vault,DerivedPayloadStore(f.queue,b"d"*32),lease,
            fixture=fixture,paths=(None,None,None,None))
    assert f.queue.status(TENANT,spec.job_id)["receipt_sha256"] is None
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads))==0


@pytest.mark.parametrize("discard_fixture",[
    ("retain","process","all_processors","bundle_rubric","shared_modalities")
],indirect=True)
@pytest.mark.parametrize("case,spoken,screen,expected_topic,expected_cta",[
    ("agreement","Organize suas vendas.","Organize suas vendas","vendas",None),
    ("conflict","Calcule os custos fixos.","Organize suas vendas",None,None),
    ("complementary","Salve este conteúdo.","Organize suas vendas","vendas","salvar"),
    ("cta_conflict","Comente sua dúvida.","Salve este post",None,None),
    ("context_veto","Não salve este post.","Salve este post",None,None),
    ("split_request","Salve","este post",None,None),
    ("unrecognized_audio","Palavras sem classificação.","Organize suas vendas","vendas",None),
    ("audio_insufficient",None,"Organize suas vendas","vendas",None),
    ("audio_no_signal",None,"Organize suas vendas","vendas",None),
])
def test_shared_av_ablation_policy_and_rights(queue_fixture,case,spoken,screen,expected_topic,expected_cta,monkeypatch,record_property):
    """Persist authored surrogate observations: contract/policy test, not native inference."""
    from tapi_gate0.asset_processor_results import (SharedAVSource,SharedAVBinding,SHARED_AV_METHOD,
        ProcessorResult,ASR,Speech,Interval,OCR,Word,VLM,Frame,Temporal,Abstention,encode)
    from tapi_gate0.asset_candidate_fusion import evaluate_shared_av_ablation,evaluate_shared_av_coverage_guard
    from tapi_gate0.asset_system_one_guarded_handoff import bridge_guarded_av_to_system_one, GuardedHandoffDenied
    f=queue_fixture
    store=DerivedPayloadStore(f.queue,b"d"*32)
    src=SharedAVSource(container_sha256=f.q.ref.target.sha256,decoder_sha256="1"*64,
        rgb_stream_sha256="2"*64,pcm_sha256="3"*64,frame_sha256="4"*64,frame_png_sha256="5"*64,
        frame_count=12,pcm_samples=48000,temporal_sample_sha256=("6"*64,)*12)
    frame=Frame(time_ms=1000,frame_sha256=src.frame_sha256,timeline="resampled_uniform")
    observations=(
        (ASR(duration_ms=3000,segments=(Speech(start_ms=1000,end_ms=2000,text=spoken),),
            vad=(Interval(start_ms=900,end_ms=2100),)) if spoken is not None else
         Abstention(processor="asr_vad",reason="no_observable_signal" if case=="audio_no_signal" else "insufficient_evidence")),
        OCR(frame=frame,width=960,height=540,words=tuple(Word(text=w,box_px=(10+i*110,20,100,30))
            for i,w in enumerate(screen.split()))),
        Temporal(samples=12,threshold=0.2,candidates=()),
        VLM(frame=frame,scene="text_card",text_present="yes"),
    )
    ids=[]
    for obs in observations:
        binding=SharedAVBinding(source=src,adapter_configuration_sha256="7"*64)
        spec=f.spec.model_copy(update={"processor":obs.processor,"method_version":SHARED_AV_METHOD,
            "configuration_sha256":binding.configuration(obs.processor)})
        f.queue.enqueue(spec)
        lease=f.queue.claim(TENANT,"worker",job_id=spec.job_id)["lease"]
        result=ProcessorResult(tenant_id=TENANT,job_id=spec.job_id,object_id=spec.object_id,
            input_sha256=src.container_sha256,attempt=lease.attempt,purpose=spec.purpose,
            method_version=spec.method_version,configuration_sha256=spec.configuration_sha256,
            origin="adapter_candidate",result=obs,shared_av=binding)
        ids.append(store.finish(lease,payload=encode(result))["artifact_id"])
    with f.q.f.engine.connect() as db:
        before=db.scalar(select(func.count()).select_from(domain_events))
    replay=evaluate_shared_av_ablation(store,TENANT,f.q.ref.object_id,ids,purpose=f.spec.purpose)
    fields={x.field_id:x for x in replay["arms"]["asr_vad+ocr+temporal+vlm"].fields}
    assert fields["tema_principal"].value==expected_topic
    assert fields["tipo_cta"].value==expected_cta
    assert fields["tem_cta"].value is (True if expected_cta else None)
    assert fields["texto_na_tela"].value is True
    if case=="agreement":
        assert {s.processor for s in fields["tema_principal"].supports}=={"asr_vad","ocr"}
    if case=="conflict":
        assert fields["tema_principal"].reason=="CONFLICTING_ANCHORS"
    if case=="complementary":
        assert fields["tipo_cta"].supports[0].processor=="asr_vad"
        assert fields["tema_principal"].supports[0].processor=="ocr"
    assert len(replay["arms"])==15
    guarded=evaluate_shared_av_coverage_guard(store,TENANT,f.q.ref.object_id,ids,purpose=f.spec.purpose)
    assert guarded["baseline"]==replay["arms"]["asr_vad+ocr+temporal+vlm"]
    assert guarded["policy_promoted"] is False and not guarded["inference_reexecuted"]
    assert guarded["coverage_details"]["asr_vad"]==({"state":"abstained",
        "reason":"no_observable_signal" if case=="audio_no_signal" else "insufficient_evidence"}
        if spoken is None else {"state":"observed","reason":None})
    g={x.field_id:x for x in guarded["guarded"].fields}
    if case in ("complementary","unrecognized_audio","audio_insufficient"):
        assert g["tema_principal"].value is None and "tema_principal" in guarded["suppressed_fields"]
        assert g["tema_principal"].reason==("INCOMPLETE_MODALITY_EVIDENCE" if case=="audio_insufficient" else
            "UNCORROBORATED_THEME_WITH_OBSERVED_MODALITIES")
    else:
        assert g["tema_principal"].value==expected_topic
    assert g["tipo_cta"].value==expected_cta
    assert g["texto_na_tela"].value is True
    # The new handoff must re-read the encrypted, rights-checked artifacts.
    # No supplied fusion report or earlier receipt can grant authority.
    handoff=bridge_guarded_av_to_system_one(store,TENANT,f.q.ref.object_id,ids,purpose=f.spec.purpose)
    assert handoff["source_fingerprint"]==guarded["source_fingerprint"]
    assert handoff==bridge_guarded_av_to_system_one(store,TENANT,f.q.ref.object_id,list(reversed(ids)),purpose=f.spec.purpose)
    projected={x["field_id"]:x for x in handoff["candidate_fields"]}
    for name,row in projected.items():
        assert (row["value"],row["state"])==(g[name].value,g[name].state)
        assert row["suppressed_by_guard"] is (name in guarded["suppressed_fields"])
        assert row["support_count"]==len(g[name].supports)
        assert len(row["provenance_sha256"])==64
    assert handoff["status"]==("PARTIAL_GUARDED_CANDIDATES_ONLY" if case=="audio_insufficient" else "GUARDED_CANDIDATES_ONLY")
    assert handoff["system_one_e1_text_observations_created"]==0
    assert handoff["scientific_admissions_created"]==0
    assert handoff["studio_write_allowed"] is False
    assert handoff["production_approved"] is False
    with pytest.raises(GuardedHandoffDenied,match="FOUR_DISTINCT_ARTIFACTS_REQUIRED"):
        bridge_guarded_av_to_system_one(store,TENANT,f.q.ref.object_id,ids[1:],purpose=f.spec.purpose)
    # DEC-008: the same live encrypted selection and current rights must
    # produce a digest-only technical ledger, not a new science decision.
    plan=ProtectedAVReviewPlan(content_id=f.q.ref.target.content_id,
        object_id=f.q.ref.object_id,artifact_ids=tuple(ids))
    kwargs=dict(tenant=TENANT,actor="fixture-operator",run_id="av-review",plan=plan)
    first=execute_protected_av_review_step(store,**kwargs)
    assert (first["revision"],first["next_node"])==(1,"retrieve")
    if case=="agreement":
        # Test drift of the projected semantics, not an alternative grant.
        # A changed fingerprint must prevent advancement of the old run.
        from tapi_gate0 import agent_graph_protected_av_dec008 as review
        project=review._project_guarded
        with monkeypatch.context() as m:
            def changed(guard):
                return {**project(guard),"source_fingerprint":"f"*64}
            m.setattr(review,"_project_guarded",changed)
            with pytest.raises(ProtectedAVReviewDenied,match="SOURCE_DRIFT_RESTART_REQUIRED"):
                execute_protected_av_review_step(store,**kwargs)
        with f.q.f.engine.connect() as db:
            assert db.scalar(select(func.count()).select_from(agent_graph_events))==1
        with pytest.raises(AgentCheckpointDenied,match="RUN_ID_CONFLICT"):
            execute_protected_av_review_step(store,**{**kwargs,"actor":"another-actor"})
        wrong=plan.model_copy(update={"content_id":"unrelated.post"})
        with pytest.raises(ProtectedAVReviewDenied,match="CANDIDATE_SCOPE_MISMATCH"):
            execute_protected_av_review_step(store,**{**kwargs,"run_id":"wrong-content","plan":wrong})
        with f.q.f.engine.connect() as db:
            assert db.scalar(select(func.count()).select_from(agent_graph_runs))==1
    final=execute_protected_av_review(store,**kwargs)
    assert final["mode"]=="av_candidate_review"
    assert (final["status"],final["revision"])==(
        ("ABSTAINED",3) if case=="audio_insufficient" else ("TRACE_RECORDED",4))
    assert not any(final[k] for k in (
        "rights_verified","scientifically_validated","studio_write_allowed",
        "publication_allowed","production_approved","global_gates_released"))
    assert execute_protected_av_review_step(store,**kwargs)==final
    with f.q.f.engine.connect() as db:
        events=db.execute(select(agent_graph_events)).mappings().all()
        assert len(events)==final["revision"]
        assert all(len(e["receipt_sha256"])==64 for e in events)
        assert spoken is None or spoken not in str(events)
        assert screen not in str(events)
    missing=evaluate_shared_av_coverage_guard(store,TENANT,f.q.ref.object_id,ids[1:],purpose=f.spec.purpose)
    m={x.field_id:x for x in missing["guarded"].fields}
    assert missing["coverage"]["asr_vad"]=="missing"
    assert all(m[k].value is None for k in ("tema_principal","tipo_cta","tem_cta"))
    assert m["texto_na_tela"].value is True
    no_vlm=evaluate_shared_av_coverage_guard(store,TENANT,f.q.ref.object_id,ids[:-1],purpose=f.spec.purpose)
    assert no_vlm["coverage"]["vlm"]=="missing"
    assert all(x.value is None for x in no_vlm["guarded"].fields)
    with pytest.raises(AssetRightsDenied,match="SHARED_AV_COMPLETE_REQUIRED"):
        evaluate_shared_av_ablation(store,TENANT,f.q.ref.object_id,ids[:-1],purpose=f.spec.purpose)
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(domain_events))==before
        assert db.scalar(select(func.count()).select_from(attempts))==4
    rv=f.q.f.state(2,revoked_asset_ids=(f.q.ref.target.asset_id,))
    f.q.f.svc.advance(f.q.f.anchor,TENANT,"instagram",rv)
    f.queue.resolve_anchor=lambda ref:f.q.f.pin(rv)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        evaluate_shared_av_ablation(store,TENANT,f.q.ref.object_id,ids,purpose=f.spec.purpose)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        evaluate_shared_av_coverage_guard(store,TENANT,f.q.ref.object_id,ids[1:],purpose=f.spec.purpose)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        bridge_guarded_av_to_system_one(store,TENANT,f.q.ref.object_id,ids,purpose=f.spec.purpose)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        execute_protected_av_review_step(store,**kwargs)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        execute_protected_av_review_step(store,**{**kwargs,"run_id":"revoked-new"})
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(agent_graph_events))==final["revision"]
        assert db.scalar(select(func.count()).select_from(agent_graph_runs))==1
    # Presentation-only: serialize observations authored by this fixture and
    # actual policy/ledger outcomes after every rights assertion has passed.
    import json
    record_property("demo_av_case", json.dumps({
        "case":case,"authored_audio":spoken,"authored_screen":screen,
        "coverage":handoff["coverage"],"fields":[{**row,
            "baseline_value":fields[row["field_id"]].value,
            "reason":g[row["field_id"]].reason} for row in handoff["candidate_fields"]],
        "source_fingerprint":handoff["source_fingerprint"],"ledger_status":final["status"],
        "ledger_revision":final["revision"],"chain_sha256":final["chain_sha256"],
        "revocation_denied":True,"native_inference":False}, ensure_ascii=False))


@_WINDOWS_JOB
@pytest.mark.parametrize("discard_fixture,case",[
    (("retain","process","all_processors","bundle_rubric","shared_modalities","shared_av_complementary"),"complementary"),
    (("retain","process","all_processors","bundle_rubric","shared_modalities","shared_av_audio_only"),"audio_only"),
    *((("retain","process","all_processors","bundle_rubric","shared_modalities","shared_av_"+case),case)
      for case in ("inventory","silence","agreement","conflict","screen_only","tone_negative")),
],indirect=["discard_fixture"])
def test_partial_shared_av_native_pipeline(queue_fixture,case):
    import os,json
    from tapi_gate0.asset_candidate_evidence import assemble_candidate_bundle
    from tapi_gate0.asset_candidate_fusion import (evaluate_shared_av_coverage_guard,
        evaluate_candidate_bundle,evaluate_shared_av_ablation)
    from tapi_gate0.asset_processor_results import PARTIAL_QUALITY,encode
    from tapi_gate0.asset_shared_av_routing import row_from_replay
    from tapi_gate0.asset_candidate_fusion import evaluate_shared_av_routing_replay
    f=queue_fixture
    paths={k:os.environ.get(v) for k,v in (
        ("tessdata_dir","TAPI_OCR_TEST_TESSDATA"),("asr_model_dir","TAPI_ASR_TEST_MODEL_DIR"),
        ("vlm_model_dir","TAPI_VLM_TEST_MODEL_DIR"),("vlm_server_exe","TAPI_VLM_TEST_SERVER_EXE"))}
    if not all(paths.values()):
        pytest.skip("explicit partial shared AV native opt-ins required")
    pipe=_pipeline(f,mode="shared_av_partial",case=case,**paths)
    ids=[]
    metrics={}
    for processor in ("temporal","ocr","asr_vad","vlm"):
        step=pipe.step("worker")
        assert step["status"]=="processed" and step["processor"]==processor
        metrics[processor]=step
        if processor=="asr_vad" and case in ("complementary","audio_only"):
            assert step["quality"]["reason"]=="ASR_FIXTURE_WER_GATE"
            assert step["quality"]["wer"]>0.50
            assert "hypothesis_sha256" not in step["quality"]
        ids.append(step["artifact_id"])
    result=pipe.step("worker")
    failed=case in ("complementary","audio_only")
    assert result["status"]==("candidate_partial" if failed else "candidate_complete_guarded")
    assert result["asr_fixture_quality_gate_passed"] is (not failed)
    assert result["semantic_quality_validated"] is False
    if failed:
        assert result["coverage_details"]["asr_vad"]=={"state":"abstained","reason":"fixture_quality_rejected"}
        assert result["quality_rejections"]["asr_vad"]["wer"]>0.50
    else:
        assert result["quality_rejections"]=={}
    bundle=assemble_candidate_bundle(pipe.store,TENANT,f.q.ref.object_id,ids,purpose=f.spec.purpose)
    assert all(e.observation.shared_av.quality_policy==PARTIAL_QUALITY for e in bundle.entries)
    audio=next(e.observation for e in bundle.entries if e.observation.result.processor=="asr_vad")
    if failed:
        assert audio.result.state=="abstained" and audio.shared_av_quality_rejection is not None
        assert b'"segments"' not in encode(audio) and b'"hypothesis_sha256"' not in encode(audio)
    else:
        assert audio.shared_av_quality_rejection is None
    for evaluator in (evaluate_candidate_bundle,evaluate_shared_av_ablation):
        with pytest.raises(AssetRightsDenied,match="PARTIAL_REQUIRES_COVERAGE_GUARD"):
            evaluator(pipe.store,TENANT,f.q.ref.object_id,ids,purpose=f.spec.purpose)
    guard=evaluate_shared_av_coverage_guard(pipe.store,TENANT,f.q.ref.object_id,ids,purpose=f.spec.purpose)
    assert guard["guarded"]==result["decisions"]
    assert guard["quality_rejections"]==result["quality_rejections"]
    fields={x.field_id:x for x in result["decisions"].fields}
    if failed:
        assert all(fields[k].value is None for k in ("tema_principal","tipo_cta","tem_cta"))
        assert fields["texto_na_tela"].value is (True if case=="complementary" else None)
    replay=evaluate_shared_av_routing_replay(pipe.store,TENANT,f.q.ref.object_id,ids,purpose=f.spec.purpose)
    assert replay==evaluate_shared_av_routing_replay(pipe.store,TENANT,f.q.ref.object_id,list(reversed(ids)),purpose=f.spec.purpose)
    assert replay["arms"]["asr_vad+ocr+temporal+vlm"]["guarded"]==result["decisions"]
    assert replay["full_quality_rejections"]==result["quality_rejections"]
    for arm,report in replay["arms"].items():
        assert all(s.processor in arm.split("+") for field in report["guarded"].fields
                   for s in (*field.supports,*field.vetoes))
    with pytest.raises(AssetRightsDenied,match="SHARED_AV_COMPLETE_REQUIRED"):
        evaluate_shared_av_routing_replay(pipe.store,TENANT,f.q.ref.object_id,ids[:-1],purpose=f.spec.purpose)
    print("SHARED_AV_ROUTING "+json.dumps(row_from_replay(case,replay,metrics),ensure_ascii=True,sort_keys=True))
    assert pipe.step("worker")==result
    print("SHARED_AV_PARTIAL "+json.dumps({"case":case,"status":result["status"],
        "quality_rejections":result["quality_rejections"],"coverage":result["coverage_details"],
        "values":{k:fields[k].value for k in ("tema_principal","tipo_cta","tem_cta","texto_na_tela")},
        "semantic_quality_validated":False},ensure_ascii=False,sort_keys=True))
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts))==4
        assert db.scalar(select(func.count()).select_from(payloads))==4
    rv=f.q.f.state(2,revoked_asset_ids=(f.q.ref.target.asset_id,))
    f.q.f.svc.advance(f.q.f.anchor,TENANT,"instagram",rv)
    f.queue.resolve_anchor=lambda ref:f.q.f.pin(rv)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        evaluate_shared_av_coverage_guard(pipe.store,TENANT,f.q.ref.object_id,ids,purpose=f.spec.purpose)
    with pytest.raises(AssetRightsDenied,match="ASSET_RIGHTS_REVOKED"):
        evaluate_shared_av_routing_replay(pipe.store,TENANT,f.q.ref.object_id,ids,purpose=f.spec.purpose)
