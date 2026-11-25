"""Offline closure of a stranded Instagram reservation without a cycle lease."""
from datetime import datetime, timedelta
import json
import re
from uuid import uuid4

from sqlalchemy import insert, select, update

from .connectors import ConnectorError, Platform
from .discovery_history import lock_tenant
from .ingestion import MANUAL_ORPHAN_REASON, cycle_leases, ingestion_runs, stable_id
from .sa_store import domain_events, outbox
from .storage import now_utc


def orphan_reservations(db, tenant):
    if db.execute(select(cycle_leases.c.cycle_key).where(
            cycle_leases.c.tenant_id == tenant)).first():
        return []
    return [{"run_key":r["run_key"], "source_account_id":r["source_account_id"],
             "requested_at":r["requested_at"], "partial_writes_unknown":True}
            for r in db.execute(select(ingestion_runs).where(
                ingestion_runs.c.tenant_id == tenant,
                ingestion_runs.c.platform == Platform.INSTAGRAM.value,
                ingestion_runs.c.status == "reserved")).mappings()]


def recover_orphan_run(engine, principal, run_key, *, stopped):
    """Close exactly one stale reservation; quarantine source, never refund or retry."""
    if principal.role != "admin":
        raise ConnectorError("BD_RECOVERY_ADMIN_REQUIRED", 403)
    if not stopped:
        raise ConnectorError("BD_RECOVERY_STOP_ALL_INGESTION_REQUIRED", 409)
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", run_key):
        raise ConnectorError("BD_RECOVERY_INVALID_RUN", 422)
    tenant = principal.tenant_id
    with engine.begin() as db:
        lock_tenant(db, tenant)
        if db.execute(select(cycle_leases.c.cycle_key).where(
                cycle_leases.c.tenant_id == tenant)).first():
            raise ConnectorError("BD_RECOVERY_INGESTION_ACTIVE", 409)
        runs = db.execute(select(ingestion_runs).where(
            ingestion_runs.c.tenant_id == tenant,
            ingestion_runs.c.status == "reserved")).mappings().all()
        if len(runs) != 1 or runs[0]["run_key"] != run_key or runs[0]["platform"] != Platform.INSTAGRAM.value:
            raise ConnectorError("BD_RECOVERY_ORPHAN_RUN_MISMATCH", 409)
        run = runs[0]
        if datetime.fromisoformat(run["requested_at"]) > now_utc() - timedelta(minutes=30):
            raise ConnectorError("BD_RECOVERY_RUN_TOO_RECENT", 409)
        changed = db.execute(update(ingestion_runs).where(
            ingestion_runs.c.tenant_id == tenant,
            ingestion_runs.c.run_key == run_key,
            ingestion_runs.c.status == "reserved").values(status="failed", reason_code=MANUAL_ORPHAN_REASON))
        if changed.rowcount != 1:
            raise ConnectorError("BD_RECOVERY_RESERVATION_CHANGED", 409)
        payload = {"run_key":run_key, "source_account_id":run["source_account_id"],
                   "reason_code":MANUAL_ORPHAN_REASON, "partial_writes_unknown":True,
                   "source_quarantined":True, "operator_confirmed_ingestion_stopped":True}
        event = db.execute(insert(domain_events).values(event_id=str(uuid4()),
            tenant_id=tenant, aggregate_type="bd_recovery",
            aggregate_id=stable_id("bd-recovery-orphan-run",tenant,run_key),
            aggregate_version=1, event_type="business_discovery.orphan_run_recovered",
            occurred_at=now_utc().isoformat(),
            payload=json.dumps({"actor_id":principal.actor_id, **payload},sort_keys=True)))
        db.execute(insert(outbox).values(seq=event.inserted_primary_key[0],attempts=0,dead_letter=0))
    return {"status":"ORPHAN_RUN_RECOVERED", **payload,
            "quota_reservation_preserved":True,"external_data_accessed":False}
