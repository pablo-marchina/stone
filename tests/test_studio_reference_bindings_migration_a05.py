"""0018 schema rehearsal on a disposable database; not production approval."""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, insert, text

from tapi_gate0.sa_store import (
    engine_for, tenants, creators, content_items,
)
from tapi_gate0.studio_e1 import studio_documents
from tapi_gate0.studio_reference_bindings_a05 import studio_reference_bindings


def _cfg(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    url = "sqlite:///" + str(tmp_path / "studio-reference-migration.sqlite")
    monkeypatch.setenv("TAPI_DATABASE_URL", url)
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    return config, url


def test_0018_empty_upgrade_downgrade_roundtrip(tmp_path, monkeypatch):
    cfg, url = _cfg(tmp_path, monkeypatch)
    command.upgrade(cfg, "head")
    engine = engine_for(url)
    assert "studio_reference_bindings" in inspect(engine).get_table_names()
    with engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM studio_reference_bindings")) == 0
    engine.dispose()
    command.downgrade(cfg, "0017_creative_reference_pep")
    engine = engine_for(url)
    assert "studio_reference_bindings" not in inspect(engine).get_table_names()
    engine.dispose()
    command.upgrade(cfg, "head")
    engine = engine_for(url)
    assert "studio_reference_bindings" in inspect(engine).get_table_names()
    engine.dispose()


def test_0018_populated_downgrade_refused(tmp_path, monkeypatch):
    cfg, url = _cfg(tmp_path, monkeypatch)
    command.upgrade(cfg, "head")
    engine = engine_for(url)
    with engine.begin() as db:
        db.execute(insert(tenants).values(tenant_id="tenantA", name="A"))
        db.execute(insert(creators).values(
            tenant_id="tenantA", id="creator", origin="instagram", payload="{}",
        ))
        db.execute(insert(content_items).values(
            tenant_id="tenantA", id="post1", creator_id="creator",
            origin="instagram", published_at="2026-11-01T00:00:00+00:00",
            payload="{}",
        ))
        db.execute(insert(studio_documents).values(
            tenant_id="tenantA", document_id="doc1",
            spec_id="spec", current_version=1,
        ))
        db.execute(insert(studio_reference_bindings).values(
            tenant_id="tenantA", document_id="doc1", content_id="post1",
            grant_id="fictional-grant", reference_set_sha256="a" * 64,
            recorded_at="2026-11-21T00:00:00+00:00",
        ))
    engine.dispose()
    with pytest.raises(RuntimeError, match="STUDIO_REFERENCE_BINDINGS_DOWNGRADE_NONEMPTY"):
        command.downgrade(cfg, "0017_creative_reference_pep")
    engine = engine_for(url)
    assert "studio_reference_bindings" in inspect(engine).get_table_names()
    engine.dispose()
