"""DEC-008: protected AV candidate review bound to the existing SQL ledger.

Trusted local caller only. This is NOT an operational agent API, E1 assessment,
scientific admission, recommendation, or creative tool. The SQLite rights,
artifact reads and checkpoint CAS share a single BEGIN IMMEDIATE transaction.
A fresh candidate digest is checked even on terminal replay; revocation or
evidence drift fails closed without another checkpoint. No LangGraph/native
saver parity or cross-database atomicity is claimed by this adapter.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from .agent_graph_checkpoints import (
    MODES, agent_graph_events, begin_run, record_node, resume_run,
)
from .asset_candidate_fusion import _evaluate_authorized_in_transaction
from .asset_derived_payloads import DerivedPayloadStore
from .asset_system_one_guarded_handoff import _project_guarded

VERSION = "tapi-dec008-protected-av-review.v1"
MODE = "av_candidate_review"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_ARTIFACT = re.compile(r"artifact\.[a-f0-9]{64}\Z")


class ProtectedAVReviewDenied(ValueError):
    """Fixed denial code; no text, media, keys or source URLs."""


def _deny(code: str):
    raise ProtectedAVReviewDenied("DEC008_PROTECTED_AV_" + code)


class ProtectedAVReviewPlan(BaseModel):
    """A research-only binding; not a LocalGraphPlan or HTTP request."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    content_id: str
    object_id: str
    artifact_ids: tuple[str, str, str, str]

    @field_validator("content_id")
    @classmethod
    def content_valid(cls, value):
        if not _ID.fullmatch(value):
            raise ValueError("CONTENT_ID_INVALID")
        return value

    @field_validator("object_id")
    @classmethod
    def object_valid(cls, value):
        if not _SHA.fullmatch(value):
            raise ValueError("OBJECT_ID_INVALID")
        return value

    @field_validator("artifact_ids")
    @classmethod
    def artifact_valid(cls, value):
        if len(set(value)) != 4 or any(not _ARTIFACT.fullmatch(x) for x in value):
            raise ValueError("ARTIFACT_SELECTION_INVALID")
        return tuple(sorted(value))


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _plan_digest(plan):
    return _digest({"schema_version": VERSION, "mode": MODE,
                    "purpose": "research_analysis",
                    "plan": plan.model_dump(mode="json")})


def _technical_result(plan_sha, candidate_sha, node, reviewable):
    if node not in MODES[MODE]:
        _deny("NODE_INVALID")
    # PASS is strictly a technical receipt, never a scientific verdict.
    # An incomplete or all-abstained bundle terminates at evidence_verify.
    outcome = "ABSTAIN" if node == "evidence_verify" and not reviewable else "PASS"
    return outcome, _digest({"schema_version": VERSION, "plan_sha256": plan_sha,
                             "candidate_sha256": candidate_sha,
                             "node": node, "outcome": outcome})


def execute_protected_av_review_step(store, *, tenant: str, actor: str,
                                     run_id: str, plan: ProtectedAVReviewPlan):
    """Re-evaluate four protected candidates and append at most one digest.

    Actor/session authentication is the responsibility of the trusted host.
    No public route accepts this plan. No caller-supplied candidate digest
    or checkpoint is accepted in lieu of a live rights-checked evaluation.
    """
    if type(plan) is not ProtectedAVReviewPlan or not isinstance(store, DerivedPayloadStore):
        _deny("TRUSTED_PLAN_AND_STORE_REQUIRED")
    if any(type(v) is not str or not _ID.fullmatch(v)
           for v in (tenant, actor, run_id)):
        _deny("SCOPE_INVALID")
    # Pydantic model_construct/model_copy can bypass validation. Recheck at
    # the trusted execution boundary, including normalized artifact order.
    try:
        plan = ProtectedAVReviewPlan.model_validate(plan.model_dump(mode="python"))
    except (ValueError, TypeError):
        _deny("PLAN_INVALID")
    plan_sha = _plan_digest(plan)
    q = store.queue
    engine = q.index.engine
    if engine.dialect.name != "sqlite":
        _deny("SQLITE_TRANSACTION_REQUIRED")
    with q._transaction() as (db, now):
        # Lock and validate ledger identity before deriving a candidate;
        # any denial below rolls back even a newly reserved run.
        begin_run(engine, tenant=tenant, actor=actor, run_id=run_id,
                  mode=MODE, plan_sha256=plan_sha, connection=db)
        state = resume_run(engine, tenant=tenant, actor=actor, run_id=run_id,
                           connection=db)
        history = db.execute(select(
            agent_graph_events.c.node, agent_graph_events.c.outcome,
            agent_graph_events.c.receipt_sha256,
        ).where(agent_graph_events.c.tenant_id == tenant,
                agent_graph_events.c.run_id == run_id).order_by(
                agent_graph_events.c.sequence)).all()
        if len(history) != state["revision"]:
            _deny("LEDGER_DRIFT")
        guard = _evaluate_authorized_in_transaction(
            store, db, now, tenant, plan.object_id, plan.artifact_ids,
            purpose="research_analysis", coverage_guard=True)
        candidate = _project_guarded(guard)
        if (candidate["tenant_id"], candidate["content_id"],
                candidate["object_id"], candidate["purpose"]) != (
                tenant, plan.content_id, plan.object_id, "research_analysis"):
            _deny("CANDIDATE_SCOPE_MISMATCH")
        candidate_sha = _digest(candidate)
        reviewable = (candidate["status"] == "GUARDED_CANDIDATES_ONLY" and
                      any(f["state"] == "candidate" for f in candidate["candidate_fields"]))
        for node, outcome, receipt in history:
            if _technical_result(plan_sha, candidate_sha, node, reviewable) != (outcome, receipt):
                _deny("SOURCE_DRIFT_RESTART_REQUIRED")
        if state["status"] != "OPEN":
            return state
        node = state["next_node"]
        outcome, receipt = _technical_result(plan_sha, candidate_sha, node, reviewable)
        return record_node(engine, tenant=tenant, actor=actor, run_id=run_id,
                           expected_revision=state["revision"], node=node,
                           outcome=outcome, receipt_sha256=receipt, connection=db)


def execute_protected_av_review(store, *, tenant: str, actor: str,
                                run_id: str, plan: ProtectedAVReviewPlan):
    """Bounded direct adapter; independently revalidates on each step."""
    for _ in range(len(MODES[MODE]) + 1):
        state = execute_protected_av_review_step(
            store, tenant=tenant, actor=actor, run_id=run_id, plan=plan)
        if state["status"] != "OPEN":
            return state
    _deny("GRAPH_LENGTH_INVALID")
