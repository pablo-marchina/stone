"""A02.8/9 local readiness snapshot: read only, never authorization.

No key loading, grant creation, network, media read, queue claim or mutation.
The trusted local operator supplies the configured tenant and database.
Counts of rows are not proof of current, signed, asset-specific rights.
"""
from contextlib import closing
from datetime import datetime, timezone
import re
from pathlib import Path

from sqlalchemy.engine import make_url
from .discovery_backup import _readonly, _integrity
from .discovery_local_db import validate_existing_database_url
from .asset_jobs import (MAX_PENDING, MAX_DAILY_TENANT_ATTEMPTS,
    MAX_DAILY_GLOBAL_ATTEMPTS, MAX_CONCURRENT)
from .asset_derived_payloads import MAX_TENANT_BYTES, MAX_GLOBAL_BYTES

REVISION="0016_asset_derived_payloads"
TABLES=("asset_rights_authorities","asset_rights_revocations","asset_rights_grants",
        "asset_lineage_nodes","asset_processing_jobs","asset_processing_attempts",
        "asset_derived_payloads")
STATES=("queued","running","cancel_requested","completed","failed","canceled")


def _require(ok,code):
    if not ok:
        raise ValueError("A02_READINESS_"+code)


def inspect(raw_url,tenant):
    _require(type(tenant) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}",tenant),
             "TENANT_REQUIRED")
    # Reject remote URLs before any connection, even if a driver is installed.
    _require(type(raw_url) is str and raw_url.startswith("sqlite:///"),"SQLITE_ONLY")
    url=make_url(validate_existing_database_url(raw_url))
    _require(url.drivername=="sqlite","SQLITE_ONLY")
    path=Path(url.database).absolute()
    _require(path.resolve()==path and path.is_file(),"SOURCE_REDIRECTED")
    with closing(_readonly(path)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        # One read snapshot, no lease reconciliation (that is a writer).
        now=datetime.now(timezone.utc)
        _require(db.execute("SELECT version_num FROM alembic_version").fetchall()==[(REVISION,)],
                 "REVISION_REQUIRED")
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        _require(set(TABLES)|{"tenants","bd_cycle_leases","ingestion_runs"}<=tables,"SCHEMA_REQUIRED")
        _require(db.execute("SELECT 1 FROM tenants WHERE tenant_id=?",(tenant,)).fetchone() is not None,
                 "TENANT_UNKNOWN")
        _integrity(db)
        def count(sql,params=()):
            return db.execute(sql,params).fetchone()[0]
        # All table names below are fixed source constants, not input.
        counts={t:count("SELECT count(*) FROM "+t+" WHERE tenant_id=?",(tenant,)) for t in TABLES}
        states={k:0 for k in STATES}
        for state,n in db.execute("SELECT state,count(*) FROM asset_processing_jobs WHERE tenant_id=? GROUP BY state",(tenant,)):
            _require(state in states,"JOB_STATE")
            states[state]=n
        lineage={k:0 for k in ("asset_active","asset_invalidated","derived_active","derived_invalidated")}
        for kind,state,n in db.execute("SELECT kind,state,count(*) FROM asset_lineage_nodes WHERE tenant_id=? GROUP BY kind,state",(tenant,)):
            key=kind+"_"+state
            _require(key in lineage,"LINEAGE_STATE")
            lineage[key]=n
        ms=int(now.timestamp()*1000)
        day=int(now.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()*1000)
        active=count("SELECT count(*) FROM asset_processing_jobs WHERE state IN ('running','cancel_requested')")
        expired=count("SELECT count(*) FROM asset_processing_jobs WHERE tenant_id=? AND state IN ('running','cancel_requested') AND (lease_ms<=? OR deadline_ms<=?)",(tenant,ms,ms))
        pending=count("SELECT count(*) FROM asset_processing_jobs WHERE state IN ('queued','running','cancel_requested') AND tenant_id=?",(tenant,))
        attempts_tenant=count("SELECT count(*) FROM asset_processing_attempts WHERE tenant_id=? AND started_ms>=?",(tenant,day))
        attempts_global=count("SELECT count(*) FROM asset_processing_attempts WHERE started_ms>=?",(day,))
        def payload_bytes(where,params=()):
            return count("SELECT coalesce(sum(length(envelope)),0) FROM asset_derived_payloads WHERE envelope IS NOT NULL"+where,params)
        bytes_tenant=payload_bytes(" AND tenant_id=?",(tenant,))
        bytes_global=payload_bytes("")
        ingestion_busy=bool(count("SELECT count(*) FROM bd_cycle_leases") or
            count("SELECT count(*) FROM ingestion_runs WHERE status='reserved'"))
        blockers=["INDEPENDENT_TRUST_AND_EXACT_ASSET_PERMISSIONS_NOT_EVALUATED",
                  "VAULT_AND_PAYLOAD_KEYS_NOT_EVALUATED","REAL_MEDIA_ADAPTER_NOT_ENABLED"]
        if not counts["asset_rights_authorities"]:
            blockers.append("NO_TENANT_AUTHORITY_ROWS")
        if not counts["asset_rights_grants"]:
            blockers.append("NO_TENANT_ASSET_GRANT_ROWS")
        if not lineage["asset_active"]:
            blockers.append("NO_ACTIVE_RETAINED_ASSET_REFERENCES")
        if active:
            blockers.append("ACTIVE_GLOBAL_LEASES_REQUIRE_RECONCILIATION")
        if ingestion_busy:
            blockers.append("ACTIVE_INGESTION")
        if pending>=MAX_PENDING:
            blockers.append("TENANT_PENDING_LIMIT")
        if attempts_tenant>=MAX_DAILY_TENANT_ATTEMPTS or attempts_global>=MAX_DAILY_GLOBAL_ATTEMPTS:
            blockers.append("DAILY_ATTEMPT_LIMIT")
        if bytes_tenant>=MAX_TENANT_BYTES or bytes_global>=MAX_GLOBAL_BYTES:
            blockers.append("DERIVED_PAYLOAD_STORAGE_LIMIT")
        return {"schema_version":"a02-operational-readiness.v1",
            "status":"A02_READINESS_INSPECTED_MEDIA_BLOCKED","revision":REVISION,
            "captured_at_utc":now.isoformat(),"tenant_registry_counts":counts,
            "tenant_lineage_counts":lineage,"tenant_job_states":states,
            "tenant_expired_active_leases":expired,"global_active_leases":active,
            "global_concurrency_limit":MAX_CONCURRENT,"active_ingestion":ingestion_busy,
            "tenant_pending":pending,"tenant_pending_limit":MAX_PENDING,
            "daily_attempts":{"tenant":attempts_tenant,"global":attempts_global,
                "tenant_limit":MAX_DAILY_TENANT_ATTEMPTS,"global_limit":MAX_DAILY_GLOBAL_ATTEMPTS,
                "window":"utc_calendar_day"},
            "encrypted_payload_bytes":{"tenant":bytes_tenant,"global":bytes_global,
                "tenant_limit":MAX_TENANT_BYTES,"global_limit":MAX_GLOBAL_BYTES,
                "includes_envelope_overhead":True},
            "integrity_check":"ok","foreign_key_check":"ok","blockers":blockers,
            "authorization_evaluated":False,"media_enabled":False,
            "database_mutated":False,"grants_created":0,"keys_loaded":False,
            "jobs_claimed":0,"external_calls":0,"scientific_evidence":False,
            "canonical_rubric":False,"global_gates_released":False}
