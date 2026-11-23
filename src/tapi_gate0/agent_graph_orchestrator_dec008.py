"""DEC-008 / IMP-027: comparable orchestration adapters, never a release gate.

Both candidates invoke the *same* already-guarded atomic SQL tool step.
LangGraph is optional and must be explicitly installed in the evaluation
sandbox; no silent fallback, network calls, new grants, Studio, or model calls.
This module does not expose either adapter through the operational API.

The LangGraph adapter compares *orchestration overhead and final parity*, NOT
LangGraph's independent persistence or crash recovery; our shared SQL ledger
owns those semantics. DEC-008 stays OPEN until both actual candidates run.
"""
from __future__ import annotations

import importlib.metadata
from typing import Any, Callable, Literal, TypedDict

from .agent_graph_checkpoints import MODES
from .agent_graph_readonly_runner import LocalGraphPlan, execute_bounded, execute_next

BACKENDS = frozenset({"direct", "langgraph"})
SCHEMA = "tapi-dec008-orchestrator-adapter.v1"


class Dec008BackendUnavailable(RuntimeError):
    """Stable non-sensitive code when the genuine candidate is not installed."""


class Dec008BackendDenied(ValueError):
    """Reject unknown backend requests, never implicitly execute one."""


class _State(TypedDict):
    receipt: dict[str, Any]


def available_backends() -> dict[str, str | None]:
    """Report *installed distribution* only, never imply it has been tested."""
    try:
        version = importlib.metadata.version("langgraph")
    except importlib.metadata.PackageNotFoundError:
        version = None
    return {"direct": "tapi-atomic-sql-ledger", "langgraph": version}


def prepare_candidate(engine, *, backend: Literal["direct", "langgraph"],
                      tenant: str, actor: str, run_id: str,
                      plan: LocalGraphPlan) -> Callable[[], dict[str, Any]]:
    """Bind and (if needed) compile a candidate *before* timed invocation."""
    if type(backend) is not str or backend not in BACKENDS:
        raise Dec008BackendDenied("DEC008_BACKEND_NOT_ALLOWED")
    if not isinstance(plan, LocalGraphPlan):
        raise Dec008BackendDenied("DEC008_VALIDATED_PLAN_REQUIRED")

    if backend == "direct":
        return lambda: execute_bounded(engine, tenant=tenant, actor=actor,
                                       run_id=run_id, plan=plan)

    try:
        # A real LangGraph installation is required; we never ship a fake
        # graph or call the direct adapter when the dependency is absent.
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise Dec008BackendUnavailable("DEC008_LANGGRAPH_NOT_INSTALLED") from None

    def invoke_step(state: _State) -> _State:
        # The node writes only the same SQL checkpoint that the direct
        # candidate uses. It never stores raw evidence in LangGraph state.
        receipt = execute_next(engine, tenant=tenant, actor=actor,
                               run_id=run_id, plan=plan)
        return {"receipt": receipt}

    def route(state: _State) -> str:
        receipt = state["receipt"]
        if receipt.get("status") == "OPEN":
            return "more"
        if receipt.get("status") in {"ABSTAINED", "BLOCKED", "TRACE_RECORDED"}:
            return "end"
        raise Dec008BackendDenied("DEC008_INVALID_TERMINAL_STATE")

    graph = StateGraph(_State)
    graph.add_node("atomic_sql_checkpoint_step", invoke_step)
    graph.add_edge(START, "atomic_sql_checkpoint_step")
    graph.add_conditional_edges(
        "atomic_sql_checkpoint_step", route,
        {"more": "atomic_sql_checkpoint_step", "end": END},
    )
    compiled = graph.compile()  # No second checkpointer or external storage.
    def invoke() -> dict[str, Any]:
        output = compiled.invoke(
            {"receipt": {}},
            config={"recursion_limit": max(25, 2 * len(MODES[plan.mode]) + 4)},
        )
        result = output.get("receipt")
        if not isinstance(result, dict) or result.get("status") not in {
            "ABSTAINED", "BLOCKED", "TRACE_RECORDED"
        }:
            raise Dec008BackendDenied("DEC008_INVALID_GRAPH_OUTPUT")
        return result

    return invoke


def execute_candidate(engine, *, backend: Literal["direct", "langgraph"],
                      tenant: str, actor: str, run_id: str,
                      plan: LocalGraphPlan) -> dict[str, Any]:
    """Convenience API; actual benchmark excludes prepare/compile overhead."""
    return prepare_candidate(engine, backend=backend, tenant=tenant,
                             actor=actor, run_id=run_id, plan=plan)()


def prepare_native_reconciled_graph(engine, *, checkpointer, tenant: str,
                                    actor: str, run_id: str,
                                    plan: LocalGraphPlan):
    """Create an *opt-in diagnostic* StateGraph backed by a genuine saver.

    Unlike the performance-only adapter, this version binds the trusted
    native receipt revision to Stone's atomic ledger. A one-step SQL-ahead
    window is reconciled without a second tool invocation. No HTTP endpoint
    calls this factory; caller must manage the saver, trust scope and thread.
    """
    if not isinstance(plan, LocalGraphPlan):
        raise Dec008BackendDenied("DEC008_VALIDATED_PLAN_REQUIRED")
    if checkpointer is None:
        raise Dec008BackendDenied("DEC008_CHECKPOINTER_REQUIRED")
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        raise Dec008BackendUnavailable("DEC008_LANGGRAPH_NOT_INSTALLED") from None
    from .agent_graph_reconciliation_dec008 import execute_reconciled_step

    def invoke_one(state: _State) -> _State:
        return {"receipt": execute_reconciled_step(
            engine, tenant=tenant, actor=actor, run_id=run_id, plan=plan,
            native_receipt=state.get("receipt"),
        )}

    def route(state: _State) -> str:
        status = state["receipt"].get("status")
        if status == "OPEN":
            return "more"
        if status in {"TRACE_RECORDED", "ABSTAINED", "BLOCKED"}:
            return "end"
        raise Dec008BackendDenied("DEC008_INVALID_TERMINAL_STATE")

    graph = StateGraph(_State)
    graph.add_node("atomic_sql_checkpoint_step", invoke_one)
    graph.add_edge(START, "atomic_sql_checkpoint_step")
    graph.add_conditional_edges("atomic_sql_checkpoint_step", route,
                                {"more": "atomic_sql_checkpoint_step", "end": END})
    return graph.compile(checkpointer=checkpointer,
                         interrupt_after=["atomic_sql_checkpoint_step"])
