"""A03 snapshot tests using disposable migrated SQLite."""
from pathlib import Path
from contextlib import closing
from datetime import datetime,timezone,timedelta
import sqlite3
import pytest
from alembic import command
from alembic.config import Config
from tapi_gate0.sa_store import engine_for,SqlDomainStore
from tapi_gate0.discovery_backup import _sha256
from tapi_gate0.discovery_expansion_capacity import inspect,RESERVATION

TENANT="capacity-fixture"

@pytest.fixture
def db(tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[1]
    path=tmp_path/"capacity.sqlite3"
    url="sqlite:///"+str(path)
    monkeypatch.setenv("TAPI_DATABASE_URL",url)
    cfg=Config(str(root/"alembic.ini"))
    cfg.set_main_option("script_location",str(root/"migrations"))
    command.upgrade(cfg,"0016_asset_derived_payloads")
    e=engine_for(url)
    try:
        SqlDomainStore(e).create_tenant(TENANT,"Fixture")
        SqlDomainStore(e).create_tenant("other","Other")
    finally:
        e.dispose()
    return path,url

def test_capacity_empty_snapshot_is_not_authorization(db):
    path,url=db
    before=_sha256(path)
    r=inspect(url,TENANT)
    assert r["technical_inventory"]["unique_media_ids"]==0
    assert r["technical_collection_reference"]["raw_post_gap"]==2000
    assert r["technical_collection_reference"]["optimistic_minimum_history_runs"]==50
    assert r["local_daily_reservations"]["history_run_slots_if_no_new_identity"]==20
    assert r["scientific_target_assessed"] is False and not r["execution_authorized"]
    assert _sha256(path)==before

def test_capacity_counts_reservations_not_provider_quota_and_isolates_tenant(db):
    path,url=db
    now=datetime.now(timezone.utc)
    with closing(sqlite3.connect(path)) as conn:
        for tenant,source in ((TENANT,"12345"),("other","67890")):
            conn.execute("INSERT INTO ingestion_source_grants (tenant_id,platform,source_account_id,approval_reference,approved_by,approved_at,expires_at,technical_verified_at,enabled) VALUES (?,?,?,?,?,?,?,?,?)",
                (tenant,"instagram",source,"fixture-approval","fixture",(now-timedelta(days=2)).isoformat(),(now+timedelta(days=1)).isoformat(),(now-timedelta(days=1)).isoformat(),1))
            conn.execute("INSERT INTO ingestion_runs (tenant_id,run_key,platform,source_account_id,requested_at,status,new_records,refreshed_records,duplicate_records) VALUES (?,?,?,?,?,?,?,?,?)",
                (tenant,"fixture-run","instagram",source,now.isoformat(),"completed",0,0,0))
            conn.execute("INSERT INTO domain_events (event_id,tenant_id,aggregate_type,aggregate_id,event_type,aggregate_version,occurred_at,payload) VALUES (?,?,?,?,?,?,?,?)",
                (tenant+"-event",tenant,"bd_identity","fixture-attempt",RESERVATION,1,now.isoformat(),"{}"))
        conn.commit()
    before=_sha256(path)
    r=inspect(url,TENANT)
    assert r["technical_inventory"]["active_technically_verified_metadata_grants"]==1
    assert r["active_grant_frontiers"]["no_checkpoint"]==1
    assert r["local_daily_reservations"]["conservative_units"]==5
    assert r["local_daily_reservations"]["remaining_units"]==75
    assert not r["local_daily_reservations"]["provider_quota_verified"]
    assert "source_account_id" not in str(r) and "fixture-approval" not in str(r)
    assert _sha256(path)==before

def test_capacity_refuses_remote_missing_unknown(db,tmp_path):
    path,url=db
    with pytest.raises(ValueError,match="SQLITE_ONLY"):
        inspect("postgresql+psycopg://localhost/private",TENANT)
    with pytest.raises(ValueError,match="TENANT_UNKNOWN"):
        inspect(url,"unknown")
    missing=tmp_path/"missing.sqlite3"
    with pytest.raises(ValueError,match="DATABASE_MUST_EXIST"):
        inspect("sqlite:///"+str(missing),TENANT)
    assert not missing.exists()
