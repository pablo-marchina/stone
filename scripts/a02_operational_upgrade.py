"""Guarded local SQLite additive 0013, 0014 or 0015 upgrade. Explicit operator action only.

Fresh verified backup first; then BEGIN IMMEDIATE and compare the current
logical snapshot to that backup. Alembic runs on the very same connection.
Any precommit failure rolls back, including transactional SQLite DDL.
Never restores over live, never provisions a grant, no external calls.
"""
from contextlib import closing
from pathlib import Path
import argparse
import json
import os
import re
import sqlite3

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url, URL
from tapi_gate0.sa_store import engine_for
from tapi_gate0.discovery_local_db import validate_existing_database_url
from tapi_gate0.discovery_backup import (
    backup_and_restore_drill, _inventory, _integrity, _readonly, _sha256,
)
from scripts.a00_baseline import check_checkout
from scripts.a02_migration_rehearsal import OLD, NEW, TABLES, schema

ROOT = Path(__file__).resolve().parents[1]


def _require(condition, code):
    if not condition:
        raise ValueError("A02_UPGRADE_"+code)


def _verify(db, before, before_schema, tenant, new, tables):
    _integrity(db)
    after = _inventory(db, tenant)
    _require(after["migration_versions"] == [new], "REVISION_MISMATCH")
    _require(set(after["table_counts"]) == set(before["table_counts"]) | tables,
             "TABLE_MISMATCH")
    _require(all(after["table_content_sha256"][name] == digest
        for name,digest in before["table_content_sha256"].items() if name!="alembic_version"),
        "LEGACY_CONTENT_CHANGED")
    _require([r for r in schema(db) if r[2] not in tables] == before_schema,
             "LEGACY_SCHEMA_CHANGED")
    _require(all(after["table_counts"][t] == 0 for t in tables), "REGISTRY_NOT_EMPTY")
    return after


def upgrade(root, raw_url, tenant, backup_name, *, stopped, lineage=False, jobs=False):
    _require(not (lineage and jobs), "TRANSITION_INVALID")
    old,new,tables=(NEW,"0014_asset_lineage",{"asset_lineage_nodes"}) if lineage else (OLD,NEW,TABLES)
    if jobs:
        old,new,tables="0014_asset_lineage","0015_asset_jobs",{"asset_processing_jobs","asset_processing_attempts"}
    _require(stopped, "ALL_WRITERS_MUST_STOP")
    _require(bool(tenant), "TENANT_REQUIRED")
    _require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.sqlite3",backup_name)),
             "PRIVATE_BASENAME_REQUIRED")
    url = make_url(validate_existing_database_url(raw_url))
    _require(url.drivername == "sqlite", "SQLITE_ONLY")
    source = Path(url.database).absolute()
    _require(source.resolve()==source and source.is_file(), "SOURCE_REDIRECTED")
    private = root/"artifacts"/"private"
    _require(private.resolve()==private.absolute(), "PRIVATE_ROOT_REDIRECTED")
    private.mkdir(parents=True,exist_ok=True,mode=0o700)
    backup = private/backup_name
    with closing(_readonly(source)) as db:
        _require(_inventory(db,tenant)["migration_versions"]==[old], "BASE_REVISION_REQUIRED")
    report = backup_and_restore_drill(source,backup,tenant,stopped=True)
    before = report["inventory"]
    _require(before["migration_versions"]==[old], "BASE_REVISION_REQUIRED")
    with closing(_readonly(backup)) as db:
        before_schema = schema(db)
    _require(_sha256(backup)==report["backup_sha256"], "BACKUP_CHANGED")
    engine = engine_for(URL.create("sqlite",database=str(source)).render_as_string(hide_password=False))
    try:
        with engine.connect() as conn:
            # SQLite DDL is transactional when an explicit BEGIN is issued.
            # Reserve the single writer before comparing and changing schema.
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            db = conn.connection.driver_connection
            try:
                _integrity(db)
                _require(_inventory(db,tenant)==before and schema(db)==before_schema,
                         "LIVE_CHANGED_AFTER_BACKUP")
                cfg = Config(str(root/"alembic.ini"))
                cfg.set_main_option("script_location",str(root/"migrations"))
                cfg.attributes["connection"]=conn
                command.upgrade(cfg,new)
                _require(db.in_transaction, "TRANSACTION_LOST")
                after = _verify(db,before,before_schema,tenant,new,tables)
                _require(_sha256(backup)==report["backup_sha256"], "BACKUP_CHANGED")
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        with closing(_readonly(source)) as db:
            _require(_verify(db,before,before_schema,tenant,new,tables)==after, "POSTCOMMIT_MISMATCH")
    finally:
        engine.dispose()
    return {"status":"A02_OPERATIONAL_MIGRATION_VERIFIED","from_revision":old,"to_revision":new,
        "backup_name":backup_name,"backup_sha256":report["backup_sha256"],
        "backup_restore_verified":True,"existing_tables_preserved":len(before["table_counts"])-1,
        "new_empty_tables":sorted(tables),"legacy_schema_unchanged":True,
        "legacy_logical_contents_match":True,"integrity_check":"ok","foreign_key_check":"ok",
        "operational_database_mutated":True,"real_grants_created":0,"media_enabled":False,
        "live_restore_performed":False,"all_writers_stopped_attested":True,
        "tenant_coverage":after["tenant_coverage"]}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-head",required=True)
    p.add_argument("--backup-name",required=True)
    p.add_argument("--confirm-all-writers-stopped",action="store_true")
    apply=p.add_mutually_exclusive_group(required=True)
    apply.add_argument("--apply-0013",action="store_true")
    apply.add_argument("--apply-0014",action="store_true")
    apply.add_argument("--apply-0015",action="store_true")
    a=p.parse_args(argv)
    try:
        _require(a.apply_0013 or a.apply_0014 or a.apply_0015,"EXPLICIT_APPLY_REQUIRED")
        check_checkout(ROOT,a.expected_head)
        result=upgrade(ROOT,os.environ.get("TAPI_DATABASE_URL",""),os.environ.get("TAPI_TENANT_ID",""),
            a.backup_name,stopped=a.confirm_all_writers_stopped,lineage=a.apply_0014,jobs=a.apply_0015)
        print(json.dumps(result))
        return 0
    except Exception as exc:
        code=str(exc) if str(exc).startswith(("A02_UPGRADE_","BASELINE_","BACKUP_")) else "A02_UPGRADE_LOCAL_ERROR"
        # Do not claim rollback after an unknown postcommit failure.
        print(json.dumps({"status":"BLOCKED","code":code,"exception_type":type(exc).__name__,
            "keep_writers_stopped":True,"manual_revision_inspection_required":True,
            "live_restore_performed":False}))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
