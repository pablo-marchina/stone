"""Offline tests of terminal-state fencing for Business Discovery writes."""
import pytest
from sqlalchemy import select, update, func

from tapi_gate0.connectors import ConnectorError, Platform
from tapi_gate0.discovery_technical import TechnicalDiscoveryReader, TechnicalDiscoveryService
from tapi_gate0.ingestion import IngestionRequest, ingestion_runs, ingestion_records, source_grants
from tapi_gate0.sa_store import content_items, domain_events, metrics_snapshots
from test_discovery_technical_a3 import setup, request as make_request, transport, TENANT, TARGET, TOKEN

REASON = "BD_ORPHANED_RUN_OPERATOR_RECOVERY"


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    for key in ("TAPI_BD_TECHNICAL_INGEST", "TAPI_OFFICIAL_METADATA_READS", "TAPI_ZERO_BILLING_CONFIRMED"):
        monkeypatch.setenv(key, "1")


def interrupt(engine, key):
    with engine.begin() as db:
        changed = db.execute(update(ingestion_runs).where(
            ingestion_runs.c.tenant_id == TENANT, ingestion_runs.c.run_key == key,
            ingestion_runs.c.status == "reserved").values(status="failed", reason_code=REASON))
        assert changed.rowcount == 1


def assert_unchanged(engine, key):
    with engine.connect() as db:
        row = db.execute(select(ingestion_runs).where(ingestion_runs.c.run_key == key)).mappings().one()
        assert row["status"] == "failed" and row["reason_code"] == REASON
        assert row["new_records"] == row["refreshed_records"] == row["duplicate_records"] == 0
        for table in (ingestion_records, content_items, metrics_snapshots):
            assert db.execute(select(func.count()).select_from(table)).scalar_one() == 0
        assert db.execute(select(func.count()).select_from(domain_events).where(
            domain_events.c.aggregate_type == "bd_technical_run")).scalar_one() == 0


@pytest.mark.parametrize("phase", ["before_verification", "before_persistence"])
def test_interrupted_technical_worker_cannot_write(tmp_path, monkeypatch, phase):
    engine, store = setup(tmp_path)
    http, calls, client = transport()
    req = make_request("a5history-20261113120000-1234abcd-01")
    try:
        if phase == "before_verification":
            original = TechnicalDiscoveryReader.fetch
            def fetch(reader, *args, **kwargs):
                result = original(reader, *args, **kwargs)
                interrupt(engine, req.run_key)
                return result
            monkeypatch.setattr(TechnicalDiscoveryReader, "fetch", fetch)
        else:
            original = store._persist_item
            def persist(*args, **kwargs):
                interrupt(engine, req.run_key)
                return original(*args, **kwargs)
            monkeypatch.setattr(store, "_persist_item", persist)
        with pytest.raises(ConnectorError, match="INGESTION_RUN_NO_LONGER_RESERVED"):
            TechnicalDiscoveryService(store).execute(TENANT, req, token=TOKEN, http=http)
        assert len(calls) == 2
        assert_unchanged(engine, req.run_key)
        if phase == "before_verification":
            with engine.connect() as db:
                assert db.execute(select(source_grants.c.technical_verified_at)).scalar_one() is None
    finally:
        client.close(); engine.dispose()


@pytest.mark.parametrize("terminal", ["completed", "failed"])
def test_terminal_run_cannot_be_finalized_again(tmp_path, terminal):
    engine, store = setup(tmp_path)
    key = "a5history-20261113120000-1234abcd-01"
    try:
        store._reserve(TENANT, IngestionRequest(platform=Platform.INSTAGRAM, source_account_id=TARGET, run_key=key))
        interrupt(engine, key)
        called = []
        with pytest.raises(ConnectorError, match="INGESTION_RUN_NO_LONGER_RESERVED"):
            store._finish(TENANT, key, terminal, added=99, after_finish=lambda db: called.append(True))
        assert called == []
        assert_unchanged(engine, key)
    finally:
        engine.dispose()


def test_finalization_callback_rolls_back_terminal_transition(tmp_path):
    engine, store = setup(tmp_path)
    key = "a5history-20261113120000-1234abcd-01"
    try:
        store._reserve(TENANT, IngestionRequest(platform=Platform.INSTAGRAM, source_account_id=TARGET, run_key=key))
        def fail(db):
            raise ConnectorError("BD_HISTORY_AUDIT_FAILED", 409)
        with pytest.raises(ConnectorError, match="BD_HISTORY_AUDIT_FAILED"):
            store._finish(TENANT, key, "completed", after_finish=fail)
        with engine.connect() as db:
            assert db.execute(select(ingestion_runs.c.status).where(ingestion_runs.c.run_key == key)).scalar_one() == "reserved"
        store._finish(TENANT, key, "failed", reason="BD_HISTORY_AUDIT_FAILED")
    finally:
        engine.dispose()
