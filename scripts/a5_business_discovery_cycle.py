"""Plan or execute exactly one A5 cycle. No scheduler, payment, or API auto-discovery."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_batch import BatchLimits, BatchManifest
from tapi_gate0.discovery_continuous import execute_cycle, plan_cycle, tenant_coverage
from tapi_gate0.ingestion import IngestionStore
from tapi_gate0.sa_store import engine_for


def main(argv=None):
    parser = argparse.ArgumentParser(description="CAP-001 A5 bounded local cycle")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--mode", choices=("history", "refresh"), required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--max-sources", type=int, default=3)
    parser.add_argument("--page-limit", type=int, default=10)
    parser.add_argument("--max-pages", type=int, default=4)
    parser.add_argument("--daily-request-budget", type=int, default=80)
    parser.add_argument("--refresh-hours", type=int, default=24)
    args = parser.parse_args(argv)
    required = ["TAPI_DATABASE_URL", "TAPI_TENANT_ID", "TAPI_META_IG_ID"]
    if args.execute:
        required += ["TAPI_INSTAGRAM_ACCESS_TOKEN", "TAPI_BD_CONTINUOUS_ENABLED",
            "TAPI_BD_TECHNICAL_INGEST", "TAPI_OFFICIAL_METADATA_READS", "TAPI_ZERO_BILLING_CONFIRMED"]
    missing = [k for k in required if not os.getenv(k)]
    if missing or (args.execute and not args.report):
        print(json.dumps({"status": "BLOCKED", "code": "A5_PREREQUISITES_MISSING",
                          "missing_environment_names": missing, "external_data_accessed": False}))
        return 2
    try:
        manifest = BatchManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
        product = args.page_limit * args.max_pages
        limits = BatchLimits(max_sources=args.max_sources, page_limit=args.page_limit,
            max_pages=args.max_pages, persist_limit=product if args.mode == "history" else min(12, product))
        url = os.environ["TAPI_DATABASE_URL"]
        if not url.startswith(("sqlite:///", "postgresql+psycopg://")):
            raise ValueError("INVALID_DATABASE_URL")
        # Local SQLite must exist: planning must not create a database.
        if url.startswith("sqlite:///") and not Path(url.removeprefix("sqlite:///")).is_file():
            raise ValueError("DATABASE_MUST_EXIST")
    except (OSError, ValidationError, ValueError):
        print(json.dumps({"status": "BLOCKED", "code": "A5_INVALID_MANIFEST_OR_LIMITS", "external_data_accessed": False}))
        return 2
    try:
        engine = engine_for(url)
    except (ValueError, SQLAlchemyError, ImportError):
        print(json.dumps({"status": "BLOCKED", "code": "A5_DATABASE_UNAVAILABLE"}))
        return 3
    tenant, viewer = os.environ["TAPI_TENANT_ID"], os.environ["TAPI_META_IG_ID"]
    options = dict(mode=args.mode, limits=limits, daily_request_budget=args.daily_request_budget,
                   refresh_hours=args.refresh_hours)
    try:
        store = IngestionStore(engine)
        if not args.execute:
            plan, _ = plan_cycle(store, tenant, manifest, viewer, **options)
            plan["tenant_coverage"] = tenant_coverage(store, tenant)
            print(json.dumps(plan, ensure_ascii=False))
            return 0
        root = (Path(__file__).resolve().parents[1] / "artifacts" / "private").resolve()
        if not args.report.resolve().is_relative_to(root) or args.report.suffix.lower() != ".json":
            raise ConnectorError("REPORT_MUST_BE_PRIVATE_JSON", 422)
        args.report.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            try:
                report = execute_cycle(store, tenant, manifest, viewer, **options)
            except ConnectorError as exc:
                report = {"status": "BLOCKED", "code": exc.code}
            json.dump(report, stream, ensure_ascii=False, indent=2)
        summary = {k: v for k, v in report.items() if k != "batch"}
        if "batch" in report:
            summary["counts"] = report["batch"]["counts"]
        summary["report_path"] = str(args.report)
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if report["status"] in {"BATCH_COMPLETED", "BATCH_NO_ELIGIBLE_OBSERVATIONS", "NO_DUE_AUTHORIZED_SOURCES"} else 4
    except ConnectorError as exc:
        print(json.dumps({"status": "BLOCKED", "code": exc.code}))
        return 3
    except (OSError, ValueError, SQLAlchemyError):
        print(json.dumps({"status": "BLOCKED", "code": "A5_REPORT_OR_DATABASE_ERROR"}))
        return 3
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
