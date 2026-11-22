"""Real SQLite, signed rights, vault and queue for bounded A02.7 batch.

Only the native child adapter is replaced by an authored header observation.
No model weights, third-party media, paid services, or release actions.
"""
from sqlalchemy import func, select
import pytest

from tapi_gate0.asset_fixture_batch import run_explicit_fixture_batch
from tapi_gate0.asset_fixture_pipeline import FixturePipeline
from tapi_gate0.asset_processor_results import ProcessorResult, Abstention, encode
from tapi_gate0.asset_rights import AssetRightsDenied
from tapi_gate0.asset_derived_payloads import payloads
from tapi_gate0.asset_jobs import attempts
from test_asset_rights_registry import (
    registry, discard_fixture, queue_fixture, _pipeline, TENANT,
)


def _synthetic_dispatch(f, monkeypatch):
    """Substitute only the native child; keep real rights/queue/crypto/fusion."""
    def dispatch(self, lease, spec):
        assert lease.job_id == spec.job_id
        observation = ProcessorResult(
            tenant_id=spec.tenant_id, job_id=spec.job_id,
            object_id=spec.object_id, input_sha256=f.q.ref.target.sha256,
            attempt=lease.attempt, purpose=spec.purpose,
            method_version=spec.method_version,
            configuration_sha256=spec.configuration_sha256,
            origin="synthetic_fixture",
            result=Abstention(processor=spec.processor, reason="fixture_header_only"),
        )
        return {**self.store.finish(lease, payload=encode(observation)), "model_calls": 0}
    monkeypatch.setattr(FixturePipeline, "_dispatch", dispatch)


def _batch(pipe, ticks=5):
    return run_explicit_fixture_batch(
        pipe, "trusted-local-worker",
        expected_plan_sha256=pipe.plan.fingerprint, max_ticks=ticks,
    )


@pytest.mark.parametrize("discard_fixture", [("retain", "process", "all_processors", "bundle_rubric")], indirect=True)
def test_signed_rights_sqlite_vault_queue_and_fusion_integrated(queue_fixture, monkeypatch):
    f = queue_fixture
    _synthetic_dispatch(f, monkeypatch)
    pipe = _pipeline(f, mode="header", case="header")
    receipt = _batch(pipe)
    assert receipt["status"] == "CANDIDATE_ONLY"
    assert receipt["reason"] == "candidate_complete"
    assert receipt["ticks_executed"] == 5
    assert len(receipt["artifact_ids"]) == 4
    assert receipt["candidate_decisions"].tenant_id == TENANT
    assert receipt["candidate_decisions"].object_id == f.q.ref.object_id
    assert receipt["candidate_evidence_sha256"] == receipt["candidate_decisions"].evidence_fingerprint
    assert receipt["scientific_evidence"] is False
    assert receipt["global_gates_released"] is False
    assert receipt["production_approved"] is False
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(payloads)) == 4
        assert db.scalar(select(func.count()).select_from(attempts)) == 4
    assert all(f.queue.status(TENANT, spec.job_id)["attempt"] == 1 for spec in pipe.plan.specs)
    again = _batch(_pipeline(f, mode="header", case="header"), ticks=1)
    assert again["status"] == "CANDIDATE_ONLY"
    assert again["artifact_ids"] == receipt["artifact_ids"]
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts)) == 4


@pytest.mark.parametrize("discard_fixture", [("retain", "process", "all_processors", "bundle_rubric")], indirect=True)
def test_manual_resume_preserves_attempts_and_encrypted_outputs(queue_fixture, monkeypatch):
    f = queue_fixture
    _synthetic_dispatch(f, monkeypatch)
    pipe = _pipeline(f, mode="header", case="header")
    first = _batch(pipe, ticks=2)
    assert first["status"] == "BUDGET_EXHAUSTED"
    assert first["ticks_executed"] == 2
    assert first["candidate_decisions"] is None
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts)) == 2
    resumed = _pipeline(f, mode="header", case="header", expected_plan=pipe.plan.fingerprint)
    final = _batch(resumed, ticks=3)
    assert final["status"] == "CANDIDATE_ONLY"
    assert final["ticks_executed"] == 3
    assert len(final["artifact_ids"]) == 4
    assert final["auto_retry_enabled"] is False
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts)) == 4
        assert db.scalar(select(func.count()).select_from(payloads)) == 4


@pytest.mark.parametrize("discard_fixture", [("retain", "process", "all_processors", "bundle_rubric")], indirect=True)
def test_signed_asset_revocation_blocks_new_attempt(queue_fixture, monkeypatch):
    f = queue_fixture
    _synthetic_dispatch(f, monkeypatch)
    pipe = _pipeline(f, mode="header", case="header")
    rv = f.q.f.state(2, revoked_asset_ids=(f.q.ref.target.asset_id,))
    f.q.f.svc.advance(f.q.f.anchor, TENANT, "instagram", rv)
    f.queue.resolve_anchor = lambda ref: f.q.f.pin(rv)
    with pytest.raises(AssetRightsDenied, match="ASSET_RIGHTS_REVOKED"):
        _batch(pipe)
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts)) == 0
        assert db.scalar(select(func.count()).select_from(payloads)) == 0


@pytest.mark.parametrize("discard_fixture", [("retain", "process", "all_processors", "bundle_rubric")], indirect=True)
def test_running_lease_halts_without_claiming_second_attempt(queue_fixture, monkeypatch):
    f = queue_fixture
    _synthetic_dispatch(f, monkeypatch)
    pipe = _pipeline(f, mode="header", case="header")
    spec = pipe.plan.specs[0]
    f.queue.enqueue(spec)
    claim = f.queue.claim(TENANT, "other-worker", job_id=spec.job_id)
    assert claim["status"] == "claimed"
    receipt = _batch(pipe)
    assert receipt["status"] == "HALTED"
    assert receipt["reason"] == "busy"
    assert receipt["ticks_executed"] == 1
    assert receipt["auto_retry_enabled"] is False
    assert f.queue.status(TENANT, spec.job_id)["state"] == "running"
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts)) == 1
        assert db.scalar(select(func.count()).select_from(payloads)) == 0


@pytest.mark.parametrize("discard_fixture", [("retain", "process", "all_processors", "bundle_rubric")], indirect=True)
def test_invalidation_during_batch_blocks_further_processing(queue_fixture, monkeypatch):
    f = queue_fixture
    _synthetic_dispatch(f, monkeypatch)
    pipe = _pipeline(f, mode="header", case="header")
    assert _batch(pipe, ticks=1)["status"] == "BUDGET_EXHAUSTED"
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts)) == 1
    f.q.index.invalidate(TENANT, object_ids=[f.q.ref.object_id])
    with pytest.raises(AssetRightsDenied):
        _batch(pipe, ticks=1)
    with f.q.f.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(attempts)) == 1
