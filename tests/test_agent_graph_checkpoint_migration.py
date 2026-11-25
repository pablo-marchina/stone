"""IMP-074: isolated Alembic upgrade/downgrade, no operational DB."""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, insert

from tapi_gate0.agent_graph_checkpoints import begin_run
from tapi_gate0.sa_store import engine_for, tenants

TABLES = {"agent_graph_runs", "agent_graph_events"}


def _cfg(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    db_url = "sqlite:///" + (tmp_path / "agent-checkpoints.sqlite").as_posix()
    monkeypatch.setenv("TAPI_DATABASE_URL", db_url)
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    return cfg, db_url


def test_empty_agent_graph_migration_roundtrip(tmp_path, monkeypatch):
    cfg, db_url = _cfg(tmp_path, monkeypatch)
    command.upgrade(cfg, "head")
    engine = engine_for(db_url)
    assert TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()
    command.downgrade(cfg, "0018_studio_reference_bindings")
    engine = engine_for(db_url)
    assert TABLES.isdisjoint(inspect(engine).get_table_names())
    engine.dispose()
    command.upgrade(cfg, "head")
    engine = engine_for(db_url)
    assert TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_nonempty_agent_graph_migration_refuses_downgrade(tmp_path, monkeypatch):
    cfg, db_url = _cfg(tmp_path, monkeypatch)
    command.upgrade(cfg, "head")
    engine = engine_for(db_url)
    with engine.begin() as db:
        db.execute(insert(tenants).values(tenant_id="tenant.1", name="Fixture"))
    begin_run(engine, tenant="tenant.1", actor="fixture.actor",
              run_id="graph.1", mode="analisar", plan_sha256="a" * 64)
    engine.dispose()
    with pytest.raises(RuntimeError, match="AGENT_GRAPH_CHECKPOINT_DOWNGRADE_NONEMPTY"):
        command.downgrade(cfg, "0018_studio_reference_bindings")
    engine = engine_for(db_url)
    assert TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_migration_never_backfills_grants_or_agent_runs(tmp_path, monkeypatch):
    cfg, db_url = _cfg(tmp_path, monkeypatch)
    command.upgrade(cfg, "head")
    engine = engine_for(db_url)
    with engine.connect() as db:
        for table in TABLES:
            assert db.exec_driver_sql("SELECT count(*) FROM " + table).scalar() == 0
    engine.dispose()
