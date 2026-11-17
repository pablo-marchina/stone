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


def test_migration_rehearsal_preserves_disposable_0012_backup(tmp_path,monkeypatch):
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
    command.upgrade(config,drill.OLD)
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
    result=drill.rehearsal(tmp_path,db.name,digest,TENANT)
    assert result["status"]=="A02_MIGRATION_REHEARSAL_VERIFIED"
    assert result["backup_unchanged"] and result["empty_downgrade_verified"]
    assert _sha256(db)==digest
    with pytest.raises(ValueError,match="BACKUP_MISMATCH"):
        drill.rehearsal(tmp_path,db.name,"0"*64,TENANT)
