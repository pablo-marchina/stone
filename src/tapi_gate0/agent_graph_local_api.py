"""IMP-074: explicit loopback-only diagnostic binding to the local graph runner.

The application factory is the ONLY opt-in. Production from_environment never
registers this router. No external origin, LLM, media or publication.
Draft endpoints require explicit operator authorship or selection of a local proposal.
Tenant/actor are taken exclusively from a revocable bearer session.
"""
from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator, ValidationError

from .agent_graph_checkpoints import AgentCheckpointDenied
from .agent_graph_readonly_runner import (
    LocalGraphDenied, LocalGraphPlan, execute_next,
)
from .identity import IdentityFailure, Principal
from .agent_draft_a05 import CreateAgentDraft
from .agent_evidence_b2 import EvidenceNotFound
from .agent_trace_draft_handoff import create_trace_bound_draft, TraceDraftDenied
from .studio_e1 import DesignDocument, StudioError
from .studio_e4 import studio_etag
from .domain import Id
from .agent_creative_proposals_local import preview_proposals, accept_proposal, ProposalDenied


def _strict_json_plan(value):
    # FastAPI supplies an already decoded Python dict, whereas the strict
    # plan's datetime parser expects a JSON timestamp. Parse as JSON before
    # binding an authenticated tenant/actor; retain all LocalGraphPlan gates.
    if type(value) is not dict:
        raise ValueError("LOCAL_GRAPH_PLAN_OBJECT_REQUIRED")
    try:
        return LocalGraphPlan.model_validate_json(json.dumps(value))
    except (ValidationError, ValueError, TypeError):
        raise ValueError("LOCAL_GRAPH_PLAN_INVALID") from None


class StepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    run_id: str = Field(min_length=1, max_length=128,
                        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    plan: Annotated[LocalGraphPlan, BeforeValidator(_strict_json_plan)]


class TraceDraftRequest(StepRequest):
    draft: CreateAgentDraft


class ProposalDraftRequest(StepRequest):
    document_id: Id
    proposal_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def router_for_local_graph_diagnostic(identity, engine) -> APIRouter:
    router = APIRouter(prefix="/v1/agent/local-graph", tags=["Local synthetic agent diagnostic"])

    def principal(request: Request) -> Principal:
        # Explicit loopback binding: a legitimate bearer token alone must not
        # turn this diagnostic endpoint into an Internet-facing agent API.
        # Never trust Forwarded/X-Forwarded-For as a substitute for peer host.
        if request.client is None or request.client.host not in {
            "127.0.0.1", "::1", "testclient",
        }:
            raise IdentityFailure("FORBIDDEN", 403)
        authorization = request.headers.get("Authorization", "")
        scheme, sep, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not sep or not token or " " in token:
            raise IdentityFailure()
        p = identity.resolve(token)
        if p.role not in {"admin", "researcher", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        return p

    @router.post("/step")
    def execute_single_step(body: StepRequest, p: Principal = Depends(principal)):
        # The request has NO tenant or actor field. Neither is user-overridable.
        # One bounded read-only node per request; only checkpoint tables mutate.
        try:
            return execute_next(engine, tenant=p.tenant_id, actor=p.actor_id,
                                run_id=body.run_id, plan=body.plan)
        except (AgentCheckpointDenied, LocalGraphDenied) as exc:
            # Both classes expose fixed reason codes, not captions or inputs.
            raise HTTPException(status_code=409, detail=str(exc)) from None

    @router.post("/creative-draft", response_model=DesignDocument, status_code=201)
    def create_local_trace_draft(body: TraceDraftRequest, response: Response,
                                 p: Principal = Depends(principal)):
        # A trace is never authority. A separate authenticated editor/admin
        # request supplies an original brief, and replays the trace inside the
        # transaction that creates the initial draft and its provenance event.
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            doc = create_trace_bound_draft(
                engine, tenant=p.tenant_id, actor=p.actor_id,
                run_id=body.run_id, plan=body.plan, payload=body.draft)
        except (AgentCheckpointDenied, LocalGraphDenied, TraceDraftDenied) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except EvidenceNotFound:
            raise HTTPException(status_code=422, detail="CREATIVE_REFERENCE_NOT_VERIFIED") from None
        except StudioError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.code) from None

        response.headers["ETag"] = studio_etag(doc)
        response.headers["Cache-Control"] = "private, no-store"
        return doc

    @router.post("/creative-proposals")
    def propose_local_creatives(body: StepRequest, response: Response,
                                p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            result = preview_proposals(engine, tenant=p.tenant_id, actor=p.actor_id,
                                       run_id=body.run_id, plan=body.plan)
        except (AgentCheckpointDenied, LocalGraphDenied, TraceDraftDenied, ProposalDenied) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except EvidenceNotFound:
            raise HTTPException(status_code=422, detail="CREATIVE_REFERENCE_NOT_VERIFIED") from None
        response.headers["Cache-Control"] = "private, no-store"
        return result

    @router.post("/creative-proposal-draft", response_model=DesignDocument, status_code=201)
    def accept_local_proposal(body: ProposalDraftRequest, response: Response,
                              p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            doc = accept_proposal(engine, tenant=p.tenant_id, actor=p.actor_id,
                                  run_id=body.run_id, plan=body.plan,
                                  proposal_sha256=body.proposal_sha256, document_id=body.document_id)
        except (AgentCheckpointDenied, LocalGraphDenied, TraceDraftDenied, ProposalDenied) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except EvidenceNotFound:
            raise HTTPException(status_code=422, detail="CREATIVE_REFERENCE_NOT_VERIFIED") from None
        except StudioError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.code) from None
        response.headers["ETag"] = studio_etag(doc)
        response.headers["Cache-Control"] = "private, no-store"
        return doc

    return router
