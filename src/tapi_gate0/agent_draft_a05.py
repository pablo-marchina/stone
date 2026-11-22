"""A05→CAP-023: atomic, authenticated synthetic-only agent-to-Studio draft.

A single server-owned database transaction binds the tenant-local reference
validation and the initial editable DesignDocument write. This path creates
only a draft; it neither uses third-party media nor grants editorial approval,
publishes content, runs a model, or executes an external provider operation.

External creative references remain denied until a separate, operational and
independently provisioned rights PEP can check them at the action boundary.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .agent_evidence_b2 import CreativeBriefRequest, EvidenceRetriever
from .domain import Id
from .studio_e1 import CreativeSpec, DesignDocument, StudioStore


class CreateAgentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: Id
    brief: CreativeBriefRequest


def create_agent_draft(engine, *, tenant_id: str, actor_id: str,
                       payload: CreateAgentDraft) -> DesignDocument:
    """All-or-nothing evidence->spec->document handoff under one SQL transaction.

    Tenant and actor MUST originate from an authenticated server session, never
    from the input payload. The B2 validator also checks creator and snapshot
    bindings, then refuses any non-synthetic/external reference. Even a valid
    return is only a mutable draft with rights_status='pending_review'.
    """
    with engine.begin() as connection:
        handoff = EvidenceRetriever(engine).handoff(
            tenant_id, payload.brief, connection=connection,
        )
        spec = CreativeSpec.model_validate(handoff.model_dump(mode="json"))
        return StudioStore(engine).create(
            tenant_id, actor_id, spec, payload.document_id,
            connection=connection,
        )
