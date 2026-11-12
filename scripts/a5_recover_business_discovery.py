"""Local administrator recovery. No Meta calls, no automatic retry, no quota reset."""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_recovery import inspect_recovery, recover_orphan_lease, review_failure
from tapi_gate0.identity import IdentityFailure, IdentityStore
from tapi_gate0.sa_store import engine_for


def main(argv=None):
    parser = argparse.ArgumentParser(description="A5 offline recovery (inspection by default)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--review-failure", metavar="RUN_KEY")
    group.add_argument("--recover-orphan-lease", metavar="CYCLE_KEY")
    parser.add_argument("--restart-history", action="store_true")
    parser.add_argument("--confirm-all-ingestion-stopped", action="store_true")
    parser.add_argument("--admin", default="admin")
    args = parser.parse_args(argv)
    mutation = bool(args.review_failure or args.recover_orphan_lease)
    if args.restart_history and not args.review_failure:
        parser.error("--restart-history requires --review-failure")
    if mutation and not args.confirm_all_ingestion_stopped:
        parser.error("stop every ingestion process before recovery; explicit confirmation required")
    url, tenant = os.getenv("TAPI_DATABASE_URL", ""), os.getenv("TAPI_TENANT_ID", "")
    if not tenant or not url.startswith(("sqlite:///", "postgresql+psycopg://")) or (
            url.startswith("sqlite:///") and not Path(url.removeprefix("sqlite:///")).is_file()):
        print(json.dumps({"status":"BLOCKED", "code":"EXISTING_DATABASE_AND_TENANT_REQUIRED"}))
        return 2
    engine = None
    try:
        engine = engine_for(url)
        if not mutation:
            report = inspect_recovery(engine, tenant)
        else:
            identity = IdentityStore(engine)
            session = identity.login(args.admin, getpass.getpass("Admin password: "), tenant)
            principal = identity.resolve(session.access_token)
            try:
                if args.review_failure:
                    report = review_failure(engine, principal, args.review_failure,
                        stopped=True, restart_history=args.restart_history)
                else:
                    report = recover_orphan_lease(engine, principal, args.recover_orphan_lease, stopped=True)
            finally:
                identity.revoke(session.access_token, principal)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (ConnectorError, IdentityFailure) as exc:
        print(json.dumps({"status":"BLOCKED", "code":exc.code, "external_data_accessed":False}))
        return 3
    except (SQLAlchemyError, OSError, ValueError, ImportError):
        print(json.dumps({"status":"BLOCKED", "code":"BD_RECOVERY_DATABASE_ERROR", "external_data_accessed":False}))
        return 3
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
