"""Disposable migrated SQLite only."""
from pathlib import Path
import sqlite3
from contextlib import closing
import pytest
from alembic import command
from alembic.config import Config
from tapi_gate0.sa_store import engine_for,SqlDomainStore
from tapi_gate0.discovery_backup import _sha256
from tapi_gate0.asset_operational_readiness import inspect,TABLES

TENANT="readiness-fixture"

@pytest.fixture
def db(tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[1]
    path=tmp_path/"readiness.sqlite3"
    url="sqlite:///"+str(path)
    monkeypatch.setenv("TAPI_DATABASE_URL",url)
    cfg=Config(str(root/"alembic.ini"))
    cfg.set_main_option("script_location",str(root/"migrations"))
    command.upgrade(cfg,"0016_asset_derived_payloads")
    engine=engine_for(url)
    try:
        SqlDomainStore(engine).create_tenant(TENANT,"Fixture")
        SqlDomainStore(engine).create_tenant("other","Other")
    finally:
        engine.dispose()
    return path,url

def test_readiness_empty_migrated_tenant_no_mutation(db):
    path,url=db
    before=_sha256(path)
    report=inspect(url,TENANT)
    assert _sha256(path)==before
    assert report["status"]=="A02_READINESS_INSPECTED_MEDIA_BLOCKED"
    assert report["tenant_registry_counts"]==dict.fromkeys(TABLES,0)
    assert report["daily_attempts"]["tenant"]==report["daily_attempts"]["global"]==0
    assert report["encrypted_payload_bytes"]["tenant"]==0
    assert "NO_TENANT_ASSET_GRANT_ROWS" in report["blockers"]
    assert not report["media_enabled"] and not report["authorization_evaluated"]
    assert not report["database_mutated"] and not report["keys_loaded"]
    assert "tenant_id" not in report and TENANT not in str(report)

def test_readiness_authority_rows_do_not_authorize_and_tenant_isolated(db):
    path,url=db
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("INSERT INTO asset_rights_authorities (tenant_id,platform,issuer_id,key_sha256,revision,claims_sha256) VALUES (?,?,?,?,?,?)",
                     ("other","instagram","authority","a"*64,1,"b"*64))
        conn.commit()
    before=_sha256(path)
    assert inspect(url,TENANT)["tenant_registry_counts"]["asset_rights_authorities"]==0
    report=inspect(url,"other")
    assert report["tenant_registry_counts"]["asset_rights_authorities"]==1
    assert "NO_TENANT_AUTHORITY_ROWS" not in report["blockers"]
    assert "INDEPENDENT_TRUST_AND_EXACT_ASSET_PERMISSIONS_NOT_EVALUATED" in report["blockers"]
    assert not report["media_enabled"] and _sha256(path)==before

def test_readiness_refuses_missing_remote_unknown_and_wrong_revision(db,tmp_path):
    path,url=db
    missing=tmp_path/"missing.sqlite3"
    with pytest.raises(ValueError,match="SQLITE_ONLY"):
        inspect("postgresql+psycopg://localhost/private",TENANT)
    with pytest.raises(ValueError,match="DATABASE_MUST_EXIST"):
        inspect("sqlite:///"+str(missing),TENANT)
    assert not missing.exists()
    with pytest.raises(ValueError,match="TENANT_UNKNOWN"):
        inspect(url,"unknown")
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("UPDATE alembic_version SET version_num='0015_asset_jobs'")
        conn.commit()
    with pytest.raises(ValueError,match="REVISION_REQUIRED"):
        inspect(url,TENANT)

def test_readiness_cli_rejects_checkout_before_inspection(monkeypatch,capsys):
    from scripts import a02_operational_readiness as cli
    def bad(*args):
        raise ValueError("BASELINE_HEAD_MISMATCH")
    monkeypatch.setattr(cli,"check_checkout",bad)
    monkeypatch.setattr(cli,"inspect",lambda *a:pytest.fail("inspection must not run"))
    assert cli.main(["--expected-head","a"*40])==2
    assert "BASELINE_HEAD_MISMATCH" in capsys.readouterr().out


def test_readiness_counts_expired_lease_without_reconciliation(db):
    from datetime import datetime,timezone
    path,url=db
    ms=int(datetime.now(timezone.utc).timestamp()*1000)
    # Minimal surrogate rows for aggregate metrics, not authentic lineage,
    # a valid job spec, or a permission grant.
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("INSERT INTO asset_lineage_nodes (tenant_id,node_id,kind,payload,purpose,state) VALUES (?,?,?,?,?,?)",
            (TENANT,"fixture-node","asset","{}","research_analysis","active"))
        conn.execute("INSERT INTO asset_processing_jobs (tenant_id,job_id,object_id,spec,state,attempt,version,created_ms,updated_ms,available_ms,worker,fence,lease_ms,deadline_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (TENANT,"fixture-job","fixture-node","{}","running",1,1,ms-2000,ms-2000,ms-2000,"fixture-worker","a"*32,ms-1000,ms+10000))
        conn.execute("INSERT INTO asset_processing_attempts (tenant_id,job_id,attempt,started_ms) VALUES (?,?,?,?)",
            (TENANT,"fixture-job",1,ms))
        conn.commit()
    before=_sha256(path)
    report=inspect(url,TENANT)
    assert report["global_active_leases"]==report["tenant_expired_active_leases"]==1
    assert report["tenant_job_states"]["running"]==report["tenant_pending"]==1
    assert report["job_history"]["tenant"]==report["job_history"]["global"]==1
    assert report["daily_attempts"]["tenant"]==report["daily_attempts"]["global"]==1
    assert "ACTIVE_GLOBAL_LEASES_REQUIRE_RECONCILIATION" in report["blockers"]
    assert "fixture-worker" not in str(report) and "fixture-job" not in str(report)
    assert _sha256(path)==before and not report["media_enabled"]
