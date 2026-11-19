"""IMP-071: local authorized FTS preview; NOT a retrieval relevance benchmark.

No network, writes to the domain DB, raw-caption reports, labels or scientific
admissions. Every returned result is tied to a live scoped manifest, verified
technical trace, caption and latest observed snapshot. Operator must stop all
writers and ingestion; two readiness passes detect local drift before release.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .discovery_caption_research import require_scoped_research
from .discovery_corpus_readiness import readiness_report
from .discovery_retrieval_fts import (
    RetrievalBaselineError, TransientScopedFts, p95_ms,
)

VERSION = "tapi-imp071-scoped-fts-preview.v1"


def _scoped_rows(engine, tenant, frame, viewer, expected_sources, expected_posts):
    """Read only STAGES[7] records through the audited readiness observer."""
    rows = []
    population = []

    def capture(source, post, metric):
        caption = post.caption
        if not isinstance(caption, str) or not caption.strip():
            raise RetrievalBaselineError("RETRIEVAL_ELIGIBLE_CAPTION_INVALID")
        rows.append({"content_id": post.content_id,
                     "snapshot_id": metric.snapshot_id,
                     "caption": caption})
        population.append((source.username, post.content_id, metric.snapshot_id,
                           sha256(caption.encode("utf-8")).hexdigest()))

    ready = readiness_report(
        engine, tenant, frame, viewer, _record_observer=capture,
    )
    if (ready["status"] != "CORPUS_READINESS_PLANNED"
            or ready["manifest_sha256"] != frame.fingerprint()
            or len(frame.sources) != expected_sources
            or len(rows) != expected_posts
            or ready["first_blocking_stage"]["CAPTION_AVAILABLE_FOR_ASSESSMENT"] != expected_posts
            or ready["completed_runs_without_valid_bd_trace"] != 0
            or ready["new_scientific_admissions"] != 0
            or ready["database_mutated"] is not False
            or ready["external_data_accessed"] is not False
            or sum(s["source_gate"] == "TECHNICAL_SCOPE_MATCHED"
                   for s in ready["sources"]) != expected_sources):
        raise RetrievalBaselineError("RETRIEVAL_SCOPE_OR_POPULATION_MISMATCH")

    if len({r["content_id"] for r in rows}) != expected_posts:
        raise RetrievalBaselineError("RETRIEVAL_DUPLICATE_ELIGIBLE_POST")
    population.sort()
    canonical = json.dumps(population, ensure_ascii=False, separators=(",", ":"))
    partition_hash = sha256(canonical.encode("utf-8")).hexdigest()
    return rows, partition_hash


def preview_scoped_fts(engine, tenant, frame, viewer, *, queries,
                       expected_posts: int, expected_sources: int, limit: int = 5):
    """Fail closed on live rights or snapshot drift; return no caption text.

    This is a private operator diagnostic, not a general-purpose retrieval API:
    do not wire it into HTTP, MCP, LLM tools, or Creative Studio.
    """
    if (not tenant or not viewer
            or not isinstance(expected_posts, int) or isinstance(expected_posts, bool)
            or not isinstance(expected_sources, int) or isinstance(expected_sources, bool)
            or expected_posts < 1 or expected_sources < 1
            or expected_posts < expected_sources):
        raise RetrievalBaselineError("RETRIEVAL_SCOPE_EXPECTATION_INVALID")
    if not isinstance(queries, (list, tuple)) or not 1 <= len(queries) <= 10:
        raise RetrievalBaselineError("RETRIEVAL_QUERY_BATCH_INVALID")

    # Gate before ANY local caption material enters the transient index.
    require_scoped_research(engine, tenant, frame, viewer)
    rows, partition_before = _scoped_rows(
        engine, tenant, frame, viewer, expected_sources, expected_posts,
    )
    try:
        with TransientScopedFts(rows, manifest_sha256=frame.fingerprint()) as index:
            if index.count != expected_posts:
                raise RetrievalBaselineError("RETRIEVAL_FTS_POPULATION_MISMATCH")
            hits = [index.search(q, limit=limit) for q in queries]
    finally:
        # Do not retain the bulk of caption strings longer than necessary.
        rows.clear()

    # Revalidate grants, provisioned contexts and the precise caption/snapshot
    # partition before returning even private IDs.
    require_scoped_research(engine, tenant, frame, viewer)
    verify_rows, partition_after = _scoped_rows(
        engine, tenant, frame, viewer, expected_sources, expected_posts,
    )
    verify_rows.clear()
    require_scoped_research(engine, tenant, frame, viewer)
    if partition_before != partition_after:
        raise RetrievalBaselineError("RETRIEVAL_PARTITION_DRIFT")

    return {
        "status": "SCOPED_FTS_LOCAL_PREVIEW_COMPLETED",
        "policy_version": VERSION,
        "manifest_sha256": frame.fingerprint(),
        "eligible_posts": expected_posts,
        "eligible_sources": expected_sources,
        "partition_sha256": partition_before,
        "queries": hits,
        "query_count": len(hits),
        "p95_search_latency_ms": p95_ms([h["latency_ms"] for h in hits]),
        "latency_excludes_readiness_and_index_build": True,
        "gold_relevance_judgments_available": False,
        "recall_at_k": None,
        "ndcg_at_k": None,
        "model_predictions_reexecuted": False,
        "external_data_accessed": False,
        "database_mutated": False,
        "scientific_admissions": 0,
        "scientifically_validated": False,
        "production_approved": False,
        "editorial_recommendations_generated": False,
    }
