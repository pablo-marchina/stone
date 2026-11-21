"""A06/A07: read-only provenance receipt for an existing synthetic Studio draft.

A private diagnostic over already-persisted DesignDocument + source records.
NO new creative spec, no generation, no asset processing, no HTTP/MCP/Studio
route, no real-world source rights, no evidence of efficacy, no permission.
Only synthetic_local content and corresponding local snapshots qualify.

The receipt is a point-in-time inspection, NOT a transferable authorization.
Changes after the read cannot be prevented by this function. Operational use
still requires a transactional PEP and current independently verified rights.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .domain import ContentItem, Creator, MetricsCreate, Origin
from .sa_store import content_items, creators, metrics_snapshots
from .studio_e1 import DesignDocument, studio_documents, studio_versions

VERSION = "tapi-a067-synthetic-draft-provenance.v1"
MAX_REFERENCES = 10
MAX_SNAPSHOTS_PER_REFERENCE = 1000


def _result(status, reason, **details):
    # Only fixed codes in negative paths, not raw DB rows or user text.
    return {
        "schema_version": VERSION,
        "status": status,
        "reason_code": reason,
        "permitted_use": (
            "private_synthetic_draft_diagnostic_only"
            if status == "SYNTHETIC_DRAFT_PROVENANCE_LINKED" else "none"
        ),
        "synthetic_evidence_linked": status == "SYNTHETIC_DRAFT_PROVENANCE_LINKED",
        "independent_gold_available": False,
        "external_rights_verified": False,
        "scientifically_validated": False,
        "creative_claim_approved": False,
        "studio_write_allowed": False,
        "render_allowed": False,
        "publication_allowed": False,
        "gates_released": False,
        "production_approved": False,
        **details,
    }


def _sha(payload):
    return sha256(payload.encode("utf-8")).hexdigest()


def inspect_synthetic_draft_provenance(engine, *, tenant_id: str,
                                       document_id: str, expected_version: int,
                                       as_of: datetime) -> dict:
    """Inspect a pinned version and synthetic citations; return no content text.

    The local caller supplies the tenant from its trusted session. No session
    validation occurs here; do not expose this function directly to clients.
    """
    if (not isinstance(tenant_id, str) or not tenant_id
            or not isinstance(document_id, str) or not document_id
            or type(expected_version) is not int or expected_version < 1
            or not isinstance(as_of, datetime) or as_of.tzinfo is None
            or as_of.utcoffset() is None):
        return _result("BLOCKED", "A067_INPUT_INVALID")
    if as_of > datetime.now(timezone.utc):
        return _result("BLOCKED", "A067_AS_OF_FUTURE")

    try:
        with engine.connect() as db:
            head = db.execute(select(studio_documents.c.current_version).where(
                studio_documents.c.tenant_id == tenant_id,
                studio_documents.c.document_id == document_id,
            )).scalar_one_or_none()
            if head is None:
                return _result("BLOCKED", "A067_DOCUMENT_NOT_IN_TENANT")
            if head != expected_version:
                return _result("BLOCKED", "A067_DOCUMENT_VERSION_CHANGED")
            raw = db.execute(select(studio_versions.c.payload).where(
                studio_versions.c.tenant_id == tenant_id,
                studio_versions.c.document_id == document_id,
                studio_versions.c.version == expected_version,
            )).scalar_one_or_none()
            if raw is None:
                return _result("BLOCKED", "A067_DOCUMENT_VERSION_MISSING")
            try:
                doc = DesignDocument.model_validate_json(raw)
            except (ValueError, ValidationError, TypeError):
                return _result("BLOCKED", "A067_DOCUMENT_INVALID")
            if (doc.tenant_id != tenant_id or doc.document_id != document_id
                    or doc.version != expected_version
                    or doc.reference_status != "unverified"
                    or doc.rights_status != "pending_review"
                    or doc.approval_status != "draft"
                    or doc.render_status != "not_implemented"):
                return _result("BLOCKED", "A067_DOCUMENT_BINDING_INVALID")
            refs = doc.reference_content_ids
            if not 1 <= len(refs) <= MAX_REFERENCES or len(refs) != len(set(refs)):
                return _result("ABSTAIN", "A067_REFERENCES_REQUIRED")

            citations = []
            for cid in refs:
                row = db.execute(
                    select(content_items.c.origin,
                           content_items.c.creator_id,
                           content_items.c.payload,
                           creators.c.origin.label("creator_origin"),
                           creators.c.payload.label("creator_payload"))
                    .select_from(content_items.join(
                        creators,
                        (creators.c.tenant_id == content_items.c.tenant_id)
                        & (creators.c.id == content_items.c.creator_id),
                    ))
                    .where(content_items.c.tenant_id == tenant_id,
                           content_items.c.id == cid)
                ).mappings().one_or_none()
                if row is None:
                    return _result("ABSTAIN", "A067_REFERENCE_MISSING")
                try:
                    post = ContentItem.model_validate_json(row["payload"])
                    creator = Creator.model_validate_json(row["creator_payload"])
                except (ValidationError, ValueError, TypeError):
                    return _result("BLOCKED", "A067_SOURCE_RECORD_INVALID")
                if (post.tenant_id != tenant_id or post.content_id != cid
                        or post.creator_id != row["creator_id"]
                        or creator.tenant_id != tenant_id
                        or creator.creator_id != post.creator_id):
                    return _result("BLOCKED", "A067_SOURCE_BINDING_INVALID")
                if (row["origin"] != Origin.SYNTHETIC.value
                        or row["creator_origin"] != Origin.SYNTHETIC.value
                        or post.origin is not Origin.SYNTHETIC
                        or creator.origin is not Origin.SYNTHETIC
                        or post.is_synthetic is not True
                        or post.source_url is not None):
                    return _result("BLOCKED", "A067_EXTERNAL_REFERENCE_DENIED")
                if post.published_at > as_of or post.created_at > as_of:
                    return _result("ABSTAIN", "A067_REFERENCE_NOT_YET_AVAILABLE")
                rows = db.execute(select(
                    metrics_snapshots.c.id, metrics_snapshots.c.payload,
                ).where(
                    metrics_snapshots.c.tenant_id == tenant_id,
                    metrics_snapshots.c.content_id == cid,
                )).all()
                if len(rows) > MAX_SNAPSHOTS_PER_REFERENCE:
                    return _result("BLOCKED", "A067_SNAPSHOT_LIMIT")
                available = []
                for snapshot_id, snapshot_raw in rows:
                    try:
                        snap = MetricsCreate.model_validate_json(snapshot_raw)
                    except (ValidationError, ValueError, TypeError):
                        return _result("BLOCKED", "A067_SNAPSHOT_INVALID")
                    if (snap.tenant_id != tenant_id or snap.content_id != cid
                            or snap.snapshot_id != snapshot_id):
                        return _result("BLOCKED", "A067_SNAPSHOT_BINDING_INVALID")
                    if (snap.observed_at <= as_of and snap.followers_measured_at <= as_of
                            and snap.follower_count > 0):
                        available.append((snap.observed_at, snap.snapshot_id, snapshot_raw))
                if not available:
                    return _result("ABSTAIN", "A067_OBSERVATIONAL_SNAPSHOT_REQUIRED")
                _, chosen_id, chosen_payload = max(
                    available, key=lambda item: (item[0], item[1])
                )
                citations.append({
                    "content_id": cid,
                    "snapshot_id": chosen_id,
                    "content_sha256": _sha(row["payload"]),
                    "snapshot_sha256": _sha(chosen_payload),
                })

            # Re-read the version pointer within the same read transaction. This
            # detects common drift; it is NOT a serializable operational lock.
            second = db.execute(select(studio_documents.c.current_version).where(
                studio_documents.c.tenant_id == tenant_id,
                studio_documents.c.document_id == document_id,
            )).scalar_one_or_none()
            if second != expected_version:
                return _result("BLOCKED", "A067_DOCUMENT_VERSION_CHANGED")

        return _result(
            "SYNTHETIC_DRAFT_PROVENANCE_LINKED",
            "A067_SYNTHETIC_ONLY_EVIDENCE",
            document_version=expected_version,
            document_sha256=_sha(raw),
            references=citations,
            reference_count=len(citations),
            snapshot_selection="latest_observed_at_not_after_as_of",
            point_in_time_only=True,
        )
    except (SQLAlchemyError, ValueError, TypeError, AttributeError):
        return _result("BLOCKED", "A067_LOCAL_INSPECTION_FAILED")
