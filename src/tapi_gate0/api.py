"""API local de saúde/prontidão. Sem autenticação para uso *somente local*.

NÃO implantar publicamente. App final exigirá identidade, RBAC, tenant isolation.
"""
from fastapi import FastAPI
from .readiness import status

app = FastAPI(title="TAPI Gate 0 Bootstrap", version="0.1.0", docs_url=None, redoc_url=None)

@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "purpose": "local_gate0_bootstrap"}

@app.get("/v1/gate0/status")
def gate0_status() -> dict:
    return status()
