"""IMP-074: real, bounded read-only tool execution over checkpoint baseline.

The host is responsible for session authentication, tenancy and actor identity.
This module is NOT an HTTP/MCP route or background scheduler. It never sends
network requests, grants third-party creative rights or publishes anything.
The ledger contains only digests; on every resume it *recomputes* prior read-
only tool receipts to fail closed when evidence changes. The creative node
ABSTAINS until a separate operation-specific signed-rights pipeline exists.

A successful trace proves neither independent gold nor permission to deploy.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from decimal import Decimal
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .sa_store import content_items, creators, metrics_snapshots

from .agent_evidence_b2 import EvidenceRetriever, EvidenceNotFound
from .agent_evidence_e1 import analyze_with_ranking
from .agent_graph_checkpoints import (
    AgentCheckpointDenied, MODES, agent_graph_events,
    begin_run, record_node, resume_run,
)
from .domain import Origin
from .sa_store import SqlDomainStore

VERSION = "tapi-imp074-verified-readonly-runner.v1"


class LocalGraphDenied(ValueError):
    """Only a constant error code; no untrusted captions or tool exceptions."""


def _deny(code: str):
    raise LocalGraphDenied("LOCAL_GRAPH_" + code)


class LocalGraphPlan(BaseModel):
    """A conservative plan; external origin is not authorized by this adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    mode: Literal["analisar", "recomendar", "gerar_criativo"]
    content_id: str = Field(min_length=1, max_length=128,
                            pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    origin: Literal["synthetic_local"] = "synthetic_local"
    as_of: datetime
    min_age_days: int = Field(default=14, ge=14, le=3650)

    @field_validator("as_of")
    @classmethod
    def require_utc(cls, value: datetime):
        if (value.tzinfo is None or value.utcoffset() != timedelta(0)):
            raise ValueError("LOCAL_GRAPH_AS_OF_UTC_REQUIRED")
        return value.astimezone(timezone.utc)


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def plan_digest(plan: LocalGraphPlan) -> str:
    if not isinstance(plan, LocalGraphPlan):
        _deny("VALIDATED_PLAN_REQUIRED")
    return _digest({"schema_version": VERSION,
                    "plan": plan.model_dump(mode="json")})


def _evidence(engine, tenant: str, plan: LocalGraphPlan, *, connection=None):
    if connection is None:
        with engine.connect() as db:
            return _evidence(engine, tenant, plan, connection=db)
    db = connection
    evidence = EvidenceRetriever(engine).get(
        tenant, plan.content_id, plan.as_of, connection=db, lock_rows=True)
    # Hash the COMPLETE validated source payload, not the 500-character
    # caption_excerpt. A replay must also detect changes to caption tails,
    # creator identity and late/older metric snapshots. The raw source
    # never reaches the checkpoint ledger or the public return value.
    source = db.execute(select(content_items.c.payload, creators.c.payload)
        .join(creators, (creators.c.tenant_id == content_items.c.tenant_id)
              & (creators.c.id == content_items.c.creator_id))
        .where(content_items.c.tenant_id == tenant,
               content_items.c.id == plan.content_id)
        .with_for_update(read=True)).one_or_none()
    if source is None:
        _deny("SOURCE_BINDING_MISSING")
    snapshot_payloads = db.execute(select(metrics_snapshots.c.payload).where(
        metrics_snapshots.c.tenant_id == tenant,
        metrics_snapshots.c.content_id == plan.content_id,
    ).with_for_update(read=True)).scalars().all()
    source_sha = _digest({"content": source[0], "creator": source[1],
                          "snapshots": sorted(snapshot_payloads)})
    if (evidence.origin != Origin.SYNTHETIC.value
            or evidence.source_url is not None):
        _deny("EXTERNAL_SOURCE_REQUIRES_PEP")
    if evidence.published_at > plan.as_of:
        _deny("FUTURE_REFERENCE")
    if evidence.snapshot_id is None:
        return None
    return evidence, source_sha


def _analysis(engine, tenant: str, plan: LocalGraphPlan, *, connection=None):
    # All ranking queries use the checkpoint transaction's exact DB view.
    class _ScopedRanking:
        def ranking(self, request):
            return SqlDomainStore(engine).ranking(request, connection=connection,
                                                  lock_rows=connection is not None)

    result = analyze_with_ranking(
        _ScopedRanking(), tenant_id=tenant, origin=Origin.SYNTHETIC,
        as_of=plan.as_of, min_age_days=plan.min_age_days,
    )
    if result.tenant_id != tenant or result.origin != Origin.SYNTHETIC:
        _deny("RANKING_SCOPE_INVALID")
    if (not result.abstained_from_pattern_claim
            or result.action not in {"collect_more_evidence", "inspect_ranked_examples"}):
        _deny("UNSUPPORTED_PATTERN_CLAIM")
    return result


def _verify_citations(engine, tenant: str, plan: LocalGraphPlan, analysis, *, connection=None):
    cited = [c for f in analysis.findings for c in f.citations]
    if not cited:
        return False
    if plan.content_id not in {c.content_id for c in cited}:
        return False
    retriever = EvidenceRetriever(engine)
    for citation in cited:
        observed = retriever.get(tenant, citation.content_id, plan.as_of,
                                 connection=connection, lock_rows=True)
        if (observed.origin != Origin.SYNTHETIC.value
                or observed.source_url is not None
                or observed.creator_id != citation.creator_id
                or observed.snapshot_id != citation.snapshot_id
                or observed.followers is None or observed.followers <= 0
                or observed.likes is None or observed.comments is None):
            _deny("CITATION_BINDING_INVALID")
        # The citation's numeric claim must equal the SQL snapshot-derived
        # engagement rate. A correct post/snapshot ID alone is not evidence
        # that a proposed number was actually computed from SQL.
        expected_er = (Decimal(observed.likes + observed.comments)
                       / Decimal(observed.followers))
        if Decimal(citation.engagement_rate) != expected_er:
            _deny("CITATION_RATE_MISMATCH")
    return True


def _node_result(engine, tenant: str, plan: LocalGraphPlan, node: str,
                 *, connection=None):
    """Return (outcome, hash), with the hash derived from actual local tools.

    Missing observations lead to ABSTAIN, invalid/corrupt evidence to BLOCKED.
    Text payloads and captions do not leave this function or enter the ledger.
    """
    plan_sha = plan_digest(plan)
    outcome = "PASS"
    payload_digest = None
    try:
        if node == "plan":
            payload_digest = plan_sha
        elif node == "retrieve":
            observed = _evidence(engine, tenant, plan, connection=connection)
            if observed is None:
                outcome = "ABSTAIN"
                payload_digest = _digest({"reason": "NO_SNAPSHOT"})
            else:
                payload_digest = _digest({
                    "observed": observed[0].model_dump(mode="json"),
                    "full_source_sha256": observed[1],
                })
        elif node in {"analytics", "evidence_verify", "recommendation_draft",
                      "output_verify"}:
            result = _analysis(engine, tenant, plan, connection=connection)
            payload_digest = _digest(result.model_dump(mode="json"))
            if result.n_eligible_posts == 0:
                outcome = "ABSTAIN"
            elif node in {"evidence_verify", "recommendation_draft", "output_verify"}:
                if not _verify_citations(engine, tenant, plan, result,
                                         connection=connection):
                    outcome = "ABSTAIN"
        elif node == "creative_spec_draft":
            # A genuine creative draft requires the external rights PEP or
            # explicit synthetic-only approval in a DIFFERENT authorized API.
            # Do not turn a prompt/fixture into an operative CreativeSpec.
            outcome = "ABSTAIN"
            payload_digest = _digest({"reason": "CREATIVE_RIGHTS_PIPELINE_NOT_BOUND"})
        else:
            _deny("NODE_NOT_ALLOWLISTED")
    except EvidenceNotFound as exc:
        code = str(exc)
        outcome = ("ABSTAIN" if code == "EVIDENCE_CONTENT_NOT_FOUND_IN_TENANT"
                   else "BLOCKED")
        payload_digest = _digest({"reason": outcome, "tool": "local_evidence"})
    except (ValueError, TypeError, AttributeError):
        outcome = "BLOCKED"
        payload_digest = _digest({"reason": "TOOL_VALIDATION_FAILURE"})
    return outcome, _digest({
        "schema_version": VERSION, "node": node, "outcome": outcome,
        "tenant_scope_sha256": _digest({"tenant": tenant, "plan": plan_sha}),
        "tool_payload_sha256": payload_digest,
    })


@contextmanager
def _consistent_step(engine):
    """One transaction for replay, source reads, citation checks and CAS.

    PostgreSQL repeatable-read fixes a coherent data view (including phantoms)
    across separate SQL statements; SQLite obtains a RESERVED writer lock on
    the tenant row before reading any evidence. Only local checkpoints mutate.
    This is NOT a proof of cross-provider permissions or external admission.
    """
    try:
        with engine.connect() as connection:
            if connection.dialect.name == "postgresql":
                connection = connection.execution_options(isolation_level="REPEATABLE READ")
            with connection.begin():
                yield connection
    except SQLAlchemyError:
        # After the transaction context has rolled back, expose only a stable
        # denial code (not database URLs, SQL parameters or raw provider text).
        _deny("TRANSACTION_ABORTED")


def execute_next(engine, *, tenant: str, actor: str, run_id: str,
                 plan: LocalGraphPlan):
    """Execute at most ONE read-only node, with full source revalidation.

    Retry/restart is safe only while underlying evidence reproduces the
    historical hashes. A drifted source makes the old run non-progressable;
    host must create a new run with a fresh pinned plan and review.
    """
    if not isinstance(plan, LocalGraphPlan):
        _deny("VALIDATED_PLAN_REQUIRED")
    # A single DB transaction binds evidence and the checkpoint CAS write.
    # Previously a mutation could land after source verification but before
    # record_node opened its separate write transaction (TOCTOU).
    with _consistent_step(engine) as db:
        begin_run(engine, tenant=tenant, actor=actor, run_id=run_id,
                  mode=plan.mode, plan_sha256=plan_digest(plan),
                  connection=db)
        state = resume_run(engine, tenant=tenant, actor=actor, run_id=run_id,
                           connection=db)
        past = db.execute(select(
            agent_graph_events.c.node, agent_graph_events.c.outcome,
            agent_graph_events.c.receipt_sha256,
        ).where(agent_graph_events.c.tenant_id == tenant,
                agent_graph_events.c.run_id == run_id).order_by(
                agent_graph_events.c.sequence)).all()
        if len(past) != state["revision"]:
            _deny("UNEXPECTED_LEDGER_REVISION")
        for node, original_outcome, original_receipt in past:
            observed_outcome, observed_receipt = _node_result(
                engine, tenant, plan, node, connection=db)
            if original_outcome != observed_outcome or original_receipt != observed_receipt:
                _deny("SOURCE_DRIFT_RESTART_REQUIRED")
        if state["status"] != "OPEN":
            return state
        node = state["next_node"]
        if node not in MODES[plan.mode]:
            _deny("INVALID_CURSOR")
        outcome, receipt_sha256 = _node_result(
            engine, tenant, plan, node, connection=db)
        return record_node(engine, tenant=tenant, actor=actor, run_id=run_id,
                           expected_revision=state["revision"], node=node,
                           outcome=outcome, receipt_sha256=receipt_sha256,
                           connection=db)


def execute_bounded(engine, *, tenant: str, actor: str, run_id: str,
                    plan: LocalGraphPlan):
    """Run only to terminal; bounded by the mode's fixed number of nodes."""
    if not isinstance(plan, LocalGraphPlan):
        _deny("VALIDATED_PLAN_REQUIRED")
    for _ in range(len(MODES[plan.mode]) + 1):
        state = execute_next(engine, tenant=tenant, actor=actor,
                             run_id=run_id, plan=plan)
        if state["status"] != "OPEN":
            return state
    _deny("UNEXPECTED_GRAPH_LENGTH")
