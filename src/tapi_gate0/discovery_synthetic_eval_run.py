"""IMP-060 / IMP-069 preparation: synthetic-only versioned FTS5 replay evidence.

Runs exactly the same hash-pinned synthetic fixture in a single safe split.
The deterministic signature excludes variable latency, while measured latency
is retained as diagnostic. No baseline-vs-candidate quality claim; no gold.
The sealed split is never queried, indexed, used in prompts or published.
"""
from __future__ import annotations

from hashlib import sha256
import json
from math import ceil, isfinite

from .discovery_gold_registry import GoldRegistryError
from .discovery_gold_retrieval_eval import benchmark_synthetic_fts

VERSION = "tapi-imp060-synthetic-evaluation-run.v1"
_STABLE_FIELDS = (
    "schema_version", "registry_manifest_sha256", "policy_version", "split",
    "documents_evaluated", "queries_evaluated", "k",
    "ranked_evidence_sha256", "macro_synthetic_recall_at_k",
    "macro_synthetic_ndcg_at_k",
)
_SAFETY_FALSE_FIELDS = (
    "sealed_test_queried", "independently_validated",
    "gold_relevance_judgments_available", "scientifically_validated",
    "gates_released", "database_mutated", "external_data_accessed",
    "production_approved",
)


def _fail(code):
    raise GoldRegistryError("GOLD_EVAL_RUN_" + code)


def replay_synthetic_fts(raw: bytes, *, expected_sha256: str,
                         split="validation", k=2, repeats=3):
    """Fail closed if ranking, metrics, version or safety claims drift."""
    if split not in ("development", "validation"):
        _fail("SEALED_SPLIT_FORBIDDEN")
    if type(k) is not int or not 1 <= k <= 50:
        _fail("K_INVALID")
    if type(repeats) is not int or not 2 <= repeats <= 5:
        _fail("REPETITIONS_INVALID")

    observations = []
    stable = None
    latencies = []
    for _ in range(repeats):
        report = benchmark_synthetic_fts(
            raw, expected_sha256=expected_sha256,
            split=split, k=k,
        )
        if not isinstance(report, dict) or any(
            name not in report for name in
            (*_STABLE_FIELDS, *_SAFETY_FALSE_FIELDS)
        ):
            _fail("CONTRACT_INCOMPLETE")
        if (report.get("status") != "SYNTHETIC_FTS_BENCHMARK_VERIFIED"
                or report["registry_manifest_sha256"] != expected_sha256
                or report["split"] != split
                or report["k"] != k
                or report.get("latency_excludes_index_build") is not True
                or any(report[name] is not False
                       for name in _SAFETY_FALSE_FIELDS)):
            _fail("CONTRACT_DRIFT")
        digest = report["ranked_evidence_sha256"]
        if (not isinstance(digest, str) or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)):
            _fail("RANK_DIGEST_INVALID")
        if (type(report["queries_evaluated"]) is not int
                or report["queries_evaluated"] < 1
                or type(report["documents_evaluated"]) is not int
                or report["documents_evaluated"] < 1):
            _fail("POPULATION_INVALID")
        for metric in ("macro_synthetic_recall_at_k",
                       "macro_synthetic_ndcg_at_k"):
            if (type(report[metric]) not in (int, float)
                    or not isfinite(report[metric])
                    or not 0 <= report[metric] <= 1):
                _fail("METRIC_INVALID")
        timing = report.get("query_latency_p95_ms")
        if (type(timing) not in (int, float) or not isfinite(timing)
                or timing < 0):
            _fail("LATENCY_INVALID")
        current = {key: report[key] for key in _STABLE_FIELDS}
        if stable is not None and current != stable:
            _fail("DETERMINISTIC_REPLAY_DRIFT")
        stable = current
        latencies.append(float(timing))
        observations.append(digest)

    # Stable signature is independent of run ordering and timer variation.
    deterministic_json = json.dumps(
        {"version": VERSION, "reference_kind": "synthetic_fixture",
         "evaluation_method": "fts5_same_candidate_replay",
         "stable_metrics": stable},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    elapsed = sorted(latencies)
    return {
        "status": "SYNTHETIC_EVALUATION_REPLAY_VERIFIED",
        "schema_version": VERSION,
        "reference_kind": "synthetic_fixture",
        "evaluation_method": "fts5_same_candidate_replay",
        "benchmark_version": stable["schema_version"],
        "retrieval_policy_version": stable["policy_version"],
        "input_fixture_sha256": expected_sha256,
        "deterministic_result_sha256": sha256(deterministic_json).hexdigest(),
        "ranked_evidence_sha256": stable["ranked_evidence_sha256"],
        "split": split,
        "documents_evaluated": stable["documents_evaluated"],
        "queries_evaluated": stable["queries_evaluated"],
        "k": k,
        "repetitions": repeats,
        "all_rankings_and_metrics_equal": len(set(observations)) == 1,
        "macro_synthetic_recall_at_k": stable["macro_synthetic_recall_at_k"],
        "macro_synthetic_ndcg_at_k": stable["macro_synthetic_ndcg_at_k"],
        "query_p95_samples_ms": latencies,
        "sample_p50_ms": elapsed[ceil(0.5 * repeats) - 1],
        "sample_p95_ms": elapsed[ceil(0.95 * repeats) - 1],
        "sample_p95_is_exploratory_not_service_slo": True,
        "latency_excludes_index_build": True,
        "sealed_test_queried": False,
        "baseline_candidate_comparison_completed": False,
        "independently_validated": False,
        "gold_relevance_judgments_available": False,
        "scientifically_validated": False,
        "gates_released": False,
        "database_mutated": False,
        "external_data_accessed": False,
        "production_approved": False,
    }
