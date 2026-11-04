"""Alembic migration 0006: append-only provenance without altering older schemas."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_0006_upgrade_downgrade_and_reapply(tmp_path, monkeypatch):
    db_file = tmp_path / "mpe-migrations.sqlite3"
    monkeypatch.setenv("TAPI_DATABASE_URL", "sqlite:///" + str(db_file))
    conf = Config(str(ROOT / "alembic.ini"))
    conf.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(conf, "head")
    db = create_engine("sqlite:///" + str(db_file))
    insp = inspect(db)
    assert insp.has_table("corpus_profiles")
    assert insp.has_table("business_discovery_provenance")
    assert insp.has_table("corpus_source_research_contexts")
    assert insp.has_table("corpus_post_scientific_reviews")
    keys = {c["name"] for c in insp.get_columns("business_discovery_provenance")}
    assert {"approval_proof_sha256", "batch_metadata_sha256", "run_key", "observed_at"} <= keys
    command.downgrade(conf, "0005_scientific_corpus")
    assert not inspect(db).has_table("business_discovery_provenance")
    assert inspect(db).has_table("corpus_profiles")
    assert inspect(db).has_table("corpus_post_scientific_reviews")
    command.upgrade(conf, "head")
    assert inspect(db).has_table("business_discovery_provenance")
    db.dispose()
