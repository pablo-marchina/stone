"""Private Business Discovery history checkpoints and fail-closed cycle leases."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json

from sqlalchemy import Column, ForeignKeyConstraint, Integer, String, Table, Text, delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from .business_discovery import CURSOR
from .connectors import ConnectorError, Platform
from .ingestion import source_grants
from .sa_store import metadata
from .storage import now_utc

history_checkpoints = Table("bd_history_checkpoints", metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("source_account_id", String(128), primary_key=True),
    Column("platform", String(32), nullable=False),
    Column("viewer_ig_id", String(32), nullable=False),
    Column("approval_reference", String(512), nullable=False),
    Column("next_cursor", String(512)),
    Column("cursor_hashes", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("pages_examined", Integer, nullable=False),
    Column("last_run_key", String(128), nullable=False),
    Column("updated_at", String(40), nullable=False),
    ForeignKeyConstraint(["tenant_id", "platform", "source_account_id"],
        ["ingestion_source_grants.tenant_id", "ingestion_source_grants.platform",
         "ingestion_source_grants.source_account_id"]))

cycle_leases = Table("bd_cycle_leases", metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("cycle_key", String(80), nullable=False),
    Column("started_at", String(40), nullable=False),
    ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]))


def read_checkpoint(db, tenant: str, source: str):
    row = db.execute(select(history_checkpoints).where(
        history_checkpoints.c.tenant_id == tenant,
        history_checkpoints.c.source_account_id == source)).mappings().first()
    return dict(row) if row else None


def checkpoint_start(db, tenant: str, source: str, viewer: str, approval: str):
    prior = read_checkpoint(db, tenant, source)
    if prior is None:
        return None
    if prior["viewer_ig_id"] != viewer or prior["approval_reference"] != approval:
        raise ConnectorError("BD_HISTORY_SCOPE_CHANGED", 403)
    if prior["status"] != "continuation_available":
        raise ConnectorError("BD_HISTORY_FRONTIER_UNCONFIRMED", 409)
    if not isinstance(prior["next_cursor"], str) or not CURSOR.fullmatch(prior["next_cursor"]):
        raise ConnectorError("BD_HISTORY_INVALID_CHECKPOINT", 409)
    return prior


def advance_checkpoint(db, *, tenant, source, viewer, approval, run_key,
                       prior, next_cursor, traversed, pages):
    """Called in the transaction that marks the reserved run completed."""
    current = read_checkpoint(db, tenant, source)
    if current != prior:
        raise ConnectorError("BD_HISTORY_CHECKPOINT_CHANGED", 409)
    # Serialize against source revocation before advancing a private cursor.
    locked = db.execute(update(source_grants).where(
        source_grants.c.tenant_id == tenant,
        source_grants.c.platform == Platform.INSTAGRAM.value,
        source_grants.c.source_account_id == source,
        source_grants.c.approval_reference == approval,
        source_grants.c.enabled == 1,
    ).values(enabled=source_grants.c.enabled))
    if locked.rowcount != 1:
        raise ConnectorError("BD_HISTORY_GRANT_CHANGED", 403)
    from datetime import datetime
    expiry = db.execute(select(source_grants.c.expires_at).where(
        source_grants.c.tenant_id == tenant,
        source_grants.c.platform == Platform.INSTAGRAM.value,
        source_grants.c.source_account_id == source)).scalar_one()
    if datetime.fromisoformat(expiry) <= now_utc():
        raise ConnectorError("BD_HISTORY_GRANT_EXPIRED", 403)
    hashes = json.loads(prior["cursor_hashes"]) if prior else []
    if not isinstance(hashes, list) or len(hashes) > 16384:
        raise ConnectorError("BD_HISTORY_INVALID_CURSOR_LEDGER", 409)
    new_hashes = [hashlib.sha256(cursor.encode()).hexdigest() for cursor in traversed]
    if len(new_hashes) != len(set(new_hashes)) or set(hashes).intersection(new_hashes):
        raise ConnectorError("BD_HISTORY_CURSOR_CYCLE", 409)
    if len(hashes) + len(new_hashes) > 16384:
        raise ConnectorError("BD_HISTORY_CURSOR_LEDGER_LIMIT", 409)
    values = dict(platform=Platform.INSTAGRAM.value, viewer_ig_id=viewer,
        approval_reference=approval, next_cursor=next_cursor,
        cursor_hashes=json.dumps(hashes + new_hashes),
        status="continuation_available" if next_cursor else "frontier_unconfirmed",
        pages_examined=(prior["pages_examined"] if prior else 0) + pages,
        last_run_key=run_key, updated_at=now_utc().isoformat())
    if prior is None:
        db.execute(insert(history_checkpoints).values(tenant_id=tenant,
            source_account_id=source, **values))
    else:
        db.execute(update(history_checkpoints).where(history_checkpoints.c.tenant_id == tenant,
            history_checkpoints.c.source_account_id == source).values(**values))


@contextmanager
def cycle_lease(engine, tenant: str, key: str):
    """One A5 cycle per tenant. A crash leaves a lease for operator recovery."""
    try:
        with engine.begin() as db:
            db.execute(insert(cycle_leases).values(tenant_id=tenant,
                cycle_key=key, started_at=now_utc().isoformat()))
    except IntegrityError as exc:
        raise ConnectorError("BD_CYCLE_LEASE_UNAVAILABLE", 409) from exc
    try:
        yield
    finally:
        with engine.begin() as db:
            db.execute(delete(cycle_leases).where(cycle_leases.c.tenant_id == tenant,
                cycle_leases.c.cycle_key == key))
