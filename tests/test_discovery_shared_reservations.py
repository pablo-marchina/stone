"""Shared Instagram reservations across A3/A4/A5/A6 and manual ingestion."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import insert, select, func

from tapi_gate0.connectors import ConnectorError, Platform
from tapi_gate0.discovery_history import cycle_lease
from tapi_gate0.discovery_identity_a6 import RESERVATION
from tapi_gate0.ingestion import IngestionRequest, ingestion_runs
from tapi_gate0.sa_store import domain_events
from tapi_gate0.storage import now_utc
from test_discovery_batch_a4 import db, SOURCES, TENANT

KEY = "a5history-20261113120000-1234abcd"


def request(index, key):
    return IngestionRequest(platform=Platform.INSTAGRAM,
        source_account_id=SOURCES[index][1], run_key=key)


def test_manual_reservation_blocked_during_cycle(tmp_path):
    engine, store = db(tmp_path)
    try:
        with cycle_lease(engine, TENANT, KEY):
            # Matching prefix alone must not grant access to the internal cycle.
            with pytest.raises(ConnectorError, match="BD_CYCLE_RESERVATION_SCOPE_MISMATCH"):
                store._reserve(TENANT, request(0, KEY+"-01"))
            with pytest.raises(ConnectorError, match="BD_CYCLE_RESERVATION_SCOPE_MISMATCH"):
                store._reserve(TENANT, request(0, "manual-run-001"))
            with pytest.raises(ConnectorError, match="BD_CYCLE_RESERVATION_SCOPE_MISMATCH"):
                store._reserve(TENANT, request(0, "manual-run-001"), cycle_key=KEY)
            store._reserve(TENANT, request(0, KEY+"-01"), cycle_key=KEY)
            store._finish(TENANT, KEY+"-01", "completed")
        store._reserve(TENANT, request(1, "manual-run-002"))
        store._finish(TENANT, "manual-run-002", "completed")
    finally:
        engine.dispose()


def test_active_manual_run_blocks_other_source_and_cycle(tmp_path):
    engine, store = db(tmp_path)
    try:
        store._reserve(TENANT, request(0, "manual-run-001"))
        with pytest.raises(ConnectorError, match="ACCOUNT_INGESTION_IN_PROGRESS"):
            store._reserve(TENANT, request(1, "manual-run-002"))
        with pytest.raises(ConnectorError, match="ACCOUNT_INGESTION_IN_PROGRESS"):
            with cycle_lease(engine, TENANT, KEY):
                pytest.fail("cycle entered despite active run")
        store._finish(TENANT, "manual-run-001", "completed")
        with cycle_lease(engine, TENANT, KEY):
            pass
    finally:
        engine.dispose()


def test_expired_cycle_context_cannot_reserve(tmp_path):
    engine, store = db(tmp_path)
    try:
        with cycle_lease(engine, TENANT, KEY):
            pass
        with pytest.raises(ConnectorError, match="BD_CYCLE_RESERVATION_SCOPE_MISMATCH"):
            store._reserve(TENANT, request(0, KEY+"-01"), cycle_key=KEY)
    finally:
        engine.dispose()


def test_shared_budget_includes_failed_and_identity_reservations(tmp_path):
    engine, store = db(tmp_path)
    try:
        now = now_utc().isoformat()
        # Historical reservations across multiple accounts; use a seeded ledger
        # to isolate the tenant-wide cap from the five-runs-per-source cap.
        with engine.begin() as conn:
            for i in range(17):
                conn.execute(insert(ingestion_runs).values(tenant_id=TENANT,
                    run_key=f"fixture-old-{i:02d}", platform="instagram",
                    source_account_id=SOURCES[0][1], requested_at=now,
                    status="failed" if i%2 else "completed"))
            for i in range(10):
                conn.execute(insert(domain_events).values(event_id=f"fixture-identity-{i}",
                    tenant_id=TENANT, aggregate_type="bd_identity",
                    aggregate_id=f"fixture-aggregate-{i}", aggregate_version=1,
                    event_type=RESERVATION, occurred_at=now, payload="{}"))
        with pytest.raises(ConnectorError, match="BD_SHARED_DAILY_BUDGET_EXCEEDED"):
            store._reserve(TENANT, request(1, "manual-run-002"))
        with engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(ingestion_runs)).scalar_one()==17
    finally:
        engine.dispose()


def test_concurrent_reservations_have_one_winner(tmp_path):
    engine, store = db(tmp_path)
    barrier = Barrier(2)
    def reserve(index):
        barrier.wait(timeout=10)
        try:
            store._reserve(TENANT, request(index, f"manual-race-{index}"))
            return "reserved"
        except ConnectorError as exc:
            return exc.code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, (0, 1)))
        assert sorted(results)==["ACCOUNT_INGESTION_IN_PROGRESS", "reserved"]
        with engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(ingestion_runs)).scalar_one()==1
    finally:
        engine.dispose()
