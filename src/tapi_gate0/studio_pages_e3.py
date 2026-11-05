"""IMP-182/183 — immutable revision restoration and carousel page editing.

Tenant-scoped, draft-only operations. Each change uses the existing
StudioCanvasStore._change transaction and optimistic current-version lock.
No remote media, publication or paid work.
"""
from __future__ import annotations

from copy import deepcopy

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .domain import Id
from .studio_e1 import DesignDocument, StudioError, studio_versions
from .studio_canvas_c2 import StudioCanvasStore


class _PageChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    page_id: Id


class DuplicatePage(_PageChange):
    new_page_id: Id


class DeletePage(_PageChange):
    pass


class ReorderPage(_PageChange):
    target_index: int = Field(ge=0, le=9)


class RestoreVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    restore_version: int = Field(ge=1)


class StudioPagesService:
    def __init__(self, engine):
        self.canvas = StudioCanvasStore(engine)

    @staticmethod
    def _carousel(raw):
        if raw["platform_intent"] != "instagram_carousel":
            raise StudioError("STUDIO_CAROUSEL_REQUIRED", 409)

    @staticmethod
    def _find(raw, page_id):
        for index, page in enumerate(raw["pages"]):
            if page["id"] == page_id:
                return index
        raise StudioError("STUDIO_PAGE_NOT_FOUND", 404)

    def duplicate(self, tenant: str, actor: str, document_id: str,
                  request: DuplicatePage) -> DesignDocument:
        def transform(raw, _db):
            self._carousel(raw)
            if len(raw["pages"]) >= 10:
                raise StudioError("STUDIO_PAGE_LIMIT", 409)
            pos = self._find(raw, request.page_id)
            if any(page["id"] == request.new_page_id for page in raw["pages"]):
                raise StudioError("STUDIO_PAGE_ALREADY_EXISTS", 409)
            duplicate = deepcopy(raw["pages"][pos])
            duplicate["id"] = request.new_page_id
            raw["pages"].insert(pos + 1, duplicate)
        return self.canvas._change(tenant, actor, document_id,
                                   request.expected_version, transform)

    def delete(self, tenant: str, actor: str, document_id: str,
               request: DeletePage) -> DesignDocument:
        def transform(raw, _db):
            self._carousel(raw)
            if len(raw["pages"]) < 2:
                raise StudioError("STUDIO_LAST_PAGE_REQUIRED", 409)
            raw["pages"].pop(self._find(raw, request.page_id))
        return self.canvas._change(tenant, actor, document_id,
                                   request.expected_version, transform)

    def reorder(self, tenant: str, actor: str, document_id: str,
                request: ReorderPage) -> DesignDocument:
        def transform(raw, _db):
            self._carousel(raw)
            src = self._find(raw, request.page_id)
            if request.target_index >= len(raw["pages"]):
                raise StudioError("STUDIO_PAGE_INDEX_OUT_OF_RANGE", 422)
            if src == request.target_index:
                raise StudioError("STUDIO_PAGE_ORDER_UNCHANGED", 409)
            page = raw["pages"].pop(src)
            raw["pages"].insert(request.target_index, page)
        return self.canvas._change(tenant, actor, document_id,
                                   request.expected_version, transform)

    def restore(self, tenant: str, actor: str, document_id: str,
                request: RestoreVersion) -> DesignDocument:
        def transform(raw, db):
            if request.restore_version >= request.expected_version:
                raise StudioError("STUDIO_RESTORE_REQUIRES_HISTORICAL_VERSION", 409)
            previous = db.execute(select(studio_versions.c.payload).where(
                studio_versions.c.tenant_id == tenant,
                studio_versions.c.document_id == document_id,
                studio_versions.c.version == request.restore_version,
            )).scalar_one_or_none()
            if previous is None:
                raise StudioError("STUDIO_VERSION_NOT_FOUND", 404)
            historical = DesignDocument.model_validate_json(previous).model_dump()
            # Restoring never restores a prior editorial/rights approval.
            historical.update(approval_status="draft", rights_status="pending_review",
                              reference_status="unverified")
            raw.clear()
            raw.update(historical)
        return self.canvas._change(tenant, actor, document_id,
                                   request.expected_version, transform)
