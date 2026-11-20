"""IMP-071: explicitly opted-in, operator-local single-path batched FTS preview.

Requires a hash-pinned, fully qualified PRIVATE comparison report and live
manifest/partition/ranking equality. This does not change default readiness,
ingestion, HTTP, MCP or Creative Studio. No network, DB mutations or gold.
Every invocation performs 3 live scope checks and 2 complete readiness passes.
If pins, permissions, trace validity or snapshots drift: fail without output.
To rollback, use scripts.a6_retrieval_preview with no batch opt-in.
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
from scripts.a6_retrieval_shadow import _digest_ranked_evidence

ROOT = Path(__file__).resolve().parents[1]
_HASH = re.compile(r"[0-9a-f]{64}")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json")


def _load_qualified_proof(private, name, proof_sha, *,
                          manifest, partition, ranking, posts, sources,
                          queries, limit):
    """Fail-closed offline attestation; no embedded private IDs are emitted."""
    if not _NAME.fullmatch(name) or not _HASH.fullmatch(proof_sha):
        raise RetrievalBaselineError("FASTPATH_PROOF_PIN_REQUIRED")
    path = private / name
    if (not path.is_file() or path.is_symlink()
            or path.resolve().parent != private or path.stat().st_size > 2_000_000):
        raise RetrievalBaselineError("FASTPATH_PROOF_PRIVATE_REQUIRED")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != proof_sha:
        raise RetrievalBaselineError("FASTPATH_PROOF_SHA_MISMATCH")
    report = json.loads(raw)
    qualified = report["qualified_batched_local"]
    rounds = qualified["qualification_runs"]
    if (report["status"] != "SCOPED_FTS_LOCAL_PREVIEW_COMPLETED"
            or report["manifest_sha256"] != manifest
            or report["partition_sha256"] != partition
            or report["eligible_posts"] != posts
            or report["eligible_sources"] != sources
            or report["query_count"] != len(queries)
            or report["production_approved"] is not False
            or report["repeat_experiment"]["partition_and_hits_stable"] is not True
            or report["repeat_experiment"]["repetitions"] < 2
            or qualified["status"] != "PRIVATE_BATCH_AUDIT_QUALIFIED"
            or qualified["operator_opt_in"] is not True
            or qualified["prior_shadow_ranking_sha256"] != ranking
            or qualified["live_partition_sha256"] != partition
            or qualified["all_rounds_equal_to_canonical"] is not True
            or qualified["canonical_readiness_default_unchanged"] is not True
            or qualified["batch_experimental_local_only"] is not True
            or qualified["failure_blocks_without_fallback"] is not True
            or qualified["production_approved"] is not False
            or not isinstance(rounds, list) or len(rounds) < 2
            or len(rounds) != report["repeat_experiment"]["repetitions"]
            or any(round_["same_rank_and_snapshots"] is not True
                   for round_ in rounds)):
        raise RetrievalBaselineError("FASTPATH_PROOF_NOT_QUALIFIED")
    digest, summaries = _digest_ranked_evidence(
        report, manifest, partition, posts, sources, queries,
    )
    if (digest != ranking
            or any(item["hit_count"] > limit for item in summaries)):
        raise RetrievalBaselineError("FASTPATH_PROOF_RANKING_MISMATCH")
    return summaries


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--expected-manifest-sha256", required=True)
    p.add_argument("--expected-partition-sha256", required=True)
    p.add_argument("--expected-ranking-sha256", required=True)
    p.add_argument("--expected-posts", type=int, required=True)
    p.add_argument("--expected-sources", type=int, required=True)
    p.add_argument("--query", action="append", required=True)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--qualification-report-name", required=True)
    p.add_argument("--expected-qualification-sha256", required=True)
    p.add_argument("--report-name", required=True)
    p.add_argument("--confirm-all-ingestion-stopped", action="store_true")
    p.add_argument("--confirm-all-writers-stopped", action="store_true")
    a = p.parse_args(argv)
    engine = None
    try:
        if not (a.confirm_all_ingestion_stopped and a.confirm_all_writers_stopped):
            raise RetrievalBaselineError("FASTPATH_STOP_CONFIRMATION_REQUIRED")
        if (not 1 <= a.repeat <= 5 or not 1 <= a.top_k <= 50
                or not 1 <= len(a.query) <= 10
                or a.expected_sources <= 0 or a.expected_posts < a.expected_sources
                or not all(_HASH.fullmatch(h) for h in (
                    a.expected_manifest_sha256, a.expected_partition_sha256,
                    a.expected_ranking_sha256, a.expected_qualification_sha256,
                ))):
            raise RetrievalBaselineError("FASTPATH_PARAMETERS_INVALID")
        for query in a.query:
            _fts_query(query)
        private = ROOT / "artifacts" / "private"
        if not private.is_dir() or private.resolve() != private.absolute():
            raise RetrievalBaselineError("FASTPATH_PRIVATE_DIRECTORY_REQUIRED")
        if not _NAME.fullmatch(a.report_name):
            raise RetrievalBaselineError("FASTPATH_REPORT_NAME_INVALID")
        target = private / a.report_name
        if target.exists() or target.is_symlink():
            raise RetrievalBaselineError("FASTPATH_REPORT_ALREADY_EXISTS")
        if (not a.manifest.is_file() or a.manifest.is_symlink()
                or a.manifest.resolve().parent != private):
            raise RetrievalBaselineError("FASTPATH_MANIFEST_PRIVATE_REQUIRED")
        frame = BatchManifest.model_validate_json(
            a.manifest.read_text(encoding="utf-8")
        )
        if (frame.fingerprint() != a.expected_manifest_sha256
                or len(frame.sources) != a.expected_sources):
            raise RetrievalBaselineError("FASTPATH_MANIFEST_PIN_MISMATCH")
        expected_summary = _load_qualified_proof(
            private, a.qualification_report_name,
            a.expected_qualification_sha256,
            manifest=a.expected_manifest_sha256,
            partition=a.expected_partition_sha256,
            ranking=a.expected_ranking_sha256,
            posts=a.expected_posts, sources=a.expected_sources,
            queries=a.query, limit=a.top_k,
        )

        tenant = os.environ.get("TAPI_TENANT_ID", "")
        viewer = os.environ.get("TAPI_META_IG_ID", "")
        if not tenant or not viewer:
            raise RetrievalBaselineError("FASTPATH_TENANT_VIEWER_REQUIRED")
        db_url = validate_existing_database_url(
            os.environ.get("TAPI_DATABASE_URL", "")
        )
        engine = engine_for(db_url)
        samples = []
        for _ in range(a.repeat):
            result = preview_scoped_fts(
                engine, tenant, frame, viewer,
                queries=a.query, expected_posts=a.expected_posts,
                expected_sources=a.expected_sources,
                limit=a.top_k, trace_auditor=audit_run_batched,
            )
            rank, summary = _digest_ranked_evidence(
                result, a.expected_manifest_sha256,
                a.expected_partition_sha256,
                a.expected_posts, a.expected_sources, a.query,
            )
            if rank != a.expected_ranking_sha256 or summary != expected_summary:
                raise RetrievalBaselineError("FASTPATH_LIVE_RANKING_OR_SNAPSHOT_DRIFT")
            samples.append(result["full_preview_elapsed_ms"])

        # Final current grants check; comparison proof is NOT authorization.
        require_scoped_research(engine, tenant, frame, viewer)
        output = {
            "status": "RETRIEVAL_BATCH_FASTPATH_LOCAL_VERIFIED",
            "manifest_sha256": a.expected_manifest_sha256,
            "partition_sha256": a.expected_partition_sha256,
            "rank_and_snapshots_sha256": a.expected_ranking_sha256,
            "qualification_report_sha256": a.expected_qualification_sha256,
            "eligible_posts": a.expected_posts,
            "eligible_sources": a.expected_sources,
            "query_summaries": expected_summary,
            "repetitions": a.repeat,
            "full_preview_latency_samples_ms": samples,
            "full_preview_p50_ms": sorted(samples)[ceil(.5 * len(samples)) - 1],
            "full_preview_p95_ms": sorted(samples)[ceil(.95 * len(samples)) - 1],
            "each_preview_scope_checks": 3,
            "each_preview_readiness_passes": 2,
            "final_scope_recheck": True,
            "single_batched_auditor_per_preview": True,
            "original_algorithm_unchanged_and_default": True,
            "explicit_local_operator_entrypoint_only": True,
            "rollback": "run a6_retrieval_preview without qualified-batched-local",
            "latency_excludes_engine_setup_proof_read_and_report_write": True,
            "uncontrolled_cache_diagnostic_only": True,
            "gold_relevance_judgments_available": False,
            "scientific_admissions": 0,
            "scientifically_validated": False,
            "database_mutated": False,
            "external_data_accessed": False,
            "production_approved": False,
            "report_name": a.report_name,
        }
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(output, file, ensure_ascii=False, indent=2)
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except ConnectorError as exc:
        code = exc.code
    except RetrievalBaselineError as exc:
        code = str(exc)
    except (ValueError, KeyError, TypeError, OSError,
            SQLAlchemyError, sqlite3.DatabaseError):
        code = "FASTPATH_LOCAL_ERROR"
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps({"status": "BLOCKED", "code": code,
                      "database_mutated": False,
                      "external_data_accessed": False}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
