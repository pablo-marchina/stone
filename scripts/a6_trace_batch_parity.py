"""IMP-071: strict read-only parity audit of A3 event traces on a scoped corpus.

Compares original per-event audit_run with experimental batched audit over
exactly the same completed local runs. It NEVER enables the new algorithm for
readiness, ingestion, HTTP, MCP or creative actions. All outputs are aggregate
or written to a fresh private report; no caption, content ID or run key output.
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
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_batch import BatchManifest
from tapi_gate0.discovery_caption_research import require_scoped_research
from tapi_gate0.discovery_corpus_readiness import readiness_report
from tapi_gate0.discovery_local_db import validate_existing_database_url
from tapi_gate0.discovery_technical import audit_run
from tapi_gate0.discovery_trace_batch import audit_run_batched
from tapi_gate0.ingestion import ingestion_runs
from tapi_gate0.sa_store import engine_for

ROOT = Path(__file__).resolve().parents[1]
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json")
_PIN = re.compile(r"[0-9a-f]{64}")


def _population(engine, tenant, frame, viewer, *, sources, posts, pin):
    members = []

    def observe(source, content, metric):
        members.append((
            source.username, content.content_id, metric.snapshot_id,
            sha256(content.caption.encode("utf-8")).hexdigest(),
        ))

    ready = readiness_report(engine, tenant, frame, viewer,
                             _record_observer=observe)
    if (ready["status"] != "CORPUS_READINESS_PLANNED"
            or ready["manifest_sha256"] != frame.fingerprint()
            or len(frame.sources) != sources
            or ready["completed_runs_without_valid_bd_trace"] != 0
            or ready["first_blocking_stage"]["CAPTION_AVAILABLE_FOR_ASSESSMENT"] != posts
            or len(members) != posts
            or len({x[1] for x in members}) != posts
            or sum(s["source_gate"] == "TECHNICAL_SCOPE_MATCHED"
                   for s in ready["sources"]) != sources
            or ready["database_mutated"] is not False
            or ready["external_data_accessed"] is not False):
        raise ValueError("TRACE_PARITY_POPULATION_INVALID")
    canonical = json.dumps(sorted(members), ensure_ascii=False,
                           separators=(",", ":"))
    if sha256(canonical.encode("utf-8")).hexdigest() != pin:
        raise ValueError("TRACE_PARITY_PARTITION_DRIFT")



def _readiness_variant(engine, tenant, frame, viewer, *,
                       auditor, expected_sources, expected_posts,
                       expected_partition):
    """Private fail-closed shadow readiness comparison; never emits text/IDs."""
    observed = []

    def capture(source, post, metric):
        observed.append((
            source.username, post.content_id, metric.snapshot_id,
            sha256(post.caption.encode("utf-8")).hexdigest(),
        ))

    require_scoped_research(engine, tenant, frame, viewer)
    started = perf_counter()
    report = readiness_report(
        engine, tenant, frame, viewer, _record_observer=capture,
        _trace_auditor=auditor,
    )
    elapsed = round((perf_counter() - started) * 1000, 6)
    require_scoped_research(engine, tenant, frame, viewer)

    if (report["status"] != "CORPUS_READINESS_PLANNED"
            or report["manifest_sha256"] != frame.fingerprint()
            or len(frame.sources) != expected_sources
            or len(observed) != expected_posts
            or len({item[1] for item in observed}) != expected_posts
            or report["completed_runs_without_valid_bd_trace"] != 0
            or report["first_blocking_stage"]["CAPTION_AVAILABLE_FOR_ASSESSMENT"] != expected_posts
            or sum(row["source_gate"] == "TECHNICAL_SCOPE_MATCHED"
                   for row in report["sources"]) != expected_sources
            or report["database_mutated"] is not False
            or report["external_data_accessed"] is not False
            or report["new_scientific_admissions"] != 0):
        raise ValueError("TRACE_PARITY_READINESS_POPULATION_INVALID")
    part = json.dumps(sorted(observed), separators=(",", ":"), ensure_ascii=False)
    if sha256(part.encode("utf-8")).hexdigest() != expected_partition:
        raise ValueError("TRACE_PARITY_READINESS_PARTITION_DRIFT")

    # UTC as_of necessarily differs between independent read-only scans.
    # Every other canonical data-card and readiness field must match exactly.
    normalized = dict(report)
    normalized.pop("as_of", None)
    card = dict(normalized["canonical_corpus_card"])
    card.pop("as_of", None)
    normalized["canonical_corpus_card"] = card
    canonical = json.dumps(normalized, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest(), elapsed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-partition-sha256", required=True)
    parser.add_argument("--expected-posts", type=int, required=True)
    parser.add_argument("--expected-sources", type=int, required=True)
    parser.add_argument("--report-name", required=True)
    parser.add_argument("--compare-readiness", action="store_true",
                        help="Compare canonical and batched audit inside full readiness")
    parser.add_argument("--readiness-repeats", type=int, default=1,
                        help="Fully revalidated shadow pairs, 1..5; requires compare-readiness")
    parser.add_argument("--confirm-all-ingestion-stopped", action="store_true")
    parser.add_argument("--confirm-all-writers-stopped", action="store_true")
    a = parser.parse_args(argv)
    engine = None
    try:
        if not a.confirm_all_ingestion_stopped or not a.confirm_all_writers_stopped:
            raise ValueError("TRACE_PARITY_STOP_CONFIRMATION_REQUIRED")
        if not 1 <= a.readiness_repeats <= 5 or (a.readiness_repeats > 1 and not a.compare_readiness):
            raise ValueError("TRACE_PARITY_READINESS_REPEAT_BOUNDS")
        private = ROOT / "artifacts" / "private"
        if (not private.is_dir() or private.resolve() != private.absolute()
                or not _NAME.fullmatch(a.report_name)
                or not _PIN.fullmatch(a.expected_manifest_sha256)
                or not _PIN.fullmatch(a.expected_partition_sha256)):
            raise ValueError("TRACE_PARITY_PRIVATE_PIN_INVALID")
        target = private / a.report_name
        if target.exists() or target.is_symlink():
            raise ValueError("TRACE_PARITY_REPORT_ALREADY_EXISTS")
        if (not a.manifest.is_file() or a.manifest.is_symlink()
                or a.manifest.resolve().parent != private):
            raise ValueError("TRACE_PARITY_MANIFEST_PRIVATE_REQUIRED")
        frame = BatchManifest.model_validate_json(
            a.manifest.read_text(encoding="utf-8")
        )
        if (frame.fingerprint() != a.expected_manifest_sha256
                or a.expected_sources <= 0 or a.expected_posts < a.expected_sources):
            raise ValueError("TRACE_PARITY_MANIFEST_OR_COUNTS_INVALID")

        tenant = os.environ.get("TAPI_TENANT_ID", "")
        viewer = os.environ.get("TAPI_META_IG_ID", "")
        url = validate_existing_database_url(os.environ.get("TAPI_DATABASE_URL", ""))
        if not tenant or not viewer:
            raise ValueError("TRACE_PARITY_SCOPE_MISSING")
        engine = engine_for(url)
        require_scoped_research(engine, tenant, frame, viewer)
        _population(engine, tenant, frame, viewer,
                    sources=a.expected_sources, posts=a.expected_posts,
                    pin=a.expected_partition_sha256)

        allowed_ids = sorted(s.expected_ig_id for s in frame.sources)
        with engine.connect() as db:
            keys = db.execute(select(ingestion_runs.c.run_key).where(
                ingestion_runs.c.tenant_id == tenant,
                ingestion_runs.c.platform == "instagram",
                ingestion_runs.c.source_account_id.in_(allowed_ids),
                ingestion_runs.c.status == "completed",
            ).order_by(ingestion_runs.c.run_key)).scalars().all()
            if not keys or len(keys) > 500:
                raise ValueError("TRACE_PARITY_RUN_COUNT_INVALID")

            original_times, batched_times = [], []
            observation_count = 0
            for i, key in enumerate(keys):
                # Alternate call order to reduce systematic warm-cache bias.
                sequence = (
                    (("original", audit_run), ("batched", audit_run_batched))
                    if i % 2 == 0 else
                    (("batched", audit_run_batched), ("original", audit_run))
                )
                compared = {}
                for label, fn in sequence:
                    started = perf_counter()
                    compared[label] = fn(engine, tenant, key, connection=db)
                    elapsed = round((perf_counter() - started) * 1000, 6)
                    (original_times if label == "original" else batched_times).append(elapsed)
                if compared["original"] != compared["batched"]:
                    raise ValueError("TRACE_PARITY_MISMATCH")
                if not compared["original"]["all_traces_valid"]:
                    raise ValueError("TRACE_PARITY_ORIGINAL_INVALID")
                observation_count += compared["original"]["observations"]

        readiness_comparison = None
        if a.compare_readiness:
            # Every read performs a fresh grant/context check and verifies the
            # complete caption/snapshot partition. No authorization caching.
            samples = {"original": [], "batched": []}
            stable_readiness_hash = None
            for round_index in range(a.readiness_repeats):
                # Reverse the within-pair order every time, preserving a
                # balanced ordering across repetitions.
                order = (
                    (("original", audit_run), ("batched", audit_run_batched))
                    if round_index % 2 == 0 else
                    (("batched", audit_run_batched), ("original", audit_run))
                )
                hashes = {}
                for label, auditor in order:
                    digest, elapsed = _readiness_variant(
                        engine, tenant, frame, viewer, auditor=auditor,
                        expected_sources=a.expected_sources,
                        expected_posts=a.expected_posts,
                        expected_partition=a.expected_partition_sha256,
                    )
                    hashes[label] = digest
                    samples[label].append(elapsed)
                if hashes["original"] != hashes["batched"]:
                    raise ValueError("TRACE_PARITY_READINESS_MISMATCH")
                if (stable_readiness_hash is not None
                        and hashes["original"] != stable_readiness_hash):
                    raise ValueError("TRACE_PARITY_READINESS_DRIFT")
                stable_readiness_hash = hashes["original"]

            def nearest_rank(values, quantile):
                sorted_values = sorted(values)
                return sorted_values[ceil(quantile * len(values)) - 1]

            readiness_comparison = {
                "status": "READINESS_BATCH_SHADOW_PARITY_VERIFIED",
                "all_non_temporal_fields_equal": True,
                "all_repetitions_equal": True,
                "report_sha256": stable_readiness_hash,
                "original_readiness_ms": samples["original"][-1],
                "batched_readiness_ms": samples["batched"][-1],
                "repetitions": a.readiness_repeats,
                "original_samples_ms": samples["original"],
                "batched_samples_ms": samples["batched"],
                "original_p50_ms": nearest_rank(samples["original"], 0.50),
                "batched_p50_ms": nearest_rank(samples["batched"], 0.50),
                "original_p95_ms": nearest_rank(samples["original"], 0.95),
                "batched_p95_ms": nearest_rank(samples["batched"], 0.95),
                "alternating_readiness_order": True,
                "canonical_default_unchanged": True,
                "shadow_algorithm_not_active": True,
                "comparison_is_uncontrolled_cache_diagnostic": True,
            }

        require_scoped_research(engine, tenant, frame, viewer)
        _population(engine, tenant, frame, viewer,
                    sources=a.expected_sources, posts=a.expected_posts,
                    pin=a.expected_partition_sha256)
        require_scoped_research(engine, tenant, frame, viewer)

        report = {
            "status": "TRACE_AUDIT_BATCH_PARITY_VERIFIED",
            "manifest_sha256": a.expected_manifest_sha256,
            "partition_sha256": a.expected_partition_sha256,
            "runs_compared": len(keys),
            "observations_compared": observation_count,
            "exact_report_parity": True,
            "all_original_traces_valid": True,
            "original_total_ms": round(sum(original_times), 6),
            "batched_total_ms": round(sum(batched_times), 6),
            "original_per_run_ms": original_times,
            "batched_per_run_ms": batched_times,
            "alternating_order": True,
            "uncontrolled_cache_diagnostic_only": True,
            "new_auditor_wired_into_readiness": False,
            "database_mutated": False,
            "external_data_accessed": False,
            "scientific_admissions": 0,
            "scientifically_validated": False,
        }
        if readiness_comparison is not None:
            report["readiness_parity"] = readiness_comparison
        # Preserve the detailed aggregate benchmark exclusively in private.
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(report, file, indent=2)
        print(json.dumps({k: v for k, v in report.items()
                          if k not in {"original_per_run_ms", "batched_per_run_ms"}}))
        return 0
    except ConnectorError as exc:
        code = exc.code
    except (ValueError, KeyError, TypeError, OSError, SQLAlchemyError,
            sqlite3.DatabaseError):
        code = "TRACE_PARITY_LOCAL_ERROR"
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps({"status": "BLOCKED", "code": code,
                      "database_mutated": False, "external_data_accessed": False}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
