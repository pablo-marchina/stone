"""A05→CAP-023: atomic, authenticated synthetic-only agent-to-Studio draft.

A single server-owned database transaction binds the tenant-local reference
validation and the initial editable DesignDocument write. This path creates
only a draft; it neither uses third-party media nor grants editorial approval,
publishes content, runs a model, or executes an external provider operation.

External creative references remain denied until a separate, operational and
independently provisioned rights PEP can check them at the action boundary.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agent_evidence_b2 import CreativeBriefRequest, EvidenceRetriever, EvidenceNotFound
from .creative_reference_pep_a05 import CreativeReferencePEP, CreativeReferencePermissionDenied
from .domain import Id
from .studio_e1 import CreativeSpec, DesignDocument, StudioStore


class CreateAgentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: Id
    brief: CreativeBriefRequest
    reference_grant_ids: dict[Id, Id] = Field(default_factory=dict, max_length=10)

    @model_validator(mode="after")
    def reference_grants_match_brief(self):
        if not set(self.reference_grant_ids) <= set(self.brief.reference_content_ids):
            raise ValueError("CREATIVE_REFERENCE_GRANTS_NOT_IN_BRIEF")
        return self


def create_agent_draft(engine, *, tenant_id: str, actor_id: str,
                       payload: CreateAgentDraft,
                       token: str | None = None,
                       creative_pep: CreativeReferencePEP | None = None) -> DesignDocument:
    """All-or-nothing evidence->spec->document handoff under one SQL transaction.

    Tenant and actor MUST originate from an authenticated server session, never
    from the input payload. The B2 validator also checks creator and snapshot
    bindings, then refuses any non-synthetic/external reference. Even a valid
    return is only a mutable draft with rights_status='pending_review'.
    """
    with engine.begin() as connection:
        retriever = EvidenceRetriever(engine)
        if not payload.reference_grant_ids:
            # No external grant IDs means the unmodified synthetic-only B2
            # policy is authoritative; never infer rights from a caption.
            handoff = retriever.handoff(
                tenant_id, payload.brief, connection=connection,
            )
            spec = CreativeSpec.model_validate(handoff.model_dump(mode="json"))
        else:
            if creative_pep is None or token is None:
                raise EvidenceNotFound("CREATIVE_REFERENCE_RIGHTS_PEP_REQUIRED")
            # Check every B2 reference in the same database transaction. For
            # mixed briefs, locally synthetic references still use the strict
            # B2 validator; external ones require both signed operations.
            synthetic = []
            external = []
            for content_id in payload.brief.reference_content_ids:
                evidence = retriever.get(
                    tenant_id, content_id, connection=connection,
                )
                if evidence.origin == "synthetic_local":
                    synthetic.append(content_id)
                    if content_id in payload.reference_grant_ids:
                        raise EvidenceNotFound("CREATIVE_REFERENCE_RIGHTS_PEP_REQUIRED")
                else:
                    external.append(content_id)
                    if content_id not in payload.reference_grant_ids:
                        raise EvidenceNotFound("CREATIVE_REFERENCE_RIGHTS_PEP_REQUIRED")
            if synthetic:
                synthetic_brief = payload.brief.model_copy(update={
                    "reference_content_ids": synthetic,
                })
                retriever.handoff(
                    tenant_id, synthetic_brief, connection=connection,
                )
            if set(payload.reference_grant_ids) != set(external):
                raise EvidenceNotFound("CREATIVE_REFERENCE_RIGHTS_PEP_REQUIRED")
            try:
                creative_pep.require_for_atomic_draft(
                    connection, token=token, tenant=tenant_id, actor=actor_id,
                    document_id=payload.document_id,
                    grant_ids=payload.reference_grant_ids,
                )
            except CreativeReferencePermissionDenied:
                raise EvidenceNotFound("CREATIVE_REFERENCE_RIGHTS_PEP_REQUIRED") from None
            # The signed PEP validates scope but NEVER changes the draft-only
            # editorial, scientific or publishing status of CreativeSpec.
            spec = CreativeSpec(
                spec_id=payload.brief.spec_id,
                tenant_id=tenant_id,
                objective=payload.brief.objective,
                headline=payload.brief.headline,
                body=payload.brief.body,
                cta=payload.brief.cta,
                platform_intent=payload.brief.platform_intent,
                reference_content_ids=payload.brief.reference_content_ids,
            )
        return StudioStore(engine).create(
            tenant_id, actor_id, spec, payload.document_id,
            connection=connection,
        )
