"""Plan identity-only Meta reads; execution uses standing DEC-018 and authenticated admin."""
import argparse
import getpass
import json
import os
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_batch import BatchManifest
from tapi_gate0.discovery_identity_a6 import execute_identity, plan_identity
from tapi_gate0.discovery_local_db import validate_existing_database_url
from tapi_gate0.identity import IdentityFailure, IdentityStore
from tapi_gate0.sa_store import engine_for


def main(argv=None):
    p = argparse.ArgumentParser(description="A6 identity-only source batches")
    p.add_argument("--manifest", type=Path, required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source", action="append")
    mode.add_argument("--plan-expansion", action="store_true", help="Offline coverage-prioritized candidate shortlist")
    p.add_argument("--max-sources", type=int, default=3)
    p.add_argument("--daily-request-budget", type=int, default=80)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--report", type=Path)
    p.add_argument("--admin", default="admin")
    args = p.parse_args(argv)
    engine = None
    try:
        tenant, viewer = os.environ["TAPI_TENANT_ID"], os.environ["TAPI_META_IG_ID"]
        manifest = BatchManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
        engine = engine_for(validate_existing_database_url(os.environ["TAPI_DATABASE_URL"]))
        if args.plan_expansion:
            if args.execute or args.report:
                raise ConnectorError("BD_EXPANSION_PLAN_ONLY",422)
            from tapi_gate0.discovery_identity_expansion import plan_expansion
            result = plan_expansion(engine,tenant,manifest,viewer,max_sources=args.max_sources,daily_budget=args.daily_request_budget)
        elif not args.execute:
            result, _ = plan_identity(engine, tenant, manifest, viewer, args.source, daily_budget=args.daily_request_budget)
        else:
            root = (Path(__file__).resolve().parents[1] / "artifacts" / "private").resolve()
            if not args.report or not args.report.resolve().is_relative_to(root) or args.report.suffix.lower() != ".json":
                raise ConnectorError("BD_IDENTITY_PRIVATE_REPORT_REQUIRED", 422)
            args.report.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd,"w",encoding="utf-8") as stream:
                identity = IdentityStore(engine)
                session = identity.login(args.admin,getpass.getpass("Admin password: "),tenant)
                principal = identity.resolve(session.access_token)
                try:
                    result = execute_identity(engine,principal,manifest,viewer,args.source,daily_budget=args.daily_request_budget)
                finally:
                    identity.revoke(session.access_token,principal)
                json.dump(result,stream,ensure_ascii=False,indent=2)
        print(json.dumps(result,ensure_ascii=False))
        return 0 if result["status"] in {"PLAN_ONLY_NO_EXTERNAL_READ","IDENTITY_BATCH_COMPLETED","EXPANSION_PLAN_READY","EXPANSION_NO_NEW_CANDIDATES"} else 4
    except (ConnectorError, IdentityFailure) as exc:
        print(json.dumps({"status":"BLOCKED","code":exc.code}))
        return 3
    except (KeyError, OSError, ValueError, ValidationError, SQLAlchemyError):
        print(json.dumps({"status":"BLOCKED","code":"BD_IDENTITY_INVALID_INPUT_OR_DATABASE"}))
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
