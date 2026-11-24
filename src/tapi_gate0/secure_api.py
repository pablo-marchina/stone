"""Secure app mode with database-backed RBAC, revocable sessions and durable events.

Local SQLite is a production-shaped test adapter. PostgreSQL uses the same
SQLAlchemy model, but operational deployment still requires live verification.
"""

import asyncio
import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .api import create_app
from .domain_api import dev_authorized
from .identity import (IdentityFailure, IdentityStore, LoginRequest, SessionResponse,
                       MemberCreate, Principal, permitted)
from .sa_store import SqlDomainStore, engine_for
from .ingestion import IngestionStore, ConnectorError, router_for_ingestion
from .discovery_ingestion import router_for_discovery_ingestion
from .discovery_technical import router_for_discovery_technical
from .corpus import router_for_corpus
from .corpus_inventory import router_for_inventory
from . import asset_rights_registry, asset_lineage_index, asset_jobs, asset_derived_payloads  # register schema only; no trust configured
from .corpus_caption_replay import CaptionReplay, config_from_env as replay_config_from_env
from .ui import router_for_authenticated_view
from .agent_api_e1 import router_for_evidence_agent
from .agent_graph_local_api import router_for_local_graph_diagnostic
from .creative_reference_pep_a05 import CreativeReferencePEP
from .creative_reference_trust_a05 import load_reference_trust
from .studio_e1 import StudioStore  # registers studio tables before schema initialization
from .studio_api import router_for_studio
from .evidence_lab import EvidenceLab, config_from_env, router_for_lab


def _token(request:Request):
    value=request.headers.get("authorization","")
    scheme,_,token=value.partition(" ")
    if scheme.lower()!="bearer" or not token or " " in token:
        raise IdentityFailure()
    return token


def create_secure_app(database_url:str,*, initialize_schema:bool=False, allow_http_local:bool=False, evidence_lab:EvidenceLab|None=None, caption_replay_config=None, creative_reference_authorities=None, enable_local_graph_diagnostic:bool=False) -> FastAPI:
    # Explicit test/local factory opt-in only, never read from environment.
    # The operational from_environment path cannot enable this endpoint.
    if enable_local_graph_diagnostic and (
        not allow_http_local or not initialize_schema
        or not database_url.startswith("sqlite:///")
    ):
        raise ValueError("LOCAL_GRAPH_DIAGNOSTIC_REQUIRES_LOCAL_SQLITE_FIXTURE")
    engine=engine_for(database_url)
    domain=SqlDomainStore(engine)
    if initialize_schema:
        domain.initialize()  # EXPLICIT offline / test only; use a reviewed migration for deployed DB.
    identity=IdentityStore(engine)
    ingestion=IngestionStore(engine)
    # Reuse existing validated domain endpoints but substitute trusted auth dependency.
    app=create_app(local_domain=True,dev_key="__secure_mode_never_use_as_key__123",db_path=":memory:")
    old_store=app.state.local_domain_store
    old_store.conn.close()
    app.state.local_domain_store=domain
    app.state.identity_store=identity
    app.state.ingestion_store=ingestion
    app.state.secure_mode=True
    # First-party UI is served same-origin to avoid CORS, cookies or paid identity providers.
    # Static files carry no tenant data; all data APIs require revocable bearer sessions.
    web_dir = Path(__file__).resolve().parent / "web"
    if web_dir.is_dir():
        app.mount("/app", StaticFiles(directory=web_dir, html=True), name="product-ui")

        @app.get("/", include_in_schema=False)
        def product_home():
            return RedirectResponse(url="/app/", status_code=307)

    @app.middleware("http")
    async def require_tls(request:Request,call_next):
        if request.url.scheme!="https":
            if not allow_http_local or (request.client is not None and request.client.host not in
                                        {"testclient","127.0.0.1","::1"}):
                return JSONResponse(status_code=403, content={"code":"HTTPS_REQUIRED"},
                                    headers={"Cache-Control":"no-store"})
        response=await call_next(request)
        # Enforce no-store globally without erasing explicitly private responses.
        # Never preserve cacheable directives supplied by an endpoint.
        directives={part.strip().lower() for part in response.headers.get("Cache-Control","").split(",")}
        response.headers["Cache-Control"]="private, no-store" if "private" in directives else "no-store"
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Referrer-Policy"]="no-referrer"
        response.headers["X-Frame-Options"]="DENY"
        response.headers["Content-Security-Policy"]=(
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; font-src 'self'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        if allow_http_local and request.url.path == "/app/demo.html":
            # Only the opt-in local demo uses verified MP4 object URLs.
            response.headers["Content-Security-Policy"] += "; media-src blob:"
        return response
    app.title="TAPI Stone — Secure Unified Domain"
    app.version="0.3.0"

    def secure_identity(request:Request):
        principal=identity.resolve(_token(request))
        if not permitted(principal,request.method,request.url.path):
            raise IdentityFailure("FORBIDDEN",403)
        request.state.principal=principal
        return principal.tenant_id

    app.dependency_overrides[dev_authorized]=secure_identity

    def current_principal(request:Request):
        return identity.resolve(_token(request))

    @app.exception_handler(IdentityFailure)
    async def handle_identity_error(_request:Request,exc:IdentityFailure):
        return JSONResponse(status_code=exc.status,content={
            "type":"about:blank","title":exc.code,"status":exc.status,
            "detail":"authentication or authorization denied","code":exc.code},
            headers={"WWW-Authenticate":"Bearer"} if exc.status==401 else {},
            media_type="application/problem+json")

    app.include_router(router_for_authenticated_view(current_principal))
    app.include_router(router_for_ingestion(identity,ingestion))
    app.include_router(router_for_discovery_ingestion(identity,ingestion))
    app.include_router(router_for_discovery_technical(identity,ingestion))
    app.include_router(router_for_corpus(identity,engine))
    if caption_replay_config is not None and not allow_http_local:
        raise ValueError('CAPTION_REPLAY_LOOPBACK_MODE_REQUIRED')
    caption_replay=CaptionReplay(engine,caption_replay_config) if caption_replay_config is not None else None
    app.include_router(router_for_inventory(current_principal,engine,caption_replay))
    app.include_router(router_for_evidence_agent(
        identity, domain,
        creative_pep=(CreativeReferencePEP(engine, creative_reference_authorities)
                      if creative_reference_authorities is not None else None),
    ))
    app.include_router(router_for_studio(identity,StudioStore(engine)))
    if enable_local_graph_diagnostic:
        app.include_router(router_for_local_graph_diagnostic(identity, engine))
    app.include_router(router_for_lab(current_principal,evidence_lab))

    @app.exception_handler(ConnectorError)
    async def handle_connector_error(_request:Request,exc:ConnectorError):
        return JSONResponse(status_code=exc.status,content={
            "type":"about:blank","title":exc.code,"status":exc.status,
            "detail":"official integration request was denied or failed", "code":exc.code},
            media_type="application/problem+json")

    @app.post("/v1/auth/sessions",response_model=SessionResponse,tags=["Identity"])
    def login(request:LoginRequest):
        return identity.login(request.username,request.password,request.tenant_id)

    @app.get("/v1/auth/me",response_model=Principal,tags=["Identity"])
    def me(principal:Annotated[Principal,Depends(current_principal)]):
        return principal

    @app.post("/v1/auth/logout",status_code=204,tags=["Identity"])
    def logout(request:Request,principal:Annotated[Principal,Depends(current_principal)]):
        identity.revoke(_token(request),principal)

    @app.post("/v1/admin/members",status_code=201,tags=["Identity"])
    def add_member(payload:MemberCreate,principal:Annotated[Principal,Depends(current_principal)]):
        return identity.add_member(principal,payload)

    @app.get("/v1/events/stream",tags=["Events"])
    async def stream_events(request:Request,principal:Annotated[Principal,Depends(current_principal)],
                            after_seq:int=0,max_events:int=0):
        if after_seq<0 or max_events<0 or max_events>200:
            return JSONResponse(status_code=422,content={"code":"INVALID_CURSOR"})
        cursor=request.headers.get("last-event-id")
        if cursor is not None:
            if not cursor.isdecimal():return JSONResponse(status_code=422,content={"code":"INVALID_CURSOR"})
            after_seq=max(after_seq,int(cursor))
        async def events():
            pos=after_seq; emitted=0; idle=0
            while not await request.is_disconnected():
                # Never trust stale session on an open stream: revalidate at each poll.
                try: identity.resolve(_token(request))
                except IdentityFailure:break
                chunk=await run_in_threadpool(domain.events,principal.tenant_id,pos,100)
                if chunk:
                    for event in chunk:
                        pos=event["seq"]
                        # Event payload is intentionally constrained to synthetic metadata.
                        import json
                        item=json.dumps(event,ensure_ascii=False,separators=(",",":"))
                        yield f"id: {pos}\nevent: domain_event\ndata: {item}\n\n"
                        emitted+=1
                        if max_events and emitted>=max_events:return
                    idle=0
                else:
                    await asyncio.sleep(0.25)
                    idle+=1
                    if idle%60==0:yield ": keepalive\n\n"
        return StreamingResponse(events(),media_type="text/event-stream",headers={
            "Cache-Control":"no-cache, no-store", "X-Accel-Buffering":"no"})

    def secure_openapi():
        if app.openapi_schema is None:
            spec=get_openapi(title=app.title,version=app.version,routes=app.routes)
            spec.setdefault("components",{}).setdefault("securitySchemes",{})["BearerAuth"]={
                "type":"http","scheme":"bearer","bearerFormat":"opaque"}
            for url,actions in spec.get("paths",{}).items():
                for method,operation in actions.items():
                    if not isinstance(operation,dict):continue
                    operation["parameters"]=[p for p in operation.get("parameters",[]) if
                        p.get("name")!="x-tapi-local-key"]
                    if url.startswith("/v1/") and url not in {"/v1/auth/sessions","/v1/gate0/status"}:
                        operation["security"]=[{"BearerAuth":[]}]
            app.openapi_schema=spec
        return app.openapi_schema
    app.openapi=secure_openapi
    return app


def from_environment():
    url=os.environ.get("TAPI_DATABASE_URL")
    if not url:raise RuntimeError("TAPI_DATABASE_URL is required for secure mode")
    lab_config=config_from_env(os.environ)
    if lab_config is not None and os.environ.get("TAPI_ALLOW_HTTP_LOOPBACK")!="1":
        raise ValueError("EVIDENCE_LAB_LOOPBACK_MODE_REQUIRED")
    lab=EvidenceLab(lab_config) if lab_config is not None else None
    # A trusted host may explicitly enable externally pinned PUBLIC anchors.
    # No trust vars: None -> all external creative references stay denied.
    # Partial/malformed settings fail application startup, never downgrade.
    reference_anchors=load_reference_trust(
        os.environ,repository_root=Path(__file__).resolve().parents[2],
    )
    return create_secure_app(url,initialize_schema=False,
        allow_http_local=os.environ.get("TAPI_ALLOW_HTTP_LOOPBACK")=="1",evidence_lab=lab,
        caption_replay_config=replay_config_from_env(os.environ),
        creative_reference_authorities=reference_anchors)
