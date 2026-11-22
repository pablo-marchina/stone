"""A02.7: bounded, explicit trusted-host driver for already-authorized fixtures.

The existing FixturePipeline is the sole queue/lease/rights/processor authority.
This helper does not renew leases, reconcile expired workers, retry failures,
write scientific assessments, select models or enable non-fixture media.
"""
from __future__ import annotations

import re
from .asset_fixture_pipeline import FixturePipeline
from .asset_candidate_fusion import CandidateDecisions
from .asset_rights import AssetRightsDenied

_SHA = re.compile(r"[a-f0-9]{64}\Z")
_ARTIFACT = re.compile(r"artifact\.[a-f0-9]{64}\Z")
_JOB = re.compile(r"job\.[a-f0-9]{64}\Z")
_WORKER = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_MODES = frozenset(("header", "temporal", "asr", "ocr", "vlm",
                    "image_pair", "shared_av", "shared_av_partial"))
_TERMINALS = frozenset(("candidate_complete", "candidate_complete_guarded",
                        "candidate_partial"))
_HALTS = frozenset(("blocked", "busy", "recovery_required",
                    "quota", "rights_blocked", "empty"))


def _deny(reason: str):
    raise AssetRightsDenied("A02_FIXTURE_BATCH_" + reason)


def _receipt(status: str, plan_sha256: str, ticks: int, *, reason: str,
             candidates=None, artifact_ids=(), quality_rejected_processors=()):
    return {"schema_version": "a02-fixture-explicit-batch.v1",
            "status": status, "reason": reason, "plan_sha256": plan_sha256,
            "ticks_executed": ticks, "artifact_ids": tuple(artifact_ids),
            "candidate_decisions": candidates,
            "candidate_evidence_sha256": (candidates.evidence_fingerprint
                                          if candidates is not None else None),
            "quality_rejected_processors": tuple(quality_rejected_processors),
            "synthetic_fixture_only": True, "auto_retry_enabled": False,
            "scientific_evidence": False, "canonical_rubric": False,
            "external_media_enabled": False, "production_approved": False,
            "global_gates_released": False}


def run_explicit_fixture_batch(pipeline: FixturePipeline, worker: str, *,
                               expected_plan_sha256: str, max_ticks: int):
    """Run at most max_ticks authorized fixture steps, then return or halt.

    A caller explicitly constructs FixturePipeline on the trusted host. Its
    _preflight/step re-check rights and persisted fences at each stage. An
    expiring lease, failed job, busy worker or partial quality never causes
    a retry, an implicit reconciliation, or a canonical assessment.
    """
    if type(pipeline) is not FixturePipeline:
        _deny("PIPELINE_REQUIRED")
    if type(worker) is not str or not _WORKER.fullmatch(worker):
        _deny("WORKER_INVALID")
    plan = pipeline.plan
    if plan.mode not in _MODES or not isinstance(plan.specs, tuple):
        _deny("SYNTHETIC_PLAN_REQUIRED")
    specs = plan.specs
    if not 1 <= len(specs) <= 8:
        _deny("PLAN_BOUNDS")
    if (type(expected_plan_sha256) is not str
            or not _SHA.fullmatch(expected_plan_sha256)
            or plan.fingerprint != expected_plan_sha256):
        _deny("PLAN_PIN_MISMATCH")
    if type(max_ticks) is not int or not 1 <= max_ticks <= len(specs) + 1:
        _deny("TICK_BUDGET")
    jobs = tuple((s.job_id, s.processor, s.tenant_id, s.object_id,
                  s.purpose, s.method_version, s.configuration_sha256)
                 for s in specs)
    if len({s[0] for s in jobs}) != len(jobs):
        _deny("DUPLICATE_JOBS")
    if (any(type(s[0]) is not str or not _JOB.fullmatch(s[0])
            or type(s[6]) is not str or not _SHA.fullmatch(s[6]) for s in jobs)
            or len({(s[2], s[3], s[4]) for s in jobs}) != 1):
        _deny("JOB_BINDING_INVALID")
    if any(s[4] != "research_analysis" for s in jobs):
        _deny("PURPOSE_INVALID")
    observed = set()
    for tick in range(1, max_ticks + 1):
        if (pipeline.plan is not plan or plan.fingerprint != expected_plan_sha256
                or tuple((s.job_id, s.processor, s.tenant_id, s.object_id,
                          s.purpose, s.method_version, s.configuration_sha256)
                         for s in plan.specs) != jobs):
            _deny("PLAN_CHANGED")
        # Never change retry_stopped to True: physical worker stop must be
        # verified and reconciled by the separate trusted maintenance flow.
        result = pipeline.step(worker, retry_stopped=False)
        if (type(result) is not dict or result.get("plan_sha256") != expected_plan_sha256
                or result.get("synthetic_fixture") is not True
                or result.get("scientific_evidence") is not False
                or result.get("canonical_rubric") is not False):
            _deny("STEP_RECEIPT_INVALID")
        if (pipeline.plan is not plan or plan.fingerprint != expected_plan_sha256
                or tuple((s.job_id, s.processor, s.tenant_id, s.object_id,
                          s.purpose, s.method_version, s.configuration_sha256)
                         for s in plan.specs) != jobs):
            _deny("PLAN_CHANGED_DURING_STEP")
        status = result.get("status")
        if status == "processed":
            key = (result.get("job_id"), result.get("processor"))
            if (key not in {(row[0], row[1]) for row in jobs}
                    or key[0] in observed or result.get("job_state") != "completed"
                    or not isinstance(result.get("artifact_id"), str)
                    or not _ARTIFACT.fullmatch(result["artifact_id"])
                    or type(result.get("model_calls")) is not int
                    or result["model_calls"] < 0):
                _deny("PROCESSED_RECEIPT_INVALID")
            observed.add(key[0])
            continue
        if status in _HALTS:
            if (result.get("job_id"), result.get("processor")) not in {
                    (row[0], row[1]) for row in jobs}:
                _deny("HALT_JOB_INVALID")
            return _receipt("HALTED", expected_plan_sha256, tick, reason=status)
        if status in _TERMINALS:
            ids = result.get("artifact_ids")
            decision = result.get("decisions")
            if (type(ids) not in (tuple, list) or len(ids) != len(jobs)
                    or len(set(ids)) != len(ids)
                    or any(type(x) is not str or not _ARTIFACT.fullmatch(x)
                           for x in ids)
                    or type(decision) is not CandidateDecisions
                    or decision.tenant_id != jobs[0][2]
                    or decision.object_id != jobs[0][3]
                    or decision.purpose != jobs[0][4]
                    or decision.scientific_evidence is not False
                    or decision.canonical_rubric is not False
                    or type(decision.evidence_fingerprint) is not str
                    or not _SHA.fullmatch(decision.evidence_fingerprint)):
                _deny("CANDIDATE_BINDING_INVALID")
            rejected = ()
            if plan.mode == "shared_av_partial":
                rejection = result.get("quality_rejections")
                if (type(rejection) is not dict or
                        not set(rejection) <= {row[1] for row in jobs}
                        or (status == "candidate_partial") != bool(rejection)
                        or status == "candidate_complete"):
                    _deny("PARTIAL_QUALITY_INVALID")
                rejected = tuple(sorted(rejection))
            elif status != "candidate_complete":
                _deny("UNEXPECTED_TERMINAL")
            return _receipt("CANDIDATE_ONLY", expected_plan_sha256, tick,
                            reason=status, candidates=decision, artifact_ids=ids,
                            quality_rejected_processors=rejected)
        _deny("UNKNOWN_STEP_STATUS")
    return _receipt("BUDGET_EXHAUSTED", expected_plan_sha256,
                    max_ticks, reason="EXPLICIT_REINVOCATION_REQUIRED")
