"""Trusted-host maintenance ticks for A02. No scheduler, media admission or API.

Logical reconciliation is atomic per tenant. Physical cleanup is separately
attested, bounded and resumable, not an atomic filesystem/DB transaction.
The independent authority pins and canonical vault must come from the host.
"""
from hashlib import sha256
import re

from sqlalchemy import select, func
from .asset_rights import AssetRightsDenied, TrustedAuthority
from .asset_rights_registry import _scope, _load_head
from .asset_lineage_index import _load
from .asset_lineage import RetainedAssetRef, DerivedArtifactRef
from .asset_jobs import AssetJobQueue, jobs, ACTIVE, MAX_PENDING, _spec, _transition, _release, _ms
from .asset_derived_payloads import DerivedPayloadStore, payloads
from .asset_indexed_vault import IndexedAssetVault
from .asset_discard import discard_invalidated
from .sa_store import tenants, domain_events

VERSION = "asset-reconciliation.v1"
MAX_SCOPES = 32
MAX_BATCH = 100


def _fail(code):
    raise AssetRightsDenied("ASSET_RECONCILE_" + code)


def _host(queue, tenant):
    if not isinstance(queue, AssetJobQueue):
        _fail("QUEUE_REQUIRED")
    if type(tenant) is not str or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", tenant):
        _fail("TENANT_INVALID")


def _known(db, tenant):
    if db.scalar(select(tenants.c.tenant_id).where(tenants.c.tenant_id == tenant)) is None:
        _fail("TENANT_UNKNOWN")


def _signed_roots(db, tenant, assets, scopes, now):
    """Only explicit, current, independently pinned scopes can tombstone roots."""
    if type(scopes) not in (tuple, list) or len(scopes) > MAX_SCOPES:
        _fail("SCOPES_INVALID")
    covered, revoked, seen = set(), set(), set()
    for pair in scopes:
        if (type(pair) not in (tuple, list) or len(pair) != 2
                or not isinstance(pair[0], TrustedAuthority) or type(pair[1]) is not str):
            _fail("SCOPES_INVALID")
        anchor, platform = pair
        key = _scope(anchor, tenant, platform)
        identity = (anchor.issuer_id, platform)
        if identity in seen:
            _fail("DUPLICATE_SCOPE")
        seen.add(identity)
        _, state = _load_head(db, key, anchor)
        rv = state.claims
        if not rv.issued_at <= now < rv.valid_until:
            _fail("REVOCATION_STALE")
        sources = {(s.tenant_id, s.platform, s.source_account_id) for s in rv.revoked_sources}
        digest = sha256(anchor.public_key).hexdigest()
        for root in assets:
            if (root.issuer_id, root.target.platform, root.issuer_key_sha256) != (*identity, digest):
                continue
            covered.add(root.object_id)
            if (root.grant_id in rv.revoked_grant_ids or root.target.asset_id in rv.revoked_asset_ids
                    or (tenant, platform, root.target.source_account_id) in sources):
                revoked.add(root.object_id)
    return covered, revoked


def reconcile_tenant(queue, tenant, *, scopes=()):
    """Atomic signed revocation + TTL + job reconciliation, no byte access.

    Missing scopes are NOT revoked. Explicit stale/mismatched scope aborts the
    whole tick; the caller can request an independent TTL-only tick. Report
    coverage, not an assertion that all authorities were supplied. Cancel an
    invalidated active job before expiry so it cannot be requeued for retry.
    Fencing does not kill workers, and no cancellation is acknowledged here.
    """
    _host(queue, tenant)
    with queue._transaction() as (db, now):
        _known(db, tenant)
        assets, derived, by_id = _load(db, tenant)
        covered, revoked = _signed_roots(db, tenant, assets, scopes, now)
        plan = queue.index._invalidate(db, tenant, assets, derived, by_id,
                                      object_ids=revoked, now=now)
        invalid = set(plan["affected_objects"])
        rows = db.execute(select(jobs).where(jobs.c.tenant_id == tenant,
            jobs.c.state.in_(("queued", "running"))).order_by(jobs.c.job_id)
            .limit(MAX_PENDING+1)).mappings().all()
        if len(rows) > MAX_PENDING:
            _fail("QUEUE_LIMIT")
        canceled, requested = 0, 0
        for row in rows:
            spec = _spec(row)
            if spec.object_id not in by_id:
                _fail("INPUT_NOT_FOUND")
            if spec.object_id not in invalid:
                continue
            if row["state"] == "running":
                changes = {"state": "cancel_requested", "reason": "input_invalidated"}
                requested += 1
            else:
                changes = _release("canceled", "input_invalidated", _ms(now))
                canceled += 1
            _transition(db, dict(row), now, "input_invalidated", **changes)
        expired = db.scalar(select(func.count()).select_from(jobs).where(
            jobs.c.tenant_id == tenant, jobs.c.state.in_(ACTIVE), jobs.c.lease_ms <= _ms(now)))
        queue._expire(db, now, tenant)
        pending = db.scalar(select(func.count()).select_from(jobs).where(
            jobs.c.tenant_id == tenant, jobs.c.state == "cancel_requested"))
        return {"status": "RECONCILED", "policy_version": VERSION,
                "scopes_verified": len(scopes), "roots_covered": len(covered),
                "roots_uncovered": len(assets)-len(covered), "signed_revoked_roots": len(revoked),
                "newly_invalidated": len(plan["newly_invalidated"]),
                "affected_objects": len(plan["affected_objects"]),
                "affected_artifacts": len(plan["affected_artifacts"]),
                "queued_canceled": canceled, "running_cancel_requested": requested,
                "expired_leases_reconciled": expired, "cancel_requested_pending": pending,
                "filesystem_mutated": False, "workers_stopped_verified": False,
                "media_enabled": False}


def cleanup_tenant(queue, vault, store, tenant, *, all_io_stopped=False, limit=MAX_BATCH):
    """Cleanup one bounded batch of already-tombstoned data, never decrypt.

    Trusted operator must stop ALL writers/readers/workers and attest correct
    canonical vault root for the tenant. A lease timeout is not that proof.
    Global active leases also block cleanup. Each existing purge/discard
    primitive commits independently; on error earlier actions may be durable.
    Retry selects remaining work, no rollback/recreation of deleted envelopes.
    Previously recorded root receipts are skipped; this is not a filesystem
    audit for reappeared files, orphan staging, backups, WAL or SSD blocks.
    """
    _host(queue, tenant)
    if all_io_stopped is not True:
        _fail("STOPPED_IO_REQUIRED")
    if type(limit) is not int or not 1 <= limit <= MAX_BATCH:
        _fail("BATCH_INVALID")
    if (not isinstance(vault, IndexedAssetVault) or vault._index.engine is not queue.index.engine
            or not isinstance(store, DerivedPayloadStore) or store.queue is not queue):
        _fail("HOST_MISMATCH")
    with queue._transaction() as (db, now):
        _known(db, tenant)
        if db.scalar(select(func.count()).select_from(jobs).where(jobs.c.state.in_(ACTIVE))):
            _fail("ACTIVE_LEASES")
        _, _, by_id = _load(db, tenant)
        ids = db.scalars(select(payloads.c.artifact_id).where(payloads.c.tenant_id == tenant,
            payloads.c.purged_at.is_(None)).order_by(payloads.c.artifact_id)).all()
        derived = []
        for ident in ids:
            if ident not in by_id or not isinstance(by_id[ident][1], DerivedArtifactRef):
                _fail("PAYLOAD_LINEAGE_MISMATCH")
            if by_id[ident][0]["state"] == "invalidated":
                derived.append(ident)
        recorded = set(db.scalars(select(domain_events.c.aggregate_id).where(
            domain_events.c.tenant_id == tenant, domain_events.c.aggregate_type == "asset_lineage",
            domain_events.c.aggregate_version == 3, domain_events.c.event_type == "asset_lineage.discarded")).all())
        roots = sorted(ident for ident, (row, ref) in by_id.items()
                       if isinstance(ref, RetainedAssetRef) and row["state"] == "invalidated"
                       and ident not in recorded)
    # All I/O remains stopped by external attestation across these transactions.
    # Do not bypass the individual tombstone and audit checks.
    selected = ([('derived', ident) for ident in derived] + [('root', ident) for ident in roots])[:limit]
    purged = removed = absent = already = 0
    for kind, ident in selected:
        if kind == 'derived':
            result = store.purge_invalidated(tenant, ident)
            if result["status"] == "PURGED":
                purged += 1
            else:
                already += 1
        else:
            result = discard_invalidated(queue.index, vault, tenant, ident, all_vault_io_stopped=True)
            if result["status"] == "ALREADY_RECORDED":
                already += 1
            elif result["directory_entry_removed"]:
                removed += 1
            else:
                absent += 1
    return {"status": "CLEANUP_BATCH_COMPLETED", "policy_version": VERSION,
            "selected": len(selected), "remaining_at_snapshot": len(derived)+len(roots)-len(selected),
            "payloads_purged": purged, "root_entries_removed": removed,
            "root_already_absent": absent, "already_recorded": already,
            "stopped_io_attested": True, "secure_erasure_verified": False, "media_enabled": False}
