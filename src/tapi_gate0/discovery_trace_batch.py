"""IMP-071: read-only batched equivalent of the A3 technical trace audit.

Not yet wired into readiness, ingestion APIs, or access authorization.
Every domain event is still correlated to its tenant-scoped snapshot/content
and globally unique outbox seq. An operator parity test against audit_run()
must pass on the authorized local corpus before any operational substitution.
"""
from __future__ import annotations

from contextlib import nullcontext
import json

from sqlalchemy import select

from .connectors import ConnectorError
from .ingestion import ingestion_runs, stable_id
from .sa_store import content_items, domain_events, metrics_snapshots, outbox

CHUNK = 400


def _chunks(values):
    values = list(dict.fromkeys(values))
    for offset in range(0, len(values), CHUNK):
        yield values[offset:offset + CHUNK]


def audit_run_batched(engine, tenant: str, run_key: str, *, connection=None) -> dict:
    """Equivalent read-only trace check with bounded IN queries.

    Preserve output keys, row order, existence semantics, tenant isolation and
    fail-closed behavior of discovery_technical.audit_run. No audit is skipped.
    """
    with (nullcontext(connection) if connection is not None else engine.connect()) as db:
        run = db.execute(select(ingestion_runs).where(
            ingestion_runs.c.tenant_id == tenant,
            ingestion_runs.c.run_key == run_key,
        )).mappings().first()
        if run is None:
            raise ConnectorError("BD_RUN_NOT_FOUND", 404)
        events = db.execute(select(domain_events).where(
            domain_events.c.tenant_id == tenant,
            domain_events.c.aggregate_type == "bd_technical_run",
            domain_events.c.aggregate_id == stable_id(
                "bd-observation-run", tenant, run_key
            ),
        ).order_by(domain_events.c.aggregate_version)).mappings().all()

        parsed = [(event, json.loads(event["payload"])) for event in events]
        snapshot_ids = [value["snapshot_id"] for _, value in parsed]
        content_ids = [value["content_id"] for _, value in parsed]
        event_seqs = [event["seq"] for event, _ in parsed]

        snapshots = set()
        for ids in _chunks(snapshot_ids):
            snapshots.update(db.execute(
                select(metrics_snapshots.c.id, metrics_snapshots.c.content_id).where(
                    metrics_snapshots.c.tenant_id == tenant,
                    metrics_snapshots.c.id.in_(ids),
                )
            ).all())

        contents = set()
        for ids in _chunks(content_ids):
            contents.update(db.execute(
                select(content_items.c.id).where(
                    content_items.c.tenant_id == tenant,
                    content_items.c.id.in_(ids),
                )
            ).scalars().all())

        outbox_seqs = set()
        for seqs in _chunks(event_seqs):
            outbox_seqs.update(db.execute(
                select(outbox.c.seq).where(outbox.c.seq.in_(seqs))
            ).scalars().all())

        details = []
        for event, value in parsed:
            content_id, snapshot_id = value["content_id"], value["snapshot_id"]
            details.append({
                "source_item_id": value["source_item_id"],
                "content_id": content_id,
                "snapshot_id": snapshot_id,
                "snapshot_exists": (snapshot_id, content_id) in snapshots,
                "content_exists": content_id in contents,
                "outbox_exists": event["seq"] in outbox_seqs,
                "metadata_sha256": value["metadata_sha256"],
                "acquisition_method": value["acquisition_method"],
                "viewer_ig_id": value["viewer_ig_id"],
                "source_account_id": value["source_account_id"],
                "scientific_eligibility": value["scientific_eligibility"],
            })

    expected = (run["new_records"] + run["refreshed_records"]
                + run["duplicate_records"])
    valid = (run["status"] == "completed" and len(details) == expected
             and all(item["snapshot_exists"] and item["content_exists"]
                     and item["outbox_exists"] for item in details))
    return {
        "run_key": run_key,
        "status": run["status"],
        "new_records": run["new_records"],
        "refreshed_records": run["refreshed_records"],
        "duplicate_records": run["duplicate_records"],
        "observations": len(details),
        "has_persisted_observations": len(details) > 0,
        "all_traces_valid": valid,
        "items": details,
    }
