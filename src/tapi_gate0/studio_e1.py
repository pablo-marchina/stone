"""CAP-023 / IMP-174..182: editable document kernel, no renderer or AI claims.

This first slice supports static text layers, draft-only persisted versions,
strict tenant isolation and optimistic locking. A preview/export is NOT present.
User-provided reference IDs are not treated as validated factual sources.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import (
    Table, Column, String, Integer, Text, ForeignKeyConstraint,
    select, insert, update,
)
from sqlalchemy.exc import IntegrityError

from .domain import Id
from .sa_store import metadata, tenants

DESIGN_SCHEMA = "design-document.v1"
HEX = r"^#[0-9A-Fa-f]{6}$"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreativeSpec(Model):
    schema_version: Literal["creative-spec.v1"] = "creative-spec.v1"
    spec_id: Id
    tenant_id: Id
    objective: str = Field(min_length=8, max_length=500)
    headline: str = Field(min_length=1, max_length=250)
    body: str = Field(min_length=1, max_length=2000)
    cta: str = Field(min_length=1, max_length=250)
    platform_intent: Literal["instagram_feed", "instagram_carousel"] = "instagram_feed"
    reference_content_ids: list[Id] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def unique_references(self):
        if len(set(self.reference_content_ids)) != len(self.reference_content_ids):
            raise ValueError("STUDIO_DUPLICATE_REFERENCE")
        return self


class Canvas(Model):
    width: int = Field(default=1080, ge=320, le=4096)
    height: int = Field(default=1350, ge=320, le=4096)
    background: str = Field(default="#FFFFFF", pattern=HEX)


class TextStyle(Model):
    font_family: Literal["sans-serif"] = "sans-serif"
    font_size: int = Field(default=64, ge=12, le=256)
    color: str = Field(default="#171717", pattern=HEX)


class TextLayer(Model):
    id: Id
    kind: Literal["text"] = "text"
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=2000)
    style: TextStyle = Field(default_factory=TextStyle)
    origin: Literal["operator_draft", "operator_edit"] = "operator_draft"
    editable: Literal[True] = True


class ImageLayer(Model):
    id: Id
    kind: Literal["image"] = "image"
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    asset_id: Id
    origin: Literal["operator_edit"] = "operator_edit"
    editable: Literal[True] = True


class DesignPage(Model):
    id: Id
    layers: list[TextLayer | ImageLayer] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def unique_layer_ids(self):
        keys = [layer.id for layer in self.layers]
        if len(keys) != len(set(keys)):
            raise ValueError("STUDIO_DUPLICATE_LAYER")
        return self


class DesignDocument(Model):
    schema_version: Literal["design-document.v1"] = DESIGN_SCHEMA
    document_id: Id
    tenant_id: Id
    spec_id: Id
    version: int = Field(ge=1)
    canvas: Canvas
    platform_intent: Literal["instagram_feed", "instagram_carousel"]
    pages: list[DesignPage] = Field(min_length=1, max_length=10)
    reference_content_ids: list[Id] = Field(default_factory=list, max_length=30)
    reference_status: Literal["unverified"] = "unverified"
    rights_status: Literal["pending_review"] = "pending_review"
    approval_status: Literal["draft"] = "draft"
    render_status: Literal["not_implemented"] = "not_implemented"

    @model_validator(mode="after")
    def ensure_layout(self):
        if self.platform_intent == "instagram_feed" and len(self.pages) != 1:
            raise ValueError("STUDIO_FEED_REQUIRES_ONE_PAGE")
        if len({page.id for page in self.pages}) != len(self.pages):
            raise ValueError("STUDIO_DUPLICATE_PAGE")
        for page in self.pages:
            for layer in page.layers:
                if layer.x + layer.w > self.canvas.width or layer.y + layer.h > self.canvas.height:
                    raise ValueError("STUDIO_LAYER_OUTSIDE_CANVAS")
        if len(set(self.reference_content_ids)) != len(self.reference_content_ids):
            raise ValueError("STUDIO_DUPLICATE_REFERENCE")
        return self


class TextLayerPatch(Model):
    page_id: Id
    layer_id: Id
    expected_version: int = Field(ge=1)
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    x: int | None = Field(default=None, ge=0)
    y: int | None = Field(default=None, ge=0)
    w: int | None = Field(default=None, gt=0)
    h: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def nonempty(self):
        if all(getattr(self, name) is None for name in ("text", "x", "y", "w", "h")):
            raise ValueError("STUDIO_PATCH_REQUIRES_CHANGE")
        return self


EDITORIAL_LAYOUT_VERSION = "tapi-editorial-layout.v1"
EDITORIAL_THEMES = {
    "inventory": ("01 / ESTOQUE", "#E5F4E6", "#103B2B", "#087A50"),
    "cashflow": ("02 / FINANÇAS", "#E3EEF9", "#153957", "#245C9B"),
    "service": ("03 / ATENDIMENTO", "#FFF2DF", "#583D21", "#9C530A"),
    "pricing": ("04 / PRECIFICAÇÃO", "#F1E8F8", "#402653", "#75439C"),
    "planning": ("05 / PLANEJAMENTO", "#E5F4F1", "#174A46", "#117A71"),
}


def draft_from_spec(spec: CreativeSpec, document_id: str, *,
                    editorial_template: str | None = None) -> DesignDocument:
    """A deterministic starter layout; not generative AI, preview or export."""
    canvas = Canvas()
    safe_margin = 70
    width = canvas.width - 2 * safe_margin
    page = DesignPage(
        id="page.1",
        layers=[
            TextLayer(id="headline", x=safe_margin, y=100, w=width, h=200,
                      text=spec.headline, style=TextStyle(font_size=72)),
            TextLayer(id="body", x=safe_margin, y=390, w=width, h=440,
                      text=spec.body, style=TextStyle(font_size=44)),
            TextLayer(id="cta", x=safe_margin, y=950, w=width, h=190,
                      text=spec.cta, style=TextStyle(font_size=56)),
        ],
    )
    if editorial_template is not None:
        # Trusted synthetic proposal path only. All visual elements are real
        # editable, typed layers, shared by preview and persisted export.
        if editorial_template not in EDITORIAL_THEMES or spec.platform_intent != "instagram_feed":
            raise ValueError("STUDIO_EDITORIAL_TEMPLATE_INVALID")
        label, background, ink, accent = EDITORIAL_THEMES[editorial_template]
        canvas = Canvas(background=background)
        page = DesignPage(id="page.1", layers=[
            TextLayer(id="headline", x=80, y=270, w=920, h=340,
                      text=spec.headline, style=TextStyle(font_size=100, color=ink)),
            TextLayer(id="body", x=80, y=650, w=920, h=320,
                      text=spec.body, style=TextStyle(font_size=52, color=ink)),
            TextLayer(id="cta", x=80, y=1040, w=920, h=160,
                      text=spec.cta, style=TextStyle(font_size=60, color=accent)),
            TextLayer(id="series", x=80, y=85, w=920, h=65,
                      text="GUIA DO EMPREENDEDOR", style=TextStyle(font_size=36, color=accent)),
            TextLayer(id="section", x=80, y=170, w=920, h=65,
                      text=label, style=TextStyle(font_size=40, color=accent)),
        ])
    return DesignDocument(
        document_id=document_id, tenant_id=spec.tenant_id,
        spec_id=spec.spec_id, version=1, canvas=canvas,
        platform_intent=spec.platform_intent,
        pages=[page], reference_content_ids=spec.reference_content_ids,
    )


studio_documents = Table(
    "studio_documents", metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("document_id", String(128), primary_key=True),
    Column("spec_id", String(128), nullable=False),
    Column("current_version", Integer, nullable=False),
    ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
)
studio_versions = Table(
    "studio_document_versions", metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("document_id", String(128), primary_key=True),
    Column("version", Integer, primary_key=True),
    Column("payload", Text, nullable=False),
    Column("created_at", String(48), nullable=False),
    Column("edited_by", String(128), nullable=False),
    ForeignKeyConstraint(
        ["tenant_id", "document_id"],
        ["studio_documents.tenant_id", "studio_documents.document_id"],
    ),
)


class StudioError(Exception):
    def __init__(self, code: str, status: int):
        self.code, self.status = code, status
        super().__init__(code)


class StudioStore:
    """Explicit tenant+actor supplied by authenticated server, never caller."""
    def __init__(self, engine):
        self.engine = engine

    def create(self, tenant: str, actor: str, spec: CreativeSpec,
               document_id: str, *, connection=None, editorial_template=None):
        if spec.tenant_id != tenant:
            raise StudioError("STUDIO_TENANT_MISMATCH", 403)
        doc = draft_from_spec(spec, document_id, editorial_template=editorial_template)
        try:
            if connection is None:
                with self.engine.begin() as conn:
                    self._create_on_connection(conn, doc, actor)
            else:
                # Shared, caller-owned transaction: do not commit independently.
                self._create_on_connection(connection, doc, actor)
        except IntegrityError as exc:
            raise StudioError("STUDIO_DOCUMENT_ALREADY_EXISTS_OR_TENANT_MISSING", 409) from exc
        return doc

    @staticmethod
    def _create_on_connection(conn, doc: DesignDocument, actor: str):
        conn.execute(insert(studio_documents).values(
            tenant_id=doc.tenant_id, document_id=doc.document_id,
            spec_id=doc.spec_id, current_version=1,
        ))
        StudioStore._insert_version(conn, doc, actor)

    @staticmethod
    def _insert_version(conn, doc: DesignDocument, actor: str):
        conn.execute(insert(studio_versions).values(
            tenant_id=doc.tenant_id, document_id=doc.document_id,
            version=doc.version, payload=doc.model_dump_json(),
            created_at=datetime.now(timezone.utc).isoformat(), edited_by=actor,
        ))

    def get(self, tenant: str, document_id: str, version: int | None = None):
        with self.engine.connect() as conn:
            if version is None:
                version = conn.execute(select(studio_documents.c.current_version).where(
                    studio_documents.c.tenant_id == tenant,
                    studio_documents.c.document_id == document_id,
                )).scalar_one_or_none()
            if version is None:
                raise StudioError("STUDIO_DOCUMENT_NOT_FOUND", 404)
            payload = conn.execute(select(studio_versions.c.payload).where(
                studio_versions.c.tenant_id == tenant,
                studio_versions.c.document_id == document_id,
                studio_versions.c.version == version,
            )).scalar_one_or_none()
        if payload is None:
            raise StudioError("STUDIO_VERSION_NOT_FOUND", 404)
        return DesignDocument.model_validate_json(payload)

    def patch_text_layer(self, tenant: str, actor: str, document_id: str,
                         patch: TextLayerPatch, *, connection=None,
                         reference_authorizer=None):
        if connection is None:
            with self.engine.begin() as conn:
                return self.patch_text_layer(
                    tenant, actor, document_id, patch, connection=conn,
                    reference_authorizer=reference_authorizer,
                )
        conn = connection
        if conn.engine is not self.engine or not conn.in_transaction():
            raise StudioError("STUDIO_TRANSACTION_REQUIRED", 409)
        # A legacy text patch can never silently reuse a signed reference.
        # Only a trusted per-action callback that revalidates grants inside
        # THIS write transaction may update a draft carrying external grants.
        from .studio_reference_bindings_a05 import studio_reference_bindings
        linked = conn.execute(select(studio_reference_bindings.c.content_id).where(
            studio_reference_bindings.c.tenant_id == tenant,
            studio_reference_bindings.c.document_id == document_id,
        ).limit(1)).first()
        if linked is not None:
            if reference_authorizer is None:
                raise StudioError("STUDIO_SIGNED_REFERENCE_RECHECK_REQUIRED", 403)
            reference_authorizer(conn)
        current = conn.execute(select(studio_documents.c.current_version).where(
            studio_documents.c.tenant_id == tenant,
            studio_documents.c.document_id == document_id,
        )).scalar_one_or_none()
        if current is None:
            raise StudioError("STUDIO_DOCUMENT_NOT_FOUND", 404)
        if current != patch.expected_version:
            raise StudioError("STUDIO_VERSION_CONFLICT", 409)
        payload = conn.execute(select(studio_versions.c.payload).where(
            studio_versions.c.tenant_id == tenant,
            studio_versions.c.document_id == document_id,
            studio_versions.c.version == current,
        )).scalar_one()
        original = DesignDocument.model_validate_json(payload)
        raw = original.model_dump()
        found = False
        for page in raw["pages"]:
            if page["id"] != patch.page_id:
                continue
            for layer in page["layers"]:
                if layer["id"] != patch.layer_id:
                    continue
                found = True
                for attr in ("text", "x", "y", "w", "h"):
                    value = getattr(patch, attr)
                    if value is not None:
                        layer[attr] = value
                layer["origin"] = "operator_edit"
        if not found:
            raise StudioError("STUDIO_LAYER_NOT_FOUND", 404)
        raw["version"] = current + 1
        # Revalidate the entire document after every edit, not just the layer.
        next_doc = DesignDocument.model_validate(raw)
        changed = conn.execute(update(studio_documents).where(
            studio_documents.c.tenant_id == tenant,
            studio_documents.c.document_id == document_id,
            studio_documents.c.current_version == current,
        ).values(current_version=current + 1))
        if changed.rowcount != 1:
            raise StudioError("STUDIO_VERSION_CONFLICT", 409)
        self._insert_version(conn, next_doc, actor)
        return next_doc


# The standalone StudioStore module can be used without importing secure_api.
# Register its signed-reference binding schema eagerly in the shared metadata
# before a local `metadata.create_all()`. This import creates NO tables, grants,
# permissions, migrations or external side effects.
from . import studio_reference_bindings_a05 as _studio_reference_bindings_a05
