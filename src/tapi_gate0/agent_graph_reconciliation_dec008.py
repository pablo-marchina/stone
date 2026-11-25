"""DEC-008: fail-closed reconciliation for Stone SQL vs LangGraph checkpoint.

A durable Stone SQL step may commit before a SECOND independent LangGraph
checkpointer records its state. This read-only, synthetic-only bridge treats
Stone's hash-checked ledger as authoritative and permits at most ONE missing
native acknowledgement. It repeats read-only source queries to revalidate
previous receipts but does not write or advance an already committed step.

The native receipt MUST originate from trusted in-process LangGraph state,
never an API request. There is no distributed transaction, exactly-once
external effect, native saver verification or publication authorization here.
Any future side-effectful tool requires an independent idempotency protocol.
"""
from __future__ import annotations

from sqlalchemy import select

from .agent_graph_checkpoints import (
    MODES, VERSION as LEDGER_VERSION, agent_graph_events,
    begin_run, record_node, resume_run,
)
from .agent_graph_readonly_runner import (
    LocalGraphPlan, _consistent_step, _node_result, plan_digest,
)


# The native receipt must be exactly the technical envelope emitted by Stone.
# Unknown fields cannot be used to smuggle permissions or source payloads via
# a future change in graph state serialization. No production authority is
# ever inferred from this receipt, including on a previously acknowledged step.
_NATIVE_RECEIPT_KEYS = frozenset({
    "schema_version", "status", "mode", "revision", "next_node",
    "chain_sha256", "synthetic_or_technical_trace_only",
    "node_execution_proved", "model_calls_performed",
    "independent_gold_available", "rights_verified",
    "scientifically_validated", "studio_write_allowed",
    "publication_allowed", "production_approved", "global_gates_released",
})


class Dec008ReconciliationDenied(ValueError):
    """Fixed error codes: never embed source or native state in exceptions."""


def _deny(code: str) -> None:
    raise Dec008ReconciliationDenied("DEC008_RECONCILIATION_" + code)


def _native_revision(native_receipt, *, plan, history):
    if native_receipt is None or native_receipt == {}:
        return 0
    if type(native_receipt) is not dict:
        _deny("NATIVE_RECEIPT_INVALID")
    if frozenset(native_receipt) != _NATIVE_RECEIPT_KEYS:
        _deny("NATIVE_RECEIPT_INVALID")
    if (native_receipt["synthetic_or_technical_trace_only"] is not True
            or native_receipt["independent_gold_available"] is not False
            or type(native_receipt["model_calls_performed"]) is not int
            or native_receipt["model_calls_performed"] != 0):
        _deny("NATIVE_AUTHORITY_FORGERY")
    revision = native_receipt.get("revision")
    if type(revision) is not int or revision < 1:
        _deny("NATIVE_RECEIPT_INVALID")
    if revision > len(history):
        _deny("NATIVE_AHEAD_OF_SQL_LEDGER")
    prior = history[revision - 1]
    if (native_receipt.get("schema_version") != LEDGER_VERSION
            or native_receipt.get("mode") != plan.mode
            or native_receipt.get("chain_sha256") != prior["chain_sha256"]):
        _deny("NATIVE_RECEIPT_MISMATCH")
    outcome = prior["outcome"]
    if outcome == "ABSTAIN":
        expected_status = "ABSTAINED"
    elif outcome == "BLOCKED":
        expected_status = "BLOCKED"
    elif revision == len(MODES[plan.mode]):
        expected_status = "TRACE_RECORDED"
    else:
        expected_status = "OPEN"
    expected_cursor = (MODES[plan.mode][revision]
                       if expected_status == "OPEN" else None)
    if (native_receipt.get("status") != expected_status
            or native_receipt.get("next_node") != expected_cursor):
        _deny("NATIVE_RECEIPT_MISMATCH")
    for field in ("rights_verified", "scientifically_validated",
                  "studio_write_allowed", "publication_allowed",
                  "production_approved", "global_gates_released",
                  "node_execution_proved"):
        if native_receipt.get(field) is not False:
            _deny("NATIVE_AUTHORITY_FORGERY")
    return revision


def execute_reconciled_step(engine, *, tenant: str, actor: str, run_id: str,
                            plan: LocalGraphPlan, native_receipt=None):
    """Execute one step OR acknowledge a validated one-step SQL/native gap.

    Only in-process synthetic read-only tools. Never expose native_receipt to
    untrusted callers, and never treat native/SQL parity as scientific gold.
    """
    if not isinstance(plan, LocalGraphPlan):
        _deny("VALIDATED_PLAN_REQUIRED")
    with _consistent_step(engine) as db:
        begin_run(engine, tenant=tenant, actor=actor, run_id=run_id,
                  mode=plan.mode, plan_sha256=plan_digest(plan),
                  connection=db)
        sql = resume_run(engine, tenant=tenant, actor=actor, run_id=run_id,
                         connection=db)
        history = db.execute(select(
            agent_graph_events.c.node, agent_graph_events.c.outcome,
            agent_graph_events.c.receipt_sha256, agent_graph_events.c.chain_sha256,
        ).where(agent_graph_events.c.tenant_id == tenant,
                agent_graph_events.c.run_id == run_id).order_by(
                agent_graph_events.c.sequence)).mappings().all()
        if len(history) != sql["revision"]:
            _deny("LEDGER_REVISION_DRIFT")
        nativerev = _native_revision(native_receipt, plan=plan, history=history)
        gap = sql["revision"] - nativerev
        if gap > 1:
            _deny("NATIVE_TOO_FAR_BEHIND")
        if gap < 0:
            _deny("NATIVE_AHEAD_OF_SQL_LEDGER")

        for event in history:
            outcome, digest = _node_result(engine, tenant, plan, event["node"],
                                           connection=db)
            if outcome != event["outcome"] or digest != event["receipt_sha256"]:
                _deny("SOURCE_DRIFT_RESTART_REQUIRED")

        # Stone already committed this step. Source queries above are rechecked,
        # but never append or advance its event a second time.
        if gap == 1 or sql["status"] != "OPEN":
            return sql
        node = sql["next_node"]
        if node not in MODES[plan.mode]:
            _deny("CURSOR_INVALID")
        outcome, digest = _node_result(engine, tenant, plan, node,
                                       connection=db)
        return record_node(engine, tenant=tenant, actor=actor, run_id=run_id,
                           expected_revision=nativerev, node=node,
                           outcome=outcome, receipt_sha256=digest,
                           connection=db)


def validate_native_resume(engine, *, tenant: str, actor: str, run_id: str,
                           plan: LocalGraphPlan, native_receipt=None):
    """Read-only resume guard, even if LangGraph has NO scheduled next node.

    SqliteSaver may expose successful pending writes after put() raises.
    Checking only the next node misses drift when invoke(None) is a no-op.
    The authoritative ledger, plan and all existing source hashes are
    validated BEFORE allowing the native graph to resume or return state.
    No step, grant or checkpoint is created by this preflight.
    """
    from .agent_graph_checkpoints import agent_graph_runs

    if not isinstance(plan, LocalGraphPlan):
        _deny("VALIDATED_PLAN_REQUIRED")
    with _consistent_step(engine) as db:
        sql = resume_run(engine, tenant=tenant, actor=actor, run_id=run_id,
                         connection=db)
        plan_sha = db.scalar(select(agent_graph_runs.c.plan_sha256).where(
            agent_graph_runs.c.tenant_id == tenant,
            agent_graph_runs.c.run_id == run_id))
        if sql["mode"] != plan.mode or plan_sha != plan_digest(plan):
            _deny("NATIVE_PLAN_MISMATCH")
        history = db.execute(select(
            agent_graph_events.c.node, agent_graph_events.c.outcome,
            agent_graph_events.c.receipt_sha256, agent_graph_events.c.chain_sha256,
        ).where(agent_graph_events.c.tenant_id == tenant,
                agent_graph_events.c.run_id == run_id).order_by(
                agent_graph_events.c.sequence)).mappings().all()
        if len(history) != sql["revision"]:
            _deny("LEDGER_REVISION_DRIFT")
        native_revision = _native_revision(native_receipt, plan=plan,
                                           history=history)
        gap = sql["revision"] - native_revision
        if gap > 1:
            _deny("NATIVE_TOO_FAR_BEHIND")
        if gap < 0:
            _deny("NATIVE_AHEAD_OF_SQL_LEDGER")
        for event in history:
            outcome, digest = _node_result(engine, tenant, plan, event["node"],
                                           connection=db)
            if outcome != event["outcome"] or digest != event["receipt_sha256"]:
                _deny("SOURCE_DRIFT_RESTART_REQUIRED")
        return sql
