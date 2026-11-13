"""Meta credential circuit breaker: offline, isolated tenant, no secret retention."""
import json

import httpx
import pytest
from sqlalchemy import select, func

from tapi_gate0.connectors import ConnectorError, OfficialHttp, Platform
from tapi_gate0.discovery_auth_guard import (
    AGGREGATE, AUTH_BLOCKED, AUTH_INVALID, BLOCK, RESET, auth_status,
    is_global_auth_failure, reset_after_rotation,
)
from tapi_gate0.discovery_history import cycle_lease
from tapi_gate0.discovery_technical import TechnicalDiscoveryRequest, TechnicalDiscoveryService
from tapi_gate0.identity import Principal
from tapi_gate0.ingestion import IngestionRequest, ingestion_records, ingestion_runs
from tapi_gate0.sa_store import domain_events, outbox
from test_discovery_batch_a4 import db, SOURCES, TENANT

VIEWER = "17841459971757521"
TOKEN = "fixture-secret-never-persisted"
ADMIN = Principal(actor_id="fixture-admin", tenant_id=TENANT, role="admin")


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    for flag in ("TAPI_BD_TECHNICAL_INGEST", "TAPI_OFFICIAL_METADATA_READS", "TAPI_ZERO_BILLING_CONFIRMED"):
        monkeypatch.setenv(flag,"1")
    monkeypatch.setenv("TAPI_INSTAGRAM_ACCESS_TOKEN",TOKEN)


def request(i, key):
    return TechnicalDiscoveryRequest(username=SOURCES[i][0], expected_ig_id=SOURCES[i][1],
        viewer_ig_id=VIEWER, run_key=key, page_limit=2, max_pages=1, persist_limit=2)


def manual(i, key):
    return IngestionRequest(platform=Platform.INSTAGRAM, source_account_id=SOURCES[i][1], run_key=key)


def state(engine):
    with engine.connect() as conn:
        return auth_status(conn,TENANT)


@pytest.mark.parametrize("status", [400,401,403])
def test_auth_failure_blocks_all_sources_without_extra_reservation(tmp_path,status):
    engine,store=db(tmp_path)
    calls=[]
    def fail(req):
        calls.append(req)
        return httpx.Response(status,json={"error":{"code":190,"error_subcode":463,"message":TOKEN,"fbtrace_id":TOKEN}})
    try:
        with httpx.Client(transport=httpx.MockTransport(fail)) as client:
            transport=OfficialHttp(client,instagram_version="v26.0")
            with pytest.raises(ConnectorError):
                TechnicalDiscoveryService(store).execute(TENANT,request(0,"auth-fail-001"),token=TOKEN,http=transport)
            assert state(engine)["blocked"] is True
            with pytest.raises(ConnectorError,match=AUTH_BLOCKED):
                TechnicalDiscoveryService(store).execute(TENANT,request(1,"auth-fail-002"),token=TOKEN,http=transport)
            with pytest.raises(ConnectorError,match=AUTH_BLOCKED):
                store.run(TENANT,manual(1,"manual-blocked"),http=transport)
            assert len(calls)==1
        with engine.connect() as conn:
            run=conn.execute(select(ingestion_runs)).mappings().one()
            assert run["reason_code"]==AUTH_INVALID and run["status"]=="failed"
            assert conn.execute(select(func.count()).select_from(ingestion_records)).scalar_one()==0
            event=conn.execute(select(domain_events).where(domain_events.c.aggregate_type==AGGREGATE)).mappings().one()
            assert event["event_type"]==BLOCK
            assert json.loads(event["payload"])=={"operation_key":"auth-fail-001","http_status":status,"code":190,"error_subcode":463}
            assert TOKEN not in event["payload"]
            assert conn.execute(select(outbox.c.seq).where(outbox.c.seq==event["seq"])).scalar_one()==event["seq"]
    finally:
        engine.dispose()


def test_source_permission_and_rate_limit_do_not_trigger_auth_halt(tmp_path):
    engine,store=db(tmp_path)
    try:
        for status,code,i in ((403,200,0),(429,4,1)):
            with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(status,json={"error":{"code":code}}))) as client:
                with pytest.raises(ConnectorError):
                    TechnicalDiscoveryService(store).execute(TENANT,request(i,f"source-failure-{i}"),token=TOKEN,http=OfficialHttp(client))
            assert state(engine)=={"status":"NOT_CHECKED","blocked":False}
    finally:
        engine.dispose()


def test_reset_is_audited_preserves_reservations_and_does_not_claim_validation(tmp_path):
    engine,store=db(tmp_path)
    calls=[]
    def fail(req):
        calls.append(req)
        return httpx.Response(400,json={"error":{"code":190,"message":TOKEN}})
    try:
        with httpx.Client(transport=httpx.MockTransport(fail)) as client:
            transport=OfficialHttp(client)
            with pytest.raises(ConnectorError):
                store.run(TENANT,manual(0,"generic-auth-001"),http=transport)
            assert state(engine)["blocked"]
            reader=Principal(actor_id="reader",tenant_id=TENANT,role="viewer")
            with pytest.raises(ConnectorError,match="BD_RECOVERY_ADMIN_REQUIRED"):
                reset_after_rotation(engine,reader,stopped=True)
            with pytest.raises(ConnectorError,match="BD_RECOVERY_STOP_ALL_INGESTION_REQUIRED"):
                reset_after_rotation(engine,ADMIN,stopped=False)
            with cycle_lease(engine,TENANT,"fixture-active"):
                with pytest.raises(ConnectorError,match="BD_RECOVERY_INGESTION_ACTIVE"):
                    reset_after_rotation(engine,ADMIN,stopped=True)
            result=reset_after_rotation(engine,ADMIN,stopped=True)
            assert result=={"status":"META_AUTH_RESET_UNVERIFIED","quota_reservation_preserved":True,"external_data_accessed":False}
            assert state(engine)["status"]=="RESET_UNVERIFIED"
            assert len(calls)==1
            with engine.connect() as conn:
                assert conn.execute(select(func.count()).select_from(ingestion_runs)).scalar_one()==1
                events=conn.execute(select(domain_events).where(domain_events.c.aggregate_type==AGGREGATE).order_by(domain_events.c.aggregate_version)).mappings().all()
                assert [e["event_type"] for e in events]==[BLOCK,RESET]
                assert TOKEN not in json.dumps([e["payload"] for e in events])
            # A reset alone is not a successful token test. Reusing the invalid
            # credential triggers another halt, charging only that new run.
            with pytest.raises(ConnectorError):
                store.run(TENANT,manual(1,"generic-auth-002"),http=transport)
            assert state(engine)["blocked"] and len(calls)==2
    finally:
        engine.dispose()


def test_guard_classification_requires_numeric_code_and_http_status():
    for diagnostic in ({},{"code":"190","http_status":400},{"code":190,"http_status":429},{"code":190},{"code":200,"http_status":403}):
        assert not is_global_auth_failure(ConnectorError("PROVIDER_REQUEST_FAILED",502,provider_diagnostic=diagnostic))
    assert not is_global_auth_failure(ValueError())
