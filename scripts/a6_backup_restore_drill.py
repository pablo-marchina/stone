"""Explicit offline SQLite backup + disposable restore. Never restores live DB."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sqlite3

from sqlalchemy.engine import make_url
from tapi_gate0.discovery_backup import BackupError, backup_and_restore_drill
from tapi_gate0.discovery_local_db import validate_existing_database_url

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-name", required=True, help="New .sqlite3 basename in artifacts/private")
    parser.add_argument("--confirm-all-writers-stopped", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.confirm_all_writers_stopped:
            raise BackupError("BACKUP_ALL_WRITERS_MUST_STOP")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.sqlite3", args.output_name):
            raise BackupError("BACKUP_PRIVATE_BASENAME_REQUIRED")
        raw = validate_existing_database_url(os.environ.get("TAPI_DATABASE_URL", ""))
        url = make_url(raw)
        if url.drivername != "sqlite":
            raise BackupError("BACKUP_SQLITE_ONLY")
        tenant = os.environ.get("TAPI_TENANT_ID", "")
        private = ROOT / "artifacts" / "private"
        # No symlink/junction redirect of the private root outside checkout.
        if private.resolve() != private.absolute():
            raise BackupError("BACKUP_PRIVATE_ROOT_REDIRECTED")
        private.mkdir(parents=True, exist_ok=True, mode=0o700)
        report = backup_and_restore_drill(Path(url.database), private / args.output_name,
                                          tenant, stopped=True)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except BackupError as exc:
        code = str(exc)
    except FileExistsError:
        code = "BACKUP_TARGET_EXISTS"
    except (OSError, sqlite3.Error, ValueError):
        code = "BACKUP_LOCAL_DATABASE_ERROR"
    print(json.dumps({"status": "BLOCKED", "code": code, "external_data_accessed": False}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
