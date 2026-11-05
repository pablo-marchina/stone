"""Authenticated CAP-023 draft document API. No external publish/render."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from .identity import IdentityFailure, Principal
from .studio_e1 import CreativeSpec, DesignDocument, StudioError, StudioStore, TextLayerPatch
from .studio_canvas_c2 import (StudioCanvasStore, UploadPNG, AssetRecord, PlaceImage, MoveLayer, LayerOrder)
from .studio_pages_e3 import StudioPagesService, DuplicatePage, DeletePage, ReorderPage, RestoreVersion


class CreateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str
    spec: CreativeSpec


def router_for_studio(identity, store: StudioStore):
    router = APIRouter(prefix="/v1/studio", tags=["Editable creative drafts"])
    canvas_store = StudioCanvasStore(store.engine)
    pages_service = StudioPagesService(store.engine)

    def principal(request: Request) -> Principal:
        value = request.headers.get("Authorization", "")
        scheme, _, token = value.partition(" ")
        if scheme.lower() != "bearer" or not token or " " in token:
            raise IdentityFailure()
        return identity.resolve(token)

    def as_http(exc: StudioError):
        raise HTTPException(status_code=exc.status, detail=exc.code) from exc

    @router.post("/documents", response_model=DesignDocument, status_code=201)
    def create_draft(body: CreateDraft, p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return store.create(p.tenant_id, p.actor_id, body.spec, body.document_id)
        except StudioError as exc:
            as_http(exc)

    @router.get("/documents/{document_id}", response_model=DesignDocument)
    def latest(document_id: str, p: Principal = Depends(principal)):
        try:
            return store.get(p.tenant_id, document_id)
        except StudioError as exc:
            as_http(exc)

    @router.get("/documents/{document_id}/versions/{version}",
                response_model=DesignDocument)
    def version(document_id: str, version: int, p: Principal = Depends(principal)):
        if version < 1:
            raise HTTPException(status_code=422, detail="STUDIO_INVALID_VERSION")
        try:
            return store.get(p.tenant_id, document_id, version)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/text-patches",
                 response_model=DesignDocument)
    def edit(document_id: str, patch: TextLayerPatch,
             p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return store.patch_text_layer(p.tenant_id, p.actor_id, document_id, patch)
        except StudioError as exc:
            as_http(exc)

    @router.post("/assets/png", response_model=AssetRecord, status_code=201)
    def upload_asset(payload: UploadPNG, p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return canvas_store.save_png(p.tenant_id, p.actor_id, payload)
        except StudioError as exc:
            as_http(exc)

    @router.get("/assets/{asset_id}/binary")
    def asset_bytes(asset_id: str, p: Principal = Depends(principal)):
        try:
            payload = canvas_store.asset_bytes(p.tenant_id, asset_id)
        except StudioError as exc:
            as_http(exc)
        return Response(
            content=payload, media_type="image/png",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @router.post("/documents/{document_id}/image-layers",
                 response_model=DesignDocument)
    def add_image(document_id: str, payload: PlaceImage,
                  p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return canvas_store.add_image(p.tenant_id, p.actor_id, document_id, payload)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/geometry",
                 response_model=DesignDocument)
    def adjust_geometry(document_id: str, payload: MoveLayer,
                        p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return canvas_store.move(p.tenant_id, p.actor_id, document_id, payload)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/order", response_model=DesignDocument)
    def reorder(document_id: str, payload: LayerOrder,
                p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return canvas_store.order(p.tenant_id, p.actor_id, document_id, payload)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/pages/duplicate", response_model=DesignDocument)
    def duplicate_page(document_id: str, payload: DuplicatePage,
                       p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return pages_service.duplicate(p.tenant_id, p.actor_id, document_id, payload)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/pages/delete", response_model=DesignDocument)
    def delete_page(document_id: str, payload: DeletePage,
                    p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return pages_service.delete(p.tenant_id, p.actor_id, document_id, payload)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/pages/reorder", response_model=DesignDocument)
    def reorder_page(document_id: str, payload: ReorderPage,
                     p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return pages_service.reorder(p.tenant_id, p.actor_id, document_id, payload)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/versions/restore", response_model=DesignDocument)
    def restore_version(document_id: str, payload: RestoreVersion,
                        p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return pages_service.restore(p.tenant_id, p.actor_id, document_id, payload)
        except StudioError as exc:
            as_http(exc)

    return router
