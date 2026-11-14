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


def test_registration_prompts_only_password_for_unique_local_admin(tmp_path, monkeypatch, capsys):
    from scripts import a6_corpus_bridge as bridge
    from test_discovery_batch_a4 import manifest, VIEWER
    from tapi_gate0.identity import sessions
    from sqlalchemy import select
    engine = engine_for("sqlite:///" + (tmp_path / "identity.sqlite").as_posix())
    try:
        metadata.create_all(engine)
        identity = IdentityStore(engine)
        password = "fixture-password-123"
        identity.bootstrap("tenant-a", "Fixture", "not-admin", password)
        frame = tmp_path / "manifest.json"
        frame.write_text(manifest(approved=1).model_dump_json(), encoding="utf-8")
        monkeypatch.setenv("TAPI_DATABASE_URL", str(engine.url))
        monkeypatch.setenv("TAPI_TENANT_ID", "tenant-a")
        monkeypatch.setenv("TAPI_META_IG_ID", VIEWER)
        prompts = []
        monkeypatch.setattr(bridge.getpass, "getpass", lambda prompt: (prompts.append(prompt), password)[1])
        def no_login_prompt(*args):
            raise AssertionError("unexpected login prompt")
        monkeypatch.setattr("builtins.input", no_login_prompt)
        def register(db, principal, manifest, viewer, *, stopped):
            assert principal.tenant_id == "tenant-a" and principal.role == "admin"
            assert stopped and viewer == VIEWER
            return {"status": "SAMPLING_PROFILES_REGISTERED", "database_mutated": False}
        monkeypatch.setattr(bridge, "register_sampling_profiles", register)
        assert bridge.main(["--manifest", str(frame), "--register-profiles",
                            "--confirm-all-ingestion-stopped"]) == 0
        assert prompts == ["Admin password: "]
        result = json.loads(capsys.readouterr().out)
        assert result["status"] == "SAMPLING_PROFILES_REGISTERED"
        assert "not-admin" not in json.dumps(result)
        with engine.connect() as db:
            assert db.execute(select(sessions.c.revoked_at)).scalar_one() is not None
    finally:
        engine.dispose()


def test_contextual_synthetic_reports_safe_checkpoint_failure(tmp_path, monkeypatch, capsys):
    from scripts import a6_audience_contextual as runner
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    model = tmp_path / "model"
    model.mkdir()
    def fail(path):
        raise ValueError("CHECKPOINT_REQUIRED_FILE_MISSING: secret/path")
    monkeypatch.setattr(runner, "_checkpoint_api", lambda: (fail, lambda path: None))
    assert runner.main(["--synthetic-smoke", "--model-dir", str(model),
                        "--report-name", "test.json"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["failure_stage"] == "checkpoint_validation"
    assert report["reason_code"] == "CHECKPOINT_REQUIRED_FILE_MISSING"
    assert report["completed_candidates_before_failure"] == 0
    assert "secret" not in json.dumps(report)


def test_contextual_synthetic_cli_with_simulated_model(tmp_path, monkeypatch, capsys):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from scripts import a6_audience_contextual as runner
    from tapi_gate0.system_one_e1 import LocalGLiNERDecider
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    model = tmp_path / "model"
    model.mkdir()
    checkpoint = {"manifest_present": True, "revision": "a"*40,
                  "files": {"model.safetensors": {"sha256": "b"*64}}}
    monkeypatch.setattr(runner, "_checkpoint_api", lambda: (lambda path: checkpoint, lambda path: None))
    class Fake:
        def classify_text(self, text, heads):
            return {key: values[0] for key, values in heads.items()}
    monkeypatch.setattr(runner, "_model_runtime", lambda: (
        lambda path: LocalGLiNERDecider(path, _test_model=Fake()),
        SimpleNamespace(inference_mode=nullcontext)))
    assert runner.main(["--synthetic-smoke", "--model-dir", str(model),
                        "--report-name", "test.json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "CONTEXTUAL_SYNTHETIC_SMOKE"
    assert report["assessed_captions"] == 6
    assert sum(sum(row.values()) for row in report["paired_counts"].values()) == 6
    assert report["scientific_admissions"] == 0
    assert "private_evidence" not in report
    saved = json.loads((tmp_path/"artifacts"/"private"/"test.json").read_text(encoding="utf-8"))
    assert len(saved["private_evidence"]) == 6
    assert runner.FIXTURES[0] not in json.dumps(saved, ensure_ascii=False)
