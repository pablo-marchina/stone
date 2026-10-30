"""Offline regression tests: official Meta cursor, no URL-following, eligible age, resume.

All Graph API responses are mocked: no credentials, traffic, or billing.
"""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tapi_gate0.connectors import ConnectorError, InstagramOfficial, OfficialHttp
from tapi_gate0.ingestion import (
    IngestionRequest, ingestion_page_checkpoints, ingestion_records, ingestion_runs,
)
from tapi_gate0.secure_api import create_secure_app


TENANT = "pagination-test"
PASSWORD = "correct-horse-battery-admin-42-safe"
ACCOUNT = "178900"


def _app(tmp_path):
    app = create_secure_app(
        f"sqlite:///{tmp_path/'cursor.sqlite3'}",
        initialize_schema=True, allow_http_local=True,
    )
    app.state.identity_store.bootstrap(TENANT, "Pagination Org", "admin", PASSWORD)
    return app


def _auth(client):
    r = client.post("/v1/auth/sessions", json={
        "username": "admin", "password": PASSWORD, "tenant_id": TENANT,
    })
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def _grant(client, headers):
    r = client.post("/v1/ingestion/grants", headers=headers, json={
        "platform": "instagram", "source_account_id": ACCOUNT,
        "approval_reference": "Approved local mock scope for regression",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=20)).isoformat(),
    })
    assert r.status_code == 201, r.text


def _media(item_id, timestamp):
    return {
        "id": item_id, "media_type": "VIDEO", "media_product_type": "REELS",
        "permalink": "https://www.instagram.com/reel/LocalTest/",
        "caption": "Marketing e vendas", "timestamp": timestamp,
        "like_count": 15, "comments_count": 1,
    }


def test_cursor_resume_skips_recent_posts_and_never_follows_next_url(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPI_OFFICIAL_METADATA_READS", "1")
    monkeypatch.setenv("TAPI_ZERO_BILLING_CONFIRMED", "1")
    monkeypatch.setenv("TAPI_INSTAGRAM_ACCESS_TOKEN", "mocked-credentials-that-never-log")
    old = "2024-01-14T12:00:00Z"
    recent = datetime.now(timezone.utc).isoformat()
    seen = []

    def provider(req):
        seen.append((req.url.host, req.url.path, req.url.params.get("after")))
        assert req.url.host == "graph.facebook.com"
        if req.url.path.endswith("/178900"):
            return httpx.Response(200, json={
                "id": ACCOUNT, "username": "approved_test_account", "followers_count": 1200,
            })
        assert req.url.path.endswith("/178900/media")
        if req.url.params.get("after") == "CURSOR_2":
            return httpx.Response(200, json={"data": [_media("179003", old)]})
        assert req.url.params.get("after") is None
        return httpx.Response(200, json={
            "data": [_media("179001", old), _media("179002", recent)],
            # This URL is intentionally untrusted; the adapter must never access it.
            "paging": {
                "next": "https://untrusted.invalid/leak",
                "cursors": {"after": "CURSOR_2"},
            },
        })

    app = _app(tmp_path)
    transport = OfficialHttp(httpx.Client(transport=httpx.MockTransport(provider)))
    with TestClient(app) as client:
        headers = _auth(client)
        _grant(client, headers)
        first = app.state.ingestion_store.run(
            TENANT, IngestionRequest(platform="instagram", source_account_id=ACCOUNT,
                                     run_key="page-0001", limit=3),
            http=transport,
        )
        assert first.new_records == 1
        assert first.excluded_too_recent == 1
        assert first.next_page_available is True
        with app.state.ingestion_store.engine.connect() as db:
            row = db.execute(select(ingestion_page_checkpoints)).mappings().one()
            assert row["next_cursor"] == "CURSOR_2"
            assert row["complete"] == 0

        second = app.state.ingestion_store.run(
            TENANT, IngestionRequest(platform="instagram", source_account_id=ACCOUNT,
                                     run_key="page-0002", limit=3, resume=True),
            http=transport,
        )
        assert second.new_records == 1
        assert second.excluded_too_recent == 0
        assert second.next_page_available is False
        with app.state.ingestion_store.engine.connect() as db:
            assert db.execute(select(func.count()).select_from(ingestion_records)).scalar_one() == 2
            row = db.execute(select(ingestion_page_checkpoints)).mappings().one()
            assert row["next_cursor"] is None and row["complete"] == 1

        with pytest.raises(ConnectorError) as exc:
            app.state.ingestion_store.run(
                TENANT, IngestionRequest(platform="instagram", source_account_id=ACCOUNT,
                                         run_key="page-0003", resume=True),
                http=transport,
            )
        assert exc.value.code == "PAGINATION_COMPLETE"
    assert all(host == "graph.facebook.com" for host, _, _ in seen)
    assert [after for _, path, after in seen if path.endswith("/media")] == [None, "CURSOR_2"]


def test_resume_requires_a_successful_page_and_no_network(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPI_OFFICIAL_METADATA_READS", "1")
    monkeypatch.setenv("TAPI_ZERO_BILLING_CONFIRMED", "1")
    monkeypatch.setenv("TAPI_INSTAGRAM_ACCESS_TOKEN", "mocked-credentials-that-never-log")
    app = _app(tmp_path)
    with TestClient(app) as client:
        _grant(client, _auth(client))
        with pytest.raises(ConnectorError) as exc:
            app.state.ingestion_store.run(
                TENANT, IngestionRequest(platform="instagram", source_account_id=ACCOUNT,
                                         run_key="page-no-checkpoint", resume=True))
        assert exc.value.code == "PAGINATION_CHECKPOINT_REQUIRED"
        with app.state.ingestion_store.engine.connect() as db:
            assert db.execute(select(func.count()).select_from(ingestion_runs)).scalar_one() == 0


def test_provider_cursor_is_validated_without_following_urls():
    def provider(req):
        if req.url.path.endswith("/178900/media"):
            return httpx.Response(200, json={
                "data": [],
                "paging": {"next": "https://untrusted.invalid", "cursors": {
                    "after": "http://untrusted.invalid/"}},
            })
        raise AssertionError("unexpected network request")

    http = OfficialHttp(httpx.Client(transport=httpx.MockTransport(provider)))
    adapter = InstagramOfficial(http)
    with pytest.raises(ConnectorError) as exc:
        adapter.fetch_page(ACCOUNT, "mocked-credentials-that-never-log",
                           {"username": "approved", "followers_count": 123}, 2)
    assert exc.value.code == "INVALID_PROVIDER_CURSOR"

    with pytest.raises(ConnectorError) as exc:
        adapter.fetch_page(ACCOUNT, "mocked-credentials-that-never-log",
                           {"username": "approved", "followers_count": 123}, 2,
                           after="https://untrusted.invalid")
    assert exc.value.code == "INVALID_PAGINATION_CURSOR"


def test_age_floor_and_platform_contract():
    with pytest.raises(ValueError):
        IngestionRequest(platform="instagram", source_account_id=ACCOUNT,
                         run_key="bad-under-age", min_age_days=13)
    with pytest.raises(ValueError):
        IngestionRequest(platform="youtube", source_account_id="UC123456789",
                         run_key="bad-youtube-resume", resume=True,
                         video_ids=["AZabcdef123"],
                         shorts_evidence_reference="Human confirmation stored in log")
