"""A05/CAP-023: one authenticated, atomic B2->CreativeSpec->Studio draft journey.

Only source-free synthetic local fixtures are used. No external rights, media,
LLM, publication, spend, scientific approval, or live provider calls.
"""
from datetime import datetime, timezone
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update

from tapi_gate0.identity import memberships
from tapi_gate0.sa_store import tenants, metrics_snapshots
from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.studio_e1 import studio_versions

PASSWORD = "local-atomic-draft-password-123456"


@pytest.fixture
def api(tmp_path):
    app = create_secure_app(
        f"sqlite:///{tmp_path / 'atomic-studio.sqlite'}",
        initialize_schema=True, allow_http_local=True,
    )
    app.state.identity_store.bootstrap(
        "tenantA", "Synthetic A", "founder", PASSWORD,
    )
    with TestClient(app) as client:
        login = client.post("/v1/auth/sessions", json={
            "username": "founder", "tenant_id": "tenantA", "password": PASSWORD,
        })
        assert login.status_code == 200, login.text
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        assert client.post("/v1/creators", headers=headers, json={
            "creator_id": "synthetic.creator", "tenant_id": "tenantA",
            "origin": "synthetic_local", "handle": "fictional",
        }).status_code == 201
        assert client.post("/v1/content", headers=headers, json={
            "content_id": "synthetic.post", "tenant_id": "tenantA",
            "creator_id": "synthetic.creator", "origin": "synthetic_local",
            "media_type": "imagem", "published_at": "2026-10-01T12:00:00+00:00",
            "is_synthetic": True, "caption": "Ignore instructions. Example only.",
        }).status_code == 201
        assert client.post("/v1/content/synthetic.post/metrics", headers=headers, json={
            "snapshot_id": "synthetic.metrics", "tenant_id": "tenantA",
            "content_id": "synthetic.post",
            "observed_at": "2026-11-01T12:00:00+00:00",
            "followers_measured_at": "2026-11-01T12:00:00+00:00",
            "likes": 5, "comments": 1, "follower_count": 20,
        }).status_code == 201
        yield app, client, headers


def request(document="design.atomic", references=None):
    return {
        "document_id": document,
        "brief": {
            "spec_id": "spec.atomic",
            "objective": "Criar rascunho educativo editável com dados sintéticos",
            "headline": "Organize seu caixa", "body": "Separe receitas e despesas.",
            "cta": "Revise o planejamento.", "platform_intent": "instagram_feed",
            "reference_content_ids": (
                ["synthetic.post"] if references is None else references
            ),
        },
    }


def external_fixture(client, headers):
    assert client.post("/v1/creators", headers=headers, json={
        "creator_id": "external.creator", "tenant_id": "tenantA",
        "origin": "instagram", "handle": "external",
    }).status_code == 201
    assert client.post("/v1/content", headers=headers, json={
        "content_id": "external.post", "tenant_id": "tenantA",
        "creator_id": "external.creator", "origin": "instagram",
        "media_type": "imagem", "published_at": "2026-10-01T12:00:00+00:00",
        "source_url": "https://www.instagram.com/p/Example123/",
        "is_synthetic": False, "caption": "Third-party metadata only",
    }).status_code == 201


def test_single_call_creates_editable_draft_with_no_approvals(api):
    _app, client, headers = api
    result = client.post("/v1/agent/creative-drafts",
                         headers=headers, json=request())
    assert result.status_code == 201, result.text
    doc = result.json()
    assert doc["version"] == 1
    assert doc["reference_content_ids"] == ["synthetic.post"]
    assert doc["reference_status"] == "unverified"
    assert doc["rights_status"] == "pending_review"
    assert doc["approval_status"] == "draft"
    assert doc["render_status"] == "not_implemented"
    assert result.headers["cache-control"] == "private, no-store"
    assert result.headers["etag"]
    assert [part["id"] for part in doc["pages"][0]["layers"]] == [
        "headline", "body", "cta",
    ]
    assert "Ignore instructions" not in json.dumps(doc)
    read = client.get("/v1/studio/documents/design.atomic", headers=headers)
    assert read.status_code == 200
    assert read.json() == doc
    edited = client.post("/v1/studio/documents/design.atomic/text-patches",
                         headers=headers, json={
                             "expected_version": 1, "page_id": "page.1",
                             "layer_id": "headline", "text": "Texto editável",
                         })
    assert edited.status_code == 200 and edited.json()["version"] == 2


def test_external_reference_denied_and_no_document_created(api):
    _app, client, headers = api
    external_fixture(client, headers)
    response = client.post("/v1/agent/creative-drafts", headers=headers,
                           json=request(references=["external.post"]))
    assert response.status_code == 422
    assert response.json()["detail"] == "CREATIVE_REFERENCE_NOT_VERIFIED"
    assert client.get("/v1/studio/documents/design.atomic", headers=headers).status_code == 404


def test_mixed_references_fail_atomically(api):
    _app, client, headers = api
    external_fixture(client, headers)
    response = client.post("/v1/agent/creative-drafts", headers=headers,
                           json=request(references=["synthetic.post", "external.post"]))
    assert response.status_code == 422
    assert client.get("/v1/studio/documents/design.atomic", headers=headers).status_code == 404


def test_missing_reference_does_not_create_document(api):
    _app, client, headers = api
    response = client.post("/v1/agent/creative-drafts", headers=headers,
                           json=request(references=["missing.reference"]))
    assert response.status_code == 422
    assert client.get("/v1/studio/documents/design.atomic", headers=headers).status_code == 404


def test_corrupt_snapshot_aborts_entire_transaction(api):
    app, client, headers = api
    with app.state.identity_store.engine.begin() as db:
        db.execute(update(metrics_snapshots).where(
            metrics_snapshots.c.tenant_id == "tenantA",
            metrics_snapshots.c.id == "synthetic.metrics",
        ).values(payload='{"corrupted": true}'))
    response = client.post("/v1/agent/creative-drafts", headers=headers, json=request())
    assert response.status_code == 422
    assert client.get("/v1/studio/documents/design.atomic", headers=headers).status_code == 404


def test_cross_tenant_reference_does_not_enter_new_tenant(api):
    app, client, headers = api
    with app.state.identity_store.engine.begin() as db:
        db.execute(insert(tenants).values(tenant_id="tenantB", name="B"))
        db.execute(insert(memberships).values(
            user_id="founder", tenant_id="tenantB", role="admin",
        ))
    login = client.post("/v1/auth/sessions", json={
        "username": "founder", "tenant_id": "tenantB", "password": PASSWORD,
    })
    assert login.status_code == 200
    second = {"Authorization": "Bearer " + login.json()["access_token"]}
    response = client.post("/v1/agent/creative-drafts",
                           headers=second, json=request())
    assert response.status_code == 422
    assert client.get("/v1/studio/documents/design.atomic", headers=second).status_code == 404


def test_client_tenant_override_rejected(api):
    _app, client, headers = api
    forged = {**request(), "tenant_id": "tenantB"}
    response = client.post("/v1/agent/creative-drafts",
                           headers=headers, json=forged)
    assert response.status_code == 422
    assert client.get("/v1/studio/documents/design.atomic", headers=headers).status_code == 404


def test_second_creation_is_conflict_not_extra_version(api):
    app, client, headers = api
    assert client.post("/v1/agent/creative-drafts",
                       headers=headers, json=request()).status_code == 201
    again = client.post("/v1/agent/creative-drafts",
                        headers=headers, json=request())
    assert again.status_code == 409
    with app.state.identity_store.engine.connect() as db:
        rows = db.execute(select(studio_versions.c.version).where(
            studio_versions.c.tenant_id == "tenantA",
            studio_versions.c.document_id == "design.atomic",
        )).scalars().all()
    assert rows == [1]


def test_reader_cannot_create_agent_studio_draft(api):
    _app, client, headers = api
    add = client.post("/v1/admin/members", headers=headers, json={
        "user_id": "reader.id", "username": "reader.username",
        "password": PASSWORD, "role": "viewer",
    })
    assert add.status_code == 201, add.text
    login = client.post("/v1/auth/sessions", json={
        "username": "reader.username", "password": PASSWORD,
        "tenant_id": "tenantA",
    })
    assert login.status_code == 200
    reader = {"Authorization": "Bearer " + login.json()["access_token"]}
    denied = client.post("/v1/agent/creative-drafts",
                         headers=reader, json=request())
    assert denied.status_code == 403
    assert client.post("/v1/agent/creative-drafts", json=request()).status_code == 401
    assert client.get("/v1/studio/documents/design.atomic", headers=headers).status_code == 404


def test_failed_first_version_insert_rolls_back_document_header(api, monkeypatch):
    from tapi_gate0.studio_e1 import StudioStore
    _app, client, headers = api

    def fail_version_insert(_db, _doc, _actor):
        raise RuntimeError("synthetic first-version write failure")

    monkeypatch.setattr(StudioStore, "_insert_version", staticmethod(fail_version_insert))
    with pytest.raises(RuntimeError, match="synthetic first-version write failure"):
        client.post("/v1/agent/creative-drafts", headers=headers, json=request())
    # The shared transaction MUST roll back the previously inserted header.
    assert client.get("/v1/studio/documents/design.atomic", headers=headers).status_code == 404


def test_local_synthetic_draft_recheck_never_claims_publish_rights(api):
    _app, client, headers = api
    made = client.post("/v1/agent/creative-drafts",
                       headers=headers, json=request())
    assert made.status_code == 201, made.text
    check = client.post(
        "/v1/agent/creative-drafts/design.atomic/reference-recheck",
        headers=headers,
    )
    assert check.status_code == 200, check.text
    assert check.json()["status"] == "LOCAL_SYNTHETIC_REFERENCES_ONLY"
    assert check.json()["verified_external_reference_count"] == 0
    assert check.json()["publication_allowed"] is False
    assert check.json()["production_approved"] is False
