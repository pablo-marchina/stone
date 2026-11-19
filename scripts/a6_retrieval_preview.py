"""IMP-071 local FTS5 preview against a verified, existing private manifest.

No provider access, no persistent index, no caption export and no database
mutation. The report remains under artifacts/private and is NOT a gold eval.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
from math import ceil

from sqlalchemy.exc import SQLAlchemyError

from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_batch import BatchManifest
from tapi_gate0.discovery_local_db import validate_existing_database_url
from tapi_gate0.discovery_retrieval_fts import RetrievalBaselineError
from tapi_gate0.discovery_retrieval_scoped import preview_scoped_fts
from tapi_gate0.sa_store import engine_for

ROOT = Path(__file__).resolve().parents[1]
_REPORT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json")
_HASH = re.compile(r"[0-9a-f]{64}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--expected-manifest-sha256", required=True)
    p.add_argument("--expected-posts", type=int, required=True)
    p.add_argument("--expected-sources", type=int, required=True)
    p.add_argument("--query", action="append", required=True)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--repeat", type=int, default=1, help="Repeat whole scoped audit 1..10 times, fail on drift")
    p.add_argument("--profile-readiness", action="store_true", help="Aggregate timing phases only; keep all guards")
    p.add_argument("--report-name", required=True)
    p.add_argument("--confirm-all-ingestion-stopped", action="store_true")
    p.add_argument("--confirm-all-writers-stopped", action="store_true")
    args = p.parse_args(argv)

    engine = None
    try:
        if not args.confirm_all_ingestion_stopped or not args.confirm_all_writers_stopped:
            raise RetrievalBaselineError("RETRIEVAL_STOP_CONFIRMATION_REQUIRED")
        if not 1 <= args.repeat <= 10:
            raise RetrievalBaselineError("RETRIEVAL_REPEAT_BOUNDS")
        private = ROOT / "artifacts" / "private"
        if not private.is_dir() or private.resolve() != private.absolute():
            raise RetrievalBaselineError("RETRIEVAL_PRIVATE_DIRECTORY_INVALID")
        if (not _REPORT_NAME.fullmatch(args.report_name)
                or not _HASH.fullmatch(args.expected_manifest_sha256)):
            raise RetrievalBaselineError("RETRIEVAL_PRIVATE_REPORT_OR_PIN_INVALID")
        target = private / args.report_name
        if target.is_symlink() or target.exists():
            raise RetrievalBaselineError("RETRIEVAL_REPORT_ALREADY_EXISTS")
        if (not args.manifest.is_file() or args.manifest.is_symlink()
                or args.manifest.resolve().parent != private):
            raise RetrievalBaselineError("RETRIEVAL_MANIFEST_PRIVATE_REQUIRED")
        frame = BatchManifest.model_validate_json(
            args.manifest.read_text(encoding="utf-8")
        )
        if frame.fingerprint() != args.expected_manifest_sha256:
            raise RetrievalBaselineError("RETRIEVAL_MANIFEST_PIN_MISMATCH")

        tenant, viewer = os.environ.get("TAPI_TENANT_ID", ""), os.environ.get("TAPI_META_IG_ID", "")
        url = validate_existing_database_url(os.environ.get("TAPI_DATABASE_URL", ""))
        if not tenant or not viewer:
            raise RetrievalBaselineError("RETRIEVAL_TENANT_VIEWER_REQUIRED")
        engine = engine_for(url)
        report = None
        elapsed = []
        readiness_profiles = []
        stable_key = None
        for _ in range(args.repeat):
            round_report = preview_scoped_fts(
                engine, tenant, frame, viewer,
                queries=args.query,
                expected_posts=args.expected_posts,
                expected_sources=args.expected_sources,
                limit=args.top_k,
                profile_readiness=args.profile_readiness,
            )
            if (round_report["manifest_sha256"] != args.expected_manifest_sha256
                    or round_report["eligible_posts"] != args.expected_posts
                    or round_report["eligible_sources"] != args.expected_sources
                    or round_report["query_count"] != len(args.query)):
                raise RetrievalBaselineError("RETRIEVAL_REPEAT_CONTRACT_DRIFT")
            # Preserve order and exact evidence references; never confuse
            # stable hit counts with stable result rankings or snapshots.
            key = (round_report["partition_sha256"], tuple(
                (h["query_sha256"], tuple(h["content_ids"]),
                 tuple(h["snapshot_ids"])) for h in round_report["queries"]
            ))
            if stable_key is not None and key != stable_key:
                raise RetrievalBaselineError("RETRIEVAL_REPEAT_PARTITION_OR_HITS_DRIFT")
            stable_key = key
            elapsed.append(round_report["full_preview_elapsed_ms"])
            if args.profile_readiness:
                profile = round_report.get("readiness_profile")
                if (not isinstance(profile, dict)
                        or not isinstance(profile.get("first_readiness"), dict)
                        or not isinstance(profile.get("second_readiness"), dict)):
                    raise RetrievalBaselineError("RETRIEVAL_READINESS_PROFILE_INVALID")
                readiness_profiles.append(profile)
            report = round_report

        sorted_elapsed = sorted(elapsed)
        report["repeat_experiment"] = {
            "repetitions": args.repeat,
            "full_path_latency_samples_ms": elapsed,
            "full_path_p50_ms": sorted_elapsed[ceil(0.50 * len(elapsed)) - 1],
            "full_path_p95_ms": sorted_elapsed[ceil(0.95 * len(elapsed)) - 1],
            "full_path_min_ms": sorted_elapsed[0],
            "full_path_max_ms": sorted_elapsed[-1],
            "partition_and_hits_stable": True,
            "each_round_revalidated_scope_and_captions": True,
            "latency_excludes_engine_setup_and_report_write": True,
            "exploratory_not_service_slo": True,
            "relevance_gold_available": False,
            "readiness_profile_samples": readiness_profiles if args.profile_readiness else None,
        }
        # The only filesystem output is private; refuse overwrites.
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({**report, "report_name": args.report_name},
                      stream, ensure_ascii=False, indent=2)
        print(json.dumps({
            "status": report["status"],
            "policy_version": report["policy_version"],
            "manifest_sha256": report["manifest_sha256"],
            "partition_sha256": report["partition_sha256"],
            "eligible_posts": report["eligible_posts"],
            "eligible_sources": report["eligible_sources"],
            "query_count": report["query_count"],
            "query_summaries": [
                {"query_sha256": result["query_sha256"],
                 "hit_count": result["hit_count"]}
                for result in report["queries"]
            ],
            "p95_search_latency_ms": report["p95_search_latency_ms"],
            "latency_excludes_readiness_and_index_build": True,
            "full_preview_elapsed_ms": report["full_preview_elapsed_ms"],
            "timing_breakdown_ms": report["timing_breakdown_ms"],
            "full_preview_includes_scope_and_revalidation": True,
            "performance_sample_is_exploratory": True,
            "repeat_experiment": report["repeat_experiment"],
            "readiness_profile": report.get("readiness_profile"),
            "gold_relevance_judgments_available": False,
            "scientific_admissions": 0,
            "database_mutated": False,
            "external_data_accessed": False,
            "report_name": args.report_name,
        }, ensure_ascii=False))
        return 0
    except ConnectorError as exc:
        code = exc.code
    except RetrievalBaselineError as exc:
        code = str(exc)
    except (OSError, ValueError, KeyError, TypeError, SQLAlchemyError, sqlite3.DatabaseError):
        code = "RETRIEVAL_LOCAL_PREVIEW_ERROR"
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps({
        "status": "BLOCKED", "code": code,
        "database_mutated": False, "external_data_accessed": False,
    }))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
