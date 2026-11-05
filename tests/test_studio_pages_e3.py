"""IMP-182/183 regression: immutable history and tenant-scoped carousel operations."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.studio_e1 import CreativeSpec, StudioError, StudioStore, studio_versions
from tapi_gate0.studio_pages_e3 import StudioPagesService, DuplicatePage, DeletePage, ReorderPage, RestoreVersion

PASSWORD = "local-studio-e3-password-strong"


def setup(tmp_path):
    app = create_secure_app(f"sqlite:///{tmp_path / 'e3.sqlite'}",
                            initialize_schema=True, allow_http_local=True)
    app.state.identity_store.bootstrap("tenantA", "A", "founder", PASSWORD)
    engine = app.state.identity_store.engine
    return app, StudioStore(engine), StudioPagesService(engine)


def spec(intent="instagram_carousel"):
    return CreativeSpec(spec_id="spec.alpha", tenant_id="tenantA",
                        objective="Criar carrossel educativo editável para MPEs",
                        headline="Seu caixa", body="Separe receitas e despesas.",
                        cta="Revise os gastos.", platform_intent=intent)


def test_duplicate_reorder_delete_are_immutable_and_attributed(tmp_path):
    app, docs, service = setup(tmp_path)
    docs.create("tenantA", "founder", spec(), "design.one")
    copied = service.duplicate("tenantA", "founder", "design.one", DuplicatePage(
        expected_version=1, page_id="page.1", new_page_id="page.2"))
    assert copied.version == 2
    assert [page.id for page in copied.pages] == ["page.1", "page.2"]
    assert copied.pages[0].model_dump(exclude={"id"}) == copied.pages[1].model_dump(exclude={"id"})
    moved = service.reorder("tenantA", "founder", "design.one", ReorderPage(
        expected_version=2, page_id="page.2", target_index=0))
    assert [page.id for page in moved.pages] == ["page.2", "page.1"]
    deleted = service.delete("tenantA", "founder", "design.one", DeletePage(
        expected_version=3, page_id="page.1"))
    assert deleted.version == 4 and [page.id for page in deleted.pages] == ["page.2"]
    assert [p.id for p in docs.get("tenantA", "design.one", 2).pages] == ["page.1", "page.2"]
    with app.state.identity_store.engine.connect() as db:
        versions = db.execute(select(studio_versions.c.version, studio_versions.c.edited_by).where(
            studio_versions.c.tenant_id == "tenantA",
            studio_versions.c.document_id == "design.one").order_by(studio_versions.c.version)).all()
    assert versions == [(1, "founder"), (2, "founder"), (3, "founder"), (4, "founder")]


def test_restore_is_new_version_without_overwriting_original(tmp_path):
    app, docs, service = setup(tmp_path)
    docs.create("tenantA", "founder", spec(), "design.one")
    service.duplicate("tenantA", "founder", "design.one", DuplicatePage(
        expected_version=1, page_id="page.1", new_page_id="page.2"))
    service.delete("tenantA", "founder", "design.one", DeletePage(
        expected_version=2, page_id="page.1"))
    restored = service.restore("tenantA", "founder", "design.one", RestoreVersion(
        expected_version=3, restore_version=2))
    assert restored.version == 4 and len(restored.pages) == 2
    assert restored.approval_status == "draft" and restored.rights_status == "pending_review"
    assert len(docs.get("tenantA", "design.one", 3).pages) == 1
    again = service.restore("tenantA", "founder", "design.one", RestoreVersion(
        expected_version=4, restore_version=3))
    assert again.version == 5 and len(again.pages) == 1
    with pytest.raises(StudioError, match="STUDIO_RESTORE_REQUIRES_HISTORICAL_VERSION"):
        service.restore("tenantA", "founder", "design.one", RestoreVersion(
            expected_version=5, restore_version=5))


def test_denials_no_partial_writes_and_page_limit(tmp_path):
    app, docs, service = setup(tmp_path)
    docs.create("tenantA", "founder", spec("instagram_feed"), "design.feed")
    with pytest.raises(StudioError, match="STUDIO_CAROUSEL_REQUIRED"):
        service.duplicate("tenantA", "founder", "design.feed", DuplicatePage(
            expected_version=1, page_id="page.1", new_page_id="page.2"))
    docs.create("tenantA", "founder", spec(), "design.carousel")
    with pytest.raises(StudioError, match="STUDIO_LAST_PAGE_REQUIRED"):
        service.delete("tenantA", "founder", "design.carousel", DeletePage(
            expected_version=1, page_id="page.1"))
    with pytest.raises(StudioError, match="STUDIO_DOCUMENT_NOT_FOUND"):
        service.duplicate("wrongTenant", "founder", "design.carousel", DuplicatePage(
            expected_version=1, page_id="page.1", new_page_id="page.2"))
    for i in range(2, 11):
        doc = service.duplicate("tenantA", "founder", "design.carousel", DuplicatePage(
            expected_version=i-1, page_id=f"page.{i-1}", new_page_id=f"page.{i}"))
    assert doc.version == 10 and len(doc.pages) == 10
    for operation in [
        lambda: service.duplicate("tenantA", "founder", "design.carousel", DuplicatePage(
            expected_version=10, page_id="page.1", new_page_id="page.11")),
        lambda: service.reorder("tenantA", "founder", "design.carousel", ReorderPage(
            expected_version=10, page_id="page.10", target_index=9)),
        lambda: service.duplicate("tenantA", "founder", "design.carousel", DuplicatePage(
            expected_version=9, page_id="page.1", new_page_id="page.X")),
    ]:
        with pytest.raises(StudioError): operation()
    assert docs.get("tenantA", "design.carousel").version == 10


def test_http_roles_and_stale_version(tmp_path):
    app, docs, service = setup(tmp_path)
    with TestClient(app) as client:
        def auth(user="founder"):
            response = client.post("/v1/auth/sessions", json={
                "username":user, "password":PASSWORD, "tenant_id":"tenantA"})
            assert response.status_code == 200
            return {"Authorization":"Bearer "+response.json()["access_token"]}
        admin = auth()
        created = client.post("/v1/studio/documents", headers=admin, json={
            "document_id":"design.one", "spec":spec().model_dump()})
        assert created.status_code == 201
        assert client.post("/v1/admin/members", headers=admin, json={
            "user_id":"viewer1", "username":"reader1", "password":PASSWORD,
            "role":"viewer"}).status_code == 201
        viewer = auth("reader1")
        path = "/v1/studio/documents/design.one/pages/duplicate"
        data = {"expected_version":1, "page_id":"page.1", "new_page_id":"page.2"}
        assert client.post(path, json=data).status_code == 401
        assert client.post(path, headers=viewer, json=data).status_code == 403
        copied = client.post(path, headers=admin, json=data)
        assert copied.status_code == 200 and copied.json()["version"] == 2
        assert client.post(path, headers=admin, json=data).status_code == 409
        restored = client.post("/v1/studio/documents/design.one/versions/restore",
                               headers=admin, json={"expected_version":2,"restore_version":1})
        assert restored.status_code == 200 and restored.json()["version"] == 3
        assert len(restored.json()["pages"]) == 1
        assert client.post("/v1/studio/documents/design.one/pages/reorder",
                           headers=viewer, json={
                           "expected_version":3,"page_id":"page.1","target_index":0}).status_code == 403
        assert client.get("/v1/studio/documents/design.one/versions/2", headers=viewer).status_code == 200
