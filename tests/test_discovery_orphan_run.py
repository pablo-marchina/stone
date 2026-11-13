"""Recovery of one orphan reservation, with no automatic retry or quota refund."""
from datetime import timedelta
import json
import pytest
from sqlalchemy import select, update, func

from tapi_gate0.connectors import ConnectorError, Platform
from tapi_gate0.discovery_history import cycle_lease
from tapi_gate0.discovery_orphan_run import orphan_reservations, recover_orphan_run
from tapi_gate0.identity import Principal
from tapi_gate0.ingestion import IngestionRequest, MANUAL_ORPHAN_REASON, ingestion_runs
from tapi_gate0.sa_store import domain_events, outbox
from tapi_gate0.storage import now_utc
from test_discovery_batch_a4 import db, SOURCES, TENANT

ADMIN = Principal(actor_id="fixture-admin", tenant_id=TENANT, role="admin")
KEY = "manual-orphan-01"


def request(i, key):
    return IngestionRequest(platform=Platform.INSTAGRAM, source_account_id=SOURCES[i][1], run_key=key)


def age(engine):
    with engine.begin() as conn:
        conn.execute(update(ingestion_runs).where(ingestion_runs.c.run_key == KEY)
            .values(requested_at=(now_utc()-timedelta(hours=1)).isoformat()))


def test_orphan_closure_preserves_ledger_and_quarantines_source(tmp_path):
    engine, store = db(tmp_path)
    try:
        store._reserve(TENANT, request(0, KEY)); age(engine)
        with engine.connect() as conn:
            assert orphan_reservations(conn,TENANT)[0]["run_key"] == KEY
        result = recover_orphan_run(engine, ADMIN, KEY, stopped=True)
        assert result["source_quarantined"] and result["partial_writes_unknown"]
        assert result["quota_reservation_preserved"] and not result["external_data_accessed"]
        with engine.connect() as conn:
            row = conn.execute(select(ingestion_runs)).mappings().one()
            assert row["status"] == "failed" and row["reason_code"] == MANUAL_ORPHAN_REASON
            event = conn.execute(select(domain_events).where(domain_events.c.event_type == "business_discovery.orphan_run_recovered")).mappings().one()
            assert json.loads(event["payload"])["actor_id"] == ADMIN.actor_id
            assert conn.execute(select(outbox.c.seq).where(outbox.c.seq == event["seq"])).scalar_one() == event["seq"]
            assert orphan_reservations(conn,TENANT) == []
        with pytest.raises(ConnectorError, match="BD_SOURCE_ORPHAN_QUARANTINED"):
            store._reserve(TENANT, request(0, "manual-next-01"))
        with pytest.raises(ConnectorError, match="INGESTION_RUN_NO_LONGER_RESERVED"):
            store._finish(TENANT, KEY, "completed", added=99)
        with pytest.raises(ConnectorError, match="BD_RECOVERY_ORPHAN_RUN_MISMATCH"):
            recover_orphan_run(engine, ADMIN, KEY, stopped=True)
        store._reserve(TENANT, request(1, "manual-next-02"))
        store._finish(TENANT, "manual-next-02", "completed")
        with engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(ingestion_runs)).scalar_one() == 2
    finally:
        engine.dispose()


def test_orphan_requires_exact_old_run_and_stopped_admin(tmp_path):
    engine, store = db(tmp_path)
    try:
        store._reserve(TENANT, request(0, KEY))
        with pytest.raises(ConnectorError, match="BD_RECOVERY_RUN_TOO_RECENT"):
            recover_orphan_run(engine,ADMIN,KEY,stopped=True)
        age(engine)
        for principal, stopped, reason in ((Principal(actor_id="reader",tenant_id=TENANT,role="viewer"),True,"BD_RECOVERY_ADMIN_REQUIRED"),
                                           (ADMIN,False,"BD_RECOVERY_STOP_ALL_INGESTION_REQUIRED")):
            with pytest.raises(ConnectorError,match=reason):
                recover_orphan_run(engine,principal,KEY,stopped=stopped)
        with pytest.raises(ConnectorError,match="BD_RECOVERY_ORPHAN_RUN_MISMATCH"):
            recover_orphan_run(engine,ADMIN,"wrong-run-key",stopped=True)
        with engine.connect() as conn:
            assert conn.execute(select(ingestion_runs.c.status)).scalar_one() == "reserved"
    finally:
        engine.dispose()


def test_manual_recovery_cannot_release_cycle_lease(tmp_path):
    engine, store = db(tmp_path)
    try:
        cycle = "a5history-20261113120000-1234abcd"
        with cycle_lease(engine,TENANT,cycle):
            store._reserve(TENANT, request(0,cycle+"-01"),cycle_key=cycle)
            with engine.connect() as conn:
                assert orphan_reservations(conn,TENANT)==[]
            with pytest.raises(ConnectorError,match="BD_RECOVERY_INGESTION_ACTIVE"):
                recover_orphan_run(engine,ADMIN,cycle+"-01",stopped=True)
            store._finish(TENANT,cycle+"-01","completed")
    finally:
        engine.dispose()


def test_generic_worker_cannot_write_after_recovery(tmp_path, monkeypatch):
    import httpx
    from tapi_gate0.connectors import OfficialHttp
    from tapi_gate0.ingestion import ingestion_records, ingestion_page_checkpoints, source_grants
    engine, store = db(tmp_path)
    # Reuse the first fixture account in the official API response.
    account = SOURCES[0][1]
    for flag in ("TAPI_OFFICIAL_METADATA_READS", "TAPI_ZERO_BILLING_CONFIRMED"):
        monkeypatch.setenv(flag,"1")
    monkeypatch.setenv("TAPI_INSTAGRAM_ACCESS_TOKEN","mocked-credentials-that-never-log")
    def provider(req):
        if req.url.path.endswith("/"+account):
            return httpx.Response(200,json={"id":account,"username":"sebrae","followers_count":1200})
        assert req.url.path.endswith("/"+account+"/media")
        age(engine)
        recover_orphan_run(engine,ADMIN,KEY,stopped=True)
        return httpx.Response(200,json={"data":[{"id":"179001","media_type":"IMAGE",
            "permalink":"https://www.instagram.com/p/Fixture123/","timestamp":"2024-01-14T12:00:00Z",
            "like_count":120,"comments_count":12}]})
    try:
        with httpx.Client(transport=httpx.MockTransport(provider)) as client:
            with pytest.raises(ConnectorError,match="INGESTION_RUN_NO_LONGER_RESERVED"):
                store.run(TENANT,request(0,KEY),http=OfficialHttp(client))
        with engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(ingestion_records)).scalar_one()==0
            assert conn.execute(select(func.count()).select_from(ingestion_page_checkpoints)).scalar_one()==0
            assert conn.execute(select(source_grants.c.technical_verified_at).where(source_grants.c.source_account_id==account)).scalar_one() is None
            assert conn.execute(select(ingestion_runs.c.reason_code)).scalar_one()==MANUAL_ORPHAN_REASON
    finally:
        engine.dispose()


def test_corpus_worker_cannot_write_after_recovery(tmp_path, monkeypatch):
    from test_discovery_corpus_ingestion import setup_store, source, invoke, TENANT as CORPUS_TENANT
    from tapi_gate0.discovery_ingestion import business_discovery_provenance
    from tapi_gate0.ingestion import ingestion_records
    store = setup_store(tmp_path)
    s, proof = source(tmp_path)
    admin = Principal(actor_id="fixture-admin",tenant_id=CORPUS_TENANT,role="admin")
    for flag in ("TAPI_MPE_PERSISTENCE_ENABLED", "TAPI_OFFICIAL_METADATA_READS", "TAPI_ZERO_BILLING_CONFIRMED"):
        monkeypatch.setenv(flag,"1")
    original = store._persist_item
    def persist(*args,**kwargs):
        age(store.engine)
        recover_orphan_run(store.engine,admin,KEY,stopped=True)
        return original(*args,**kwargs)
    monkeypatch.setattr(store,"_persist_item",persist)
    try:
        with pytest.raises(ConnectorError,match="INGESTION_RUN_NO_LONGER_RESERVED"):
            invoke(store,s,proof,{"likes":20},key=KEY)
        with store.engine.connect() as conn:
            for table in (ingestion_records,business_discovery_provenance):
                assert conn.execute(select(func.count()).select_from(table)).scalar_one()==0
            assert conn.execute(select(ingestion_runs.c.reason_code)).scalar_one()==MANUAL_ORPHAN_REASON
    finally:
        store.engine.dispose()
