"""IMP-071: local-only end-to-end retrieval shadow parity.

Compare original and batched technical trace audit within the COMPLETE
rights-gated FTS preview. Each alternative performs 2 readiness scans and
3 scoped-rights checks. No existing runtime caller enables batch by default.
No captions or internal content/snapshot IDs are exported in the JSON report.
Never wire this experiment to HTTP, MCP, agents, Creative Studio, or ingestion.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from math import ceil
import os
from pathlib import Path
import re
import sqlite3

from sqlalchemy.exc import SQLAlchemyError

from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_batch import BatchManifest
from tapi_gate0.discovery_caption_research import require_scoped_research
from tapi_gate0.discovery_local_db import validate_existing_database_url
from tapi_gate0.discovery_retrieval_fts import RetrievalBaselineError, _fts_query
from tapi_gate0.discovery_retrieval_scoped import preview_scoped_fts
from tapi_gate0.discovery_trace_batch import audit_run_batched
from tapi_gate0.sa_store import engine_for

ROOT = Path(__file__).resolve().parents[1]
_HASH = re.compile(r"[0-9a-f]{64}")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json")


def _digest_ranked_evidence(report, expected_manifest, expected_partition,
                            expected_posts, expected_sources, expected_queries):
    """Only SHA256 over ranked private refs survives outside process memory."""
    if (report["status"] != "SCOPED_FTS_LOCAL_PREVIEW_COMPLETED"
            or report["manifest_sha256"] != expected_manifest
            or report["partition_sha256"] != expected_partition
            or report["eligible_posts"] != expected_posts
            or report["eligible_sources"] != expected_sources
            or report["query_count"] != len(expected_queries)
            or report["gold_relevance_judgments_available"] is not False
            or report["scientifically_validated"] is not False
            or report["database_mutated"] is not False
            or report["external_data_accessed"] is not False
            or report["scientific_admissions"] != 0
            or report["full_preview_includes_scope_and_revalidation"] is not True):
        raise RetrievalBaselineError("RETRIEVAL_SHADOW_CONTRACT_DRIFT")

    ranked = []
    summary = []
    for query, hit in zip(expected_queries, report["queries"], strict=True):
        expected_query_sha = sha256(query.encode("utf-8")).hexdigest()
        ids, snaps = hit["content_ids"], hit["snapshot_ids"]
        if (hit["query_sha256"] != expected_query_sha
                or hit["manifest_sha256"] != expected_manifest
                or hit["gold_metrics"] is not None
                or hit["scientifically_validated"] is not False
                or not isinstance(ids, list) or not isinstance(snaps, list)
                or len(ids) != len(snaps) or len(ids) != hit["hit_count"]
                or len(ids) != len(set(ids))):
            raise RetrievalBaselineError("RETRIEVAL_SHADOW_RESULT_INVALID")
        ranked.append((expected_query_sha, tuple(ids), tuple(snaps)))
        summary.append({"query_sha256": expected_query_sha,
                        "hit_count": len(ids)})
    digest = sha256(json.dumps(ranked, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8")).hexdigest()
    return digest, summary


def _nearest_rank(samples, q):
    return sorted(samples)[ceil(q * len(samples)) - 1]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--expected-manifest-sha256", required=True)
    p.add_argument("--expected-partition-sha256", required=True)
    p.add_argument("--expected-posts", type=int, required=True)
    p.add_argument("--expected-sources", type=int, required=True)
    p.add_argument("--query", action="append", required=True)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--report-name", required=True)
    p.add_argument("--confirm-all-ingestion-stopped", action="store_true")
    p.add_argument("--confirm-all-writers-stopped", action="store_true")
    a = p.parse_args(argv)
    engine = None
    try:
        if not (a.confirm_all_ingestion_stopped and a.confirm_all_writers_stopped):
            raise RetrievalBaselineError("RETRIEVAL_SHADOW_STOP_CONFIRMATION_REQUIRED")
        if (not 1 <= a.repeat <= 5 or not 1 <= a.top_k <= 50
                or not 1 <= len(a.query) <= 10
                or a.expected_sources < 1 or a.expected_posts < a.expected_sources):
            raise RetrievalBaselineError("RETRIEVAL_SHADOW_LIMITS_INVALID")
        for q in a.query:
            _fts_query(q)
        private = ROOT / "artifacts" / "private"
        if (not private.is_dir() or private.resolve() != private.absolute()
                or not _NAME.fullmatch(a.report_name)
                or not _HASH.fullmatch(a.expected_manifest_sha256)
                or not _HASH.fullmatch(a.expected_partition_sha256)):
            raise RetrievalBaselineError("RETRIEVAL_SHADOW_PRIVATE_PIN_INVALID")
        target = private / a.report_name
        if target.exists() or target.is_symlink():
            raise RetrievalBaselineError("RETRIEVAL_SHADOW_REPORT_EXISTS")
        if (not a.manifest.is_file() or a.manifest.is_symlink()
                or a.manifest.resolve().parent != private):
            raise RetrievalBaselineError("RETRIEVAL_SHADOW_MANIFEST_PRIVATE_REQUIRED")
        frame = BatchManifest.model_validate_json(a.manifest.read_text(encoding="utf-8"))
        if (frame.fingerprint() != a.expected_manifest_sha256
                or len(frame.sources) != a.expected_sources):
            raise RetrievalBaselineError("RETRIEVAL_SHADOW_MANIFEST_MISMATCH")
        tenant = os.environ.get("TAPI_TENANT_ID", "")
        viewer = os.environ.get("TAPI_META_IG_ID", "")
        if not tenant or not viewer:
            raise RetrievalBaselineError("RETRIEVAL_SHADOW_TENANT_VIEWER_MISSING")
        url = validate_existing_database_url(os.environ.get("TAPI_DATABASE_URL", ""))
        engine = engine_for(url)

        times = {"original": [], "batched": []}
        expected_rank_digest = None
        summary = None
        for i in range(a.repeat):
            order = (
                ("original", "batched") if i % 2 == 0
                else ("batched", "original")
            )
            digests = {}
            for label in order:
                kwargs = {"trace_auditor": audit_run_batched} if label == "batched" else {}
                report = preview_scoped_fts(
                    engine, tenant, frame, viewer,
                    queries=a.query,
                    expected_posts=a.expected_posts,
                    expected_sources=a.expected_sources,
                    limit=a.top_k,
                    **kwargs,
                )
                digest, query_summary = _digest_ranked_evidence(
                    report, a.expected_manifest_sha256,
                    a.expected_partition_sha256,
                    a.expected_posts, a.expected_sources,
                    a.query,
                )
                if (expected_rank_digest is not None
                        and digest != expected_rank_digest):
                    raise RetrievalBaselineError("RETRIEVAL_SHADOW_RANK_OR_SNAPSHOT_DRIFT")
                if expected_rank_digest is None:
                    expected_rank_digest, summary = digest, query_summary
                if summary != query_summary:
                    raise RetrievalBaselineError("RETRIEVAL_SHADOW_HITS_DRIFT")
                digests[label] = digest
                times[label].append(report["full_preview_elapsed_ms"])
            if digests["original"] != digests["batched"]:
                raise RetrievalBaselineError("RETRIEVAL_SHADOW_PARITY_MISMATCH")

        # A final grant/context check immediately before PRIVATE report creation.
        require_scoped_research(engine, tenant, frame, viewer)
        benchmark = {
            "status": "RETRIEVAL_SHADOW_FULL_PARITY_VERIFIED",
            "manifest_sha256": a.expected_manifest_sha256,
            "partition_sha256": a.expected_partition_sha256,
            "eligible_posts": a.expected_posts,
            "eligible_sources": a.expected_sources,
            "queries": summary,
            "query_count": len(summary),
            "rank_and_snapshots_sha256": expected_rank_digest,
            "repetitions": a.repeat,
            "all_repetitions_and_rankings_equal": True,
            "alternating_order": True,
            "original_full_preview_ms": times["original"],
            "batched_full_preview_ms": times["batched"],
            "original_p50_ms": _nearest_rank(times["original"], 0.5),
            "batched_p50_ms": _nearest_rank(times["batched"], 0.5),
            "original_p95_ms": _nearest_rank(times["original"], 0.95),
            "batched_p95_ms": _nearest_rank(times["batched"], 0.95),
            "each_preview_has_3_scope_checks_and_2_readiness": True,
            "original_is_default": True,
            "batched_runtime_active": False,
            "uncontrolled_cache_diagnostic_only": True,
            "latency_excludes_engine_setup_and_report_write": True,
            "gold_relevance_judgments_available": False,
            "scientific_admissions": 0,
            "external_data_accessed": False,
            "database_mutated": False,
            "production_approved": False,
            "report_name": a.report_name,
        }
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(benchmark, f, ensure_ascii=False, indent=2)
        print(json.dumps(benchmark, ensure_ascii=False))
        return 0
    except ConnectorError as exc:
        code = exc.code
    except RetrievalBaselineError as exc:
        code = str(exc)
    except (OSError, ValueError, TypeError, KeyError, SQLAlchemyError,
            sqlite3.DatabaseError):
        code = "RETRIEVAL_SHADOW_LOCAL_ERROR"
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps({"status": "BLOCKED", "code": code,
                      "database_mutated": False, "external_data_accessed": False}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
