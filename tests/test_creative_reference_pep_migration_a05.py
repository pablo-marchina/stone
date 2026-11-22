"""A05 registry migration rehearsal on disposable SQLite. No real grants."""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, insert, text

from tapi_gate0.sa_store import engine_for, tenants

TABLES = {
    "a054_reference_authorities",
    "a054_reference_revocations",
    "a054_reference_grants",
}


def _config(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    db_url = "sqlite:///" + str(tmp_path / "creative-registry-fixture.sqlite")
    monkeypatch.setenv("TAPI_DATABASE_URL", db_url)
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    return cfg, db_url


def test_empty_registry_migration_round_trip(tmp_path, monkeypatch):
    cfg, db_url = _config(tmp_path, monkeypatch)
    command.upgrade(cfg, "head")
    engine = engine_for(db_url)
    assert TABLES <= set(inspect(engine).get_table_names())
    with engine.connect() as db:
        assert all(db.scalar(text("SELECT count(*) FROM " + name)) == 0
                   for name in TABLES)
    engine.dispose()
    command.downgrade(cfg, "0016_asset_derived_payloads")
    engine = engine_for(db_url)
    assert not TABLES.intersection(inspect(engine).get_table_names())
    engine.dispose()
    command.upgrade(cfg, "head")
    engine = engine_for(db_url)
    assert TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_populated_signed_registry_cannot_be_silently_downgraded(
        tmp_path, monkeypatch):
    cfg, db_url = _config(tmp_path, monkeypatch)
    command.upgrade(cfg, "head")
    engine = engine_for(db_url)
    with engine.begin() as db:
        db.execute(insert(tenants).values(
            tenant_id="fixture-tenant", name="Fixture",
        ))
        db.execute(text(
            "INSERT INTO a054_reference_authorities "
            "(tenant_id, platform, issuer_id, public_key_sha256, revision, state_sha256) "
            "VALUES ('fixture-tenant', 'instagram', 'fixture-issuer', "
            "'0000000000000000000000000000000000000000000000000000000000000000', "
            "0, '1111111111111111111111111111111111111111111111111111111111111111')"
        ))
    engine.dispose()
    with pytest.raises(RuntimeError, match="CREATIVE_REF_REGISTRY_DOWNGRADE_NONEMPTY"):
        command.downgrade(cfg, "0016_asset_derived_payloads")
    engine = engine_for(db_url)
    assert TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()
