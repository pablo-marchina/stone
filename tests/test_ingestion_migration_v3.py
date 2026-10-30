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
