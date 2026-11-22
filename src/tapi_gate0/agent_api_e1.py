"""Read-only, authenticated evidence-first analysis over tenant ranking data.

This is a bounded deterministic tool composition, not a hosted LLM/MCP
endpoint. Its trust boundary is the server-side SqlDomainStore, never raw
client-supplied ranking rows or citations.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from .agent_evidence_e1 import AgentRecommendation, analyze_with_ranking
from .domain import Origin
from .identity import IdentityFailure, Principal
from .agent_evidence_b2 import (EvidenceRetriever, EvidenceNotFound, CreativeBriefRequest, CreativeSpecHandoff, ObservedEvidence)
from .agent_draft_a05 import CreateAgentDraft, create_agent_draft
from .studio_e1 import DesignDocument, StudioError
from .studio_e4 import studio_etag


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

    return router
