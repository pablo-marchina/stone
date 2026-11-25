"""IMP-069 A04.4: versioned, synthetic-only evaluation and local gate.

This adapter does not retrieve operational data, access a network, mutate a DB,
query sealed_test, or authorize production. Every terminal outcome is a report.
The CLI is responsible for write-once persistence of that report.
"""
from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite
import re

from .discovery_synthetic_comparison import (
    BASELINE_VERSION, CANDIDATE_VERSION,
    VERSION as COMPARISON_VERSION,
    compare_synthetic_baseline_candidate,
)

VERSION = "tapi-imp069-local-eval-engine.v1"
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_SAFE_ERROR = re.compile(r"GOLD_(?:COMPARE|FTS|REGISTRY)_[A-Z0-9_]{1,80}\Z")
_MAX_BYTES = 2_000_000
_SAFETY_FALSE = (
    "sealed_test_queried", "independently_validated",
    "gold_relevance_judgments_available", "scientifically_validated",
    "gates_released", "database_mutated", "external_data_accessed",
    "production_approved", "candidate_selected_for_production",
    "dec006_decided",
)


class LocalEvaluationError(ValueError):
    """Typed local contract failure without fixture content in the message."""


def _valid_delta(value):
    return (type(value) in (int, float) and isfinite(value)
            and -1.0 <= value <= 1.0)


def _base_report(*, evaluation_version, fixture_sha256, split, k):
    # Never reflect arbitrary input strings into stdout or persisted evidence.
    return {
        "schema_version": VERSION,
        "evaluation_version": (evaluation_version if isinstance(evaluation_version, str)
                               and _LABEL.fullmatch(evaluation_version) else None),
        "fixture_sha256": (fixture_sha256 if isinstance(fixture_sha256, str)
                           and _SHA.fullmatch(fixture_sha256) else None),
        "reference_kind": "synthetic_fixture",
        "split": split if split in ("development", "validation") else None,
        "k": k if type(k) is int and 1 <= k <= 50 else None,
        "status": "BLOCKED",
        "reason_code": "EVAL_NOT_STARTED",
        "local_gate": "BLOCKED",
        "local_gate_scope": "synthetic_regression_only",
        "global_gate_released": False,
        "baseline_candidate_comparison_completed": False,
        "sealed_test_queried": False,
        "gold_relevance_judgments_available": False,
        "independently_validated": False,
        "scientifically_validated": False,
        "gates_released": False,
        "external_data_accessed": False,
        "database_mutated": False,
        "candidate_selected_for_production": False,
        "dec006_decided": False,
        "production_approved": False,
    }


def _comparison_legal(value, *, fixture_sha256, split, k):
    """Reject fake successes or drift even if a producer changes its contract."""
    if not isinstance(value, dict):
        raise LocalEvaluationError("EVAL_COMPARISON_CONTRACT_INVALID")
    expected = {
        "status": "SYNTHETIC_BASELINE_CANDIDATE_COMPARISON_VERIFIED",
        "schema_version": COMPARISON_VERSION,
        "reference_kind": "synthetic_fixture",
        "input_fixture_sha256": fixture_sha256,
        "split": split,
        "k": k,
        "baseline_policy_version": BASELINE_VERSION,
        "candidate_policy_version": CANDIDATE_VERSION,
        "comparison_scope": "synthetic_validation_only",
        "baseline_candidate_comparison_completed": True,
        "timing_is_exploratory_not_comparable_service_slo": True,
        "latency_excludes_index_build": True,
    }
    if (any(value.get(key) != expected_value for key, expected_value in expected.items())
            or any(value.get(key) is not False for key in _SAFETY_FALSE)
            or type(value.get("documents_evaluated")) is not int
            or type(value.get("queries_evaluated")) is not int
            or value["documents_evaluated"] < 1
            or value["queries_evaluated"] < 1):
        raise LocalEvaluationError("EVAL_COMPARISON_CONTRACT_INVALID")
    for field in ("baseline_ranked_evidence_sha256",
                  "candidate_ranked_evidence_sha256"):
        if not isinstance(value.get(field), str) or not _SHA.fullmatch(value[field]):
            raise LocalEvaluationError("EVAL_RANK_DIGEST_INVALID")
    fields = ("baseline_synthetic_recall_at_k", "baseline_synthetic_ndcg_at_k",
              "candidate_synthetic_recall_at_k", "candidate_synthetic_ndcg_at_k")
    if any(type(value.get(field)) not in (int, float) or
           not isfinite(value[field]) or not 0 <= value[field] <= 1
           for field in fields):
        raise LocalEvaluationError("EVAL_METRIC_INVALID")
    for field in ("synthetic_recall_delta", "synthetic_ndcg_delta"):
        if not _valid_delta(value.get(field)):
            raise LocalEvaluationError("EVAL_DELTA_INVALID")
    if (abs(value["synthetic_recall_delta"] - (
            value["candidate_synthetic_recall_at_k"] -
            value["baseline_synthetic_recall_at_k"])) > 0.000002
            or abs(value["synthetic_ndcg_delta"] - (
                value["candidate_synthetic_ndcg_at_k"] -
                value["baseline_synthetic_ndcg_at_k"])) > 0.000002):
        raise LocalEvaluationError("EVAL_DELTA_MISMATCH")
    for field in ("baseline_query_latency_p95_ms", "candidate_query_latency_p95_ms"):
        sample = value.get(field)
        if type(sample) not in (int, float) or not isfinite(sample) or sample < 0:
            raise LocalEvaluationError("EVAL_LATENCY_INVALID")


def evaluate_versioned_synthetic(raw: bytes, *, expected_sha256: str,
                                 evaluation_version: str, split="validation", k=2,
                                 min_recall_delta=0.0, min_ndcg_delta=0.0,
                                 plan_only=False) -> dict:
    """Return a safe terminal record for every outcome; never approve a global gate.

    PASS/FAIL apply only to the configured synthetic regression thresholds.
    BLOCKED covers invalid scope/fixture/contract. NOT_RUN is explicit plan-only.
    """
    report = _base_report(evaluation_version=evaluation_version,
                          fixture_sha256=expected_sha256, split=split, k=k)
    try:
        if (report["evaluation_version"] is None
                or report["fixture_sha256"] is None
                or report["split"] is None or report["k"] is None
                or type(plan_only) is not bool
                or not _valid_delta(min_recall_delta)
                or not _valid_delta(min_ndcg_delta)):
            raise LocalEvaluationError("EVAL_SPEC_INVALID")
        if not isinstance(raw, bytes) or not 0 < len(raw) <= _MAX_BYTES:
            raise LocalEvaluationError("EVAL_INPUT_INVALID")
        if sha256(raw).hexdigest() != expected_sha256:
            raise LocalEvaluationError("EVAL_INPUT_SHA_MISMATCH")
        contract = {
            "engine_version": VERSION,
            "evaluation_version": evaluation_version,
            "fixture_sha256": expected_sha256,
            "split": split,
            "k": k,
            "min_recall_delta": float(min_recall_delta),
            "min_ndcg_delta": float(min_ndcg_delta),
            "baseline_policy_version": BASELINE_VERSION,
            "candidate_policy_version": CANDIDATE_VERSION,
        }
        report["evaluation_spec_sha256"] = sha256(json.dumps(
            contract, sort_keys=True, separators=(",", ":"),
            allow_nan=False).encode("utf-8")).hexdigest()
        report["baseline_policy_version"] = BASELINE_VERSION
        report["candidate_policy_version"] = CANDIDATE_VERSION
        report["min_recall_delta"] = float(min_recall_delta)
        report["min_ndcg_delta"] = float(min_ndcg_delta)
        if plan_only:
            report.update(status="NOT_RUN", reason_code="EVAL_PLAN_ONLY",
                          local_gate="NOT_EVALUATED")
            return report
        compared = compare_synthetic_baseline_candidate(
            raw, expected_sha256=expected_sha256, split=split, k=k,
        )
        _comparison_legal(compared, fixture_sha256=expected_sha256,
                          split=split, k=k)
        safe = (
            "documents_evaluated", "queries_evaluated",
            "baseline_ranked_evidence_sha256", "candidate_ranked_evidence_sha256",
            "baseline_synthetic_recall_at_k", "candidate_synthetic_recall_at_k",
            "baseline_synthetic_ndcg_at_k", "candidate_synthetic_ndcg_at_k",
            "synthetic_recall_delta", "synthetic_ndcg_delta",
            "baseline_query_latency_p95_ms", "candidate_query_latency_p95_ms",
        )
        report.update({key: compared[key] for key in safe})
        report["baseline_candidate_comparison_completed"] = True
        # Versioned deterministic proof excludes nondeterministic timing.
        proof = {key: report[key] for key in safe
                 if "latency" not in key}
        proof["evaluation_spec_sha256"] = report["evaluation_spec_sha256"]
        report["deterministic_result_sha256"] = sha256(json.dumps(
            proof, sort_keys=True, separators=(",", ":"),
            allow_nan=False).encode("utf-8")).hexdigest()
        allowed = (compared["synthetic_recall_delta"] >= float(min_recall_delta)
                   and compared["synthetic_ndcg_delta"] >= float(min_ndcg_delta))
        report.update(
            status="PASS" if allowed else "FAIL",
            reason_code="EVAL_LOCAL_SYNTHETIC_PASS" if allowed else "EVAL_THRESHOLD_NOT_MET",
            local_gate="PASS" if allowed else "FAIL",
        )
    except LocalEvaluationError as exc:
        report.update(status="BLOCKED", reason_code=str(exc), local_gate="BLOCKED")
    except Exception as exc:
        # Never serialize provider/fixture/raw error text. Preserve only vetted
        # validation codes; all other failures are generic and fail closed.
        code = str(exc)
        report.update(
            status="BLOCKED" if _SAFE_ERROR.fullmatch(code) else "ERROR",
            reason_code=code if _SAFE_ERROR.fullmatch(code) else "EVAL_RUNTIME_ERROR",
            local_gate="BLOCKED",
        )
    return report
