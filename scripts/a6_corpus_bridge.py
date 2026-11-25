"""Offline MPE audience signal preview and explicit sampling profile registration."""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_batch import BatchManifest
from tapi_gate0.discovery_corpus_bridge import audience_preview, register_sampling_profiles
from tapi_gate0.discovery_local_db import validate_existing_database_url
from tapi_gate0.identity import IdentityFailure, IdentityStore, users, memberships, utcnow
from datetime import datetime
from tapi_gate0.sa_store import engine_for
from tapi_gate0.local_admin_selection import select_admin_login
from tapi_gate0.discovery_caption_research import plan_research, provision_research, revoke_research

ROOT = Path(__file__).resolve().parents[1]


def inspect_local_admins(engine, tenant):
    """OS-operator CLI only; never select passwords, tokens or hashes."""
    with engine.connect() as db:
        rows = db.execute(select(users.c.login, users.c.disabled, users.c.locked_until)
            .join(memberships, memberships.c.user_id == users.c.user_id)
            .where(memberships.c.tenant_id == tenant, memberships.c.role == "admin")
            .order_by(users.c.login)).mappings().all()
    now = utcnow()
    return {"status": "LOCAL_ADMIN_INSPECTION", "admins": [
        {"login": row["login"], "disabled": bool(row["disabled"]),
         "temporarily_locked": bool(row["locked_until"] and
             datetime.fromisoformat(row["locked_until"]) > now)} for row in rows],
        "database_mutated": False, "external_data_accessed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--report-name", help="Optional new private JSON basename for per-post hashes and spans")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--register-profiles", action="store_true")
    group.add_argument("--plan-contexts", action="store_true")
    group.add_argument("--register-contexts", action="store_true")
    group.add_argument("--revoke-context", metavar="USERNAME")
    group.add_argument("--inspect-local-admins", action="store_true", help="OS operator only; show login and lock state, no secrets")
    parser.add_argument("--confirm-all-ingestion-stopped", action="store_true")
    parser.add_argument("--admin", help="Existing local admin login; auto-detect unique enabled admin if omitted")
    args = parser.parse_args(argv)
    engine = None
    try:
        url = validate_existing_database_url(os.environ.get("TAPI_DATABASE_URL", ""))
        tenant, viewer = os.getenv("TAPI_TENANT_ID", ""), os.getenv("TAPI_META_IG_ID", "")
        if not tenant:
            raise ValueError("MISSING_SCOPE")
        engine = engine_for(url)
        if args.inspect_local_admins:
            if engine.dialect.name != "sqlite" or args.report_name or args.manifest:
                raise ConnectorError("BD_CORPUS_LOCAL_SQLITE_INSPECTION_ONLY", 422)
            print(json.dumps(inspect_local_admins(engine, tenant), ensure_ascii=False))
            return 0
        if not viewer or args.manifest is None:
            raise ValueError("MISSING_SCOPE")
        manifest = BatchManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
        if args.plan_contexts:
            print(json.dumps(plan_research(engine, tenant, manifest, viewer), ensure_ascii=False))
            return 0
        if args.register_profiles or args.register_contexts or args.revoke_context:
            if not args.confirm_all_ingestion_stopped or args.report_name:
                raise ConnectorError("BD_CORPUS_ADMIN_STOP_REQUIRED", 422)
            identity = IdentityStore(engine)
            login = args.admin
            if login is None:
                if engine.dialect.name != "sqlite":
                    raise ConnectorError("LOCAL_ADMIN_EXPLICIT_LOGIN_REQUIRED", 422)
                try:
                    login = select_admin_login(inspect_local_admins(engine, tenant)["admins"])
                except ValueError as exc:
                    raise ConnectorError(str(exc), 403) from exc
            if not login or len(login) > 128:
                raise ConnectorError("BD_CORPUS_ADMIN_LOGIN_REQUIRED", 422)
            session = identity.login(login, getpass.getpass("Admin password: "), tenant)
            principal = identity.resolve(session.access_token)
            try:
                if args.register_contexts:
                    result = provision_research(engine, principal, manifest, viewer, stopped=True)
                elif args.revoke_context:
                    result = revoke_research(engine, principal, manifest, viewer, args.revoke_context, stopped=True)
                else:
                    result = register_sampling_profiles(engine, principal, manifest, viewer, stopped=True)
            finally:
                identity.revoke(session.access_token, principal)
            result["operation_mutated"] = result["database_mutated"]
            if args.register_profiles:
                result["sampling_registry_mutated"] = result["database_mutated"]
            result["identity_session_written"] = True
            result["database_mutated"] = True
        else:
            result = audience_preview(engine, tenant, manifest, viewer,
                                      include_private_evidence=bool(args.report_name))
            if args.report_name:
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json", args.report_name):
                    raise ConnectorError("BD_CORPUS_PRIVATE_REPORT_REQUIRED", 422)
                private = ROOT / "artifacts" / "private"
                if private.resolve() != private.absolute():
                    raise ConnectorError("BD_CORPUS_PRIVATE_ROOT_REDIRECTED", 422)
                private.mkdir(parents=True, exist_ok=True, mode=0o700)
                fd = os.open(private / args.report_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(result, stream, ensure_ascii=False, indent=2)
                result.pop("private_evidence")
                result["report_name"] = args.report_name
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ConnectorError, IdentityFailure) as exc:
        code = exc.code
    except FileExistsError:
        code = "BD_CORPUS_REPORT_EXISTS"
    except (OSError, ValueError, SQLAlchemyError, KeyError, TypeError, ImportError, EOFError):
        code = "BD_CORPUS_BRIDGE_LOCAL_ERROR"
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps({"status": "BLOCKED", "code": code, "external_data_accessed": False}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
