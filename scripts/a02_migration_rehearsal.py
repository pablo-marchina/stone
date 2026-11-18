"""Rehearse one reviewed additive migration on a pinned private backup.

No access to the live database URL, no restore over original, no real
authorities or grants. Report only aggregate checks.
"""
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile

from sqlalchemy.engine import URL
from tapi_gate0.discovery_backup import _inventory, _integrity, _readonly, _copy, _sha256
from scripts.a00_baseline import child_environment

ROOT=Path(__file__).resolve().parents[1]
OLD="0012_bd_history_checkpoints"
NEW="0013_asset_rights_registry"
TABLES={"asset_rights_authorities","asset_rights_revocations","asset_rights_grants"}


def schema(db):
    return db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()


def rehearsal(root,name,digest,tenant,*,lineage=False,jobs=False):
    if lineage and jobs:
        raise ValueError("A02_MIGRATION_TRANSITION_INVALID")
    old,new,tables=(NEW,"0014_asset_lineage",{"asset_lineage_nodes"}) if lineage else (OLD,NEW,TABLES)
    if jobs:
        old,new,tables="0014_asset_lineage","0015_asset_jobs",{"asset_processing_jobs","asset_processing_attempts"}
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.sqlite3",name) or not re.fullmatch(r"[a-f0-9]{64}",digest):
        raise ValueError("A02_MIGRATION_PIN_INVALID")
    private=root/"artifacts"/"private"
    path=private/name
    if path.resolve()!=path.absolute() or not path.is_file() or _sha256(path)!=digest:
        raise ValueError("A02_MIGRATION_BACKUP_MISMATCH")
    with tempfile.TemporaryDirectory(prefix="rights-migration-",dir=private) as tmp:
        target=Path(tmp)/"copy.sqlite3"
        with closing(_readonly(path)) as original:
            original.execute("BEGIN")
            _integrity(original)
            before=_inventory(original,tenant)
            before_schema=schema(original)
            if before["migration_versions"]!=[old]:
                raise ValueError("A02_MIGRATION_BASE_REQUIRED")
            with closing(sqlite3.connect(target)) as copy:
                _copy(original,copy)
        env=child_environment(root,os.environ)
        env["TAPI_DATABASE_URL"]=URL.create("sqlite",database=str(target)).render_as_string(hide_password=False)
        command=[sys.executable,"-m","alembic","-c",str(root/"alembic.ini")]
        result=subprocess.run(command+["upgrade",new],cwd=root,env=env,
            stdin=subprocess.DEVNULL,capture_output=True,timeout=120,check=False)
        if result.returncode:
            raise ValueError("A02_MIGRATION_UPGRADE_FAILED")
        with closing(_readonly(target)) as db:
            _integrity(db)
            after=_inventory(db,tenant)
            if after["migration_versions"]!=[new]:
                raise ValueError("A02_MIGRATION_VERSION_MISMATCH")
            if set(after["table_counts"])!=set(before["table_counts"])|tables:
                raise ValueError("A02_MIGRATION_TABLE_MISMATCH")
            for table,d in before["table_content_sha256"].items():
                if table!="alembic_version" and after["table_content_sha256"][table]!=d:
                    raise ValueError("A02_MIGRATION_CONTENT_CHANGED")
            if [r for r in schema(db) if r[2] not in tables]!=before_schema:
                raise ValueError("A02_MIGRATION_LEGACY_SCHEMA_CHANGED")
            if any(after["table_counts"][t]!=0 for t in tables):
                raise ValueError("A02_MIGRATION_REGISTRY_NOT_EMPTY")
        # Empty-only downgrade must restore original logical state.
        result=subprocess.run(command+["downgrade",old],cwd=root,env=env,
            stdin=subprocess.DEVNULL,capture_output=True,timeout=120,check=False)
        if result.returncode:
            raise ValueError("A02_MIGRATION_DOWNGRADE_FAILED")
        with closing(_readonly(target)) as db:
            _integrity(db)
            if _inventory(db,tenant)!=before:
                raise ValueError("A02_MIGRATION_DOWNGRADE_MISMATCH")
        if _sha256(path)!=digest:
            raise ValueError("A02_MIGRATION_BACKUP_CHANGED")
    return {"status":"A02_MIGRATION_REHEARSAL_VERIFIED","backup_name":name,
        "backup_sha256":digest,"from_revision":old,"to_revision":new,
        "existing_tables_preserved":len(before["table_counts"])-1,
        "new_empty_tables":sorted(tables),"legacy_schema_unchanged":True,
        "upgrade_integrity_verified":True,"empty_downgrade_verified":True,
        "backup_unchanged":True,"operational_database_accessed":False,
        "operational_database_mutated":False,"real_grants_created":0,"media_enabled":False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup-name",required=True)
    p.add_argument("--backup-sha256",required=True)
    p.add_argument("--tenant",required=True)
    modes=p.add_mutually_exclusive_group()
    modes.add_argument("--lineage",action="store_true",help="Rehearse 0013 to 0014")
    modes.add_argument("--jobs",action="store_true",help="Rehearse 0014 to 0015")
    a=p.parse_args(argv)
    try:
        result=rehearsal(ROOT,a.backup_name,a.backup_sha256,a.tenant,lineage=a.lineage,jobs=a.jobs)
        print(json.dumps(result))
        return 0
    except (ValueError,OSError,sqlite3.Error,subprocess.SubprocessError) as exc:
        code=str(exc) if str(exc).startswith("A02_MIGRATION_") else "A02_MIGRATION_LOCAL_ERROR"
        print(json.dumps({"status":"BLOCKED","code":code,"exception_type":type(exc).__name__}))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
