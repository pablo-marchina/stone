"""DEC-008 read-only restart preflight: no native state can bypass source drift.

These tests use real SQL and zero LangGraph import; native full-path cases
remain in test_dec008_langgraph_saver_failure_actual.py on Windows.
"""
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update

from scripts import dec008_orchestrator_benchmark as bench
from tapi_gate0.agent_graph_checkpoints import agent_graph_events
from tapi_gate0.agent_graph_orchestrator_dec008 import _GuardedNativeReconciledGraph
from tapi_gate0.agent_graph_readonly_runner import LocalGraphPlan
from tapi_gate0.agent_graph_reconciliation_dec008 import (
    Dec008ReconciliationDenied, execute_reconciled_step, validate_native_resume,
)
from tapi_gate0.sa_store import content_items, engine_for


@pytest.fixture
def case(tmp_path):
    engine = engine_for("sqlite:///" + str(tmp_path / "preflight.sqlite"))
    bench._prepare(engine)
    plan = LocalGraphPlan(
        mode="analisar", content_id="fixture.post", as_of=bench.AS_OF,
    )
    try:
        yield engine, plan
    finally:
        engine.dispose()


def step(engine, plan, receipt=None):
    return execute_reconciled_step(
        engine, tenant=bench.TENANT, actor=bench.ACTOR, run_id=bench.RUN,
        plan=plan, native_receipt=receipt,
    )


def validate(engine, plan, receipt):
    return validate_native_resume(
        engine, tenant=bench.TENANT, actor=bench.ACTOR, run_id=bench.RUN,
        plan=plan, native_receipt=receipt,
    )


def corrupt(engine):
    with engine.begin() as db:
        old = json.loads(db.scalar(select(content_items.c.payload)))
        old["caption"] += " TAMPERED WITHOUT AUTHORITY"
        db.execute(update(content_items).values(payload=json.dumps(old)))


def test_sql_ahead_and_native_parity_are_reaudited_without_writes(case):
    engine, plan = case
    first = step(engine, plan)
    second = step(engine, plan, first)
    with engine.connect() as db:
        count_before = len(db.execute(select(agent_graph_events)).all())
    assert count_before == 2
    assert validate(engine, plan, first) == second
    assert validate(engine, plan, second) == second
    with engine.connect() as db:
        assert len(db.execute(select(agent_graph_events)).all()) == count_before


@pytest.mark.parametrize("native_level", [1, 2])
def test_drift_rejected_even_if_native_claims_latest_revision(case, native_level):
    engine, plan = case
    first = step(engine, plan)
    second = step(engine, plan, first)
    corrupt(engine)
    with pytest.raises(Dec008ReconciliationDenied,
                       match="SOURCE_DRIFT_RESTART_REQUIRED"):
        validate(engine, plan, first if native_level == 1 else second)
    with engine.connect() as db:
        assert len(db.execute(select(agent_graph_events)).all()) == 2


def test_native_plan_mismatch_and_receipt_forgery_denied(case):
    engine, plan = case
    state = step(engine, plan)
    other_plan = plan.model_copy(update={"content_id": "other.content"})
    with pytest.raises(Dec008ReconciliationDenied,
                       match="NATIVE_PLAN_MISMATCH"):
        validate(engine, other_plan, state)
    forged = dict(state, production_approved=True)
    with pytest.raises(Dec008ReconciliationDenied):
        validate(engine, plan, forged)


def test_native_receipt_authority_and_shape_forgery_leave_sql_untouched(case):
    """An already committed read-only receipt never grants external authority.

    Each forged native value must be rejected before any ledger mutation.
    A native checkpoint is not a grant, gold, creative approval or evidence of
    an executed side-effectful tool.
    """
    engine, plan = case
    first = step(engine, plan)
    candidates = [
        dict(first, **{field: True}) for field in (
            "rights_verified", "independent_gold_available",
            "scientifically_validated", "studio_write_allowed",
            "publication_allowed", "production_approved",
            "global_gates_released", "node_execution_proved",
        )
    ]
    candidates.extend((
        dict(first, model_calls_performed=1),
        dict(first, model_calls_performed=True),
        dict(first, unexpected_field="do-not-trust"),
        dict(first, revision=True),
        dict(first, revision=999),
        dict(first, next_node="unauthorized"),
        dict(first, chain_sha256="0"*64),
        dict(first, synthetic_or_technical_trace_only=False),
    ))
    with engine.connect() as db:
        before = len(db.execute(select(agent_graph_events)).all())
    assert before == 1
    for candidate in candidates:
        with pytest.raises(Dec008ReconciliationDenied):
            validate(engine, plan, candidate)
    with engine.connect() as db:
        assert len(db.execute(select(agent_graph_events)).all()) == before
    assert validate(engine, plan, first) == first


def test_wrapper_blocks_drifts_before_noop_native_resume(case):
    engine, plan = case
    first = step(engine, plan)
    second = step(engine, plan, first)
    calls = []
    class CompletedNative:
        def get_state(self, config):
            return SimpleNamespace(values={"receipt": second}, next=())
        def invoke(self, value, config, **kwargs):
            calls.append(value)
            return {"receipt": value["receipt"]}
    graph = _GuardedNativeReconciledGraph(
        CompletedNative(), engine=engine, tenant=bench.TENANT,
        actor=bench.ACTOR, run_id=bench.RUN, plan=plan,
    )
    config = {"configurable": {"thread_id": "fixture-trusted-thread"}}
    assert graph.invoke(None, config)["receipt"] == second
    assert calls == [{"receipt": second}]
    calls.clear()
    corrupt(engine)
    with pytest.raises(Dec008ReconciliationDenied,
                       match="SOURCE_DRIFT_RESTART_REQUIRED"):
        graph.invoke(None, config)
    assert calls == []


def test_resume_requires_trusted_thread_identifier(case):
    engine, plan = case
    step(engine, plan)
    class NoNative:
        def get_state(self, config):
            raise AssertionError("should be denied before reading checkpoint")
    graph = _GuardedNativeReconciledGraph(
        NoNative(), engine=engine, tenant=bench.TENANT,
        actor=bench.ACTOR, run_id=bench.RUN, plan=plan,
    )
    with pytest.raises(ValueError, match="DEC008_TRUSTED_THREAD_REQUIRED"):
        graph.invoke(None, {})
