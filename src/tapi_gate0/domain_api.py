"""Executable local development API: synthetic-only and authenticated.

No network integrations, automatic publication, campaigns, CRM, or source grants.
The same contracts can later be carried into a properly authenticated production API.
"""
from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, ConfigDict, Field

from .domain import (
    AccessDecisionResponse, ContentCreate, ContentItem, CreativeCreate, CreativeVersion,
    Creator, CreatorCreate, DomainEvent, Insight, InsightCreate, LocalOperationRequest,
    MetricsCreate, Origin, ProblemDetail, RankingRequest, RankingResult, RubricAssessment,
    RubricAssessmentCreate, DOMAIN_ENTITIES,
)
from .policy import decide
from .storage import LocalDomainStore, DomainNotFound, DomainIntegrityError, DuplicateDomainId


class DomainAPIError(Exception):
    def __init__(self, status_code: int, code: str, detail: str):
        self.status_code,self.code,self.detail=status_code,code,detail


def forbidden(detail="external sources and operations remain unauthorized"):
    raise DomainAPIError(403,"SOURCE_PERMISSION_DENIED",detail)


def dev_authorized(request: Request, x_tapi_local_key: Annotated[str | None, Header()] = None):
    key = request.app.state.local_domain_key
    if request.client is None or request.client.host not in {"testclient","127.0.0.1","::1"}:
        raise DomainAPIError(403,"LOCAL_ONLY","local development API is restricted to loopback")
    if not key or not x_tapi_local_key or not secrets.compare_digest(key, x_tapi_local_key):
        raise DomainAPIError(401,"INVALID_LOCAL_KEY","provide the configured local development key")
    return "local-research"


router=APIRouter(prefix="/v1",tags=["Local synthetic domain"],dependencies=[Depends(dev_authorized)])


def store(request:Request)->LocalDomainStore:
    return request.app.state.local_domain_store


def guard(item, tenant):
    if item.tenant_id != tenant:
        raise DomainAPIError(403,"TENANT_MISMATCH","tenant identifier does not match authenticated principal")


def synthetic_only(origin:Origin):
    if origin != Origin.SYNTHETIC:
        forbidden("external content cannot be imported before verified rights and connector authorization")


@router.get("/domain/catalog")
def catalog(tenant: Annotated[str,Depends(dev_authorized)]):
    return {"tenant_id":tenant,"entities":DOMAIN_ENTITIES,"active_source":"synthetic_local",
            "external_actions_enabled":False,"budget_brl":0,
            "working_operations":["creators","content","metrics","rubric","ranking","insights","creatives","lineage","events"],
            "not_yet_operational":["external_collection","publishing","paid_campaigns","crm","production_auth","model_inference"]}


@router.post("/creators",response_model=Creator,status_code=status.HTTP_201_CREATED,
             responses={401:{"model":ProblemDetail},403:{"model":ProblemDetail},409:{"model":ProblemDetail}})
def create_creator(payload:CreatorCreate,request:Request,tenant:Annotated[str,Depends(dev_authorized)]):
    guard(payload,tenant); synthetic_only(payload.origin)
    return store(request).create_creator(payload)


@router.get("/creators/{creator_id}",response_model=Creator)
def get_creator(creator_id:str,request:Request,tenant:Annotated[str,Depends(dev_authorized)]):
    return store(request).creator(tenant,creator_id)


@router.post("/content",response_model=ContentItem,status_code=201)
def create_content(payload:ContentCreate,request:Request,tenant:Annotated[str,Depends(dev_authorized)]):
    guard(payload,tenant); synthetic_only(payload.origin)
    return store(request).create_content(payload)


@router.get("/content/{content_id}",response_model=ContentItem)
def get_content(content_id:str,request:Request,tenant:Annotated[str,Depends(dev_authorized)]):
    return store(request).content(tenant,content_id)


@router.post("/content/{content_id}/metrics",response_model=MetricsCreate,status_code=201)
def append_metrics(content_id:str,payload:MetricsCreate,request:Request,tenant:Annotated[str,Depends(dev_authorized)]):
    guard(payload,tenant)
    if payload.content_id != content_id:
        raise DomainAPIError(422,"PATH_PAYLOAD_MISMATCH","content_id in payload must match path")
    return store(request).create_metrics(payload)


@router.post("/content/{content_id}/assessments",response_model=RubricAssessment,status_code=201)
def append_assessment(content_id:str,payload:RubricAssessmentCreate,request:Request,tenant:Annotated[str,Depends(dev_authorized)]):
    guard(payload,tenant)
    if payload.content_id != content_id:
        raise DomainAPIError(422,"PATH_PAYLOAD_MISMATCH","content_id in payload must match path")
    return store(request).create_assessment(payload)


@router.get("/content/{content_id}/assessments/latest",response_model=RubricAssessment)
def latest_assessment(content_id:str,request:Request,tenant:Annotated[str,Depends(dev_authorized)]):
    return store(request).latest_assessment(tenant,content_id)


@router.post("/analyses/rankings",response_model=RankingResult)
def compute_ranking(payload:RankingRequest,request:Request,tenant:Annotated[str,Depends(dev_authorized)]):
    guard(payload,tenant); synthetic_only(payload.origin)
    return store(request).ranking(payload)


@router.post("/insights",response_model=Insight,status_code=201)
def create_insight(payload:InsightCreate,request:Request,tenant:Annotated[str,Depends(dev_authorized)]):
    guard(payload,tenant)
    if payload.analysis_kind=="causal_experiment":
        raise DomainAPIError(403,"CAUSAL_EVIDENCE_REQUIRED","synthetic descriptive flow cannot assert causal experiment")
    return store(request).create_insight(payload)


@router.get("/insights/{insight_id}",response_model=Insight)
def get_insight(insight_id:str,request:Request,tenant:Annotated[str,Depends(dev_authorized)]):
    return store(request).insight(tenant,insight_id)


@router.post("/creatives",response_model=CreativeVersion,status_code=201)
def create_creative(payload:CreativeCreate,request:Request,tenant:Annotated[str,Depends(dev_authorized)]):
    guard(payload,tenant)
    if payload.status != "draft":
        raise DomainAPIError(403,"EDITORIAL_APPROVAL_REQUIRED","local fixture creatives must start as draft")
    return store(request).create_creative(payload)


@router.get("/creatives/{creative_id}",response_model=CreativeVersion)
def get_creative(creative_id:str,request:Request,tenant:Annotated[str,Depends(dev_authorized)]):
    return store(request).creative(tenant,creative_id)


@router.get("/creatives/{creative_id}/lineage")
def get_lineage(creative_id:str,request:Request,tenant:Annotated[str,Depends(dev_authorized)]):
    return store(request).lineage(tenant,creative_id)


@router.get("/events")
def list_events(request:Request,tenant:Annotated[str,Depends(dev_authorized)],after_seq:int=0,limit:int=100):
    if after_seq<0 or not (1<=limit<=200):
        raise DomainAPIError(422,"INVALID_CURSOR","after_seq must be nonnegative and limit between 1 and 200")
    return {"tenant_id":tenant,"events":store(request).events(tenant,after_seq,limit)}


@router.post("/policy/check",response_model=AccessDecisionResponse)
def check_source_policy(payload:LocalOperationRequest):
    d=decide(payload.source,payload.operation)
    return AccessDecisionResponse(permitted=d.permitted,code=d.code,reason=d.reason)


class ExternalOperation(BaseModel):
    model_config=ConfigDict(extra="forbid")
    tenant_id: str
    source: str
    request_id: str = Field(min_length=1)


@router.post("/collections",responses={403:{"model":ProblemDetail}})
def blocked_collect(payload:ExternalOperation,tenant:Annotated[str,Depends(dev_authorized)]):
    guard(payload,tenant)
    forbidden("no authorized third-party collection connector is configured")


@router.post("/publications",responses={403:{"model":ProblemDetail}})
def blocked_publish(payload:ExternalOperation,tenant:Annotated[str,Depends(dev_authorized)]):
    guard(payload,tenant)
    forbidden("publishing requires verified platform rights and explicit per-action approval")


@router.post("/campaigns",responses={403:{"model":ProblemDetail}})
def blocked_campaign(payload:ExternalOperation,tenant:Annotated[str,Depends(dev_authorized)]):
    guard(payload,tenant)
    forbidden("paid campaigns cannot run under the mandatory zero-spend policy")


@router.post("/crm/conversions",responses={403:{"model":ProblemDetail}})
def blocked_crm(payload:ExternalOperation,tenant:Annotated[str,Depends(dev_authorized)]):
    guard(payload,tenant)
    forbidden("CRM access and personal data processing are not authorized")
