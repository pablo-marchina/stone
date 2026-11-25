"""DEC-008 optional REAL LangGraph SQLite checkpointer recovery probes.

Requires langgraph==1.2.24 and langgraph-checkpoint-sqlite==3.1.3. Never
substitute a mock. This is a local synthetic diagnostic of two independent
persistence systems, not proof of cross-database atomicity or production.
"""
from __future__ import annotations

import json
from typing import Any, TypedDict

import pytest
from sqlalchemy import select, update

from scripts import dec008_orchestrator_benchmark as bench
from tapi_gate0.agent_graph_checkpoints import agent_graph_events, agent_graph_runs
from tapi_gate0.agent_graph_readonly_runner import (
    LocalGraphDenied, LocalGraphPlan, execute_bounded, execute_next,
)
from tapi_gate0.sa_store import content_items, engine_for


class _State(TypedDict):
    receipt: dict[str, Any]


def _runtime():
    # skip (never pass or fake) if either *real* optional dependency is absent
    pytest.importorskip("langgraph.graph", reason="DEC008_REAL_LANGGRAPH_UNAVAILABLE")
    pytest.importorskip("langgraph.checkpoint.sqlite", reason="DEC008_NATIVE_SQLITE_SAVER_UNAVAILABLE")
    from langgraph.graph import END, START, StateGraph
    from langgraph.checkpoint.sqlite import SqliteSaver
    return END, START, StateGraph, SqliteSaver


def _graph(engine, saver, *, mode="analisar", actor=bench.ACTOR):
    END, START, StateGraph, _ = _runtime()
    plan = LocalGraphPlan(mode=mode, content_id="fixture.post", as_of=bench.AS_OF)
    graph = StateGraph(_State)

    def step(state: _State) -> _State:
        return {"receipt": execute_next(
            engine, tenant=bench.TENANT, actor=actor,
            run_id=bench.RUN, plan=plan,
        )}

    def route(state: _State) -> str:
        status = state["receipt"]["status"]
        if status == "OPEN":
            return "more"
        if status in {"TRACE_RECORDED", "ABSTAINED", "BLOCKED"}:
            return "end"
        raise AssertionError("DEC008_UNEXPECTED_TERMINAL")

    graph.add_node("one_atomic_sql_step", step)
    graph.add_edge(START, "one_atomic_sql_step")
    graph.add_conditional_edges(
        "one_atomic_sql_step", route,
        {"more": "one_atomic_sql_step", "end": END},
    )
    # Pause after each SQL commit. SQL ledger is authoritative; saver is only
    # a SECOND, independently durable LangGraph state for this experiment.
    return graph.compile(checkpointer=saver, interrupt_after=["one_atomic_sql_step"])


def _config():
    return {
        "configurable": {"thread_id": "synthetic-dec008-tenantA-actorA-run1"},
        "recursion_limit": 25,
    }


def _sql_engine(tmp_path):
    engine = engine_for("sqlite:///" + (tmp_path / "stone-ledger.sqlite").as_posix())
    return engine


@pytest.mark.parametrize("mode,terminal,revision", [
    ("analisar", "TRACE_RECORDED", 5),
    ("recomendar", "TRACE_RECORDED", 6),
    ("gerar_criativo", "ABSTAINED", 5),
])
def test_native_saver_cold_reopen_matches_atomic_sql_ledger(tmp_path, mode, terminal, revision):
    _, _, _, SqliteSaver = _runtime()
    engine = _sql_engine(tmp_path)
    saver_path = tmp_path / "native-langgraph.sqlite"
    try:
        bench._prepare(engine)
        config = _config()
        with SqliteSaver.from_conn_string(str(saver_path)) as saver:
            graph = _graph(engine, saver, mode=mode)
            first = graph.invoke({"receipt": {}}, config)
            assert first["receipt"]["revision"] == 1
            assert graph.get_state(config).values["receipt"]["revision"] == 1
            assert graph.get_state(config).next  # Paused with a next SQL node
        # Both the SQLite native checkpointer and SQLAlchemy connection close
        # to model a real process restart (no shared Python object survives).
        engine.dispose()
        engine = _sql_engine(tmp_path)
        with SqliteSaver.from_conn_string(str(saver_path)) as saver:
            recovered = _graph(engine, saver, mode=mode)
            snapshot = recovered.get_state(config)
            assert snapshot.values["receipt"]["revision"] == 1
            result = None
            for expected_revision in range(2, revision + 1):
                result = recovered.invoke(None, config)
                assert result["receipt"]["revision"] == expected_revision
            assert result is not None
            receipt = result["receipt"]
            assert receipt["status"] == terminal
            assert receipt["production_approved"] is False
            assert receipt["publication_allowed"] is False
            assert recovered.get_state(config).next == ()
            # Resume a terminal thread must not execute an extra SQL node.
            resumed = recovered.invoke(None, config)
            assert resumed["receipt"] == receipt
        with engine.connect() as db:
            ledger = db.execute(select(agent_graph_runs)).mappings().one()
            events = db.execute(select(agent_graph_events)).all()
            assert ledger["revision"] == revision
            assert ledger["chain_sha256"] == receipt["chain_sha256"]
            assert len(events) == revision
        # Native checkpointer saves only technical receipts, not raw source.
        assert b"INJECTION" not in saver_path.read_bytes()
    finally:
        engine.dispose()


def test_native_saver_resume_detects_modified_source_and_keeps_ledger(tmp_path):
    _, _, _, SqliteSaver = _runtime()
    engine = _sql_engine(tmp_path)
    saver_path = tmp_path / "native-langgraph.sqlite"
    try:
        bench._prepare(engine)
        config = _config()
        with SqliteSaver.from_conn_string(str(saver_path)) as saver:
            graph = _graph(engine, saver)
            graph.invoke({"receipt": {}}, config)  # plan
            second = graph.invoke(None, config)      # retrieve, source hashed
            assert second["receipt"]["revision"] == 2
        engine.dispose()
        engine = _sql_engine(tmp_path)
        with engine.begin() as db:
            raw = db.scalar(select(content_items.c.payload).where(
                content_items.c.id == "fixture.post"))
            source = json.loads(raw)
            source["caption"] += " changed after checkpoint"
            db.execute(update(content_items).where(
                content_items.c.id == "fixture.post",
            ).values(payload=json.dumps(source)))
        with SqliteSaver.from_conn_string(str(saver_path)) as saver:
            recovered = _graph(engine, saver)
            with pytest.raises(LocalGraphDenied, match="SOURCE_DRIFT_RESTART_REQUIRED"):
                recovered.invoke(None, config)
        with engine.connect() as db:
            assert db.scalar(select(agent_graph_runs.c.revision)) == 2
            assert len(db.execute(select(agent_graph_events)).all()) == 2
    finally:
        engine.dispose()
