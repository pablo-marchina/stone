"""Read-only bridge from BD technical inventory to scientific evidence planning."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import re


STAGES = ("SOURCE_NOT_ELIGIBLE", "CONTENT_INVALID", "NONPRIMARY_FORMAT",
          "TOO_RECENT", "METRICS_MISSING_OR_INVALID", "TRACE_MISSING",
          "CAPTION_UNAVAILABLE", "CAPTION_AVAILABLE_FOR_ASSESSMENT")


def classify_record(post, metric, *, source_ok, trace_ok, cutoff):
    """First blocking stage only; a caption is availability, not audience evidence."""
    if not source_ok:
        return STAGES[0]
    if post is None or post.is_synthetic or post.origin != "instagram":
        return STAGES[1]
    if post.media_type not in {"reels", "carrossel"}:
        return STAGES[2]
    if post.published_at > cutoff:
        return STAGES[3]
    if metric is None or metric.follower_count <= 0:
        return STAGES[4]
    if not trace_ok:
        return STAGES[5]
    return STAGES[7] if post.caption and post.caption.strip() else STAGES[6]


def counts_for(stages):
    counts = Counter(stages)
    if set(counts) - set(STAGES):
        raise ValueError("BD_READINESS_UNKNOWN_STAGE")
    return {stage: counts[stage] for stage in STAGES}


def source_gate(source, grant, now):
    if source is None or source.status != "approved":
        return "MANIFEST_SOURCE_NOT_APPROVED"
    if source.expires_at <= now:
        return "MANIFEST_SOURCE_EXPIRED"
    if not grant or not grant["enabled"] or datetime.fromisoformat(grant["expires_at"]) <= now:
        return "ACTIVE_GRANT_REQUIRED"
    if grant["approval_reference"] != source.approval_reference:
        return "GRANT_REFERENCE_MISMATCH"
    if not grant["technical_verified_at"] or datetime.fromisoformat(grant["technical_verified_at"]) > now:
        return "TECHNICAL_VERIFICATION_REQUIRED"
    return "TECHNICAL_SCOPE_MATCHED"


def readiness_report(engine, tenant, manifest, viewer):
    """Aggregate only. No caption export, model inference, registration or admission."""
    from sqlalchemy import select
    from pydantic import ValidationError
    from .connectors import ConnectorError
    from .corpus import corpus_data_card, corpus_profiles
    from .discovery_technical import audit_run
    from .domain import ContentItem, MetricsCreate
    from .ingestion import ingestion_records, ingestion_runs, source_grants
    from .sa_store import content_items, metrics_snapshots, tenants
    from .scientific_corpus import source_research_contexts
    from .storage import now_utc

    if not re.fullmatch(r"[0-9]{5,32}", viewer):
        raise ConnectorError("BD_BATCH_INVALID_VIEWER", 422)
    now = now_utc().astimezone(timezone.utc)
    cutoff = now - timedelta(days=14)
    manifest_by_id = {s.expected_ig_id: s for s in manifest.sources if s.expected_ig_id}
    with engine.connect() as db:
        if not db.execute(select(tenants.c.tenant_id).where(tenants.c.tenant_id == tenant)).first():
            raise ConnectorError("INGESTION_TENANT_NOT_FOUND", 404)
        def instagram_rows(table):
            return db.execute(select(table).where(table.c.tenant_id == tenant,
                table.c.platform == "instagram")).mappings().all()
        records = [r for r in instagram_rows(ingestion_records) if r["metadata_only"] == 1]
        grants = {r["source_account_id"]: r for r in instagram_rows(source_grants)}
        profiles = {r["source_account_id"] for r in instagram_rows(corpus_profiles)}
        contexts = {r["source_account_id"] for r in instagram_rows(source_research_contexts)}
        source_ids = set(manifest_by_id) | {r["source_account_id"] for r in records}
        gates = {sid: source_gate(manifest_by_id.get(sid), grants.get(sid), now) for sid in source_ids}
        allowed_ids = {sid for sid, reason in gates.items() if reason == "TECHNICAL_SCOPE_MATCHED"}
        allowed_content = {r["content_id"] for r in records if r["source_account_id"] in allowed_ids}
        posts, latest = {}, {}
        # Chunk IN predicates to remain within older SQLite variable limits.
        keys = sorted(allowed_content)
        for offset in range(0, len(keys), 400):
            chunk = keys[offset:offset+400]
            for cid, blob in db.execute(select(content_items.c.id, content_items.c.payload).where(
                    content_items.c.tenant_id == tenant, content_items.c.id.in_(chunk))):
                try:
                    post = ContentItem.model_validate_json(blob)
                    if post.content_id == cid and post.tenant_id == tenant:
                        posts[cid] = post
                except ValidationError:
                    pass
            for cid, blob in db.execute(select(metrics_snapshots.c.content_id, metrics_snapshots.c.payload).where(
                    metrics_snapshots.c.tenant_id == tenant, metrics_snapshots.c.content_id.in_(chunk))):
                try:
                    metric = MetricsCreate.model_validate_json(blob)
                except ValidationError:
                    continue
                if metric.tenant_id != tenant or metric.content_id != cid or metric.observed_at > now:
                    continue
                previous = latest.get(cid)
                if previous is None or (metric.observed_at, metric.snapshot_id) > (previous.observed_at, previous.snapshot_id):
                    latest[cid] = metric
        traces = set()
        audited_runs = invalid_runs = 0
        for run in instagram_rows(ingestion_runs):
            sid = run["source_account_id"]
            if sid not in allowed_ids or run["status"] != "completed":
                continue
            audit = audit_run(engine, tenant, run["run_key"], connection=db)
            if not audit["all_traces_valid"]:
                invalid_runs += 1
                continue
            if not audit["items"]:
                continue
            audited_runs += 1
            for item in audit["items"]:
                if (item["source_account_id"] == sid and item["viewer_ig_id"] == viewer
                        and item["acquisition_method"] == "graph_business_discovery"
                        and re.fullmatch(r"[a-f0-9]{64}", item["metadata_sha256"])):
                    traces.add((sid, item["source_item_id"], item["content_id"]))
        per_source = defaultdict(list)
        for r in records:
            sid, cid = r["source_account_id"], r["content_id"]
            per_source[sid].append(classify_record(posts.get(cid), latest.get(cid),
                source_ok=sid in allowed_ids,
                trace_ok=(sid, r["source_item_id"], cid) in traces, cutoff=cutoff))
    sources = []
    for source in manifest.sources:
        sid = source.expected_ig_id
        stages = per_source.get(sid, [])
        sources.append({"username": source.username, "stratum": source.sampling_stratum,
            "manifest_status": source.status, "source_gate": gates.get(sid, "MANIFEST_SOURCE_NOT_APPROVED"),
            "technical_records": len(stages), "first_blocking_stage": counts_for(stages),
            "profile_registered": sid in profiles, "source_context_registered": sid in contexts})
    stages = [stage for values in per_source.values() for stage in values]
    totals = counts_for(stages)
    # Canonical card remains the authority on scientific eligibility; do not promote.
    card = corpus_data_card(engine, tenant, as_of=now)
    return {"schema_version": "tapi-bd-corpus-readiness.v1", "status": "CORPUS_READINESS_PLANNED",
            "as_of": now.isoformat(), "manifest_sha256": manifest.fingerprint(),
            "technical_inventory": {"records": len(records),
                "unique_media_ids": len({r["source_item_id"] for r in records}),
                "profiles": len(per_source), "records_outside_manifest": sum(len(v) for k,v in per_source.items() if k not in manifest_by_id)},
            "first_blocking_stage": totals, "audited_completed_nonempty_runs": audited_runs,
            "completed_runs_without_valid_bd_trace": invalid_runs,
            "sources": sources, "canonical_corpus_card": card,
            "caption_availability_is_not_targeting_evidence": True,
            "media_modalities_assessed": False, "new_scientific_admissions": 0,
            "external_data_accessed": False, "database_mutated": False,
            "production_approved": False}
