"""A05/CAP-023: re-check persisted external reference grants on demand.

This is a *draft-use diagnostic action*, NOT a license or release certificate.
Every call revalidates the current signed rights in one transaction, and writes
an audit event only if an external PEP verification passes. No publish/render.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .agent_evidence_b2 import EvidenceNotFound, EvidenceRetriever
from .creative_reference_pep_a05 import CreativeReferencePEP, CreativeReferencePermissionDenied
from .domain import ContentItem, Id
from .sa_store import content_items
from .studio_e1 import DesignDocument, StudioError, studio_documents, studio_versions
from .studio_reference_bindings_a05 import (
    ReferenceBindingDenied, load_reference_bindings,
)


class ReferenceRecheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    document_id: Id
    verified_external_reference_count: int = Field(ge=0)
    rights_status: str = "pending_review"
    approval_status: str = "draft"
    publication_allowed: bool = False
    production_approved: bool = False


def recheck_document_references(
    engine, *, tenant: str, actor: str, token: str | None,
    document_id: str, creative_pep: CreativeReferencePEP | None,
) -> ReferenceRecheckResult:
    """Re-evaluate stored grants; never infer permission from a stored receipt.

    The current document and all bindings are checked inside the same DB
    transaction as the signed grant and revocation checks. A result is *only*
    evidence that the particular draft reference check passed at that instant.
    """
    with engine.begin() as db:
        payload = db.execute(select(studio_versions.c.payload).select_from(
            studio_versions.join(
                studio_documents,
                (studio_documents.c.tenant_id == studio_versions.c.tenant_id)
                & (studio_documents.c.document_id == studio_versions.c.document_id)
                & (studio_documents.c.current_version == studio_versions.c.version),
            )
        ).where(
            studio_versions.c.tenant_id == tenant,
            studio_versions.c.document_id == document_id,
        )).scalar_one_or_none()
        if payload is None:
            raise StudioError("STUDIO_DOCUMENT_NOT_FOUND", 404)
        try:
            doc = DesignDocument.model_validate_json(payload)
            if doc.tenant_id != tenant or doc.document_id != document_id:
                raise ReferenceBindingDenied()
            bindings = load_reference_bindings(
                db, tenant=tenant, document_id=document_id,
                reference_content_ids=doc.reference_content_ids,
            )
            retriever = EvidenceRetriever(engine)
            for content_id in doc.reference_content_ids:
                # Reject missing, corrupt, foreign-tenant or relabeled records,
                # including those not covered by a signed external grant.
                evidence = retriever.get(tenant, content_id, connection=db)
                if content_id not in bindings:
                    row = db.execute(select(content_items.c.payload).where(
                        content_items.c.tenant_id == tenant,
                        content_items.c.id == content_id,
                    )).scalar_one_or_none()
                    item = ContentItem.model_validate_json(row)
                    if (evidence.origin != "synthetic_local"
                            or item.is_synthetic is not True
                            or item.source_url is not None):
                        raise ReferenceBindingDenied()
            if bindings:
                if creative_pep is None or token is None:
                    raise ReferenceBindingDenied()
                creative_pep.require_for_atomic_draft(
                    db, token=token, tenant=tenant, actor=actor,
                    document_id=document_id, grant_ids=bindings,
                    audit_event_type="creative_reference.rechecked_for_draft",
                )
        except (EvidenceNotFound, CreativeReferencePermissionDenied,
                ReferenceBindingDenied, ValueError, TypeError, AttributeError):
            raise ReferenceBindingDenied() from None
    return ReferenceRecheckResult(
        document_id=document_id,
        status=("SIGNED_REFERENCES_CURRENT_FOR_DRAFT_REVIEW_ONLY"
                if bindings else "LOCAL_SYNTHETIC_REFERENCES_ONLY"),
        verified_external_reference_count=len(bindings),
    )
