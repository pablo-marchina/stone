"""IMP-074: explicit loopback-only diagnostic binding to the local graph runner.

The application factory is the ONLY opt-in. Production from_environment never
registers this router. No external origin, LLM, media, Studio or publication.
Tenant/actor are taken exclusively from a revocable bearer session.
"""
from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator, ValidationError

from .agent_graph_checkpoints import AgentCheckpointDenied
from .agent_graph_readonly_runner import (
    LocalGraphDenied, LocalGraphPlan, execute_next,
)
from .identity import IdentityFailure, Principal


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

    return router
