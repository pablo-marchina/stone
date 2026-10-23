"""Bootstrap + opt-in local-only unified-domain application.

No public deployment should expose the local fixture API. No external operations.
"""
from __future__ import annotations

import os
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .readiness import status
from .domain_api import DomainAPIError, router
from .storage import DomainIntegrityError, DomainNotFound, DuplicateDomainId, LocalDomainStore


def create_app(*, local_domain:bool=False, dev_key:str|None=None, db_path:str=":memory:") -> FastAPI:
    if local_domain:
        if not dev_key or len(dev_key) < 32:
            raise ValueError("local development API requires a strong 32+ character key")
    app = FastAPI(title="TAPI Stone — local domain contracts" if local_domain else "TAPI Gate 0 Bootstrap",
                  version="0.2.0" if local_domain else "0.1.0",
                  docs_url="/docs" if local_domain else None,
                  redoc_url=None, openapi_url="/openapi.json" if local_domain else None)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status":"ok","purpose":"local_gate0_bootstrap"}

    @app.get("/v1/gate0/status")
    def gate0_status() -> dict:
        return status()

    if local_domain:
        app.state.local_domain_key=dev_key
        app.state.local_domain_store=LocalDomainStore(db_path)
        app.include_router(router)

        @app.exception_handler(DomainAPIError)
        async def api_problem(_:Request,exc:DomainAPIError):
            return JSONResponse(status_code=exc.status_code,content={"type":"about:blank","title":exc.code,
                "status":exc.status_code,"detail":exc.detail,"code":exc.code},media_type="application/problem+json")

        @app.exception_handler(DomainNotFound)
        async def domain_not_found(_:Request,exc:DomainNotFound):
            return JSONResponse(status_code=404,content={"type":"about:blank","title":"NOT_FOUND","status":404,
                "detail":str(exc),"code":"NOT_FOUND"},media_type="application/problem+json")

        @app.exception_handler(DuplicateDomainId)
        async def duplicate(_:Request,exc:DuplicateDomainId):
            return JSONResponse(status_code=409,content={"type":"about:blank","title":"DUPLICATE_ID","status":409,
                "detail":str(exc),"code":"DUPLICATE_ID"},media_type="application/problem+json")

        @app.exception_handler(DomainIntegrityError)
        async def domain_integrity(_:Request,exc:DomainIntegrityError):
            return JSONResponse(status_code=422,content={"type":"about:blank","title":"DOMAIN_INTEGRITY","status":422,
                "detail":str(exc),"code":"DOMAIN_INTEGRITY"},media_type="application/problem+json")

        @app.exception_handler(RequestValidationError)
        async def payload_error(_:Request,exc:RequestValidationError):
            # Deliberately do not echo untrusted payload values in error messages.
            return JSONResponse(status_code=422,content={"type":"about:blank","title":"INVALID_REQUEST","status":422,
                "detail":"request does not satisfy the contract","code":"INVALID_REQUEST"},media_type="application/problem+json")
    return app


_local_enabled = os.environ.get("TAPI_LOCAL_DOMAIN_ENABLE") == "1"
app = create_app(local_domain=_local_enabled,
                 dev_key=os.environ.get("TAPI_LOCAL_DOMAIN_KEY") if _local_enabled else None,
                 db_path=os.environ.get("TAPI_LOCAL_DB", ":memory:"))
