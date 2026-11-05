"""Authenticated CAP-023 draft document API. No external publish/render."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header
from pydantic import BaseModel, ConfigDict

from .identity import IdentityFailure, Principal
from .studio_e1 import CreativeSpec, DesignDocument, StudioError, StudioStore, TextLayerPatch
from .studio_canvas_c2 import (StudioCanvasStore, UploadPNG, AssetRecord, PlaceImage, MoveLayer, LayerOrder)
from .studio_pages_e3 import StudioPagesService, DuplicatePage, DeletePage, ReorderPage, RestoreVersion
from .studio_video_e5 import (StoryboardStore, StoryboardDocument, CreateStoryboard, UpdateStoryboard)
from .studio_e4 import (studio_etag, assert_etag, version_diff, ProposedTextEdit,
                        ApplyTextProposal, preview_text_proposal, apply_text_proposal)


class CreateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str
    spec: CreativeSpec


def router_for_studio(identity, store: StudioStore):
    router = APIRouter(prefix="/v1/studio", tags=["Editable creative drafts"])
    canvas_store = StudioCanvasStore(store.engine)
    pages_service = StudioPagesService(store.engine)
    video = StoryboardStore(store.engine)

    def principal(request: Request) -> Principal:
        value = request.headers.get("Authorization", "")
        scheme, _, token = value.partition(" ")
        if scheme.lower() != "bearer" or not token or " " in token:
            raise IdentityFailure()
        return identity.resolve(token)

    def as_http(exc: StudioError):
        raise HTTPException(status_code=exc.status, detail=exc.code) from exc

    def with_etag(doc: DesignDocument, response: Response):
        response.headers["ETag"] = studio_etag(doc)
        response.headers["Cache-Control"] = "private, no-store"
        return doc

    def check_write(tenant: str, document_id: str, expected_version: int,
                    if_match: str | None):
        # Old clients remain compatible; new browser sends If-Match on every write.
        assert_etag(store.get(tenant, document_id), if_match, expected_version)


    @router.post("/documents", response_model=DesignDocument, status_code=201)
    def create_draft(body: CreateDraft, response: Response, p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return with_etag(store.create(p.tenant_id, p.actor_id, body.spec, body.document_id), response)
        except StudioError as exc:
            as_http(exc)

    @router.get("/documents/{document_id}", response_model=DesignDocument)
    def latest(document_id: str, response: Response, p: Principal = Depends(principal)):
        try:
            return with_etag(store.get(p.tenant_id, document_id), response)
        except StudioError as exc:
            as_http(exc)

    @router.get("/documents/{document_id}/versions/diff")
    def compare_versions(document_id: str, from_version: int, to_version: int,
                         p: Principal = Depends(principal)):
        try:
            return version_diff(store, p.tenant_id, document_id, from_version, to_version)
        except StudioError as exc:
            as_http(exc)

    @router.get("/documents/{document_id}/versions/{version}",
                response_model=DesignDocument)
    def version(document_id: str, version: int, response: Response, p: Principal = Depends(principal)):
        if version < 1:
            raise HTTPException(status_code=422, detail="STUDIO_INVALID_VERSION")
        try:
            return with_etag(store.get(p.tenant_id, document_id, version), response)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/edit-proposals/preview")
    def preview_edit(document_id: str, payload: ProposedTextEdit,
                     p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return preview_text_proposal(store, p.tenant_id, document_id, payload)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/edit-proposals/apply",
                 response_model=DesignDocument)
    def apply_edit(document_id: str, payload: ApplyTextProposal, response: Response,
                   if_match: str | None = Header(default=None, alias="If-Match"),
                   p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return with_etag(apply_text_proposal(store, p.tenant_id, p.actor_id,
                document_id, payload, if_match), response)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/text-patches",
                 response_model=DesignDocument)
    def edit(document_id: str, patch: TextLayerPatch,
             response: Response,
             if_match: str | None = Header(default=None, alias="If-Match"),
             p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            check_write(p.tenant_id, document_id, patch.expected_version, if_match)
            return with_etag(store.patch_text_layer(p.tenant_id, p.actor_id, document_id, patch), response)
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
                  response: Response,
             if_match: str | None = Header(default=None, alias="If-Match"),
             p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            check_write(p.tenant_id, document_id, payload.expected_version, if_match)
            return with_etag(canvas_store.add_image(p.tenant_id, p.actor_id, document_id, payload), response)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/geometry",
                 response_model=DesignDocument)
    def adjust_geometry(document_id: str, payload: MoveLayer,
                        response: Response,
             if_match: str | None = Header(default=None, alias="If-Match"),
             p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            check_write(p.tenant_id, document_id, payload.expected_version, if_match)
            return with_etag(canvas_store.move(p.tenant_id, p.actor_id, document_id, payload), response)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/order", response_model=DesignDocument)
    def reorder(document_id: str, payload: LayerOrder,
                response: Response,
             if_match: str | None = Header(default=None, alias="If-Match"),
             p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            check_write(p.tenant_id, document_id, payload.expected_version, if_match)
            return with_etag(canvas_store.order(p.tenant_id, p.actor_id, document_id, payload), response)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/pages/duplicate", response_model=DesignDocument)
    def duplicate_page(document_id: str, payload: DuplicatePage,
                       response: Response,
             if_match: str | None = Header(default=None, alias="If-Match"),
             p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            check_write(p.tenant_id, document_id, payload.expected_version, if_match)
            return with_etag(pages_service.duplicate(p.tenant_id, p.actor_id, document_id, payload), response)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/pages/delete", response_model=DesignDocument)
    def delete_page(document_id: str, payload: DeletePage,
                    response: Response,
             if_match: str | None = Header(default=None, alias="If-Match"),
             p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            check_write(p.tenant_id, document_id, payload.expected_version, if_match)
            return with_etag(pages_service.delete(p.tenant_id, p.actor_id, document_id, payload), response)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/pages/reorder", response_model=DesignDocument)
    def reorder_page(document_id: str, payload: ReorderPage,
                     response: Response,
             if_match: str | None = Header(default=None, alias="If-Match"),
             p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            check_write(p.tenant_id, document_id, payload.expected_version, if_match)
            return with_etag(pages_service.reorder(p.tenant_id, p.actor_id, document_id, payload), response)
        except StudioError as exc:
            as_http(exc)

    @router.post("/documents/{document_id}/versions/restore", response_model=DesignDocument)
    def restore_version(document_id: str, payload: RestoreVersion,
                        response: Response,
             if_match: str | None = Header(default=None, alias="If-Match"),
             p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            check_write(p.tenant_id, document_id, payload.expected_version, if_match)
            return with_etag(pages_service.restore(p.tenant_id, p.actor_id, document_id, payload), response)
        except StudioError as exc:
            as_http(exc)

    @router.post("/storyboards", response_model=StoryboardDocument, status_code=201)
    def create_storyboard(payload: CreateStoryboard, p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return video.create(p.tenant_id, p.actor_id, payload)
        except StudioError as exc:
            as_http(exc)

    @router.get("/storyboards/{storyboard_id}", response_model=StoryboardDocument)
    def get_storyboard(storyboard_id: str, p: Principal = Depends(principal)):
        try:
            return video.get(p.tenant_id, storyboard_id)
        except StudioError as exc:
            as_http(exc)

    @router.get("/storyboards/{storyboard_id}/versions/{version}", response_model=StoryboardDocument)
    def get_storyboard_version(storyboard_id: str, version: int,
                               p: Principal = Depends(principal)):
        if version < 1:
            raise HTTPException(status_code=422, detail="STORYBOARD_INVALID_VERSION")
        try:
            return video.get(p.tenant_id, storyboard_id, version)
        except StudioError as exc:
            as_http(exc)

    @router.post("/storyboards/{storyboard_id}/timeline", response_model=StoryboardDocument)
    def edit_storyboard(storyboard_id: str, payload: UpdateStoryboard,
                        p: Principal = Depends(principal)):
        if p.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)
        try:
            return video.update(p.tenant_id, p.actor_id, storyboard_id, payload)
        except StudioError as exc:
            as_http(exc)

    return router
