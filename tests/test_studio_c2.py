"""C2: real PNG persistence, authenticated canvas asset routes, durable layer geometry."""
import base64
import hashlib
import struct
import zlib

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect

from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.studio_e1 import CreativeSpec, StudioError, StudioStore
from tapi_gate0.studio_canvas_c2 import (
    StudioCanvasStore, UploadPNG, PlaceImage, MoveLayer, LayerOrder, decode_png,
)

PASSWORD = "studio-safe-local-password-123456"


def png_rgba():
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    row = b"\x00\xff\x00\x00\xff"
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row))
            + chunk(b"IEND", b""))


def spec():
    return CreativeSpec(
        spec_id="spec.demo", tenant_id="tenantA",
        objective="Construir uma publicação de educação financeira",
        headline="Seu caixa organizado",
        body="Liste as entradas e saídas do seu negócio.",
        cta="Faça uma revisão semanal.",
    )


def app_for(tmp_path):
    app = create_secure_app(
        f"sqlite:///{tmp_path/'studio_c2.sqlite'}",
        initialize_schema=True, allow_http_local=True,
    )
    app.state.identity_store.bootstrap("tenantA", "Demo A", "founder", PASSWORD)
    return app


def auth(client, username="founder"):
    login = client.post("/v1/auth/sessions", json={
        "username": username, "password": PASSWORD, "tenant_id": "tenantA",
    })
    assert login.status_code == 200, login.text
    return {"Authorization": "Bearer " + login.json()["access_token"]}


def test_png_header_hash_and_rights_validation():
    raw = png_rgba()
    assert decode_png(base64.b64encode(raw).decode())[1:] == (1, 1)
    with pytest.raises(ValidationError, match="RIGHTS_ATTESTATION"):
        UploadPNG(data_base64=base64.b64encode(raw).decode(), rights_attested=False)
    with pytest.raises(StudioError, match="STUDIO_PNG_REQUIRED"):
        decode_png(base64.b64encode(b"fake svg or text").decode())
    with pytest.raises(StudioError, match="STUDIO_BAD_BASE64"):
        decode_png("not~valid!")
    with pytest.raises(StudioError, match="STUDIO_ASSET_TOO_LARGE"):
        decode_png(base64.b64encode(raw + b"0" * 524288).decode())


def test_image_asset_is_tenant_scoped_and_persistent(tmp_path):
    app = app_for(tmp_path)
    store = StudioCanvasStore(app.state.identity_store.engine)
    encoded = base64.b64encode(png_rgba()).decode()
    result = store.save_png("tenantA", "founder",
                            UploadPNG(data_base64=encoded, rights_attested=True))
    assert result.sha256 == hashlib.sha256(png_rgba()).hexdigest()
    assert result.media_type == "image/png"
    assert store.asset_bytes("tenantA", result.asset_id) == png_rgba()
    with pytest.raises(StudioError, match="STUDIO_ASSET_NOT_FOUND"):
        store.asset_bytes("otherTenant", result.asset_id)
    repeat = store.save_png("tenantA", "founder",
                            UploadPNG(data_base64=encoded, rights_attested=True))
    assert repeat.asset_id == result.asset_id


def test_add_move_version_replay_and_tenant_bounds(tmp_path):
    app = app_for(tmp_path)
    engine = app.state.identity_store.engine
    docs = StudioStore(engine)
    docs.create("tenantA", "founder", spec(), "design.one")
    canvas = StudioCanvasStore(engine)
    asset = canvas.save_png("tenantA", "founder", UploadPNG(
        data_base64=base64.b64encode(png_rgba()).decode(),
        rights_attested=True,
    ))
    inserted = canvas.add_image("tenantA", "founder", "design.one", PlaceImage(
        expected_version=1, page_id="page.1", layer_id="layer.img",
        asset_id=asset.asset_id, x=50, y=60, w=200, h=180,
    ))
    assert inserted.version == 2
    assert inserted.pages[0].layers[-1].kind == "image"
    changed = canvas.move("tenantA", "founder", "design.one", MoveLayer(
        expected_version=2, page_id="page.1", layer_id="layer.img", x=150, y=120,
    ))
    assert changed.version == 3
    assert changed.pages[0].layers[-1].x == 150
    assert docs.get("tenantA", "design.one", 2).pages[0].layers[-1].x == 50
    with pytest.raises(StudioError, match="STUDIO_VERSION_CONFLICT"):
        canvas.move("tenantA", "founder", "design.one", MoveLayer(
            expected_version=2, page_id="page.1", layer_id="layer.img", y=100,
        ))
    with pytest.raises(StudioError, match="STUDIO_DOCUMENT_NOT_FOUND"):
        canvas.move("otherTenant", "someone", "design.one", MoveLayer(
            expected_version=3, page_id="page.1", layer_id="layer.img", y=100,
        ))
    with pytest.raises(ValidationError, match="STUDIO_LAYER_OUTSIDE_CANVAS"):
        canvas.move("tenantA", "founder", "design.one", MoveLayer(
            expected_version=3, page_id="page.1", layer_id="layer.img", x=1000,
        ))
    assert docs.get("tenantA", "design.one").version == 3


def test_secure_canvas_routes_guard_assets_and_viewer_writes(tmp_path):
    app = app_for(tmp_path)
    with TestClient(app) as client:
        hdr = auth(client)
        create = client.post("/v1/studio/documents", json={
            "document_id": "design.one", "spec": spec().model_dump(),
        }, headers=hdr)
        assert create.status_code == 201, create.text
        raw = png_rgba()
        upload = client.post("/v1/studio/assets/png", json={
            "data_base64": base64.b64encode(raw).decode(), "rights_attested": True,
        }, headers=hdr)
        assert upload.status_code == 201, upload.text
        asset = upload.json()["asset_id"]
        assert client.get("/v1/studio/assets/" + asset + "/binary").status_code == 401
        response = client.get("/v1/studio/assets/" + asset + "/binary", headers=hdr)
        assert response.status_code == 200
        assert response.content == raw
        assert response.headers["content-type"].startswith("image/png")
        placed = client.post("/v1/studio/documents/design.one/image-layers", json={
            "expected_version":1, "page_id":"page.1", "layer_id":"layer.img",
            "asset_id":asset, "x":100, "y":100, "w":180, "h":140,
        }, headers=hdr)
        assert placed.status_code == 200, placed.text
        assert placed.json()["version"] == 2
        moved = client.post("/v1/studio/documents/design.one/geometry", json={
            "expected_version":2, "page_id":"page.1", "layer_id":"layer.img", "x":200,
        }, headers=hdr)
        assert moved.status_code == 200, moved.text
        assert moved.json()["pages"][0]["layers"][-1]["x"] == 200
        assert client.post("/v1/admin/members", headers=hdr, json={
            "user_id":"viewer1","username":"reader1",
            "password":PASSWORD,"role":"viewer",
        }).status_code == 201
        viewer = auth(client,"reader1")
        assert client.get("/v1/studio/documents/design.one", headers=viewer).status_code == 200
        assert client.post("/v1/studio/documents/design.one/geometry", headers=viewer, json={
            "expected_version":3,"page_id":"page.1","layer_id":"layer.img","x":250,
        }).status_code == 403
        assert client.post("/v1/studio/assets/png", headers=viewer, json={
            "data_base64":base64.b64encode(raw).decode(),"rights_attested":True,
        }).status_code == 403


def test_studio_migration_0007_creates_asset_blob_table(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    from tapi_gate0.sa_store import engine_for

    root = Path(__file__).resolve().parents[1]
    url = f"sqlite:///{tmp_path/'migration.sqlite'}"
    monkeypatch.setenv("TAPI_DATABASE_URL", url)
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "head")
    engine = engine_for(url)
    assert "studio_assets" in inspect(engine).get_table_names()
    command.downgrade(config, "0006_discovery_provenance")
    assert "studio_assets" not in inspect(engine).get_table_names()
    engine.dispose()


def test_layer_order_changes_are_immutable_and_tenant_bounded(tmp_path):
    app = app_for(tmp_path)
    engine = app.state.identity_store.engine
    docs = StudioStore(engine)
    docs.create("tenantA", "founder", spec(), "design.stack")
    store = StudioCanvasStore(engine)
    new = store.order("tenantA", "founder", "design.stack", LayerOrder(
        expected_version=1, page_id="page.1", layer_id="headline",
        direction="forward",
    ))
    assert new.version == 2
    assert [item.id for item in new.pages[0].layers] == ["body", "headline", "cta"]
    old = docs.get("tenantA", "design.stack", 1)
    assert [item.id for item in old.pages[0].layers] == ["headline", "body", "cta"]
    with pytest.raises(StudioError, match="STUDIO_VERSION_CONFLICT"):
        store.order("tenantA", "founder", "design.stack", LayerOrder(
            expected_version=1, page_id="page.1", layer_id="headline",
            direction="backward",
        ))
    with pytest.raises(StudioError, match="STUDIO_ORDER_UNCHANGED"):
        store.order("tenantA", "founder", "design.stack", LayerOrder(
            expected_version=2, page_id="page.1", layer_id="cta",
            direction="forward",
        ))
    assert docs.get("tenantA", "design.stack").version == 2
