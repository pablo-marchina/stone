"""Offline MPE audience signal preview and explicit sampling profile registration."""
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
from tapi_gate0.discovery_corpus_bridge import audience_preview, register_sampling_profiles
from tapi_gate0.discovery_local_db import validate_existing_database_url
from tapi_gate0.identity import IdentityFailure, IdentityStore
from tapi_gate0.sa_store import engine_for

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--report-name", help="Optional new private JSON basename for per-post hashes and spans")
    parser.add_argument("--register-profiles", action="store_true")
    parser.add_argument("--confirm-all-ingestion-stopped", action="store_true")
    parser.add_argument("--admin", default="admin")
    args = parser.parse_args(argv)
    engine = None
    try:
        url = validate_existing_database_url(os.environ.get("TAPI_DATABASE_URL", ""))
        tenant, viewer = os.getenv("TAPI_TENANT_ID", ""), os.getenv("TAPI_META_IG_ID", "")
        if not tenant or not viewer:
            raise ValueError("MISSING_SCOPE")
        manifest = BatchManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
        engine = engine_for(url)
        if args.register_profiles:
            if not args.confirm_all_ingestion_stopped or args.report_name:
                raise ConnectorError("BD_CORPUS_ADMIN_STOP_REQUIRED", 422)
            identity = IdentityStore(engine)
            session = identity.login(args.admin, getpass.getpass("Admin password: "), tenant)
            principal = identity.resolve(session.access_token)
            try:
                result = register_sampling_profiles(engine, principal, manifest, viewer, stopped=True)
            finally:
                identity.revoke(session.access_token, principal)
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
    except (OSError, ValueError, SQLAlchemyError, KeyError, TypeError, ImportError):
        code = "BD_CORPUS_BRIDGE_LOCAL_ERROR"
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps({"status": "BLOCKED", "code": code, "external_data_accessed": False}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
