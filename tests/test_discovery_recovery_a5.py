"""Offline recovery preserves history, reservations and audit evidence."""
import json
from datetime import timedelta
import pytest
from sqlalchemy import insert, select
from tapi_gate0.connectors import ConnectorError, Platform
from tapi_gate0.discovery_history import cycle_leases, cycle_lease
from tapi_gate0.discovery_recovery import inspect_recovery, recover_orphan_lease, review_failure
from tapi_gate0.identity import Principal
from tapi_gate0.ingestion import ingestion_runs
from tapi_gate0.sa_store import domain_events, outbox
from tapi_gate0.storage import now_utc
from test_discovery_history_a5 import checkpoint, cycle, provider, switches
from test_discovery_batch_a4 import db, SOURCES, TENANT

ADMIN = Principal(actor_id="fixture-admin", tenant_id=TENANT, role="admin")
KEY = "a5history-20261112120000-1234abcd"


def test_review_failed_run_preserves_checkpoint_and_quota(tmp_path):
    engine,store=db(tmp_path)
    ok,calls,client=provider();bad,bad_calls,bad_client=provider(fail=True)
    try:
        cycle(store,ok); before=checkpoint(engine)
        failed=cycle(store,bad); run=failed["cycle_key"]+"-01"
        assert cycle(store,ok)["status"]=="NO_DUE_AUTHORIZED_SOURCES"
        assert not inspect_recovery(engine,TENANT)["latest_a5_blocked_runs"][0]["reviewed"]
        with pytest.raises(ConnectorError,match="BD_RECOVERY_ADMIN_REQUIRED"):
            review_failure(engine,Principal(actor_id="reader",tenant_id=TENANT,role="viewer"),run,stopped=True)
        with pytest.raises(ConnectorError,match="BD_RECOVERY_STOP_ALL_INGESTION_REQUIRED"):
            review_failure(engine,ADMIN,run,stopped=False)
        with cycle_lease(engine,TENANT,"fixture-active"):
            with pytest.raises(ConnectorError,match="BD_RECOVERY_INGESTION_ACTIVE"):
                review_failure(engine,ADMIN,run,stopped=True)
        report=review_failure(engine,ADMIN,run,stopped=True)
        assert report["quota_reservation_preserved"] and report["external_data_accessed"] is False
        assert checkpoint(engine)==before and "CURSOR_ONE" not in json.dumps(report)
        assert len(calls)==1 and len(bad_calls)==1
        with engine.connect() as conn:
            assert conn.execute(select(ingestion_runs.c.status).where(ingestion_runs.c.run_key==run)).scalar_one()=="failed"
            assert conn.execute(select(domain_events.c.event_type).where(domain_events.c.aggregate_type=="bd_recovery")).scalar_one()=="business_discovery.failed_run_reviewed"
        with pytest.raises(ConnectorError,match="BD_RECOVERY_RUN_NOT_LATEST_UNREVIEWED"):
            review_failure(engine,ADMIN,run,stopped=True)
        assert cycle(store,ok,budget=8)["status"]=="NO_DUE_AUTHORIZED_SOURCES"
        assert cycle(store,ok)["batch"]["counts"]["new_records"]==2
        assert ".after(CURSOR_ONE)" in calls[-1]
    finally:
        client.close();bad_client.close();engine.dispose()


def test_restart_history_preserves_records_and_restarts_from_top(tmp_path):
    engine,store=db(tmp_path)
    ok,calls,client=provider();bad,_,bad_client=provider(loop=True)
    try:
        cycle(store,ok); failed=cycle(store,bad);run=failed["cycle_key"]+"-01"
        assert failed["status"]=="BATCH_STOPPED_ON_SOURCE_FAILURE"
        report=review_failure(engine,ADMIN,run,stopped=True,restart_history=True)
        assert report["previous_checkpoint_pages"]==1 and checkpoint(engine) is None
        assert "CURSOR_ONE" not in json.dumps(report)
        result=cycle(store,ok)
        assert result["batch"]["counts"]["new_records"]==0
        assert ".after(" not in calls[-1]
        assert result["tenant_coverage_after"]["unique_media_ids"]==2
    finally:
        client.close();bad_client.close();engine.dispose()


def test_orphan_recovery_matches_exact_key_preserves_reservations_and_audits(tmp_path):
    engine,store=db(tmp_path)
    try:
        run=KEY+"-01"
        with engine.begin() as conn:
            conn.execute(insert(cycle_leases).values(tenant_id=TENANT,cycle_key=KEY,started_at=(now_utc()-timedelta(hours=1)).isoformat()))
            conn.execute(insert(ingestion_runs).values(tenant_id=TENANT,run_key=run,platform=Platform.INSTAGRAM.value,source_account_id=SOURCES[0][1],requested_at=now_utc().isoformat(),status="reserved"))
        assert inspect_recovery(engine,TENANT)["reserved_runs"]==1
        with pytest.raises(ConnectorError,match="BD_RECOVERY_LEASE_MISMATCH"):
            recover_orphan_lease(engine,ADMIN,KEY[:-1]+"e",stopped=True)
        report=recover_orphan_lease(engine,ADMIN,KEY,stopped=True)
        assert report["abandoned_runs"]==[{"run_key":run,"observations_recorded":0}]
        assert inspect_recovery(engine,TENANT)["lease"] is None
        with engine.connect() as conn:
            row=conn.execute(select(ingestion_runs).where(ingestion_runs.c.run_key==run)).mappings().one()
            assert row["status"]=="failed" and row["reason_code"]=="BD_ORPHANED_RUN_OPERATOR_RECOVERY"
            event=conn.execute(select(domain_events).where(domain_events.c.event_type=="business_discovery.orphan_lease_recovered")).mappings().one()
            assert conn.execute(select(outbox.c.seq).where(outbox.c.seq==event["seq"])).scalar_one()==event["seq"]
        assert not inspect_recovery(engine,TENANT)["latest_a5_blocked_runs"][0]["reviewed"]
    finally:
        engine.dispose()


def test_orphan_recovery_rejects_recent_lease_and_unrelated_reservation(tmp_path):
    engine,store=db(tmp_path)
    try:
        with cycle_lease(engine,TENANT,KEY):
            with pytest.raises(ConnectorError,match="BD_RECOVERY_LEASE_TOO_RECENT"):
                recover_orphan_lease(engine,ADMIN,KEY,stopped=True)
        with engine.begin() as conn:
            conn.execute(insert(cycle_leases).values(tenant_id=TENANT,cycle_key=KEY,started_at=(now_utc()-timedelta(hours=1)).isoformat()))
            conn.execute(insert(ingestion_runs).values(tenant_id=TENANT,run_key="unrelated-run",platform=Platform.INSTAGRAM.value,source_account_id=SOURCES[0][1],requested_at=now_utc().isoformat(),status="reserved"))
        with pytest.raises(ConnectorError,match="BD_RECOVERY_UNRELATED_RESERVATION"):
            recover_orphan_lease(engine,ADMIN,KEY,stopped=True)
        assert inspect_recovery(engine,TENANT)["reserved_runs"]==1
        assert inspect_recovery(engine,TENANT)["lease"]["cycle_key"]==KEY
    finally:
        engine.dispose()
