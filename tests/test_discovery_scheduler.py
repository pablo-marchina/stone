"""Scheduler policy and durable claims: no real network."""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select, func

from tapi_gate0 import discovery_scheduler as s
from tapi_gate0.connectors import ConnectorError
from tapi_gate0.sa_store import domain_events, outbox
from test_discovery_batch_a4 import db, manifest, TENANT, VIEWER, TOKEN


@pytest.fixture
def context(tmp_path, monkeypatch):
    engine, store = db(tmp_path)
    now = [datetime(2026, 11, 13, 10, tzinfo=timezone.utc)]
    monkeypatch.setattr(s, "now_utc", lambda: now[0])
    for k in ("TAPI_BD_SCHEDULER_ENABLED", "TAPI_BD_CONTINUOUS_ENABLED", "TAPI_BD_TECHNICAL_INGEST",
              "TAPI_OFFICIAL_METADATA_READS", "TAPI_ZERO_BILLING_CONFIRMED", "TAPI_META_REQUIRE_TOKEN_EXPIRY"):
        monkeypatch.setenv(k, "1")
    # Test the real scheduler ledger, but isolate provider/plan behavior and clock.
    inspection = {"lease": None, "reserved_runs": 0, "orphan_runs_without_lease": [],
                  "quarantined_sources": [], "latest_a5_blocked_runs": [],
                  "meta_auth": {"blocked": False}, "meta_credential_expiry": {
                      "blocked": False, "token_expires_at": "2027-01-01T00:00:00+00:00"}}
    monkeypatch.setattr(s, "inspect_recovery", lambda *a: inspection)
    available = {"history": ["source-a"], "refresh": ["source-b"]}
    monkeypatch.setattr(s, "plan_cycle", lambda *a, **kw: ({"selected_sources": available[kw["mode"]]}, []))
    monkeypatch.setattr(s, "tenant_coverage", lambda *a: {"unique_media_ids": 0})
    calls = []
    def execute(*a, **kw):
        calls.append(kw["mode"])
        return {"status": "BATCH_COMPLETED", "cycle_key": "fixture-cycle"}
    monkeypatch.setattr(s, "execute_cycle", execute)
    try:
        yield store, now, inspection, available, calls
    finally:
        engine.dispose()


def preview(store):
    return s.preview_tick(store, TENANT, manifest(), VIEWER)


def tick(store):
    return s.execute_tick(store, TENANT, manifest(), VIEWER, token=TOKEN)


def ledger(store):
    with store.engine.connect() as db:
        rows = db.execute(select(domain_events).where(domain_events.c.aggregate_type == s.AGGREGATE)
                          .order_by(domain_events.c.seq)).mappings().all()
        assert all(db.execute(select(func.count()).select_from(outbox).where(outbox.c.seq == r["seq"])).scalar_one() == 1 for r in rows)
    return rows


def test_preview_is_read_only_and_chooses_history(context):
    store, _, _, _, calls = context
    r = preview(store)
    assert r["proposed_mode"] == "history" and not r["execution_blockers"]
    assert r["external_data_accessed"] is False and not calls and not ledger(store)


def test_refresh_hour_and_fallback(context):
    store, now, _, available, _ = context
    now[0] += timedelta(hours=1)
    assert preview(store)["proposed_mode"] == "refresh"
    available["refresh"] = []
    assert preview(store)["proposed_mode"] == "history"


def test_no_due_does_not_consume_slot(context):
    store, _, _, available, calls = context
    available.update(history=[], refresh=[])
    assert tick(store)["status"] == "SCHEDULER_NO_DUE_SOURCES"
    assert not calls and not ledger(store)


def test_claim_finish_and_same_slot_replay(context):
    store, now, _, _, calls = context
    assert tick(store)["status"] == "SCHEDULER_COMPLETED"
    assert [r["event_type"] for r in ledger(store)] == [s.CLAIM, s.FINISH]
    with pytest.raises(ConnectorError, match="BD_SCHEDULER_SLOT_ALREADY_CONSUMED"):
        tick(store)
    now[0] += timedelta(hours=1)
    assert tick(store)["status"] == "SCHEDULER_COMPLETED"
    assert calls == ["history", "refresh"]


def test_flags_fail_before_claim(context, monkeypatch):
    store, _, _, _, calls = context
    monkeypatch.delenv("TAPI_BD_SCHEDULER_ENABLED")
    with pytest.raises(ConnectorError, match="BD_SCHEDULER_FLAGS_REQUIRED"):
        tick(store)
    assert not ledger(store) and not calls


@pytest.mark.parametrize("key,value,code", [
    ("meta_credential_expiry", {"blocked": False, "token_expires_at": None}, "BD_SCHEDULER_TOKEN_EXPIRY_REQUIRED"),
    ("meta_auth", {"blocked": True}, "BD_META_AUTH_BLOCKED"),
    ("reserved_runs", 1, "BD_SCHEDULER_INGESTION_ACTIVE"),
    ("quarantined_sources", ["blocked"], "BD_SCHEDULER_SOURCE_REVIEW_REQUIRED"),
])
def test_preflight_blocks(context, key, value, code):
    store, _, inspection, _, calls = context
    inspection[key] = value
    assert code in preview(store)["execution_blockers"]
    with pytest.raises(ConnectorError, match=code):
        tick(store)
    assert not calls and not ledger(store)


def test_interrupted_claim_blocks_until_exact_admin_ack(context, monkeypatch):
    store, now, _, _, _ = context
    def crash(*a, **kw):
        raise RuntimeError("interrupted")
    monkeypatch.setattr(s, "execute_cycle", crash)
    with pytest.raises(RuntimeError):
        tick(store)
    seq = ledger(store)[0]["seq"]
    now[0] += timedelta(hours=1)
    with pytest.raises(ConnectorError, match="BD_SCHEDULER_STOP_REVIEW_REQUIRED"):
        tick(store)
    admin = SimpleNamespace(role="admin", tenant_id=TENANT, actor_id="fixture")
    with pytest.raises(ConnectorError, match="BD_SCHEDULER_STOP_NOT_CURRENT"):
        s.acknowledge_stop(store, admin, seq+1, stopped=True)
    with pytest.raises(ConnectorError, match="BD_SCHEDULER_ADMIN_STOP_REQUIRED"):
        s.acknowledge_stop(store, admin, seq, stopped=False)
    assert s.acknowledge_stop(store, admin, seq, stopped=True)["quota_reservation_preserved"]
    assert preview(store)["state"]["status"] == "ACKNOWLEDGED"
    assert [r["event_type"] for r in ledger(store)] == [s.CLAIM, s.ACK]


def test_failed_batch_stops_and_ack_cannot_reuse_slot(context, monkeypatch):
    store, _, _, _, _ = context
    monkeypatch.setattr(s, "execute_cycle", lambda *a, **kw: {"status": "BATCH_AUDIT_FAILED"})
    assert tick(store)["status"] == "SCHEDULER_STOPPED"
    seq = ledger(store)[-1]["seq"]
    admin = SimpleNamespace(role="admin", tenant_id=TENANT, actor_id="fixture")
    s.acknowledge_stop(store, admin, seq, stopped=True)
    with pytest.raises(ConnectorError, match="BD_SCHEDULER_SLOT_ALREADY_CONSUMED"):
        tick(store)


def test_ack_requires_recovery_first(context, monkeypatch):
    store, _, inspection, _, _ = context
    monkeypatch.setattr(s, "execute_cycle", lambda *a, **kw: {"status": "BATCH_STOPPED_ON_SOURCE_FAILURE"})
    tick(store)
    inspection["reserved_runs"] = 1
    admin = SimpleNamespace(role="admin", tenant_id=TENANT, actor_id="fixture")
    with pytest.raises(ConnectorError, match="BD_SCHEDULER_RECOVERY_REQUIRED"):
        s.acknowledge_stop(store, admin, ledger(store)[-1]["seq"], stopped=True)


def test_stale_preview_cannot_double_claim(context):
    store, _, _, _, calls = context
    r = preview(store)
    s._claim(store, TENANT, r)
    with pytest.raises(ConnectorError, match="BD_SCHEDULER_STOP_REVIEW_REQUIRED"):
        s._claim(store, TENANT, r)
    assert len(ledger(store)) == 1 and not calls


def test_compact_local_preflight_never_echoes_token_or_deferred_names(monkeypatch):
    import json
    for name in s.EXECUTION_FLAGS:
        monkeypatch.setenv(name,"1")
    monkeypatch.setenv("TAPI_INSTAGRAM_ACCESS_TOKEN","secret-fixture-not-for-output")
    plan={"selected_sources":["source-a"],"deferred":[{"username":"other","reason":"SOURCE_NOT_APPROVED"}],
          "meta_auth":{"status":"NOT_CHECKED"},"meta_credential_expiry":{"status":"WITHIN_DECLARED_WINDOW","provider_verified":False},
          "daily_request_budget":80,"conservative_reserved_pages_today":0,
          "max_official_requests":4,"max_observations_to_persist":40}
    report={"execution_blockers":[],"plans":{"history":plan},"proposed_mode":"history",
            "preferred_mode":"history","slot":"2026-11-14T03:00:00+00:00","state":{"status":"NEVER_RUN"},
            "tenant_coverage":{"unique_media_ids":605}}
    result=s.local_preflight_summary(report)
    assert result["status"]=="SCHEDULER_LOCAL_READY"
    assert result["token_present"] and not result["provider_verified"] and not result["database_mutated"]
    assert result["deferred_reason_counts"]=={"SOURCE_NOT_APPROVED":1}
    assert "secret-fixture-not-for-output" not in json.dumps(result) and "other" not in json.dumps(result)
    monkeypatch.delenv("TAPI_INSTAGRAM_ACCESS_TOKEN")
    monkeypatch.delenv(s.EXECUTION_FLAGS[0])
    report["execution_blockers"]=["BD_META_EXPIRY_CONFIGURATION_INVALID"]
    blocked=s.local_preflight_summary(report)
    assert blocked["status"]=="SCHEDULER_LOCAL_BLOCKED"
    assert set(blocked["execution_blockers"])=={"BD_META_EXPIRY_CONFIGURATION_INVALID","BD_SCHEDULER_FLAGS_REQUIRED","BD_SCHEDULER_TOKEN_REQUIRED"}
    assert report["execution_blockers"]==["BD_META_EXPIRY_CONFIGURATION_INVALID"]


def test_cycle_summary_excludes_private_evidence():
    result=s.cycle_summary({"mode":"history","status":"BATCH_COMPLETED",
        "tenant_coverage_before":{"unique_media_ids":605},"tenant_coverage_after":{"unique_media_ids":606},
        "batch":{"counts":{"new_records":1},"sources":[{"username":"source-a","new_records":1,
                  "evidence":[{"caption":"private"}],"audit_all_traces_valid":True}]}})
    assert result["counts"]["new_records"]==1
    assert result["sources"]==[{"username":"source-a","new_records":1,"audit_all_traces_valid":True}]
    assert result["scientific_admissions"]==0
