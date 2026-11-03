"""Alembic 0003 upgrade/downgrade contracts for existing and clean SQLite databases.

No real providers, external requests, or billing.
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]


def _config(monkeypatch, path):
    monkeypatch.setenv("TAPI_DATABASE_URL", f"sqlite:///{path}")
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return config


def _column_names(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_0002_to_0003_and_rollback_preserve_existing_run(tmp_path, monkeypatch):
    path = tmp_path / "upgrade-existing.sqlite3"
    conf = _config(monkeypatch, path)
    command.upgrade(conf, "0002_official_ingestion")
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as db:
        db.execute(text("INSERT INTO tenants (tenant_id, name) VALUES ('t1', 'Test')"))
        db.execute(text("""INSERT INTO ingestion_source_grants
            (tenant_id,platform,source_account_id,approval_reference,approved_by,
             approved_at,expires_at,enabled)
            VALUES ('t1','instagram','178900','local mock only','test','2026-10-30T00:00:00Z',
                    '2026-11-30T00:00:00Z',1)"""))
        db.execute(text("""INSERT INTO ingestion_runs
            (tenant_id,run_key,platform,source_account_id,requested_at,status,
             new_records,duplicate_records)
            VALUES ('t1','old-run','instagram','178900','2026-10-30T00:00:00Z',
                    'completed',2,0)"""))
    command.upgrade(conf, "head")
    assert inspect(engine).has_table("ingestion_page_checkpoints")
    assert "refreshed_records" in _column_names(engine, "ingestion_runs")
    with engine.connect() as db:
        assert db.execute(text(
            "SELECT new_records, refreshed_records FROM ingestion_runs WHERE run_key='old-run'"
        )).one() == (2, 0)
    command.downgrade(conf, "0002_official_ingestion")
    assert not inspect(engine).has_table("ingestion_page_checkpoints")
    assert "refreshed_records" not in _column_names(engine, "ingestion_runs")
    command.upgrade(conf, "head")
    assert inspect(engine).has_table("ingestion_page_checkpoints")
    assert "refreshed_records" in _column_names(engine, "ingestion_runs")
    engine.dispose()


def test_clean_database_upgrade_head(tmp_path, monkeypatch):
    path = tmp_path / "upgrade-clean.sqlite3"
    conf = _config(monkeypatch, path)
    command.upgrade(conf, "head")
    engine = create_engine(f"sqlite:///{path}")
    assert inspect(engine).has_table("ingestion_page_checkpoints")
    assert "refreshed_records" in _column_names(engine, "ingestion_runs")
    assert "ingestion_source_grants" in inspect(engine).get_table_names()
    engine.dispose()


def test_migrated_schema_persists_new_and_refreshed_metric_snapshots(tmp_path, monkeypatch):
    """Test the actual Alembic schema, not a schema constructed by create_all."""
    from datetime import datetime, timedelta, timezone

    import httpx
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select

    from tapi_gate0.connectors import OfficialHttp
    from tapi_gate0.ingestion import IngestionRequest, ingestion_runs
    from tapi_gate0.sa_store import metrics_snapshots
    from tapi_gate0.secure_api import create_secure_app

    path = tmp_path / "migrated-ingestion.sqlite3"
    conf = _config(monkeypatch, path)
    command.upgrade(conf, "head")
    app = create_secure_app(f"sqlite:///{path}", initialize_schema=False,
                            allow_http_local=True)
    app.state.identity_store.bootstrap(
        "migrated-org", "Migrated org", "admin", "correct-horse-battery-admin-42-safe")
    monkeypatch.setenv("TAPI_OFFICIAL_METADATA_READS", "1")
    monkeypatch.setenv("TAPI_ZERO_BILLING_CONFIRMED", "1")
    monkeypatch.setenv("TAPI_INSTAGRAM_ACCESS_TOKEN", "mocked-credentials-only")
    changing = {"likes": 3}

    def responder(req):
        assert req.url.host == "graph.facebook.com"
        if req.url.path.endswith("/178900"):
            return httpx.Response(200, json={
                "id": "178900", "username": "authorized_fixture", "followers_count": 125})
        assert req.url.path.endswith("/178900/media")
        return httpx.Response(200, json={"data": [{
            "id": "179001", "media_type": "VIDEO", "media_product_type": "REELS",
            "permalink": "https://www.instagram.com/reel/Fixture/",
            "timestamp": "2024-01-01T00:00:00Z", "caption": "Vendas",
            "like_count": changing["likes"], "comments_count": 2,
        }]})

    transport = OfficialHttp(httpx.Client(transport=httpx.MockTransport(responder)))
    with TestClient(app) as cli:
        login = cli.post("/v1/auth/sessions", json={
            "username": "admin", "password": "correct-horse-battery-admin-42-safe",
            "tenant_id": "migrated-org"})
        assert login.status_code == 200
        header = {"Authorization": "Bearer " + login.json()["access_token"]}
        grant = cli.post("/v1/ingestion/grants", headers=header, json={
            "platform": "instagram", "source_account_id": "178900",
            "approval_reference": "Approved offline mock testing only",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()})
        assert grant.status_code == 201
        store = app.state.ingestion_store

        def execute(key):
            return store.run("migrated-org", IngestionRequest(
                platform="instagram", source_account_id="178900", run_key=key),
                http=transport)

        assert execute("migrated-first").new_records == 1
        changing["likes"] = 10
        assert execute("migrated-refresh").refreshed_records == 1
        assert execute("migrated-again").duplicate_records == 1
        with store.engine.connect() as db:
            assert db.execute(select(func.count()).select_from(metrics_snapshots)).scalar_one() == 2
            assert db.execute(select(ingestion_runs.c.refreshed_records).where(
                ingestion_runs.c.run_key == "migrated-refresh")).scalar_one() == 1
