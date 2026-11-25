"""Tests use only disposable databases and an explicitly temporary URL."""
from pathlib import Path
from contextlib import closing
import sqlite3
import shutil

import pytest
from alembic import command
from alembic.config import Config
from tapi_gate0.discovery_backup import _inventory, _readonly, _sha256
from tapi_gate0.sa_store import SqlDomainStore, engine_for
from scripts import a02_operational_upgrade as op

TENANT = "upgrade-fixture"


@pytest.fixture(params=[0,1,2,3],ids=["0013","0014","0015","0016"])
def target(tmp_path,monkeypatch,request):
    root=Path(__file__).resolve().parents[1]
    shutil.copytree(root/"migrations",tmp_path/"migrations")
    shutil.copy2(root/"alembic.ini",tmp_path/"alembic.ini")
    if request.param==3:
        shutil.copytree(root/"src",tmp_path/"src")
    db=tmp_path/"live-fixture.sqlite3"
    url="sqlite:///"+str(db)
    monkeypatch.setenv("TAPI_DATABASE_URL",url)
    cfg=Config(str(tmp_path/"alembic.ini"))
    cfg.set_main_option("script_location",str(tmp_path/"migrations"))
    command.upgrade(cfg,"0015_asset_jobs" if request.param==3 else "0014_asset_lineage" if request.param==2 else op.NEW if request.param==1 else op.OLD)
    engine=engine_for(url)
    try:
        SqlDomainStore(engine).create_tenant(TENANT,"Fixture")
    finally:
        engine.dispose()
    return tmp_path,db,url,request.param


def inventory(db):
    with closing(_readonly(db)) as conn:
        return _inventory(conn,TENANT)


def run(target,**kwargs):
    root,db,url,mode=target
    return op.upgrade(root,url,TENANT,"pre-0013.sqlite3",stopped=True,lineage=mode==1,jobs=mode==2,payloads=mode==3,**kwargs)


def test_operational_upgrade_preserves_every_legacy_table(target):
    root,db,url,mode=target
    before=inventory(db)
    result=run(target)
    after=inventory(db)
    assert result["status"]=="A02_OPERATIONAL_MIGRATION_VERIFIED"
    assert result["backup_restore_verified"] and result["legacy_logical_contents_match"]
    assert result["real_grants_created"]==0 and not result["media_enabled"]
    assert after["migration_versions"]==["0016_asset_derived_payloads" if mode==3 else "0015_asset_jobs" if mode==2 else "0014_asset_lineage" if mode==1 else op.NEW]
    if mode==3:
        assert result["fresh_payload_rehearsal_verified"] is True
        assert result["new_empty_tables"]==["asset_derived_payloads"]
    assert all(after["table_content_sha256"][t]==h for t,h in before["table_content_sha256"].items() if t!="alembic_version")
    backup=root/"artifacts"/"private"/result["backup_name"]
    assert inventory(backup)==before and _sha256(backup)==result["backup_sha256"]
    with pytest.raises(ValueError,match="BASE_REVISION_REQUIRED"):
        op.upgrade(root,url,TENANT,"another.sqlite3",stopped=True,lineage=mode==1,jobs=mode==2,payloads=mode==3)


def test_precommit_failure_rolls_back_actual_alembic_ddl(target,monkeypatch):
    root,db,url,mode=target
    before=inventory(db)
    def fail(*args):
        raise ValueError("A02_UPGRADE_FIXTURE_POSTCHECK")
    monkeypatch.setattr(op,"_verify",fail)
    with pytest.raises(ValueError,match="FIXTURE_POSTCHECK"):
        run(target)
    assert inventory(db)==before
    assert inventory(root/"artifacts"/"private"/"pre-0013.sqlite3")==before


def test_changes_after_backup_are_detected_before_upgrade(target,monkeypatch):
    root,db,url,mode=target
    real=op.backup_and_restore_drill
    def change(*args,**kwargs):
        report=real(*args,**kwargs)
        with closing(sqlite3.connect(db)) as conn:
            conn.execute("UPDATE tenants SET name='changed' WHERE tenant_id=?",(TENANT,))
            conn.commit()
        return report
    monkeypatch.setattr(op,"backup_and_restore_drill",change)
    with pytest.raises(ValueError,match="LIVE_CHANGED_AFTER_BACKUP"):
        run(target)
    assert inventory(db)["migration_versions"]==["0015_asset_jobs" if mode==3 else "0014_asset_lineage" if mode==2 else op.NEW if mode==1 else op.OLD]


def test_requires_stopped_writers_and_refuses_nonexistent_database(target):
    root,db,url,mode=target
    before=inventory(db)
    with pytest.raises(ValueError,match="ALL_WRITERS_MUST_STOP"):
        op.upgrade(root,url,TENANT,"pre.sqlite3",stopped=False,lineage=mode==1,jobs=mode==2,payloads=mode==3)
    missing=root/"absent.sqlite3"
    with pytest.raises(ValueError,match="DATABASE_MUST_EXIST"):
        op.upgrade(root,"sqlite:///"+str(missing),TENANT,"pre.sqlite3",stopped=True,lineage=mode==1,jobs=mode==2,payloads=mode==3)
    assert not missing.exists() and inventory(db)==before
    assert not (root/"artifacts").exists()


@pytest.mark.parametrize("target",[3],indirect=True)
def test_payloads_rehearsal_failure_blocks_before_writer(target,monkeypatch):
    root,db,url,mode=target
    before=inventory(db)
    monkeypatch.setattr(op,"rehearsal",lambda *a,**k:{"status":"BLOCKED"})
    with pytest.raises(ValueError,match="PAYLOAD_REHEARSAL_NOT_VERIFIED"):
        run(target)
    assert inventory(db)==before
    assert inventory(root/"artifacts"/"private"/"pre-0013.sqlite3")==before


def test_payloads_cli_requires_pinned_preflight(monkeypatch,capsys):
    monkeypatch.setattr(op,"check_checkout",lambda *a:None)
    def never(*a,**k):
        pytest.fail("upgrade invoked without verified preflight")
    monkeypatch.setattr(op,"upgrade",never)
    args=["--expected-head","a"*40,"--backup-name","new.sqlite3",
          "--confirm-all-writers-stopped","--apply-0016"]
    assert op.main(args)==2
    assert "PAYLOAD_PREFLIGHT_REQUIRED" in capsys.readouterr().out
    def reject(*a,**k):
        raise ValueError("A02_PREFLIGHT_REPORT_PIN_MISMATCH")
    monkeypatch.setattr(op,"verify_report",reject)
    assert op.main(args+["--preflight-report","bad","--preflight-sha256","0"*64])==2
    assert "REPORT_PIN_MISMATCH" in capsys.readouterr().out
