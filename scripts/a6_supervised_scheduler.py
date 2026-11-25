"""Plan a single supervised scheduler tick, optionally execute or acknowledge a stop."""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re

from sqlalchemy.exc import SQLAlchemyError
from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_batch import BatchManifest
from tapi_gate0.discovery_local_db import validate_existing_database_url
from tapi_gate0.discovery_scheduler import acknowledge_stop, execute_tick, preview_tick, local_preflight_summary, cycle_summary
from tapi_gate0.identity import IdentityFailure, IdentityStore
from tapi_gate0.ingestion import IngestionStore
from tapi_gate0.sa_store import engine_for

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--execute", action="store_true")
    group.add_argument("--check-ready", action="store_true", help="Compact local preflight; nonzero exit if blocked or no due sources")
    group.add_argument("--acknowledge-stop", type=int, metavar="EVENT_SEQ")
    parser.add_argument("--confirm-all-ingestion-stopped", action="store_true")
    parser.add_argument("--admin", default="admin")
    parser.add_argument("--report-name", help="New private JSON report basename, required for execution")
    parser.add_argument("--max-sources", type=int, default=3)
    parser.add_argument("--daily-request-budget", type=int, default=80)
    parser.add_argument("--refresh-hours", type=int, default=24)
    args = parser.parse_args(argv)
    engine = None
    execution_started = False
    try:
        tenant = os.environ.get("TAPI_TENANT_ID", "")
        viewer = os.environ.get("TAPI_META_IG_ID", "")
        if not tenant:
            raise ConnectorError("BD_SCHEDULER_TENANT_REQUIRED", 422)
        url = validate_existing_database_url(os.environ.get("TAPI_DATABASE_URL", ""))
        if args.acknowledge_stop is not None:
            if args.acknowledge_stop <= 0 or not args.confirm_all_ingestion_stopped:
                raise ConnectorError("BD_SCHEDULER_ADMIN_STOP_REQUIRED", 422)
            engine = engine_for(url)
            identity = IdentityStore(engine)
            session = identity.login(args.admin, getpass.getpass("Admin password: "), tenant)
            principal = identity.resolve(session.access_token)
            try:
                report = acknowledge_stop(IngestionStore(engine), principal, args.acknowledge_stop, stopped=True)
            finally:
                identity.revoke(session.access_token, principal)
        else:
            if args.manifest is None or not viewer:
                raise ConnectorError("BD_SCHEDULER_MANIFEST_AND_VIEWER_REQUIRED", 422)
            manifest = BatchManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
            options = dict(max_sources=args.max_sources, daily_budget=args.daily_request_budget,
                           refresh_hours=args.refresh_hours)
            engine = engine_for(url)
            store = IngestionStore(engine)
            if not args.execute:
                report = preview_tick(store, tenant, manifest, viewer, **options)
                if args.check_ready:
                    report = local_preflight_summary(report)
            else:
                if not os.getenv("TAPI_INSTAGRAM_ACCESS_TOKEN"):
                    raise ConnectorError("BD_SCHEDULER_TOKEN_REQUIRED", 403)
                if not args.report_name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json", args.report_name):
                    raise ConnectorError("BD_SCHEDULER_PRIVATE_REPORT_REQUIRED", 422)
                private = ROOT / "artifacts" / "private"
                if private.resolve() != private.absolute():
                    raise ConnectorError("BD_SCHEDULER_PRIVATE_ROOT_REDIRECTED", 422)
                private.mkdir(parents=True, exist_ok=True, mode=0o700)
                fd = os.open(private / args.report_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    execution_started = True
                    try:
                        report = execute_tick(store, tenant, manifest, viewer, **options)
                    except ConnectorError as exc:
                        report = {"status": "BLOCKED", "code": exc.code, "external_data_accessed": None}
                    json.dump(report, stream, ensure_ascii=False, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Keep full cycle/evidence private; only a safe summary on stdout.
                cycle = report.get("cycle")
                report = {k: v for k, v in report.items() if k not in {"plans", "cycle"}}
                if cycle is not None:
                    report["cycle_summary"] = cycle_summary(cycle)
                report["report_name"] = args.report_name
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["status"] in {"SCHEDULER_PLAN_ONLY", "SCHEDULER_LOCAL_READY", "SCHEDULER_COMPLETED",
                                         "SCHEDULER_NO_DUE_SOURCES", "SCHEDULER_STOP_ACKNOWLEDGED"} else 4
    except (ConnectorError, IdentityFailure) as exc:
        code = exc.code
    except FileExistsError:
        code = "BD_SCHEDULER_REPORT_EXISTS"
    except (OSError, ValueError, SQLAlchemyError, ImportError):
        code = "BD_SCHEDULER_LOCAL_ERROR"
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps({"status": "BLOCKED", "code": code,
                      "external_data_accessed": None if execution_started else False}))
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
