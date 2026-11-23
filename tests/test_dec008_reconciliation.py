"""DEC-008: SQL/native dual-write reconciliation, real local SQL, no LangGraph fake."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select, update

from scripts import dec008_orchestrator_benchmark as bench
from tapi_gate0.agent_graph_checkpoints import agent_graph_events, agent_graph_runs
from tapi_gate0.agent_graph_readonly_runner import LocalGraphPlan, execute_next
from tapi_gate0.agent_graph_reconciliation_dec008 import (
    Dec008ReconciliationDenied, execute_reconciled_step,
)
from tapi_gate0.sa_store import content_items, engine_for


@pytest.fixture
def engine(tmp_path):
    db = engine_for("sqlite:///" + str(tmp_path / "ledger.sqlite"))
    bench._prepare(db)
    try:
        yield db
    finally:
        db.dispose()


def plan(mode="analisar"):
    return LocalGraphPlan(mode=mode, content_id="fixture.post", as_of=bench.AS_OF)


def reconciled(engine, native_receipt=None, *, mode="analisar", actor=bench.ACTOR):
    return execute_reconciled_step(
        engine, tenant=bench.TENANT, actor=actor,
        run_id=bench.RUN, plan=plan(mode), native_receipt=native_receipt,
    )


@pytest.mark.parametrize("mode,final,steps", [
    ("analisar", "TRACE_RECORDED", 5),
    ("recomendar", "TRACE_RECORDED", 6),
    ("gerar_criativo", "ABSTAINED", 5),
])
def test_reconciles_single_missing_native_commit_at_every_step(engine, mode, final, steps):
    native = {}
    for index in range(steps):
        expected = reconciled(engine, native, mode=mode)
        assert expected["revision"] == index + 1
        # Crash after SQL commit, before LangGraph commits its checkpoint.
        restored = reconciled(engine, native, mode=mode)
        assert restored == expected
        with engine.connect() as db:
            assert len(db.execute(select(agent_graph_events)).all()) == index + 1
        native = restored  # Native saver finally persisted the returned receipt.
    assert native["status"] == final
    assert reconciled(engine, native, mode=mode) == native
    assert native["studio_write_allowed"] is False
    assert native["production_approved"] is False


def test_recovers_one_step_committed_by_existing_atomic_runner(engine):
    sql = execute_next(engine, tenant=bench.TENANT, actor=bench.ACTOR,
                       run_id=bench.RUN, plan=plan())
    assert sql["revision"] == 1
    assert reconciled(engine, {}) == sql
    assert reconciled(engine, sql)["revision"] == 2


def test_rejects_more_than_one_missing_native_step(engine):
    for _ in range(2):
        execute_next(engine, tenant=bench.TENANT, actor=bench.ACTOR,
                     run_id=bench.RUN, plan=plan())
    with pytest.raises(Dec008ReconciliationDenied, match="NATIVE_TOO_FAR_BEHIND"):
        reconciled(engine, {})
    with engine.connect() as db:
        assert db.scalar(select(agent_graph_runs.c.revision)) == 2


def test_rejects_native_checkpoint_ahead_of_sql(engine):
    first = reconciled(engine, {})
    forged = dict(first, revision=2)
    with pytest.raises(Dec008ReconciliationDenied, match="NATIVE_AHEAD_OF_SQL_LEDGER"):
        reconciled(engine, forged)
    assert reconciled(engine, first)["revision"] == 2


@pytest.mark.parametrize("mutation", [
    {"chain_sha256": "f" * 64},
    {"status": "BLOCKED"},
    {"schema_version": "invalid"},
    {"mode": "recomendar"},
    {"revision": True},
    {"next_node": "studio_handoff"},
    {"production_approved": True},
    {"rights_verified": True},
])
def test_detects_native_receipt_forgery(engine, mutation):
    real = reconciled(engine, {})
    corrupted = dict(real, **mutation)
    with pytest.raises(Dec008ReconciliationDenied):
        reconciled(engine, corrupted)
    with engine.connect() as db:
        assert db.scalar(select(agent_graph_runs.c.revision)) == 1


def test_source_drift_denies_native_repair_and_does_not_advance(engine):
    plan_receipt = reconciled(engine, {})
    retrieved = reconciled(engine, plan_receipt)
    assert retrieved["revision"] == 2
    with engine.begin() as db:
        raw = db.scalar(select(content_items.c.payload))
        content = json.loads(raw)
        content["caption"] += " NEW UNTRUSTED CONTENT"
        db.execute(update(content_items).values(payload=json.dumps(content)))
    with pytest.raises(Dec008ReconciliationDenied,
                       match="SOURCE_DRIFT_RESTART_REQUIRED"):
        reconciled(engine, plan_receipt)
    with engine.connect() as db:
        assert db.scalar(select(agent_graph_runs.c.revision)) == 2
        assert len(db.execute(select(agent_graph_events)).all()) == 2


def test_other_actor_cannot_reconcile(engine):
    one = reconciled(engine, {})
    with pytest.raises(ValueError, match="RUN_ID_CONFLICT"):
        reconciled(engine, one, actor="untrusted-user")


def test_invalid_native_envelope_denied(engine):
    with pytest.raises(Dec008ReconciliationDenied, match="VALIDATED_PLAN_REQUIRED"):
        execute_reconciled_step(engine, tenant=bench.TENANT,
                                actor=bench.ACTOR, run_id=bench.RUN,
                                plan={"mode": "analisar"})
    with pytest.raises(Dec008ReconciliationDenied, match="NATIVE_RECEIPT_INVALID"):
        reconciled(engine, native_receipt=["unsafe"])
