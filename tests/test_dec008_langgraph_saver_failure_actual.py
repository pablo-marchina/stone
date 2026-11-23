"""DEC-008 optional real LangGraph saver fault-injection regression.

A genuine SqliteSaver.put is made to raise after Stone SQL commits its second
read-only step. LangGraph may ALREADY expose this step through pending writes
or a separately persisted checkpoint: do not assume native revision stays 1.
This is a controlled Python exception, NOT a hard process kill,
a distributed transaction, or a guarantee of exactly-once external effects.
Requires LangGraph 1.2.24 and langgraph-checkpoint-sqlite 3.1.3.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select, update

from scripts import dec008_orchestrator_benchmark as bench
from tapi_gate0.agent_graph_checkpoints import agent_graph_events, agent_graph_runs
from tapi_gate0.agent_graph_orchestrator_dec008 import prepare_native_reconciled_graph
from tapi_gate0.agent_graph_readonly_runner import LocalGraphPlan
from tapi_gate0.agent_graph_reconciliation_dec008 import Dec008ReconciliationDenied
from tapi_gate0.sa_store import content_items, engine_for


def _saver():
    pytest.importorskip("langgraph.graph", reason="DEC008_REAL_LANGGRAPH_UNAVAILABLE")
    pytest.importorskip("langgraph.checkpoint.sqlite", reason="DEC008_SQLITE_SAVER_UNAVAILABLE")
    from langgraph.checkpoint.sqlite import SqliteSaver
    return SqliteSaver


def _config():
    return {"configurable": {"thread_id": "dec008-fault-injected-fixture"},
            "recursion_limit": 25}


def _graph(engine, saver, mode):
    return prepare_native_reconciled_graph(
        engine, checkpointer=saver, tenant=bench.TENANT,
        actor=bench.ACTOR, run_id=bench.RUN,
        plan=LocalGraphPlan(mode=mode, content_id="fixture.post", as_of=bench.AS_OF),
    )


def _raise_during_second_native_commit(saver, engine, monkeypatch):
    """Inject before the first genuine native .put seeing SQL revision 2."""
    original = saver.put
    injected = {"raised": 0}

    def fail_after_sql_commit(*args, **kwargs):
        with engine.connect() as db:
            revision = db.scalar(select(agent_graph_runs.c.revision))
        if revision == 2 and injected["raised"] == 0:
            injected["raised"] += 1
            raise RuntimeError("DEC008_INJECTED_NATIVE_SAVER_WRITE_FAILURE")
        return original(*args, **kwargs)

    monkeypatch.setattr(saver, "put", fail_after_sql_commit)
    return injected


@pytest.mark.parametrize("mode,terminal,steps", [
    ("analisar", "TRACE_RECORDED", 5),
    ("recomendar", "TRACE_RECORDED", 6),
    ("gerar_criativo", "ABSTAINED", 5),
])
def test_real_saver_put_failure_reconciles_without_duplicate_step(
        tmp_path, monkeypatch, mode, terminal, steps):
    SqliteSaver = _saver()
    stone = tmp_path / "stone.sqlite"
    native = tmp_path / "native.sqlite"
    engine = engine_for("sqlite:///" + stone.as_posix())
    try:
        bench._prepare(engine)
        with SqliteSaver.from_conn_string(str(native)) as saver:
            graph = _graph(engine, saver, mode)
            first = graph.invoke({"receipt": {}}, _config())
            assert first["receipt"]["revision"] == 1
            injected = _raise_during_second_native_commit(saver, engine, monkeypatch)
            with pytest.raises(RuntimeError, match="DEC008_INJECTED_NATIVE_SAVER_WRITE_FAILURE"):
                graph.invoke(None, _config())
            assert injected["raised"] == 1
        with engine.connect() as db:
            assert db.scalar(select(agent_graph_runs.c.revision)) == 2
            assert len(db.execute(select(agent_graph_events)).all()) == 2
        engine.dispose()
        engine = engine_for("sqlite:///" + stone.as_posix())
        with SqliteSaver.from_conn_string(str(native)) as saver:
            restored = _graph(engine, saver, mode)
            # LangGraph can expose node-2 pending writes even when saver.put
            # raised; the native snapshot may show revision 1 OR 2. Neither
            # observation proves the whole graph is safely resumable.
            observed_revision = restored.get_state(_config()).values["receipt"]["revision"]
            assert observed_revision in (1, 2)
            result = None
            revisions = []
            for _ in range(steps + 2):
                result = restored.invoke(None, _config())
                current = result["receipt"]["revision"]
                revisions.append(current)
                with engine.connect() as db:
                    assert len(db.execute(select(agent_graph_events)).all()) == current
                if result["receipt"]["status"] != "OPEN":
                    break
            assert result is not None
            assert result["receipt"]["revision"] == steps
            assert result["receipt"]["status"] == terminal
            assert revisions == sorted(set(revisions))
            assert result["receipt"]["production_approved"] is False
            assert result["receipt"]["publication_allowed"] is False
    finally:
        engine.dispose()


def test_real_saver_put_failure_then_evidence_drift_abstains_from_recovery(
        tmp_path, monkeypatch):
    SqliteSaver = _saver()
    stone = tmp_path / "stone.sqlite"
    native = tmp_path / "native.sqlite"
    engine = engine_for("sqlite:///" + stone.as_posix())
    try:
        bench._prepare(engine)
        with SqliteSaver.from_conn_string(str(native)) as saver:
            graph = _graph(engine, saver, "analisar")
            assert graph.invoke({"receipt": {}}, _config())["receipt"]["revision"] == 1
            injected = _raise_during_second_native_commit(saver, engine, monkeypatch)
            with pytest.raises(RuntimeError, match="DEC008_INJECTED_NATIVE_SAVER_WRITE_FAILURE"):
                graph.invoke(None, _config())
            assert injected["raised"] == 1
        with engine.begin() as db:
            raw = db.scalar(select(content_items.c.payload))
            changed = json.loads(raw)
            changed["caption"] += " AFTER SQL BEFORE NATIVE"
            db.execute(update(content_items).values(payload=json.dumps(changed)))
        engine.dispose()
        engine = engine_for("sqlite:///" + stone.as_posix())
        with SqliteSaver.from_conn_string(str(native)) as saver:
            graph = _graph(engine, saver, "analisar")
            with pytest.raises(Dec008ReconciliationDenied,
                               match="SOURCE_DRIFT_RESTART_REQUIRED"):
                graph.invoke(None, _config())
        with engine.connect() as db:
            assert db.scalar(select(agent_graph_runs.c.revision)) == 2
            assert len(db.execute(select(agent_graph_events)).all()) == 2
    finally:
        engine.dispose()
