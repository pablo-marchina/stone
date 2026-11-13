"""Local-only diagnostic and contextual policy integration tests."""
import json
from datetime import timedelta
from sqlalchemy import update

from tapi_gate0.identity import IdentityStore, users, utcnow
from tapi_gate0.sa_store import metadata, engine_for
from scripts.a6_corpus_bridge import inspect_local_admins
from scripts.a6_audience_contextual import main


def test_admin_inspection_is_scoped_and_excludes_secret_columns(tmp_path):
    engine = engine_for("sqlite:///" + (tmp_path / "identity.sqlite").as_posix())
    try:
        metadata.create_all(engine)
        identity = IdentityStore(engine)
        identity.bootstrap("tenant-a", "Fixture", "different-admin", "fixture-password-123")
        assert inspect_local_admins(engine, "tenant-b")["admins"] == []
        report = inspect_local_admins(engine, "tenant-a")
        assert report["admins"] == [{"login": "different-admin", "disabled": False, "temporarily_locked": False}]
        assert "hash" not in json.dumps(report) and "fixture-password" not in json.dumps(report)
        with engine.begin() as db:
            db.execute(update(users).values(locked_until=(utcnow()+timedelta(minutes=15)).isoformat()))
        assert inspect_local_admins(engine, "tenant-a")["admins"][0]["temporarily_locked"]
    finally:
        engine.dispose()


def test_real_contextual_execution_denied_before_model_or_database(capsys, monkeypatch):
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    monkeypatch.setenv("TAPI_DATABASE_URL", "not-a-db")
    assert main(["--execute"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["code"] == "BD_CONTEXTUAL_CLASSIFICATION_SCOPE_BLOCKED"
    assert report["classification_scope_allowed"] is False
    assert report["scientific_admissions"] == 0
    assert main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "CONTEXTUAL_READINESS"
