"""A03 offline technical expansion capacity snapshot, never acquisition authorization."""
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from sqlalchemy.engine import make_url
from .discovery_backup import _readonly, _integrity
from .discovery_local_db import validate_existing_database_url
from .asset_operational_readiness import REVISION
from .discovery_identity_a6 import RESERVATION

MIN_POSTS=2000
MIN_PROFILES=30
DAILY_BUDGET=80
IDENTITY_LIMIT=10
PAGES_PER_RUN=4
ITEMS_PER_PAGE=10

def _require(ok,code):
    if not ok:
        raise ValueError("A03_CAPACITY_"+code)

def _active(row,now):
    try:
        approved,verified,expires=(datetime.fromisoformat(row[k]) for k in
            ("approved_at","technical_verified_at","expires_at"))
        return row["enabled"]==1 and approved<=verified<=now<expires
    except (ValueError,TypeError):
        return False

def inspect(raw_url,tenant):
    _require(isinstance(tenant,str) and 0<len(tenant)<=128,"TENANT_REQUIRED")
    _require(isinstance(raw_url,str) and raw_url.startswith("sqlite:///"),"SQLITE_ONLY")
    url=make_url(validate_existing_database_url(raw_url))
    _require(url.drivername=="sqlite","SQLITE_ONLY")
    path=Path(url.database).absolute()
    _require(path.resolve()==path and path.is_file(),"SOURCE_REDIRECTED")
    with closing(_readonly(path)) as db:
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        now=datetime.now(timezone.utc)
        day=now.date().isoformat()
        def scalar(sql,args=()):
            return db.execute(sql,args).fetchone()[0]
        _require([r[0] for r in db.execute("SELECT version_num FROM alembic_version")]==[REVISION],"REVISION_REQUIRED")
        _require(scalar("SELECT count(*) FROM tenants WHERE tenant_id=?",(tenant,))==1,"TENANT_UNKNOWN")
        # Integrity helper uses tuple comparisons; temporarily restore tuple rows.
        db.row_factory=None
        _integrity(db)
        db.row_factory=sqlite3.Row
        scope=(tenant,"instagram")
        records=scalar("SELECT count(*) FROM ingestion_records WHERE tenant_id=? AND platform=? AND metadata_only=1",scope)
        unique=scalar("SELECT count(DISTINCT source_item_id) FROM ingestion_records WHERE tenant_id=? AND platform=? AND metadata_only=1",scope)
        profiles=scalar("SELECT count(DISTINCT source_account_id) FROM ingestion_records WHERE tenant_id=? AND platform=? AND metadata_only=1",scope)
        registered=scalar("SELECT count(*) FROM corpus_profiles WHERE tenant_id=? AND platform=?",scope)
        counts=dict(db.execute("SELECT source_account_id,count(*) FROM ingestion_records WHERE tenant_id=? AND platform=? AND metadata_only=1 GROUP BY source_account_id",scope).fetchall())
        grants={r["source_account_id"]:r for r in db.execute("SELECT source_account_id,approved_at,technical_verified_at,expires_at,enabled,approval_reference FROM ingestion_source_grants WHERE tenant_id=? AND platform=?",scope)}
        checkpoints={r["source_account_id"]:r for r in db.execute("SELECT source_account_id,status,approval_reference FROM bd_history_checkpoints WHERE tenant_id=? AND platform=?",scope)}
        active={k for k,v in grants.items() if _active(v,now)}
        frontier=Counter()
        for k in active:
            row=checkpoints.get(k)
            if row is None:
                frontier["no_checkpoint"]+=1
            elif row["approval_reference"]!=grants[k]["approval_reference"]:
                frontier["scope_mismatch"]+=1
            elif row["status"]=="continuation_available":
                frontier["continuation_recorded"]+=1
            elif row["status"]=="frontier_unconfirmed":
                frontier["frontier_unconfirmed"]+=1
            else:
                frontier["unknown_state"]+=1
        identities=scalar("SELECT count(*) FROM domain_events WHERE tenant_id=? AND event_type=? AND occurred_at>=?",(tenant,RESERVATION,day))
        runs=scalar("SELECT count(*) FROM ingestion_runs WHERE tenant_id=? AND platform=? AND requested_at>=?",(*scope,day))
        used=identities+PAGES_PER_RUN*runs
        available=max(0,DAILY_BUDGET-used)
        busy=bool(scalar("SELECT count(*) FROM bd_cycle_leases WHERE tenant_id=?",(tenant,)) or
            scalar("SELECT count(*) FROM ingestion_runs WHERE tenant_id=? AND status='reserved'",(tenant,)))
        missing=max(0,MIN_POSTS-unique)
        missing_profiles=max(0,MIN_PROFILES-profiles)
        # An optimistic mathematical lower bound, not a scheduling forecast.
        # Every new observed profile requires at least one history run;
        # new identities, excluded posts and renewals may increase costs.
        items_per_run=PAGES_PER_RUN*ITEMS_PER_PAGE
        min_runs=max((missing+items_per_run-1)//items_per_run,missing_profiles)
        min_units=min_runs*PAGES_PER_RUN
        return {"schema_version":"a03-technical-capacity.v1","status":"A03_CAPACITY_INSPECTED_PLAN_ONLY",
            "captured_at_utc":now.isoformat(),"utc_day":day,
            "technical_inventory":{"records":records,"unique_media_ids":unique,"profiles_with_records":profiles,
                "cross_source_duplicate_records":records-unique,"registered_profiles":registered,
                "active_technically_verified_metadata_grants":len(active),
                "active_grants_with_records":sum(k in counts for k in active)},
            "active_grant_frontiers":{k:frontier[k] for k in ("no_checkpoint","scope_mismatch","continuation_recorded","frontier_unconfirmed","unknown_state")},
            "technical_collection_reference":{"minimum_posts":MIN_POSTS,"minimum_profiles":MIN_PROFILES,
                "raw_post_gap":missing,"raw_profile_gap":missing_profiles,
                "optimistic_minimum_history_runs":min_runs,
                "optimistic_minimum_reserved_history_units":min_units,
                "assumption":"at most 40 distinct new items per four-page run; excludes identity cost and all losses"},
            "local_daily_reservations":{"identity":identities,"metadata_runs":runs,"conservative_units":used,
                "policy_ceiling":DAILY_BUDGET,"remaining_units":available,
                "identity_slots_remaining":min(max(0,IDENTITY_LIMIT-identities),available),
                "history_run_slots_if_no_new_identity":available//PAGES_PER_RUN,
                "provider_quota_verified":False},
            "tenant_ingestion_active":busy,"scientific_target_assessed":False,
            "scientific_admissions_created":0,"manifest_viewer_and_cursor_validity_assessed":False,
            "external_credentials_loaded":False,"external_calls":0,"database_mutated":False,
            "media_enabled":False,"execution_authorized":False,"global_gates_released":False}
