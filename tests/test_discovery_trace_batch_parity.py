"""Synthetic-only safety tests of private batched-vs-original audit parity CLI."""
from types import SimpleNamespace as NS
import json

import pytest

from scripts import a6_trace_batch_parity as cli

PIN = "a" * 64
POPULATION = "b" * 64


class FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, _stmt):
        return self

    def scalars(self):
        return self

    def all(self):
        return ["private-run-A", "private-run-B"]


def fixture(monkeypatch, tmp_path, *, drift=False):
    private = tmp_path / "artifacts" / "private"
    private.mkdir(parents=True)
    manifest = private / "manifest.json"
    manifest.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli.BatchManifest, "model_validate_json",
                        lambda _: NS(
                            fingerprint=lambda: PIN,
                            sources=[NS(expected_ig_id="111"),
                                     NS(expected_ig_id="222")],
                        ))
    monkeypatch.setattr(cli, "validate_existing_database_url",
                        lambda url: url)
    engine = NS(connect=lambda: FakeConn(), dispose=lambda: None)
    monkeypatch.setattr(cli, "engine_for", lambda _url: engine)
    calls = {"scope": 0, "population": 0, "original": 0, "batched": 0}

    def scope(*_):
        calls["scope"] += 1

    def population(*_, **__):
        calls["population"] += 1

    def original(_engine, _tenant, key, *, connection):
        calls["original"] += 1
        return {"all_traces_valid": True, "observations": 2,
                "items": [{"content_id": key}]}

    def batched(_engine, _tenant, key, *, connection):
        calls["batched"] += 1
        return {"all_traces_valid": True, "observations": 2,
                "items": [{"content_id":
                           "other-private-run" if drift and key == "private-run-B"
                           else key}]}

    monkeypatch.setattr(cli, "require_scoped_research", scope)
    monkeypatch.setattr(cli, "_population", population)
    monkeypatch.setattr(cli, "audit_run", original)
    monkeypatch.setattr(cli, "audit_run_batched", batched)
    monkeypatch.setenv("TAPI_TENANT_ID", "fixture")
    monkeypatch.setenv("TAPI_META_IG_ID", "12345")
    monkeypatch.setenv("TAPI_DATABASE_URL", "sqlite:///fixture.sqlite3")

    args = [
        "--manifest", str(manifest),
        "--expected-manifest-sha256", PIN,
        "--expected-partition-sha256", POPULATION,
        "--expected-posts", "1069",
        "--expected-sources", "2",
        "--report-name", "trace-parity.json",
        "--confirm-all-ingestion-stopped",
        "--confirm-all-writers-stopped",
    ]
    return private, calls, args


def test_cli_fail_closed_without_stopped_writers(capsys):
    assert cli.main([
        "--manifest", "unavailable.json",
        "--expected-manifest-sha256", PIN,
        "--expected-partition-sha256", POPULATION,
        "--expected-posts", "1069",
        "--expected-sources", "2",
        "--report-name", "trace-parity.json",
    ]) == 2
    assert "TRACE_PARITY_LOCAL_ERROR" in capsys.readouterr().out


def test_cli_exact_parity_rechecks_scope_and_redacts_run_identifiers(
        monkeypatch, tmp_path, capsys):
    private, calls, args = fixture(monkeypatch, tmp_path)
    assert cli.main(args) == 0
    stdout = capsys.readouterr().out
    assert "private-run-A" not in stdout
    assert "private-run-B" not in stdout
    assert "exact_report_parity" in stdout
    report = json.loads(
        (private / "trace-parity.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "TRACE_AUDIT_BATCH_PARITY_VERIFIED"
    assert report["runs_compared"] == 2
    assert report["observations_compared"] == 4
    assert report["new_auditor_wired_into_readiness"] is False
    assert report["database_mutated"] is False
    assert report["external_data_accessed"] is False
    assert len(report["original_per_run_ms"]) == 2
    assert len(report["batched_per_run_ms"]) == 2
    assert calls == {"scope": 3, "population": 2,
                     "original": 2, "batched": 2}
    assert cli.main(args) == 2
    assert "TRACE_PARITY_LOCAL_ERROR" in capsys.readouterr().out


def test_cli_different_evidence_blocks_entire_private_report(
        monkeypatch, tmp_path, capsys):
    private, calls, args = fixture(monkeypatch, tmp_path, drift=True)
    assert cli.main(args) == 2
    assert not (private / "trace-parity.json").exists()
    assert calls["population"] == 1
    assert calls["original"] == 2
    assert calls["batched"] == 2
    assert "TRACE_PARITY_LOCAL_ERROR" in capsys.readouterr().out
