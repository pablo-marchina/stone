"""Authenticated evidence-first agent API, including atomic draft creation.

The deterministic ranking/evidence tools are read-only. The creative-drafts
route creates only an internal editable draft, protected by the session and
the transactional reference-rights PEP. No hosted LLM or external publication.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request, HTTPException, Response, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .agent_evidence_e1 import AgentRecommendation, analyze_with_ranking
from .domain import Origin
from .identity import IdentityFailure, Principal
from .agent_evidence_b2 import (EvidenceRetriever, EvidenceNotFound, CreativeBriefRequest, CreativeSpecHandoff, ObservedEvidence)
from .agent_draft_a05 import CreateAgentDraft, create_agent_draft
from .studio_e1 import (DesignDocument, StudioError, StudioStore,
                        TextLayerPatch, studio_versions)
from .studio_e4 import studio_etag, assert_etag
from .studio_reference_bindings_a05 import ReferenceBindingDenied
from .studio_reference_lifecycle_a05 import ReferenceRecheckResult, recheck_document_references


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: Origin = Origin.SYNTHETIC
    as_of: datetime
    min_age_days: int = Field(default=14, ge=14, le=3650)


def router_for_evidence_agent(identity, domain_store, *, creative_pep=None):
    router = APIRouter(prefix="/v1/agent", tags=["Evidence-first agent E1"])

    def principal(request: Request) -> Principal:
        value = request.headers.get("Authorization", "")
        scheme, _, token = value.partition(" ")
        if scheme.lower() != "bearer" or not token or " " in token:
            raise IdentityFailure()
        return identity.resolve(token)

    @router.post("/analyze-ranking", response_model=AgentRecommendation)
    def analyze(payload: AnalyzeRequest, p: Principal = Depends(principal)):
        if p.role not in {"admin", "researcher", "annotator", "editor", "viewer", "service"}:
            raise IdentityFailure("FORBIDDEN", 403)
        # Tenant is drawn ONLY from the verified session.
        return analyze_with_ranking(
            domain_store, tenant_id=p.tenant_id, origin=payload.origin,
            as_of=payload.as_of, min_age_days=payload.min_age_days,
        )

    @router.get("/evidence/{content_id}", response_model=ObservedEvidence)
    def evidence(content_id: str, p: Principal = Depends(principal)):
        try:
            return EvidenceRetriever(domain_store.engine).get(p.tenant_id, content_id)
        except EvidenceNotFound:
            raise HTTPException(status_code=404, detail="EVIDENCE_NOT_FOUND")

    @router.post("/creative-spec", response_model=CreativeSpecHandoff)
    def handoff(payload: CreativeBriefRequest, p: Principal = Depends(principal)):
        if p.role not in {"admin", "researcher", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return EvidenceRetriever(domain_store.engine).handoff(p.tenant_id, payload)
        except EvidenceNotFound:
            raise HTTPException(status_code=422, detail="CREATIVE_REFERENCE_NOT_VERIFIED")

    @router.post("/creative-drafts", response_model=DesignDocument, status_code=201)
    def create_draft(payload: CreateAgentDraft, response: Response,
                     request: Request,
                     p: Principal = Depends(principal)):
        # Only editor/admin can mutate Studio. The verified session, not JSON,
        # supplies the tenant and actor. All source checks + writes are atomic.
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            doc = create_agent_draft(
                domain_store.engine, tenant_id=p.tenant_id,
                actor_id=p.actor_id, payload=payload,
                token=request.headers.get("Authorization", "").partition(" ")[2],
                creative_pep=creative_pep,
            )
        except EvidenceNotFound:
            raise HTTPException(status_code=422, detail="CREATIVE_REFERENCE_NOT_VERIFIED")
        except StudioError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.code) from exc
        response.headers["ETag"] = studio_etag(doc)
        response.headers["Cache-Control"] = "private, no-store"
        return doc

    @router.post("/creative-drafts/{document_id}/reference-recheck",
                 response_model=ReferenceRecheckResult)
    def recheck_draft_references(document_id: str, request: Request,
                                 p: Principal = Depends(principal)):
        # Explicit POST: a successful external check appends an audit event.
        # The result NEVER authorizes publication, media use or final export.
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return recheck_document_references(
                domain_store.engine, tenant=p.tenant_id, actor=p.actor_id,
                token=request.headers.get("Authorization", "").partition(" ")[2],
                document_id=document_id, creative_pep=creative_pep,
            )
        except ReferenceBindingDenied:
            raise HTTPException(status_code=422, detail="CREATIVE_REFERENCE_NOT_VERIFIED")
        except StudioError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.code) from exc

    @router.post("/creative-drafts/{document_id}/text-patches",
                 response_model=DesignDocument)
    def edit_signed_draft(document_id: str, patch: TextLayerPatch,
                          response: Response, request: Request,
                          if_match: str | None = Header(default=None, alias="If-Match"),
                          p: Principal = Depends(principal)):
        """Action-scoped reference PEP and Studio version write in ONE txn.

        Never trust a prior /reference-recheck receipt for mutation.
        A current Ed25519 grant check is required at the actual edit boundary.
        """
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        if if_match is None:
            raise HTTPException(status_code=428, detail="STUDIO_IF_MATCH_REQUIRED")
        try:
            with domain_store.engine.begin() as db:
                row = db.execute(select(studio_versions.c.payload).where(
                    studio_versions.c.tenant_id == p.tenant_id,
                    studio_versions.c.document_id == document_id,
                    studio_versions.c.version == patch.expected_version,
                )).scalar_one_or_none()
                if row is None:
                    raise StudioError("STUDIO_VERSION_CONFLICT", 409)
                current = DesignDocument.model_validate_json(row)
                if current.tenant_id != p.tenant_id or current.document_id != document_id:
                    raise StudioError("STUDIO_DOCUMENT_BINDING_INVALID", 409)
                assert_etag(current, if_match, patch.expected_version)
                checked = False

                def authorize_refs(connection):
                    nonlocal checked
                    if not checked:
                        recheck_document_references(
                            domain_store.engine, tenant=p.tenant_id,
                            actor=p.actor_id,
                            token=request.headers.get("Authorization", "").partition(" ")[2],
                            document_id=document_id, creative_pep=creative_pep,
                            connection=connection,
                        )
                        checked = True

                # Even an unbound manual draft must have its references
                # validated. For signed references, StudioStore invokes the
                # same callback again, but it cannot skip the prior check.
                authorize_refs(db)
                doc = StudioStore(domain_store.engine).patch_text_layer(
                    p.tenant_id, p.actor_id, document_id, patch,
                    connection=db, reference_authorizer=authorize_refs,
                )
        except ReferenceBindingDenied:
            raise HTTPException(status_code=422, detail="CREATIVE_REFERENCE_NOT_VERIFIED")
        except StudioError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.code) from exc
        response.headers["ETag"] = studio_etag(doc)
        response.headers["Cache-Control"] = "private, no-store"
        return doc

    return router
