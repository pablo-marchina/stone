"""CAP-023 E1: structured draft, isolated SQL history and authenticated edits.

No image rendering or AI generation is asserted by these tests.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import insert

from tapi_gate0.sa_store import engine_for, metadata, tenants
from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.studio_e1 import (
    CreativeSpec, DesignDocument, StudioError, StudioStore, TextLayerPatch,
    draft_from_spec,
)

PASSWORD = "test-password-with-sufficient-length-123"


def _spec(tenant="tenantA"):
    return CreativeSpec(
        spec_id="spec.01", tenant_id=tenant,
        objective="Criar um exemplo visual editável de educação financeira",
        headline="Organize seu caixa",
        body="Separe receitas e despesas em categorias.",
        cta="Revise seu planejamento.",
        reference_content_ids=["synthetic.ref1"],
    )


def _store(tmp_path):
    engine = engine_for(f"sqlite:///{tmp_path/'studio.sqlite'}")
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(tenants).values(tenant_id="tenantA", name="Example A"))
        conn.execute(insert(tenants).values(tenant_id="tenantB", name="Example B"))
    return StudioStore(engine)


def test_draft_is_editable_text_only_not_approved_or_rendered():
    doc = draft_from_spec(_spec(), "design.01")
    assert doc.version == 1
    assert [x.id for x in doc.pages[0].layers] == ["headline", "body", "cta"]
    assert doc.reference_status == "unverified"
    assert doc.approval_status == "draft"
    assert doc.render_status == "not_implemented"
    assert doc.rights_status == "pending_review"
    assert doc.reference_content_ids == ["synthetic.ref1"]


def test_duplicate_references_and_invalid_layout_rejected():
    payload = _spec().model_dump()
    payload["reference_content_ids"] = ["item1", "item1"]
    with pytest.raises(ValidationError, match="STUDIO_DUPLICATE_REFERENCE"):
        CreativeSpec.model_validate(payload)
    raw = draft_from_spec(_spec(), "design.01").model_dump()
    raw["pages"][0]["layers"][0]["w"] = raw["canvas"]["width"] + 50
    with pytest.raises(ValidationError, match="STUDIO_LAYER_OUTSIDE_CANVAS"):
        DesignDocument.model_validate(raw)


def test_sql_version_history_and_optimistic_lock(tmp_path):
    store = _store(tmp_path)
    first = store.create("tenantA", "alice", _spec(), "design.01")
    assert first.version == 1
    patch = TextLayerPatch(
        page_id="page.1", layer_id="headline",
        expected_version=1, text="Controle seu fluxo de caixa",
    )
    second = store.patch_text_layer("tenantA", "alice", "design.01", patch)
    assert second.version == 2
    assert store.get("tenantA", "design.01").version == 2
    assert store.get("tenantA", "design.01", 1).pages[0].layers[0].text == "Organize seu caixa"
    assert store.get("tenantA", "design.01", 2).pages[0].layers[0].text == "Controle seu fluxo de caixa"
    reopened = StudioStore(engine_for("sqlite:///" + str(tmp_path / "studio.sqlite")))
    assert reopened.get("tenantA", "design.01").version == 2
    with pytest.raises(StudioError, match="STUDIO_VERSION_CONFLICT"):
        store.patch_text_layer("tenantA", "alice", "design.01", patch)
    with pytest.raises(StudioError, match="STUDIO_DOCUMENT_ALREADY_EXISTS"):
        store.create("tenantA", "alice", _spec(), "design.01")


def test_tenant_isolation_and_invalid_edits(tmp_path):
    store = _store(tmp_path)
    store.create("tenantA", "adminA", _spec(), "design.01")
    with pytest.raises(StudioError, match="STUDIO_TENANT_MISMATCH"):
        store.create("tenantB", "adminB", _spec(), "design.02")
    with pytest.raises(StudioError, match="STUDIO_DOCUMENT_NOT_FOUND"):
        store.get("tenantB", "design.01")
    with pytest.raises(StudioError, match="STUDIO_DOCUMENT_NOT_FOUND"):
        store.patch_text_layer("tenantB", "adminB", "design.01", TextLayerPatch(
            page_id="page.1", layer_id="headline", expected_version=1, text="Not allowed",
        ))
    with pytest.raises(StudioError, match="STUDIO_LAYER_NOT_FOUND"):
        store.patch_text_layer("tenantA", "adminA", "design.01", TextLayerPatch(
            page_id="page.1", layer_id="does-not-exist", expected_version=1, text="No",
        ))
    with pytest.raises(ValidationError, match="STUDIO_PATCH_REQUIRES_CHANGE"):
        TextLayerPatch(page_id="page.1", layer_id="headline", expected_version=1)
    with pytest.raises(ValidationError, match="STUDIO_LAYER_OUTSIDE_CANVAS"):
        store.patch_text_layer("tenantA", "adminA", "design.01", TextLayerPatch(
            page_id="page.1", layer_id="headline", expected_version=1, x=1000,
        ))
    assert store.get("tenantA", "design.01").version == 1


def _login(client, username="founder", password=PASSWORD):
    result = client.post("/v1/auth/sessions", json={
        "username":username, "password":password, "tenant_id":"tenantA",
    })
    assert result.status_code == 200, result.text
    return {"Authorization":"Bearer " + result.json()["access_token"]}


def test_secure_api_draft_edit_read_and_viewer_rbac(tmp_path):
    app = create_secure_app(
        f"sqlite:///{tmp_path/'api.sqlite'}",
        initialize_schema=True, allow_http_local=True,
    )
    app.state.identity_store.bootstrap("tenantA", "Tenant A", "founder", PASSWORD)
    with TestClient(app) as client:
        admin = _login(client)
        assert client.get("/v1/studio/documents/design.01").status_code == 401
        created = client.post("/v1/studio/documents", headers=admin, json={
            "document_id":"design.01", "spec":_spec().model_dump(),
        })
        assert created.status_code == 201, created.text
        assert created.json()["approval_status"] == "draft"
        edit = client.post("/v1/studio/documents/design.01/text-patches",
                           headers=admin, json={
            "page_id":"page.1", "layer_id":"headline",
            "expected_version":1, "text":"Novo título",
        })
        assert edit.status_code == 200, edit.text
        assert edit.json()["version"] == 2
        old = client.get("/v1/studio/documents/design.01/versions/1",headers=admin)
        assert old.status_code == 200
        assert old.json()["pages"][0]["layers"][0]["text"] == "Organize seu caixa"
        assert client.post("/v1/studio/documents/design.01/text-patches",
                           headers=admin, json={
            "page_id":"page.1", "layer_id":"headline",
            "expected_version":1, "text":"Replayed",
        }).status_code == 409
        add = client.post("/v1/admin/members", headers=admin, json={
            "user_id":"viewer1", "username":"reader1",
            "password":PASSWORD, "role":"viewer",
        })
        assert add.status_code == 201
        viewer = _login(client, "reader1")
        assert client.get("/v1/studio/documents/design.01",headers=viewer).status_code == 200
        assert client.post("/v1/studio/documents/design.02",headers=viewer,
                           json={"document_id":"design.02", "spec":_spec().model_dump()}).status_code in (403, 404, 405)
        assert client.post("/v1/studio/documents", headers=viewer, json={
            "document_id":"design.02", "spec":_spec().model_dump(),
        }).status_code == 403


def test_alembic_upgrade_head_contains_studio_tables(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    root = Path(__file__).resolve().parents[1]
    url = f"sqlite:///{tmp_path/'migrated.sqlite'}"
    monkeypatch.setenv("TAPI_DATABASE_URL", url)
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "head")
    engine = engine_for(url)
    names = set(inspect(engine).get_table_names())
    assert "studio_documents" in names
    assert "studio_document_versions" in names
    command.downgrade(config, "0006_discovery_provenance")
    after = set(inspect(engine).get_table_names())
    assert "studio_documents" not in after
    assert "studio_document_versions" not in after
    command.upgrade(config, "head")
    assert "studio_document_versions" in inspect(engine).get_table_names()
    engine.dispose()
