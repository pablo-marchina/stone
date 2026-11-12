"""CAP-001/A4: explicitly curated Business Discovery batch and coverage report.

No OAuth or provider calls without --execute and all existing permission gates.
Run output is private and is never accepted into the scientific corpus.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pydantic import ValidationError

from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_batch import (
    BatchLimits, BatchManifest, TechnicalDiscoveryBatch, selection_plan,
)
from tapi_gate0.ingestion import IngestionStore
from tapi_gate0.sa_store import engine_for


def _write_private_report(path: Path, report: dict) -> None:
    root = (Path(__file__).resolve().parents[1] / "artifacts" / "private").resolve()
    if not path.resolve().is_relative_to(root) or path.suffix.lower() != ".json":
        raise ValueError("REPORT_MUST_BE_PRIVATE_JSON")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CAP-001 approved-source batch (offline by default)")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="opt-in to real metadata reads")
    parser.add_argument("--report", type=Path, help="required private JSON path for real batch")
    parser.add_argument("--batch-key", help="unique idempotency key for this operation")
    parser.add_argument("--max-sources", type=int, default=3)
    parser.add_argument("--page-limit", type=int, default=10)
    parser.add_argument("--max-pages", type=int, default=4)
    parser.add_argument("--persist-limit", type=int, default=12)
    args = parser.parse_args(argv)
    try:
        manifest = BatchManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
        limits = BatchLimits(max_sources=args.max_sources, page_limit=args.page_limit,
                             max_pages=args.max_pages, persist_limit=args.persist_limit)
    except (OSError, ValidationError, ValueError):
        print(json.dumps({"status": "BLOCKED", "code": "INVALID_BATCH_MANIFEST_OR_LIMITS",
                          "external_data_accessed": False}))
        return 2
    if not args.execute:
        print(json.dumps(selection_plan(manifest, limits), ensure_ascii=False))
        return 0
    # Do not create files, connect to a database or call the provider until
    # all operator prerequisites are present. Only NAME missing is disclosed.
    required = ("TAPI_DATABASE_URL", "TAPI_TENANT_ID", "TAPI_META_IG_ID",
                "TAPI_INSTAGRAM_ACCESS_TOKEN", "TAPI_BD_TECHNICAL_INGEST",
                "TAPI_OFFICIAL_METADATA_READS", "TAPI_ZERO_BILLING_CONFIRMED")
    missing = [key for key in required if not os.getenv(key)]
    if missing or not args.report:
        print(json.dumps({"status": "BLOCKED", "code": "BATCH_PREREQUISITES_MISSING",
                          "missing_environment_names": missing,
                          "report_path_required": not bool(args.report),
                          "external_data_accessed": False}))
        return 2
    url = os.environ["TAPI_DATABASE_URL"]
    if not url.startswith(("sqlite:///", "postgresql+psycopg://")):
        print(json.dumps({"status": "BLOCKED", "code": "LOCAL_DB_URL_REQUIRED",
                          "external_data_accessed": False}))
        return 2
    try:
        root = (Path(__file__).resolve().parents[1] / "artifacts" / "private").resolve()
        if not args.report.resolve().is_relative_to(root) or args.report.suffix.lower() != ".json":
            raise ValueError("REPORT_MUST_BE_PRIVATE_JSON")
        if args.report.exists():
            raise ValueError("REPORT_ALREADY_EXISTS")
        engine = engine_for(url)
        try:
            result = TechnicalDiscoveryBatch(IngestionStore(engine)).execute(
                os.environ["TAPI_TENANT_ID"], manifest, limits,
                os.environ["TAPI_META_IG_ID"], batch_key=args.batch_key)
        finally:
            engine.dispose()
        _write_private_report(args.report, result)
        print(json.dumps({"status": result["status"], "batch_key": result["batch_key"],
                          "report_path": str(args.report),
                          "coverage": result["coverage"], "counts": result["counts"],
                          "scientific_admissions_from_batch": 0}, ensure_ascii=False))
        return 0 if result["status"] in ("BATCH_COMPLETED", "BATCH_NO_ELIGIBLE_OBSERVATIONS") else 4
    except ConnectorError as exc:
        print(json.dumps({"status": "BLOCKED", "code": exc.code,
                          "external_data_accessed": False}))
        return 3
    except (ValueError, OSError):
        print(json.dumps({"status": "BLOCKED", "code": "BATCH_REPORT_OR_DATABASE_ERROR"}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
