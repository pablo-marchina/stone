"""IMP-027 / DEC-008 hard gates; no fake candidate is used as benchmark proof."""
from __future__ import annotations

import builtins
import json
import sys
import types

import pytest
from sqlalchemy import select

from scripts import dec008_orchestrator_benchmark as bm
from tapi_gate0.agent_graph_checkpoints import agent_graph_events, agent_graph_runs
from tapi_gate0.agent_graph_orchestrator_dec008 import (
    Dec008BackendDenied, Dec008BackendUnavailable, execute_candidate,
)
from tapi_gate0.agent_graph_readonly_runner import LocalGraphPlan
from tapi_gate0.sa_store import engine_for


@pytest.fixture
def engine():
    engine = engine_for("sqlite:///:memory:")
    bm._prepare(engine)
    yield engine
    engine.dispose()


def make_plan(mode="analisar"):
    return LocalGraphPlan(mode=mode, content_id="fixture.post", as_of=bm.AS_OF)


@pytest.mark.parametrize("mode,status,revision", [
    ("analisar", "TRACE_RECORDED", 5),
    ("recomendar", "TRACE_RECORDED", 6),
    ("gerar_criativo", "ABSTAINED", 5),
])
def test_direct_runs_real_sql_with_terminal_ledger_and_no_rights(engine, mode, status, revision):
    receipt = execute_candidate(
        engine, backend="direct", tenant=bm.TENANT, actor=bm.ACTOR,
        run_id=bm.RUN, plan=make_plan(mode),
    )
    assert receipt["status"] == status
    assert receipt["revision"] == revision
    assert all(receipt[field] is False for field in bm.NEVER_TRUE)
    assert receipt["model_calls_performed"] == 0
    with engine.connect() as db:
        assert len(db.execute(select(agent_graph_events)).all()) == revision
        assert len(db.execute(select(agent_graph_runs)).all()) == 1
    assert "INJECTION" not in str(receipt)


def test_unavailable_real_graph_fails_without_silent_direct_fallback(engine, monkeypatch):
    original = builtins.__import__

    def no_langgraph(name, *args, **kwargs):
        if name == "langgraph.graph":
            raise ModuleNotFoundError("langgraph not installed")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_langgraph)
    with pytest.raises(Dec008BackendUnavailable, match="DEC008_LANGGRAPH_NOT_INSTALLED"):
        execute_candidate(engine, backend="langgraph", tenant=bm.TENANT,
                          actor=bm.ACTOR, run_id=bm.RUN, plan=make_plan())
    with engine.connect() as db:
        assert db.execute(select(agent_graph_runs)).first() is None
        assert db.execute(select(agent_graph_events)).first() is None


@pytest.mark.parametrize("bad", ["fake", "LANGGRAPH", "auto", "", None, True])
def test_no_implicit_backend_fallback_or_authority(engine, bad):
    with pytest.raises(Dec008BackendDenied, match="DEC008_BACKEND_NOT_ALLOWED"):
        execute_candidate(engine, backend=bad, tenant=bm.TENANT, actor=bm.ACTOR,
                          run_id=bm.RUN, plan=make_plan())
    with engine.connect() as db:
        assert db.execute(select(agent_graph_runs)).first() is None


def test_raw_unvalidated_plan_is_rejected_before_any_writes(engine):
    with pytest.raises(Dec008BackendDenied, match="DEC008_VALIDATED_PLAN_REQUIRED"):
        execute_candidate(engine, backend="direct", tenant=bm.TENANT,
                          actor=bm.ACTOR, run_id=bm.RUN, plan={"mode": "analisar"})
    with engine.connect() as db:
        assert db.execute(select(agent_graph_runs)).first() is None


@pytest.mark.parametrize("mode", ["analisar", "recomendar", "gerar_criativo"])
def test_offline_benchmark_reports_unavailable_as_not_comparable(monkeypatch, mode):
    monkeypatch.setattr(bm, "available_backends", lambda: {
        "direct": "fixture-ledger", "langgraph": None,
    })
    original = bm.prepare_candidate

    def direct_only(engine, *, backend, **kw):
        if backend == "langgraph":
            raise Dec008BackendUnavailable("DEC008_LANGGRAPH_NOT_INSTALLED")
        return original(engine, backend=backend, **kw)

    monkeypatch.setattr(bm, "prepare_candidate", direct_only)
    report = bm.benchmark(repetitions=3, mode=mode)
    assert report["status"] == "NOT_COMPARABLE"
    assert report["decision"] == "DEC-008_OPEN"
    assert report["results"]["langgraph"]["status"] == "NOT_RUN_DEPENDENCY_UNAVAILABLE"
    assert report["results"]["direct"]["execution_latency"]["n"] == 3
    assert report["results"]["direct"]["terminal_status"] == (
        "ABSTAINED" if mode == "gerar_criativo" else "TRACE_RECORDED")
    assert report["parity_verified"] is False
    assert not report["production_approved"] and not report["global_gates_released"]
    assert "INJECTION" not in json.dumps(report)


@pytest.mark.parametrize("kwargs", [
    {"repetitions": 2}, {"repetitions": 101}, {"repetitions": True},
    {"mode": "publish"},
])
def test_benchmark_rejects_invalid_protocol_without_io(kwargs):
    with pytest.raises(ValueError):
        bm.benchmark(**kwargs)


def test_cli_refuses_to_report_parity_if_langgraph_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(bm, "available_backends", lambda: {"direct": "local", "langgraph": None})
    def direct_only(engine, *, backend, **kw):
        if backend == "langgraph":
            raise Dec008BackendUnavailable("DEC008_LANGGRAPH_NOT_INSTALLED")
        from tapi_gate0.agent_graph_orchestrator_dec008 import prepare_candidate
        return prepare_candidate(engine, backend=backend, **kw)
    monkeypatch.setattr(bm, "prepare_candidate", direct_only)
    destination = tmp_path / "result.json"
    assert bm.main(["--repetitions", "3", "--output", str(destination)]) == 2
    report = json.loads(destination.read_text())
    assert report["decision"] == "DEC-008_OPEN"
    assert report["status"] == "NOT_COMPARABLE"
    output = capsys.readouterr().out
    assert "DEC008_PARITY_VERIFIED=false" in output


class _FakeStateGraph:
    """TEST DOUBLE: tests adapter calling contract, not actual LangGraph."""
    def __init__(self, state):
        self.fn = None
        self.route = None
        self.edges = None

    def add_node(self, _name, fn):
        self.fn = fn

    def add_edge(self, _source, _target):
        pass

    def add_conditional_edges(self, _name, route, choices):
        self.route = route
        self.edges = choices

    def compile(self):
        return self

    def invoke(self, value, config):
        for _ in range(config["recursion_limit"]):
            value = self.fn(value)
            if self.route(value) == "end":
                return value
        raise AssertionError("fake runner exceeded recursion bound")


def test_langgraph_adapter_contract_only_using_explicit_fake(engine, monkeypatch):
    import tapi_gate0.agent_graph_orchestrator_dec008 as adaptor
    stub_package = types.ModuleType("langgraph")
    stub_graph = types.ModuleType("langgraph.graph")
    stub_graph.START = "__start__"
    stub_graph.END = "__end__"
    stub_graph.StateGraph = _FakeStateGraph
    monkeypatch.setitem(sys.modules, "langgraph", stub_package)
    monkeypatch.setitem(sys.modules, "langgraph.graph", stub_graph)
    receipt = adaptor.execute_candidate(engine, backend="langgraph", tenant=bm.TENANT,
                                        actor=bm.ACTOR, run_id=bm.RUN, plan=make_plan())
    assert receipt["status"] == "TRACE_RECORDED"
    assert receipt["revision"] == 5
    assert receipt["production_approved"] is False
    # A stub is NEVER a benchmark or a DEC candidate measurement.


def test_same_seed_yields_same_full_ledger_for_independent_direct_runs(tmp_path):
    values = []
    for i in (0, 1):
        engine = engine_for("sqlite:///" + str(tmp_path / f"run{i}.sqlite"))
        try:
            bm._prepare(engine)
            result = execute_candidate(engine, backend="direct", tenant=bm.TENANT,
                                       actor=bm.ACTOR, run_id=bm.RUN, plan=make_plan())
            values.append((result["revision"], result["status"],
                           result["chain_sha256"]))
        finally:
            engine.dispose()
    assert values[0] == values[1]
