"""Real SQL ledger and guarded projection; protected source is a test double.

These tests do not prove rights, decrypt media or invoke LangGraph. The signed
rights integration lives in test_asset_rights_registry.py, using actual storage.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace as S

import pytest
from sqlalchemy import create_engine, select, func, insert

from tapi_gate0 import agent_graph_protected_av_dec008 as review
from tapi_gate0.agent_graph_checkpoints import (
    agent_graph_events, agent_graph_runs, AgentCheckpointDenied,
)
from tapi_gate0.sa_store import metadata, tenants
from tapi_gate0.asset_system_one_guarded_handoff import FIELDS, PROCESSORS

IDS = tuple("artifact." + str(n)*64 for n in range(4))
OBJECT = "b"*64
TENANT = "fixture"


def guard(*, partial=False, all_abstained=False):
    names = list(FIELDS) + [f"other{i}" for i in range(16)]
    fields = tuple(S(field_id=n, state="abstained" if n in FIELDS else "not_assessed",
                     value=None, supports=(), vetoes=()) for n in names)
    if not all_abstained:
        fields[3].state = "candidate"
        fields[3].value = True
        fields[3].supports = (S(artifact_id=IDS[1], payload_sha256="d"*64, processor="ocr"),)
    decision = S(tenant_id=TENANT, content_id="post", object_id=OBJECT,
                 purpose="research_analysis", evidence_fingerprint="a"*64,
                 scientific_evidence=False, canonical_rubric=False, fields=fields)
    coverage = {p: "observed" for p in PROCESSORS}
    details = {p: {"state": "observed", "reason": None} for p in PROCESSORS}
    if partial:
        coverage["asr_vad"] = "abstained"
        details["asr_vad"] = {"state": "abstained", "reason": "insufficient_evidence"}
    return dict(schema_version="shared-av-coverage-guard.v1", baseline=decision,
                guarded=deepcopy(decision), source_fingerprint="a"*64,
                coverage=coverage, coverage_details=details, quality_rejections={},
                suppressed_fields=(), inference_reexecuted=False,
                canonical_rubric=False, scientific_evidence=False, policy_promoted=False)


class _FakeQueue:
    def __init__(self, engine):
        self.index = S(engine=engine)

    @contextmanager
    def _transaction(self):
        with self.index.engine.connect() as db:
            db.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield db, datetime.now(timezone.utc)
                db.commit()
            except BaseException:
                db.rollback()
                raise


class _FakeStore:
    """Test-only; production continues requiring DerivedPayloadStore."""
    def __init__(self, engine):
        self.queue = _FakeQueue(engine)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/review.sqlite")
    metadata.create_all(engine, tables=[tenants, agent_graph_runs, agent_graph_events])
    with engine.begin() as db:
        db.execute(insert(tenants), {"tenant_id": TENANT, "name": "fixture"})
    store = _FakeStore(engine)
    state = S(guard=guard(), revoked=False, calls=0)

    def evaluate(s, db, now, tenant, root, ids, *, purpose, coverage_guard):
        assert s is store and db.engine is engine and db.in_transaction()
        assert tenant == TENANT and root == OBJECT and ids == IDS
        assert purpose == "research_analysis" and coverage_guard is True
        state.calls += 1
        if state.revoked:
            raise ValueError("SIMULATED_REVOCATION")
        return deepcopy(state.guard)

    monkeypatch.setattr(review, "DerivedPayloadStore", _FakeStore)
    monkeypatch.setattr(review, "_evaluate_authorized_in_transaction", evaluate)
    plan = review.ProtectedAVReviewPlan(content_id="post", object_id=OBJECT, artifact_ids=IDS)
    kw = dict(tenant=TENANT, actor="operator", run_id="run", plan=plan)
    try:
        yield S(e=engine, store=store, source=state, kw=kw)
    finally:
        engine.dispose()


def count(s, table):
    with s.e.connect() as db:
        return db.scalar(select(func.count()).select_from(table))


def step(s, **kwargs):
    return review.execute_protected_av_review_step(s.store, **(s.kw | kwargs))


def full(s):
    return review.execute_protected_av_review(s.store, **s.kw)


def test_full_terminal_and_no_duplicate(setup):
    s = setup
    out = full(s)
    assert (out["status"], out["revision"]) == ("TRACE_RECORDED", 4)
    assert step(s) == out and s.source.calls == 5
    assert count(s, agent_graph_events) == 4
    assert out["production_approved"] is False and out["studio_write_allowed"] is False


@pytest.mark.parametrize("partial,empty", [(True, False), (False, True)])
def test_partial_and_empty_abstain(setup, partial, empty):
    s = setup
    s.source.guard = guard(partial=partial, all_abstained=empty)
    out = full(s)
    assert (out["status"], out["revision"]) == ("ABSTAINED", 3)
    assert step(s) == out
    assert count(s, agent_graph_events) == 3


def test_drift_rolls_back(setup):
    s = setup
    step(s)
    s.source.guard["guarded"].evidence_fingerprint = "f"*64
    s.source.guard["baseline"].evidence_fingerprint = "f"*64
    s.source.guard["source_fingerprint"] = "f"*64
    with pytest.raises(review.ProtectedAVReviewDenied, match="SOURCE_DRIFT"):
        step(s)
    assert count(s, agent_graph_events) == 1


def test_revoked_terminal_and_new_run_roll_back(setup):
    s = setup
    full(s)
    s.source.revoked = True
    for run in ["run", "new-run"]:
        with pytest.raises(ValueError, match="SIMULATED_REVOCATION"):
            step(s, run_id=run)
    assert count(s, agent_graph_runs) == 1
    assert count(s, agent_graph_events) == 4


def test_actor_scope(setup):
    s = setup
    step(s)
    with pytest.raises(AgentCheckpointDenied, match="RUN_ID_CONFLICT"):
        step(s, actor="other")
    assert s.source.calls == 1 and count(s, agent_graph_events) == 1


def test_content_binding(setup):
    s = setup
    p = s.kw["plan"].model_copy(update={"content_id": "other"})
    with pytest.raises(review.ProtectedAVReviewDenied, match="CANDIDATE_SCOPE_MISMATCH"):
        step(s, plan=p)
    assert count(s, agent_graph_runs) == 0
    assert count(s, agent_graph_events) == 0


def test_malformed_plan_and_order(setup):
    s = setup
    p = s.kw["plan"].model_copy(update={"artifact_ids": (IDS[0],)*4})
    with pytest.raises(review.ProtectedAVReviewDenied, match="PLAN_INVALID"):
        step(s, plan=p)
    assert count(s, agent_graph_runs) == 0 and s.source.calls == 0
    rev = review.ProtectedAVReviewPlan(content_id="post", object_id=OBJECT,
                                      artifact_ids=tuple(reversed(IDS)))
    assert review._plan_digest(rev) == review._plan_digest(s.kw["plan"])
    assert step(s, plan=rev)["revision"] == 1
