"""IMP-060 / CT-04: synthetic-only lexical baseline vs SQLite FTS5.

No independent gold or architectural decision. Both rankers use exactly the
same hash-pinned synthetic fixture and development/validation split.
The sealed split is never searched, returned or used to choose a method.
"""
from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite
import re
from time import perf_counter

from .discovery_gold_registry import (
    GoldRegistryError, build_synthetic_registry,
)
from .discovery_gold_retrieval_eval import (
    VERSION as BENCH_VERSION, benchmark_synthetic_fts,
)
from .discovery_retrieval_fts import p95_ms

VERSION = "tapi-imp060-synthetic-comparison.v1"
BASELINE_VERSION = "tapi-imp060-exact-token-baseline.v1"
CANDIDATE_VERSION = "tapi-imp071-fts5-local.v1"
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_SAFETY_FALSE = (
    "sealed_test_queried", "independently_validated",
    "gold_relevance_judgments_available", "scientifically_validated",
    "gates_released", "database_mutated", "external_data_accessed",
    "production_approved",
)


def _fail(reason):
    raise GoldRegistryError("GOLD_COMPARE_" + reason)


def compare_synthetic_baseline_candidate(raw: bytes, *,
                                         expected_sha256: str,
                                         split="validation", k=2):
    """Run separate algorithms without using the synthetic oracle for tuning."""
    if split not in ("development", "validation"):
        _fail("SEALED_SPLIT_FORBIDDEN")
    if type(k) is not int or not 1 <= k <= 50:
        _fail("K_INVALID")

    # The existing evaluator validates the SHA of raw bytes, JSON duplicate
    # keys, every document/query hash, split isolation and every judgment
    # before any comparison is made.
    candidate = benchmark_synthetic_fts(
        raw, expected_sha256=expected_sha256, split=split, k=k,
    )
    if (not isinstance(candidate, dict)
            or candidate.get("status") != "SYNTHETIC_FTS_BENCHMARK_VERIFIED"
            or candidate.get("schema_version") != BENCH_VERSION
            or candidate.get("policy_version") != CANDIDATE_VERSION
            or candidate.get("registry_manifest_sha256") != expected_sha256
            or candidate.get("split") != split
            or candidate.get("k") != k
            or candidate.get("latency_excludes_index_build") is not True
            or any(candidate.get(key) is not False for key in _SAFETY_FALSE)):
        _fail("CANDIDATE_CONTRACT_INVALID")

    # This has already passed strict JSON validation, including no duplicate
    # keys, through benchmark_synthetic_fts. Do not copy any text into output.
    bundle = json.loads(raw.decode("utf-8"))
    registry = build_synthetic_registry(
        bundle["registry"], manifest_sha256=expected_sha256,
    )
    safe_docs = tuple(d for d in registry._documents if d.split == split)
    safe_queries = tuple(q for q in registry._queries if q.split == split)
    if (not safe_docs or not safe_queries
            or candidate.get("documents_evaluated") != len(safe_docs)
            or candidate.get("queries_evaluated") != len(safe_queries)):
        _fail("POPULATION_DRIFT")
    candidate_digest = candidate.get("ranked_evidence_sha256")
    if (not isinstance(candidate_digest, str)
            or not re.fullmatch("[a-f0-9]{64}", candidate_digest)):
        _fail("CANDIDATE_RANKING_DIGEST_INVALID")

    captions = {
        d["content_id"]: d["caption"] for d in bundle["synthetic_inputs"]["documents"]
    }
    query_text = {
        q["query_id"]: q["text"] for q in bundle["synthetic_inputs"]["queries"]
    }
    baseline_scores = []
    baseline_evidence = []
    latency_samples = []
    for query in safe_queries:
        terms = set(_TOKEN.findall(query_text[query.query_id].casefold()))
        if not terms:
            _fail("QUERY_TOKENS_INVALID")
        start = perf_counter()
        # This baseline is intentionally simple and fixed: AND-overlap terms,
        # tie-break by content ID. No gold labels influence its ranking.
        ranked = sorted(
            d.content_id for d in safe_docs
            if terms.issubset(set(_TOKEN.findall(
                captions[d.content_id].casefold()
            )))
        )[:k]
        elapsed = (perf_counter() - start) * 1000
        score = registry.evaluate_synthetic_query(
            query.query_id, ranked, k=k,
        )
        if (score["synthetic_recall_at_k"] is None
                or score["synthetic_ndcg_at_k"] is None
                or score["scientifically_validated"] is not False):
            _fail("BASELINE_METRIC_INVALID")
        baseline_scores.append(score)
        baseline_evidence.append((
            query.query_sha256,
            tuple(ranked),
            tuple(
                "synthetic-" + next(
                    d.content_sha256[:16] for d in safe_docs
                    if d.content_id == cid
                ) for cid in ranked
            ),
        ))
        latency_samples.append(elapsed)

    count = len(baseline_scores)
    baseline_recall = round(sum(
        result["synthetic_recall_at_k"] for result in baseline_scores
    ) / count, 6)
    baseline_ndcg = round(sum(
        result["synthetic_ndcg_at_k"] for result in baseline_scores
    ) / count, 6)
    candidate_recall = candidate["macro_synthetic_recall_at_k"]
    candidate_ndcg = candidate["macro_synthetic_ndcg_at_k"]
    if any(
        type(metric) not in (int, float)
        or not isfinite(metric) or not 0 <= metric <= 1
        for metric in (candidate_recall, candidate_ndcg)
    ):
        _fail("CANDIDATE_METRIC_INVALID")
    timing = candidate.get("query_latency_p95_ms")
    if (type(timing) not in (int, float) or not isfinite(timing)
            or timing < 0):
        _fail("CANDIDATE_LATENCY_INVALID")
    baseline_digest = sha256(json.dumps(
        baseline_evidence, ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()

    return {
        "status": "SYNTHETIC_BASELINE_CANDIDATE_COMPARISON_VERIFIED",
        "schema_version": VERSION,
        "reference_kind": "synthetic_fixture",
        "input_fixture_sha256": expected_sha256,
        "split": split,
        "k": k,
        "documents_evaluated": len(safe_docs),
        "queries_evaluated": count,
        "baseline_policy_version": BASELINE_VERSION,
        "candidate_policy_version": CANDIDATE_VERSION,
        "baseline_ranked_evidence_sha256": baseline_digest,
        "candidate_ranked_evidence_sha256": candidate_digest,
        "baseline_synthetic_recall_at_k": baseline_recall,
        "baseline_synthetic_ndcg_at_k": baseline_ndcg,
        "candidate_synthetic_recall_at_k": candidate_recall,
        "candidate_synthetic_ndcg_at_k": candidate_ndcg,
        "synthetic_recall_delta": round(candidate_recall - baseline_recall, 6),
        "synthetic_ndcg_delta": round(candidate_ndcg - baseline_ndcg, 6),
        "baseline_query_latency_p95_ms": p95_ms(latency_samples),
        "candidate_query_latency_p95_ms": candidate["query_latency_p95_ms"],
        "timing_is_exploratory_not_comparable_service_slo": True,
        "latency_excludes_index_build": True,
        "baseline_candidate_comparison_completed": True,
        "comparison_scope": "synthetic_validation_only",
        "candidate_selected_for_production": False,
        "dec006_decided": False,
        "sealed_test_queried": False,
        "independently_validated": False,
        "gold_relevance_judgments_available": False,
        "scientifically_validated": False,
        "gates_released": False,
        "database_mutated": False,
        "external_data_accessed": False,
        "production_approved": False,
    }
