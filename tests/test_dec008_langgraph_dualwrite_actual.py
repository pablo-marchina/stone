"""DEC-008 optional real saver: simulate SQL committed before native checkpoint.

This tests an injected one-step native acknowledgement gap, not a hard-kill or
exactly-once semantics for arbitrary external side effects. No fake LangGraph.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select, update

from scripts import dec008_orchestrator_benchmark as bench
from tapi_gate0.agent_graph_checkpoints import agent_graph_events, agent_graph_runs
from tapi_gate0.agent_graph_orchestrator_dec008 import prepare_native_reconciled_graph
from tapi_gate0.agent_graph_readonly_runner import LocalGraphPlan, execute_next
from tapi_gate0.agent_graph_reconciliation_dec008 import Dec008ReconciliationDenied
from tapi_gate0.sa_store import content_items, engine_for


def _runtime():
    pytest.importorskip("langgraph.graph", reason="DEC008_REAL_LANGGRAPH_UNAVAILABLE")
    pytest.importorskip("langgraph.checkpoint.sqlite", reason="DEC008_NATIVE_SAVER_UNAVAILABLE")
    from langgraph.checkpoint.sqlite import SqliteSaver
    return SqliteSaver


def _config():
    return {"configurable": {"thread_id": "dec008-synthetic-tenant-run"},
            "recursion_limit": 25}


def _plan(mode):
    return LocalGraphPlan(mode=mode, content_id="fixture.post", as_of=bench.AS_OF)


@pytest.mark.parametrize("mode,terminal,revision", [
    ("analisar", "TRACE_RECORDED", 5),
    ("recomendar", "TRACE_RECORDED", 6),
    ("gerar_criativo", "ABSTAINED", 5),
])
def test_one_sql_native_commit_gap_repairs_without_duplicate_event(
        tmp_path, mode, terminal, revision):
    SqliteSaver = _runtime()
    engine_path = tmp_path / "stone.sqlite"
    native_path = tmp_path / "langgraph.sqlite"
    engine = engine_for("sqlite:///" + str(engine_path))
    try:
        bench._prepare(engine)
        plan = _plan(mode)
        with SqliteSaver.from_conn_string(str(native_path)) as saver:
            graph = prepare_native_reconciled_graph(
                engine, checkpointer=saver, tenant=bench.TENANT,
                actor=bench.ACTOR, run_id=bench.RUN, plan=plan,
            )
            first = graph.invoke({"receipt": {}}, _config())
            assert first["receipt"]["revision"] == 1
            assert graph.get_state(_config()).values["receipt"]["revision"] == 1

        # Simulate crash in the window AFTER Stone SQL step 2 committed,
        # BEFORE LangGraph saved that step. Keep native DB stuck at rev 1.
        second = execute_next(engine, tenant=bench.TENANT, actor=bench.ACTOR,
                              run_id=bench.RUN, plan=plan)
        assert second["revision"] == 2
        with engine.connect() as db:
            assert len(db.execute(select(agent_graph_events)).all()) == 2
        engine.dispose()
        engine = engine_for("sqlite:///" + str(engine_path))
        with SqliteSaver.from_conn_string(str(native_path)) as saver:
            recovered = prepare_native_reconciled_graph(
                engine, checkpointer=saver, tenant=bench.TENANT,
                actor=bench.ACTOR, run_id=bench.RUN, plan=plan,
            )
            assert recovered.get_state(_config()).values["receipt"]["revision"] == 1
            synced = recovered.invoke(None, _config())
            assert synced["receipt"] == second
            with engine.connect() as db:
                assert len(db.execute(select(agent_graph_events)).all()) == 2
            for step in range(3, revision + 1):
                final = recovered.invoke(None, _config())
                assert final["receipt"]["revision"] == step
            assert final["receipt"]["status"] == terminal
            assert final["receipt"]["production_approved"] is False
            assert final["receipt"]["studio_write_allowed"] is False
            assert recovered.get_state(_config()).next == ()
    finally:
        engine.dispose()


def test_source_drift_blocks_reconciliation_after_missing_native_commit(tmp_path):
    SqliteSaver = _runtime()
    engine = engine_for("sqlite:///" + str(tmp_path / "stone.sqlite"))
    try:
        bench._prepare(engine)
        plan = _plan("analisar")
        native = tmp_path / "langgraph.sqlite"
        with SqliteSaver.from_conn_string(str(native)) as saver:
            graph = prepare_native_reconciled_graph(
                engine, checkpointer=saver, tenant=bench.TENANT,
                actor=bench.ACTOR, run_id=bench.RUN, plan=plan)
            assert graph.invoke({"receipt": {}}, _config())["receipt"]["revision"] == 1
        assert execute_next(engine, tenant=bench.TENANT, actor=bench.ACTOR,
                            run_id=bench.RUN, plan=plan)["revision"] == 2
        with engine.begin() as db:
            original = json.loads(db.scalar(select(content_items.c.payload)))
            original["caption"] += " TAMPERED"
            db.execute(update(content_items).values(payload=json.dumps(original)))
        with SqliteSaver.from_conn_string(str(native)) as saver:
            graph = prepare_native_reconciled_graph(
                engine, checkpointer=saver, tenant=bench.TENANT,
                actor=bench.ACTOR, run_id=bench.RUN, plan=plan)
            with pytest.raises(Dec008ReconciliationDenied,
                               match="SOURCE_DRIFT_RESTART_REQUIRED"):
                graph.invoke(None, _config())
        with engine.connect() as db:
            assert db.scalar(select(agent_graph_runs.c.revision)) == 2
    finally:
        engine.dispose()
