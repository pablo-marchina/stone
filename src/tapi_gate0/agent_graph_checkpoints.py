"""IMP-074 / CAP-005: durable, tenant-scoped *technical* graph checkpoints.

This is a zero-spend baseline for comparing deterministic orchestration with
LangGraph (DEC-008 remains OPEN). It does NOT execute tools or trust the digest
as proof that a tool ran. No user prompts, external captions, model outputs,
credentials or responses are persisted. No HTTP/MCP route or scheduler is
registered. The final node never writes to Studio or authorizes a release.

The trusted host alone may call this API after separately validating the
actor/session and real tool evidence. A hash-only trace is NOT scientific gold,
a current source grant, or an operator approval. All receipts are diagnostic.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import re

from sqlalchemy import (
    Column, ForeignKeyConstraint, Integer, String, Table,
    insert, select, update,
)
from sqlalchemy.exc import IntegrityError

from .sa_store import metadata, tenants

VERSION = "tapi-imp074-agent-checkpoint-baseline.v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
MODES = {
    "analisar": ("plan", "retrieve", "analytics", "evidence_verify", "output_verify"),
    "recomendar": ("plan", "retrieve", "analytics", "evidence_verify",
                  "recommendation_draft", "output_verify"),
    "gerar_criativo": ("plan", "retrieve", "analytics", "evidence_verify",
                     "creative_spec_draft", "output_verify"),
}
OUTCOMES = frozenset({"PASS", "ABSTAIN", "BLOCKED"})
TERMINALS = frozenset({"TRACE_RECORDED", "ABSTAINED", "BLOCKED"})

agent_graph_runs = Table(
    "agent_graph_runs", metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("run_id", String(128), primary_key=True),
    Column("actor_sha256", String(64), nullable=False),
    Column("mode", String(32), nullable=False),
    Column("plan_sha256", String(64), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("cursor", String(40)),
    Column("status", String(32), nullable=False),
    Column("chain_sha256", String(64), nullable=False),
    Column("created_at", String(48), nullable=False),
    Column("updated_at", String(48), nullable=False),
    ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="RESTRICT"),
)

agent_graph_events = Table(
    "agent_graph_events", metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("run_id", String(128), primary_key=True),
    Column("sequence", Integer, primary_key=True),
    Column("node", String(40), nullable=False),
    Column("outcome", String(16), nullable=False),
    Column("receipt_sha256", String(64), nullable=False),
    Column("chain_sha256", String(64), nullable=False),
    Column("created_at", String(48), nullable=False),
    ForeignKeyConstraint(["tenant_id", "run_id"],
                         ["agent_graph_runs.tenant_id", "agent_graph_runs.run_id"],
                         ondelete="RESTRICT"),
)


class AgentCheckpointDenied(ValueError):
    """Fixed code only. Never include caller-supplied strings in exceptions."""


def _deny(code):
    raise AgentCheckpointDenied("AGENT_CHECKPOINT_" + code)


def _id(value):
    return type(value) is str and _ID.fullmatch(value) is not None


def _sha(value):
    return type(value) is str and _SHA.fullmatch(value) is not None


def _digest(parts):
    return sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def _actor_hash(tenant, actor):
    return _digest({"tenant": tenant, "actor": actor, "scope": VERSION})


def _seed(row):
    return _digest({"version": VERSION, "tenant": row["tenant_id"],
                    "run": row["run_id"], "actor_sha256": row["actor_sha256"],
                    "mode": row["mode"], "plan_sha256": row["plan_sha256"]})


def _next(previous, row, sequence, node, outcome, receipt):
    return _digest({"previous": previous, "tenant": row["tenant_id"],
                    "run": row["run_id"], "sequence": sequence,
                    "node": node, "outcome": outcome,
                    "receipt_sha256": receipt})


def _lock_tenant(db, tenant):
    # A no-op UPDATE is deliberately a write lock: SQLite has no FOR UPDATE.
    # PostgreSQL locks the tenant row, serializing CAS with other trusted hosts.
    locked = db.execute(update(tenants).where(
        tenants.c.tenant_id == tenant).values(name=tenants.c.name))
    if locked.rowcount != 1:
        _deny("TENANT_UNAVAILABLE")


def _load(db, tenant, run_id, actor_sha):
    row = db.execute(select(agent_graph_runs).where(
        agent_graph_runs.c.tenant_id == tenant,
        agent_graph_runs.c.run_id == run_id).with_for_update()).mappings().one_or_none()
    if row is None or row["actor_sha256"] != actor_sha:
        _deny("RUN_NOT_IN_TRUSTED_SCOPE")
    run = dict(row)
    nodes = MODES.get(run["mode"])
    if (nodes is None or not _sha(run["plan_sha256"])
            or not _sha(run["actor_sha256"]) or not _sha(run["chain_sha256"])
            or type(run["revision"]) is not int
            or not 0 <= run["revision"] <= len(nodes)):
        _deny("STORED_STATE_INVALID")
    history = db.execute(select(agent_graph_events).where(
        agent_graph_events.c.tenant_id == tenant,
        agent_graph_events.c.run_id == run_id).order_by(
        agent_graph_events.c.sequence)).mappings().all()
    if len(history) != run["revision"]:
        _deny("LEDGER_GAP_OR_EXTRA_ENTRY")
    previous = _seed(run)
    state = "OPEN"
    cursor = nodes[0]
    for i, event in enumerate(history):
        expected = _next(previous, run, i + 1, nodes[i],
                         event["outcome"], event["receipt_sha256"])
        if (event["sequence"] != i + 1 or event["node"] != nodes[i]
                or event["outcome"] not in OUTCOMES
                or not _sha(event["receipt_sha256"])
                or event["chain_sha256"] != expected
                or state != "OPEN"):
            _deny("LEDGER_INTEGRITY_INVALID")
        previous = expected
        if event["outcome"] != "PASS":
            state = "ABSTAINED" if event["outcome"] == "ABSTAIN" else "BLOCKED"
            cursor = None
        elif i + 1 == len(nodes):
            state = "TRACE_RECORDED"
            cursor = None
        else:
            cursor = nodes[i + 1]
    if (run["chain_sha256"] != previous or run["status"] != state
            or run["cursor"] != cursor):
        _deny("STORED_STATE_DRIFT")
    return run, history


def _receipt(run):
    return {
        "schema_version": VERSION,
        "status": run["status"],
        "mode": run["mode"],
        "revision": run["revision"],
        "next_node": run["cursor"],
        "chain_sha256": run["chain_sha256"],
        "synthetic_or_technical_trace_only": True,
        "node_execution_proved": False,
        "model_calls_performed": 0,
        "independent_gold_available": False,
        "rights_verified": False,
        "scientifically_validated": False,
        "studio_write_allowed": False,
        "publication_allowed": False,
        "production_approved": False,
        "global_gates_released": False,
    }


def begin_run(engine, *, tenant, actor, run_id, mode, plan_sha256):
    """Reserve a tenant-bound synthetic trace; replay the same plan exactly."""
    if (not _id(tenant) or not _id(actor) or not _id(run_id)
            or type(mode) is not str or mode not in MODES
            or not _sha(plan_sha256)):
        _deny("INPUT_INVALID")
    actor_sha = _actor_hash(tenant, actor)
    try:
        with engine.begin() as db:
            _lock_tenant(db, tenant)
            found = db.execute(select(agent_graph_runs).where(
                agent_graph_runs.c.tenant_id == tenant,
                agent_graph_runs.c.run_id == run_id)).mappings().one_or_none()
            if found is not None:
                if (found["actor_sha256"] != actor_sha
                        or found["mode"] != mode
                        or found["plan_sha256"] != plan_sha256):
                    _deny("RUN_ID_CONFLICT")
                run, _ = _load(db, tenant, run_id, actor_sha)
                return _receipt(run)
            timestamp = datetime.now(timezone.utc).isoformat()
            row = dict(tenant_id=tenant, run_id=run_id,
                       actor_sha256=actor_sha, mode=mode,
                       plan_sha256=plan_sha256, revision=0,
                       cursor=MODES[mode][0], status="OPEN",
                       created_at=timestamp, updated_at=timestamp)
            row["chain_sha256"] = _seed(row)
            db.execute(insert(agent_graph_runs).values(**row))
            return _receipt(row)
    except IntegrityError:
        _deny("CONCURRENT_START_CONFLICT")


def record_node(engine, *, tenant, actor, run_id, expected_revision,
                node, outcome, receipt_sha256):
    """Record a host-verified node receipt, never execute any tool itself.

    A retry with identical (sequence, node, outcome, receipt hash) is safe;
    stale or contradictory updates are denied and no writes occur. A stored
    trace alone is not proof of tool execution, provenance or permissions.
    """
    if (not _id(tenant) or not _id(actor) or not _id(run_id)
            or type(expected_revision) is not int or expected_revision < 0
            or type(node) is not str or type(outcome) is not str
            or outcome not in OUTCOMES or not _sha(receipt_sha256)):
        _deny("INPUT_INVALID")
    actor_sha = _actor_hash(tenant, actor)
    with engine.begin() as db:
        _lock_tenant(db, tenant)
        run, history = _load(db, tenant, run_id, actor_sha)
        if expected_revision < run["revision"]:
            if expected_revision >= len(history):
                _deny("REVISION_CONFLICT")
            prior = history[expected_revision]
            if (prior["node"] != node or prior["outcome"] != outcome
                    or prior["receipt_sha256"] != receipt_sha256):
                _deny("REPLAY_CONFLICT")
            return _receipt(run)
        if expected_revision != run["revision"] or run["status"] != "OPEN":
            _deny("REVISION_CONFLICT")
        nodes = MODES[run["mode"]]
        if node != run["cursor"]:
            _deny("NODE_OUT_OF_ORDER")
        next_revision = expected_revision + 1
        next_chain = _next(run["chain_sha256"], run, next_revision,
                           node, outcome, receipt_sha256)
        if outcome != "PASS":
            status = "ABSTAINED" if outcome == "ABSTAIN" else "BLOCKED"
            next_node = None
        elif next_revision == len(nodes):
            status, next_node = "TRACE_RECORDED", None
        else:
            status, next_node = "OPEN", nodes[next_revision]
        now = datetime.now(timezone.utc).isoformat()
        db.execute(insert(agent_graph_events).values(
            tenant_id=tenant, run_id=run_id, sequence=next_revision,
            node=node, outcome=outcome, receipt_sha256=receipt_sha256,
            chain_sha256=next_chain, created_at=now,
        ))
        updated = db.execute(update(agent_graph_runs).where(
            agent_graph_runs.c.tenant_id == tenant,
            agent_graph_runs.c.run_id == run_id,
            agent_graph_runs.c.revision == expected_revision,
            agent_graph_runs.c.chain_sha256 == run["chain_sha256"],
        ).values(revision=next_revision, cursor=next_node, status=status,
                 chain_sha256=next_chain, updated_at=now))
        if updated.rowcount != 1:
            _deny("CONCURRENT_UPDATE_CONFLICT")
        return _receipt({**run, "revision": next_revision,
                         "cursor": next_node, "status": status,
                         "chain_sha256": next_chain})


def resume_run(engine, *, tenant, actor, run_id):
    """Recheck full hash chain on read; no tool replay or privilege implied."""
    if not _id(tenant) or not _id(actor) or not _id(run_id):
        _deny("INPUT_INVALID")
    with engine.connect() as db:
        run, _ = _load(db, tenant, run_id, _actor_hash(tenant, actor))
        return _receipt(run)
