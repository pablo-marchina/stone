"""Reconcile verified identity events into a new private manifest, without grants or network."""
from __future__ import annotations

from datetime import datetime
import json
import re

from sqlalchemy import select

from .business_discovery import IG_ID
from .connectors import ConnectorError
from .discovery_batch import BatchManifest
from .ingestion import stable_id
from .sa_store import domain_events, outbox, tenants

CYCLE = re.compile(r"a6identity-[0-9]{14}-[a-f0-9]{8}\Z")
RESERVATION = "business_discovery.identity_reserved"
RESULT = "business_discovery.identity_result"


def _invalid():
    return ConnectorError("BD_RECONCILE_INVALID_IDENTITY_TRACE", 409)


def _payload(row):
    try:
        value = json.loads(row["payload"])
    except (TypeError, ValueError, RecursionError):
        raise _invalid() from None
    if not isinstance(value, dict):
        raise _invalid()
    return value


def _trace(rows):
    """Validate reservation/result linkage, sequence, versions and outbox."""
    if not 1 <= len(rows) <= 2:
        raise _invalid()
    reserve = rows[0]
    p = _payload(reserve)
    cycle = p.get("cycle_key")
    username = p.get("username")
    viewer = p.get("viewer_ig_id")
    fingerprint = p.get("manifest_sha256")
    try:
        day = datetime.fromisoformat(reserve["occurred_at"]).date().isoformat()
    except (TypeError, ValueError):
        raise _invalid() from None
    if (reserve["event_type"] != RESERVATION or reserve["aggregate_version"] != 1
            or reserve["outbox_seq"] is None or not isinstance(cycle, str) or not CYCLE.fullmatch(cycle)
            or not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", username)
            or not isinstance(viewer, str) or not IG_ID.fullmatch(viewer)
            or not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", fingerprint)
            or not isinstance(p.get("actor_id"), str) or not p["actor_id"]
            or reserve["aggregate_id"] != stable_id("bd-identity-attempt", reserve["tenant_id"], day, username.casefold())):
        raise _invalid()
    # Older A6 events used a private reference hash. They are not accepted by this
    # DEC-018 reconciliation path; no retroactive approval is inferred.
    if p.get("institutional_decision") != "DEC-018" or p.get("operation") != "business_discovery_identity_read":
        raise _invalid()
    if len(rows) == 1:
        return p, None
    result = rows[1]
    r = _payload(result)
    if (result["event_type"] != RESULT or result["aggregate_version"] != 2
            or result["outbox_seq"] is None or result["seq"] <= reserve["seq"]
            or result["occurred_at"] < reserve["occurred_at"]
            or r.get("username") != username or r.get("status") not in {"IDENTIFIED", "BLOCKED"}):
        raise _invalid()
    if r["status"] == "IDENTIFIED":
        ident = r.get("instagram_id")
        if not isinstance(ident, str) or not IG_ID.fullmatch(ident) or ident == viewer:
            raise _invalid()
    elif not isinstance(r.get("code"), str) or not r["code"]:
        raise _invalid()
    return p, r


def reconcile_identities(engine, tenant, viewer, manifest: BatchManifest, cycles):
    """Read-only. Only selected cycles from the exact input manifest may add IDs."""
    if (not IG_ID.fullmatch(viewer) or not 1 <= len(cycles) <= 20
            or len(set(cycles)) != len(cycles) or any(not CYCLE.fullmatch(c) for c in cycles)):
        raise ConnectorError("BD_RECONCILE_INVALID_SELECTION", 422)
    fingerprint = manifest.fingerprint()
    by_handle = {s.username.casefold(): s for s in manifest.sources}
    by_id = {s.expected_ig_id: s.username.casefold() for s in manifest.sources if s.expected_ig_id}
    with engine.connect() as db:
        if not db.execute(select(tenants.c.tenant_id).where(tenants.c.tenant_id == tenant)).first():
            raise ConnectorError("INGESTION_TENANT_NOT_FOUND", 404)
        rows = db.execute(select(domain_events, outbox.c.seq.label("outbox_seq"))
            .outerjoin(outbox, outbox.c.seq == domain_events.c.seq).where(
                domain_events.c.tenant_id == tenant, domain_events.c.aggregate_type == "bd_identity")
            .order_by(domain_events.c.aggregate_id, domain_events.c.aggregate_version)).mappings().all()
    groups = {}
    for row in rows:
        groups.setdefault(row["aggregate_id"], []).append(row)
    observed = {}
    observed_ids = {}
    selected = {}
    found = set()
    skipped = []
    for group in groups.values():
        reserve, result = _trace(group)
        cycle = reserve["cycle_key"]
        handle = reserve["username"].casefold()
        if result and result["status"] == "IDENTIFIED":
            ident = result["instagram_id"]
            if observed.setdefault(handle, ident) != ident or observed_ids.setdefault(ident, handle) != handle:
                raise ConnectorError("BD_RECONCILE_IDENTITY_CONFLICT", 409)
        if cycle not in cycles:
            continue
        found.add(cycle)
        if reserve["manifest_sha256"] != fingerprint or reserve["viewer_ig_id"] != viewer:
            raise ConnectorError("BD_RECONCILE_MANIFEST_OR_VIEWER_MISMATCH", 409)
        source = by_handle.get(handle)
        if not source or source.status not in {"candidate", "review"} or source.audience_intent == "not_mpe_targeted":
            raise ConnectorError("BD_RECONCILE_SOURCE_NOT_ELIGIBLE", 409)
        if not result or result["status"] != "IDENTIFIED":
            skipped.append({"username": source.username, "cycle_key": cycle,
                            "reason": result["code"] if result else "NO_RESULT_RESERVED"})
            continue
        ident = result["instagram_id"]
        if (source.expected_ig_id and source.expected_ig_id != ident) or by_id.get(ident, handle) != handle:
            raise ConnectorError("BD_RECONCILE_IDENTITY_CONFLICT", 409)
        selected[handle] = ident
        by_id[ident] = handle
    if found != set(cycles):
        raise ConnectorError("BD_RECONCILE_CYCLE_NOT_FOUND", 404)
    if not selected:
        raise ConnectorError("BD_RECONCILE_NO_SUCCESSFUL_IDENTITIES", 409)
    sources = []
    changes = []
    for source in manifest.sources:
        ident = selected.get(source.username.casefold())
        if ident and not source.expected_ig_id:
            sources.append(source.model_copy(update={"expected_ig_id": ident}))
            changes.append({"username":source.username, "instagram_id":ident, "status":source.status})
        else:
            sources.append(source)
    # Revalidate the complete model, including global handle/ID uniqueness.
    updated = BatchManifest.model_validate({"schema_version":manifest.schema_version,
        "sources":[s.model_dump() for s in sources]})
    return updated, {"status":"IDENTITY_RECONCILIATION_PLANNED", "manifest_sha256_before":fingerprint,
        "manifest_sha256_after":updated.fingerprint(), "cycles":list(cycles),
        "verified_identities":len(selected), "ids_added":len(changes), "changes":changes,
        "skipped":skipped, "sources":len(updated.sources),
        "approved":sum(s.status == "approved" for s in updated.sources),
        "grants_created":0, "database_written":False, "external_data_accessed":False,
        "scientific_admissions":0}
