"""A05: strictly local, synthetic-only CreativeSpec handoff diagnostic.

This is NOT a rights PEP, an HTTP/MCP route, a Studio write, or a path for
third-party posts. There is no operation-specific creative-source grant in the
B2 storage contract, so the experimental adapter denies every external origin.
A successful inspection does not authorize production, external assets or
CreativeSpec publication; no creative payload leaves this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import select

from .agent_evidence_b2 import CreativeBriefRequest, EvidenceRetriever
from .domain import ContentItem, Creator, Origin
from .sa_store import content_items, creators

VERSION = "tapi-a05-synthetic-creative-diagnostic.v1"


class CreativeReferenceDenied(PermissionError):
    """Sanitized, fixed-reason denial, without IDs, captions or payloads."""


def _deny(code):
    raise CreativeReferenceDenied("A05_" + code)


def _bind_synthetic(engine, tenant_id, reference_ids):
    """Pin both tenant-bound content and creator records; no external data."""
    result = []
    with engine.connect() as con:
        for cid in reference_ids:
            row = con.execute(
                select(content_items.c.payload, creators.c.payload)
                .join(creators, (creators.c.tenant_id == content_items.c.tenant_id)
                      & (creators.c.id == content_items.c.creator_id))
                .where(content_items.c.tenant_id == tenant_id,
                       content_items.c.id == cid)
            ).first()
            if row is None:
                _deny("REFERENCE_NOT_IN_TENANT")
            try:
                content = ContentItem.model_validate_json(row[0])
                creator = Creator.model_validate_json(row[1])
            except Exception:
                _deny("REFERENCE_INVALID")
            if (content.tenant_id != tenant_id or content.content_id != cid
                    or creator.tenant_id != tenant_id
                    or creator.creator_id != content.creator_id):
                _deny("REFERENCE_BINDING_INVALID")
            if (content.origin is not Origin.SYNTHETIC
                    or creator.origin is not Origin.SYNTHETIC
                    or content.is_synthetic is not True
                    or content.source_url is not None):
                _deny("EXTERNAL_CREATIVE_RIGHTS_NOT_ESTABLISHED")
            if content.published_at > datetime.now(timezone.utc):
                _deny("REFERENCE_NOT_YET_PUBLISHED")
            # Persisted payload hashes pin exactly the rows examined. No
            # assumption of a global transaction/lease or grant validity.
            result.append(sha256(row[0].encode("utf-8") + b"\0" +
                                 row[1].encode("utf-8")).hexdigest())
    return tuple(result)


def inspect_synthetic_creative_handoff(engine, tenant_id: str,
                                       request: CreativeBriefRequest) -> dict:
    """Run a synthetic diagnostic, never return an actionable CreativeSpec.

    Caller must already be trusted to provide its tenant; this function must
    NOT be exposed as an HTTP/MCP authorization endpoint. It proves only
    consistency of local synthetic fixtures across this one call.
    """
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        _deny("TRUSTED_TENANT_REQUIRED")
    if not isinstance(request, CreativeBriefRequest):
        _deny("VALIDATED_BRIEF_REQUIRED")
    ids = request.reference_content_ids
    if not ids or len(set(ids)) != len(ids):
        _deny("REFERENCE_SET_INVALID")
    before = _bind_synthetic(engine, tenant_id, ids)
    try:
        spec = EvidenceRetriever(engine).handoff(tenant_id, request)
    except Exception:
        _deny("EVIDENCE_HANDOFF_REJECTED")
    after = _bind_synthetic(engine, tenant_id, ids)
    if before != after:
        _deny("REFERENCE_DRIFT")
    if (spec.tenant_id != tenant_id
            or spec.reference_content_ids != ids
            or spec.schema_version != "creative-spec.v1"):
        _deny("HANDOFF_BINDING_INVALID")
    spec_digest = sha256(spec.model_dump_json().encode("utf-8")).hexdigest()
    return {
        "schema_version": VERSION,
        "status": "SYNTHETIC_CREATIVE_DIAGNOSTIC_VERIFIED",
        "reference_kind": "synthetic_local",
        "reference_count": len(ids),
        "creative_spec_sha256": spec_digest,
        "permitted_use": "private_synthetic_diagnostic_only",
        "reference_records_consistent_at_check": True,
        "current_external_rights_verified": False,
        "external_reference_admitted": False,
        "studio_write_allowed": False,
        "publication_allowed": False,
        "scientifically_validated": False,
        "gates_released": False,
        "production_approved": False,
        "external_data_accessed": False,
        "database_mutated": False,
    }
