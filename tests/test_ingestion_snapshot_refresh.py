"""IMP-168: offline refresh should append metrics, never overwrite or invent missing values."""
from datetime import datetime, timedelta, timezone
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tapi_gate0.connectors import OfficialHttp
from tapi_gate0.domain import RankingRequest
from tapi_gate0.ingestion import IngestionRequest, ingestion_records, ingestion_runs
from tapi_gate0.sa_store import metrics_snapshots, content_items, domain_events, outbox
from tapi_gate0.secure_api import create_secure_app

ACCOUNT = "178900"
TENANT = "refresh-check"
PASSWORD = "correct-horse-battery-admin-42-safe"


def app_with_admin(tmp_path):
    app = create_secure_app(f"sqlite:///{tmp_path/'refresh.sqlite3'}",
                            initialize_schema=True, allow_http_local=True)
    app.state.identity_store.bootstrap(TENANT, "Refresh Org", "admin", PASSWORD)
    return app


def test_refresh_preserves_old_snapshots_and_updates_ranking(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPI_OFFICIAL_METADATA_READS", "1")
    monkeypatch.setenv("TAPI_ZERO_BILLING_CONFIRMED", "1")
    monkeypatch.setenv("TAPI_INSTAGRAM_ACCESS_TOKEN", "mocked-credentials-that-never-log")
    state = {"likes": 10, "views": None, "comments": 2, "followers": 100}
    def responder(req):
        if req.url.path.endswith("/178900"):
            return httpx.Response(200, json={
                "id": ACCOUNT, "username": "verified_test", "followers_count": state["followers"]})
        if req.url.path.endswith("/178900/media"):
            return httpx.Response(200, json={"data": [{
                "id": "179001", "media_type": "VIDEO", "media_product_type": "REELS",
                "permalink": "https://www.instagram.com/reel/Refresh1/",
                "timestamp": "2024-01-14T12:00:00Z",
                "caption": "Marketing", "like_count": state["likes"],
                "comments_count": state["comments"],
            }]})
        raise AssertionError("Unexpected external path")
    provider = OfficialHttp(httpx.Client(transport=httpx.MockTransport(responder)))
    app = app_with_admin(tmp_path)
    with TestClient(app) as client:
        login = client.post("/v1/auth/sessions", json={
            "username": "admin", "password": PASSWORD, "tenant_id": TENANT})
        assert login.status_code == 200
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        grant = client.post("/v1/ingestion/grants", json={
            "platform": "instagram", "source_account_id": ACCOUNT,
            "approval_reference": "Approved mock-only test scope",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=20)).isoformat(),
        }, headers=headers)
        assert grant.status_code == 201
        store = app.state.ingestion_store
        def run(key):
            return store.run(TENANT, IngestionRequest(
                platform="instagram", source_account_id=ACCOUNT, run_key=key,
                limit=2), http=provider)
        one = run("run-refresh-1")
        assert (one.new_records, one.refreshed_records, one.duplicate_records) == (1,0,0)
        assert (run("run-refresh-2").new_records, run("run-refresh-3").duplicate_records) == (0,1)

        state["likes"] = 25
        state["followers"] = 125
        refreshed = run("run-refresh-4")
        assert (refreshed.new_records,refreshed.refreshed_records,refreshed.duplicate_records) == (0,1,0)
        unchanged = run("run-refresh-5")
        assert unchanged.duplicate_records == 1 and unchanged.refreshed_records == 0
        with store.engine.connect() as db:
            assert db.execute(select(func.count()).select_from(content_items)).scalar_one() == 1
            assert db.execute(select(func.count()).select_from(ingestion_records)).scalar_one() == 1
            rows = db.execute(select(metrics_snapshots.c.payload)).scalars().all()
            assert len(rows) == 2
            # A2 includes one audited grant-creation event in addition to
            # the two content lifecycle events, all with transactional outbox.
            assert db.execute(select(func.count()).select_from(domain_events)).scalar_one() == 3
            assert db.execute(select(func.count()).select_from(outbox)).scalar_one() == 3
            refreshed_in_ledger = db.execute(
                select(ingestion_runs.c.refreshed_records)
                .where(ingestion_runs.c.run_key == "run-refresh-4")
            ).scalar_one()
            assert refreshed_in_ledger == 1
            assert (db.execute(select(domain_events.c.event_type)
                .where(domain_events.c.aggregate_type == "content")
                .order_by(domain_events.c.aggregate_version)).scalars().all()) == [
                    "ingestion.content_processed", "ingestion.metrics_refreshed"]
            assert db.execute(select(domain_events.c.event_type).where(
                domain_events.c.aggregate_type == "ingestion_source_grant"
            )).scalar_one() == "ingestion.grant.created"
        rank = app.state.local_domain_store.ranking(RankingRequest(
            tenant_id=TENANT, origin="instagram", min_age_days=14,
            as_of=datetime.now(timezone.utc)))
        assert rank.n_posts == 1
        assert rank.rows[0].likes == 25
        assert rank.rows[0].followers == 125
        assert [ __import__("json").loads(x)["likes"] for x in rows ] == [10, 25]


def test_missing_metrics_do_not_erase_last_known_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPI_OFFICIAL_METADATA_READS", "1")
    monkeypatch.setenv("TAPI_ZERO_BILLING_CONFIRMED", "1")
    monkeypatch.setenv("TAPI_INSTAGRAM_ACCESS_TOKEN", "mocked-credentials-that-never-log")
    stats = {"like_count": 2, "comments_count": 1}
    def responder(req):
        if req.url.path.endswith("/178900"):
            return httpx.Response(200, json={
                "id": ACCOUNT, "username": "authorized", "followers_count": 100})
        return httpx.Response(200, json={"data": [{
            "id": "179001", "media_type": "VIDEO", "media_product_type": "REELS",
            "permalink": "https://www.instagram.com/reel/Test/",
            "timestamp": "2024-01-14T12:00:00Z", **stats,
        }]})
    app = app_with_admin(tmp_path)
    provider = OfficialHttp(httpx.Client(transport=httpx.MockTransport(responder)))
    with TestClient(app) as client:
        login = client.post("/v1/auth/sessions", json={
            "username": "admin", "password": PASSWORD, "tenant_id": TENANT})
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        assert client.post("/v1/ingestion/grants", headers=headers, json={
            "platform": "instagram", "source_account_id": ACCOUNT,
            "approval_reference": "Approved mock-only test scope",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=20)).isoformat(),
        }).status_code == 201
        store = app.state.ingestion_store
        def run(k):
            return store.run(TENANT, IngestionRequest(
                platform="instagram", source_account_id=ACCOUNT, run_key=k),
                http=provider)
        assert run("first-read").new_records == 1
        stats.pop("like_count")
        assert run("missing-likes").duplicate_records == 1
        with store.engine.connect() as db:
            assert db.execute(select(func.count()).select_from(metrics_snapshots)).scalar_one() == 1
