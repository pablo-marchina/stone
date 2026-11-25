"""C2: bounded PNG asset persistence and SQL-backed layer manipulation.

Does not fetch remote URLs, execute SVG, load fonts or publish. Asset bytes
are stored per tenant in the same DB; browser canvas export is explicitly local.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import zlib
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import (
    Table, Column, String, Integer, LargeBinary, ForeignKeyConstraint,
    select, insert, update,
)
from sqlalchemy.exc import IntegrityError

from .domain import Id
from .sa_store import metadata, tenants
from .studio_e1 import DesignDocument, ImageLayer, StudioError, StudioStore, studio_documents, studio_versions

MAX_PNG_BYTES = 524288
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

studio_assets = Table(
    "studio_assets", metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("asset_id", String(128), primary_key=True),
    Column("sha256", String(64), nullable=False),
    Column("media_type", String(32), nullable=False),
    Column("byte_size", Integer, nullable=False),
    Column("width", Integer, nullable=False),
    Column("height", Integer, nullable=False),
    Column("rights_status", String(32), nullable=False),
    Column("uploaded_at", String(48), nullable=False),
    Column("uploaded_by", String(128), nullable=False),
    Column("data", LargeBinary, nullable=False),
    ForeignKeyConstraint(["tenant_id"], [tenants.c.tenant_id]),
)


class UploadPNG(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_base64: str = Field(min_length=16, max_length=750000)
    rights_attested: bool

    @model_validator(mode="after")
    def require_rights_attestation(self):
        if self.rights_attested is not True:
            raise ValueError("STUDIO_ASSET_RIGHTS_ATTESTATION_REQUIRED")
        return self


class AssetRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: Id
    sha256: str
    media_type: str
    byte_size: int
    width: int
    height: int
    rights_status: str


class PlaceImage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    page_id: Id
    layer_id: Id
    asset_id: Id
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)


class MoveLayer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    page_id: Id
    layer_id: Id
    x: int | None = Field(default=None, ge=0)
    y: int | None = Field(default=None, ge=0)
    w: int | None = Field(default=None, gt=0)
    h: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def must_change(self):
        if all(getattr(self, field) is None for field in ("x", "y", "w", "h")):
            raise ValueError("STUDIO_MOVE_EMPTY")
        return self


class LayerOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    page_id: Id
    layer_id: Id
    direction: Literal["forward", "backward"]


def decode_png(value: str) -> tuple[bytes, int, int]:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise StudioError("STUDIO_BAD_BASE64", 422) from exc
    if len(raw) > MAX_PNG_BYTES:
        raise StudioError("STUDIO_ASSET_TOO_LARGE", 413)
    if (len(raw) < 33 or not raw.startswith(PNG_SIGNATURE)
            or raw[12:16] != b"IHDR" or int.from_bytes(raw[8:12], "big") != 13):
        raise StudioError("STUDIO_PNG_REQUIRED", 422)
    width = int.from_bytes(raw[16:20], "big")
    height = int.from_bytes(raw[20:24], "big")
    if not (1 <= width <= 2048 and 1 <= height <= 2048):
        raise StudioError("STUDIO_IMAGE_DIMENSIONS_INVALID", 422)
    # Restrict to standard 8-bit RGB/RGBA/non-interlaced PNG. Never allow
    # browsers to interpret SVG or HTML supplied by a remote source.
    if raw[24] != 8 or raw[25] not in (2, 6) or raw[26:29] != b"\x00\x00\x00":
        raise StudioError("STUDIO_UNSUPPORTED_PNG_FORMAT", 422)
    # Validate complete chunk structure, CRC and bounded decoded pixels; a
    # forged PNG signature alone is not a safe persisted image.
    pos, frames, ended = 8, bytearray(), False
    while pos + 12 <= len(raw):
        size = int.from_bytes(raw[pos:pos+4], "big")
        end = pos + 12 + size
        if size > MAX_PNG_BYTES or end > len(raw):
            raise StudioError("STUDIO_INVALID_PNG_CHUNKS", 422)
        tag = raw[pos+4:pos+8]
        data = raw[pos+8:pos+8+size]
        crc = int.from_bytes(raw[pos+8+size:end], "big")
        if zlib.crc32(tag + data) & 0xffffffff != crc:
            raise StudioError("STUDIO_INVALID_PNG_CRC", 422)
        if pos == 8 and (tag != b"IHDR" or size != 13):
            raise StudioError("STUDIO_INVALID_PNG_CHUNKS", 422)
        if tag == b"IDAT":
            frames.extend(data)
        if tag == b"IEND":
            if size != 0 or end != len(raw):
                raise StudioError("STUDIO_INVALID_PNG_CHUNKS", 422)
            ended = True
            break
        pos = end
    if not ended or not frames:
        raise StudioError("STUDIO_INVALID_PNG_CHUNKS", 422)
    expected = height * (1 + width * (4 if raw[25] == 6 else 3))
    try:
        decoder = zlib.decompressobj()
        decoded = decoder.decompress(bytes(frames), expected + 1)
        if len(decoded) != expected or not decoder.eof or decoder.unused_data:
            raise ValueError("wrong pixel count")
    except (zlib.error, ValueError) as exc:
        raise StudioError("STUDIO_INVALID_PNG_PIXELS", 422) from exc
    return raw, width, height


class StudioCanvasStore:
    def __init__(self, engine):
        self.engine = engine
        self.docs = StudioStore(engine)

    def save_png(self, tenant: str, actor: str, payload: UploadPNG) -> AssetRecord:
        raw, width, height = decode_png(payload.data_base64)
        checksum = hashlib.sha256(raw).hexdigest()
        asset_id = "asset." + checksum[:32]
        with self.engine.begin() as db:
            old = db.execute(select(studio_assets).where(
                studio_assets.c.tenant_id == tenant,
                studio_assets.c.asset_id == asset_id)).mappings().first()
            if not old:
                db.execute(insert(studio_assets).values(
                    tenant_id=tenant, asset_id=asset_id, sha256=checksum,
                    media_type="image/png", byte_size=len(raw), width=width,
                    height=height, rights_status="operator_attested",
                    uploaded_at=datetime.now(timezone.utc).isoformat(),
                    uploaded_by=actor, data=raw))
        return AssetRecord(asset_id=asset_id, sha256=checksum, media_type="image/png",
                           byte_size=len(raw), width=width, height=height,
                           rights_status="operator_attested")

    def asset_bytes(self, tenant: str, asset_id: str) -> bytes:
        with self.engine.connect() as db:
            payload = db.execute(select(studio_assets.c.data).where(
                studio_assets.c.tenant_id == tenant,
                studio_assets.c.asset_id == asset_id)).scalar_one_or_none()
        if payload is None:
            raise StudioError("STUDIO_ASSET_NOT_FOUND", 404)
        return bytes(payload)

    def _change(self, tenant, actor, doc_id, expected_version, transform,
                *, connection=None, reference_authorizer=None):
        if connection is None:
            with self.engine.begin() as db:
                return self._change(
                    tenant, actor, doc_id, expected_version, transform,
                    connection=db, reference_authorizer=reference_authorizer,
                )
        db = connection
        if db.engine is not self.engine or not db.in_transaction():
            raise StudioError("STUDIO_TRANSACTION_REQUIRED", 409)
        # Protect EVERY canvas/page mutation, not just the HTTP router:
        # external reference grants must be checked inside THIS transaction.
        from .studio_reference_bindings_a05 import studio_reference_bindings
        signed = db.execute(select(studio_reference_bindings.c.content_id).where(
            studio_reference_bindings.c.tenant_id == tenant,
            studio_reference_bindings.c.document_id == doc_id,
        ).limit(1)).first()
        if signed is not None:
            if reference_authorizer is None:
                raise StudioError("STUDIO_SIGNED_REFERENCE_RECHECK_REQUIRED", 403)
            reference_authorizer(db)
        current = db.execute(select(studio_documents.c.current_version).where(
            studio_documents.c.tenant_id == tenant,
            studio_documents.c.document_id == doc_id)).scalar_one_or_none()
        if current is None:
            raise StudioError("STUDIO_DOCUMENT_NOT_FOUND", 404)
        if current != expected_version:
            raise StudioError("STUDIO_VERSION_CONFLICT", 409)
        blob = db.execute(select(studio_versions.c.payload).where(
            studio_versions.c.tenant_id == tenant,
            studio_versions.c.document_id == doc_id,
            studio_versions.c.version == current)).scalar_one()
        raw = DesignDocument.model_validate_json(blob).model_dump()
        transform(raw, db)
        raw["version"] = current + 1
        new = DesignDocument.model_validate(raw)
        updated = db.execute(update(studio_documents).where(
            studio_documents.c.tenant_id == tenant,
            studio_documents.c.document_id == doc_id,
            studio_documents.c.current_version == current).values(current_version=current + 1))
        if updated.rowcount != 1:
            raise StudioError("STUDIO_VERSION_CONFLICT", 409)
        StudioStore._insert_version(db, new, actor)
        return new

    def add_image(self, tenant: str, actor: str, document_id: str,
                  payload: PlaceImage) -> DesignDocument:
        def transform(raw, db):
            exists = db.execute(select(studio_assets.c.asset_id).where(
                studio_assets.c.tenant_id == tenant,
                studio_assets.c.asset_id == payload.asset_id)).scalar_one_or_none()
            if not exists:
                raise StudioError("STUDIO_ASSET_NOT_FOUND", 404)
            for page in raw["pages"]:
                if page["id"] == payload.page_id:
                    if any(item["id"] == payload.layer_id for item in page["layers"]):
                        raise StudioError("STUDIO_LAYER_ALREADY_EXISTS", 409)
                    page["layers"].append(ImageLayer(
                        id=payload.layer_id, asset_id=payload.asset_id,
                        x=payload.x, y=payload.y, w=payload.w, h=payload.h,
                    ).model_dump())
                    return
            raise StudioError("STUDIO_PAGE_NOT_FOUND", 404)
        return self._change(tenant, actor, document_id, payload.expected_version, transform)

    def move(self, tenant: str, actor: str, document_id: str,
             payload: MoveLayer, *, connection=None,
             reference_authorizer=None) -> DesignDocument:
        def transform(raw, db):
            for page in raw["pages"]:
                if page["id"] != payload.page_id:
                    continue
                for layer in page["layers"]:
                    if layer["id"] == payload.layer_id:
                        for name in ("x", "y", "w", "h"):
                            value = getattr(payload, name)
                            if value is not None:
                                layer[name] = value
                        layer["origin"] = "operator_edit"
                        return
            raise StudioError("STUDIO_LAYER_NOT_FOUND", 404)
        return self._change(
            tenant, actor, document_id, payload.expected_version, transform,
            connection=connection, reference_authorizer=reference_authorizer,
        )

    def order(self, tenant: str, actor: str, document_id: str,
              payload: LayerOrder) -> DesignDocument:
        """Move a layer one step in z-order. Later layers cover earlier ones."""
        def transform(raw, db):
            for page in raw["pages"]:
                if page["id"] != payload.page_id:
                    continue
                layers = page["layers"]
                for index, layer in enumerate(layers):
                    if layer["id"] != payload.layer_id:
                        continue
                    target = index + (1 if payload.direction == "forward" else -1)
                    if target < 0 or target >= len(layers):
                        raise StudioError("STUDIO_ORDER_UNCHANGED", 409)
                    layers[index], layers[target] = layers[target], layers[index]
                    return
            raise StudioError("STUDIO_LAYER_NOT_FOUND", 404)
        return self._change(tenant, actor, document_id, payload.expected_version, transform)
