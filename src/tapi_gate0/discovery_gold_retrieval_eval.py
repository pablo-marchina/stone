"""IMP-060 + IMP-071: engineering-only FTS5 benchmark with synthetic CT-04 data.

No production, corpus access, network, persisted index, LLM, or true gold.
Sealed-test text is hash-checked but never sent to FTS5 or prompt tooling.
"""
from __future__ import annotations

from hashlib import sha256
import json
from collections.abc import Mapping

from .discovery_gold_registry import (
    GoldRegistryError, build_synthetic_registry, _strict_pairs,
)
from .discovery_retrieval_fts import (
    TransientScopedFts, RetrievalBaselineError, p95_ms,
)

VERSION = "tapi-imp060-fts-synthetic-benchmark.v1"
_MAX_INPUT_BYTES = 2_000_000


def _fail(code):
    raise GoldRegistryError("GOLD_FTS_" + code)


def _exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        _fail("SCHEMA_INVALID")


def benchmark_synthetic_fts(raw: bytes, *, expected_sha256: str,
                            split: str = "validation", k: int = 2):
    """Hash-pin full fixture; validate references, then index ONE safe split."""
    if split not in ("development", "validation"):
        _fail("SEALED_EVALUATION_DENIED")
    if type(k) is not int or not 1 <= k <= 50:
        _fail("K_INVALID")
    if (not isinstance(raw, bytes) or not 0 < len(raw) <= _MAX_INPUT_BYTES
            or not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_sha256)):
        _fail("INPUT_PIN_INVALID")
    if sha256(raw).hexdigest() != expected_sha256:
        _fail("INPUT_SHA_MISMATCH")
    try:
        bundle = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_pairs,
                            parse_constant=lambda _: _fail("JSON_CONSTANT_INVALID"))
    except GoldRegistryError:
        raise
    except (ValueError, TypeError, UnicodeDecodeError, RecursionError):
        _fail("JSON_INVALID")
    _exact(bundle, ("version", "registry", "synthetic_inputs"))
    if bundle["version"] != VERSION:
        _fail("VERSION_INVALID")
    registry = build_synthetic_registry(
        bundle["registry"], manifest_sha256=expected_sha256,
    )
    if registry.summary()["reference_kind"] != "synthetic_fixture":
        _fail("NON_SYNTHETIC_DENIED")
    inputs = bundle["synthetic_inputs"]
    _exact(inputs, ("documents", "queries"))
    if not isinstance(inputs["documents"], list) or not isinstance(inputs["queries"], list):
        _fail("INPUT_SCHEMA_INVALID")

    # Verify every synthetic text reference, including sealed entries, before
    # constructing any search index. Do not index or print sealed entries.
    expected_docs = {d.content_id: d for d in registry._documents}
    expected_queries = {q.query_id: q for q in registry._queries}
    texts, queries = {}, {}
    for row in inputs["documents"]:
        _exact(row, ("content_id", "caption"))
        cid, caption = row["content_id"], row["caption"]
        if (not isinstance(cid, str) or cid not in expected_docs or cid in texts
                or not isinstance(caption, str)
                or not 0 < len(caption) <= 100_000
                or sha256(caption.encode("utf-8")).hexdigest()
                   != expected_docs[cid].content_sha256):
            _fail("DOCUMENT_HASH_OR_REF_INVALID")
        texts[cid] = caption
    if set(texts) != set(expected_docs):
        _fail("DOCUMENT_POPULATION_DRIFT")
    for row in inputs["queries"]:
        _exact(row, ("query_id", "text"))
        qid, query = row["query_id"], row["text"]
        if (not isinstance(qid, str) or qid not in expected_queries or qid in queries
                or not isinstance(query, str) or not 0 < len(query) <= 300
                or sha256(query.encode("utf-8")).hexdigest()
                   != expected_queries[qid].query_sha256):
            _fail("QUERY_HASH_OR_REF_INVALID")
        queries[qid] = query
    if set(queries) != set(expected_queries):
        _fail("QUERY_POPULATION_DRIFT")

    safe_docs = [d for d in registry._documents if d.split == split]
    safe_queries = [q for q in registry._queries if q.split == split]
    if not safe_docs or not safe_queries:
        _fail("SPLIT_EMPTY")
    if any(not q.complete_judgments for q in safe_queries):
        _fail("JUDGMENTS_INCOMPLETE")

    scores = []
    latencies = []
    try:
        with TransientScopedFts((
            {"content_id": d.content_id,
             "snapshot_id": "synthetic-" + d.content_sha256[:16],
             "caption": texts[d.content_id]}
            for d in safe_docs
        ), manifest_sha256=registry.manifest_sha256) as index:
            if index.count != len(safe_docs):
                _fail("INDEX_POPULATION_DRIFT")
            for query in safe_queries:
                hit = index.search(queries[query.query_id], limit=k)
                if (hit["manifest_sha256"] != expected_sha256
                        or hit["query_sha256"] != query.query_sha256
                        or hit["scientifically_validated"] is not False
                        or hit["gold_metrics"] is not None):
                    _fail("SEARCH_CONTRACT_DRIFT")
                score = registry.evaluate_synthetic_query(
                    query.query_id, hit["content_ids"], k=k,
                )
                if (score["synthetic_recall_at_k"] is None
                        or score["synthetic_ndcg_at_k"] is None):
                    _fail("METRIC_UNAVAILABLE")
                scores.append(score)
                latencies.append(hit["latency_ms"])
    except RetrievalBaselineError:
        _fail("FTS_ENGINE_REJECTED")
    count = len(scores)
    return {
        "status": "SYNTHETIC_FTS_BENCHMARK_VERIFIED",
        "schema_version": VERSION,
        "registry_manifest_sha256": expected_sha256,
        "policy_version": "tapi-imp071-fts5-local.v1",
        "split": split,
        "documents_evaluated": len(safe_docs),
        "queries_evaluated": count,
        "k": k,
        "macro_synthetic_recall_at_k": round(
            sum(s["synthetic_recall_at_k"] for s in scores) / count, 6),
        "macro_synthetic_ndcg_at_k": round(
            sum(s["synthetic_ndcg_at_k"] for s in scores) / count, 6),
        "query_latency_p95_ms": p95_ms(latencies),
        "latency_excludes_index_build": True,
        "sealed_test_queried": False,
        "independently_validated": False,
        "gold_relevance_judgments_available": False,
        "scientifically_validated": False,
        "gates_released": False,
        "database_mutated": False,
        "external_data_accessed": False,
        "production_approved": False,
    }
