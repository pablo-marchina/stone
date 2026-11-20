"""Synthetic, offline tests for opt-in full retrieval shadow parity."""
from types import SimpleNamespace as NS
import json

from scripts import a6_retrieval_shadow as cli

MANIFEST = "a" * 64
PARTITION = "b" * 64
Q_HASH = "c" * 64


def fixture(monkeypatch, tmp_path, *, mismatch=False, drift=False, deny=False):
    private = tmp_path / "artifacts" / "private"
    private.mkdir(parents=True)
    manifest = private / "pin.json"
    manifest.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli.BatchManifest, "model_validate_json",
                        lambda _: NS(fingerprint=lambda: MANIFEST,
                                     sources=[NS(username="fixture")]))
    monkeypatch.setattr(cli, "validate_existing_database_url", lambda url: url)
    monkeypatch.setattr(cli, "engine_for",
                        lambda _url: NS(dispose=lambda: None))
    record = {"calls": [], "scopes": 0}

    def preview(*_args, queries, trace_auditor=None, **_kwargs):
        label = "batched" if trace_auditor is cli.audit_run_batched else "original"
        record["calls"].append(label)
        n = len(record["calls"])
        snapshot = "snapshot-updated" if drift and n >= 3 else "private-snapshot"
        content = "private-other-id" if mismatch and label == "batched" else "private-id"
        return {
            "status": "SCOPED_FTS_LOCAL_PREVIEW_COMPLETED",
            "manifest_sha256": MANIFEST,
            "partition_sha256": PARTITION,
            "eligible_posts": 3,
            "eligible_sources": 1,
            "query_count": 1,
            "queries": [{
                "query_sha256": cli.sha256(queries[0].encode()).hexdigest(),
                "manifest_sha256": MANIFEST,
                "hit_count": 1,
                "content_ids": [content],
                "snapshot_ids": [snapshot],
                "gold_metrics": None,
                "scientifically_validated": False,
            }],
            "full_preview_elapsed_ms": float(10 + n),
            "full_preview_includes_scope_and_revalidation": True,
            "gold_relevance_judgments_available": False,
            "scientifically_validated": False,
            "database_mutated": False,
            "external_data_accessed": False,
            "scientific_admissions": 0,
        }

    def gate(*_):
        record["scopes"] += 1
        if deny:
            raise cli.RetrievalBaselineError("SCOPE_DENIED")

    monkeypatch.setattr(cli, "preview_scoped_fts", preview)
    monkeypatch.setattr(cli, "require_scoped_research", gate)
    monkeypatch.setenv("TAPI_TENANT_ID", "fixture-tenant")
    monkeypatch.setenv("TAPI_META_IG_ID", "12345")
    monkeypatch.setenv("TAPI_DATABASE_URL", "sqlite:///fixture.sqlite3")
    argv = [
        "--manifest", str(manifest),
        "--expected-manifest-sha256", MANIFEST,
        "--expected-partition-sha256", PARTITION,
        "--expected-posts", "3",
        "--expected-sources", "1",
        "--query", "gestão financeira",
        "--top-k", "5",
        "--repeat", "3",
        "--report-name", "shadow.json",
        "--confirm-all-ingestion-stopped",
        "--confirm-all-writers-stopped",
    ]
    return private, argv, record


def test_shadow_full_preview_equal_3_runs_and_redacted_stdout(
        monkeypatch, tmp_path, capsys):
    private, argv, record = fixture(monkeypatch, tmp_path)
    assert cli.main(argv) == 0
    assert record["calls"] == [
        "original", "batched", "batched", "original", "original", "batched"
    ]
    assert record["scopes"] == 1
    stdout = capsys.readouterr().out
    for private_item in ("private-id", "private-snapshot", "gestão financeira"):
        assert private_item not in stdout
    data = json.loads((private / "shadow.json").read_text(encoding="utf-8"))
    assert data["status"] == "RETRIEVAL_SHADOW_FULL_PARITY_VERIFIED"
    assert data["all_repetitions_and_rankings_equal"] is True
    assert data["repetitions"] == 3
    assert data["original_full_preview_ms"] == [11.0, 14.0, 15.0]
    assert data["batched_full_preview_ms"] == [12.0, 13.0, 16.0]
    assert data["original_p50_ms"] == 14.0
    assert data["batched_p50_ms"] == 13.0
    assert data["original_p95_ms"] == 15.0
    assert data["batched_p95_ms"] == 16.0
    assert data["batched_runtime_active"] is False
    assert data["original_is_default"]
    assert "content_ids" not in str(data)
    assert "snapshot_ids" not in str(data)
    assert cli.main(argv) == 2
    assert "RETRIEVAL_SHADOW_REPORT_EXISTS" in capsys.readouterr().out


def test_shadow_rank_difference_aborts_without_persisting(
        monkeypatch, tmp_path, capsys):
    private, argv, record = fixture(monkeypatch, tmp_path, mismatch=True)
    assert cli.main(argv) == 2
    assert record["calls"] == ["original", "batched"]
    assert record["scopes"] == 0
    assert not (private / "shadow.json").exists()
    assert "RETRIEVAL_SHADOW_RANK_OR_SNAPSHOT_DRIFT" in capsys.readouterr().out


def test_shadow_new_snapshot_aborts_across_rounds(
        monkeypatch, tmp_path):
    private, argv, record = fixture(monkeypatch, tmp_path, drift=True)
    assert cli.main(argv) == 2
    assert record["calls"] == ["original", "batched", "batched"]
    assert record["scopes"] == 0
    assert not (private / "shadow.json").exists()


def test_shadow_rechecks_live_scope_before_persisting(
        monkeypatch, tmp_path, capsys):
    private, argv, record = fixture(monkeypatch, tmp_path, deny=True)
    assert cli.main(argv) == 2
    assert len(record["calls"]) == 6
    assert record["scopes"] == 1
    assert not (private / "shadow.json").exists()
    assert "SCOPE_DENIED" in capsys.readouterr().out


def test_shadow_requires_stop_confirmation_before_private_or_db(
        capsys):
    assert cli.main([
        "--manifest", "missing.json",
        "--expected-manifest-sha256", MANIFEST,
        "--expected-partition-sha256", PARTITION,
        "--expected-posts", "3",
        "--expected-sources", "1",
        "--query", "gestão",
        "--report-name", "x.json",
    ]) == 2
    assert "STOP_CONFIRMATION_REQUIRED" in capsys.readouterr().out


def test_shadow_invalid_limits_refuse_before_db(
        monkeypatch, tmp_path, capsys):
    _, argv, record = fixture(monkeypatch, tmp_path)
    i = argv.index("--repeat")
    argv[i + 1] = "6"
    assert cli.main(argv) == 2
    assert record == {"calls": [], "scopes": 0}
    assert "RETRIEVAL_SHADOW_LIMITS_INVALID" in capsys.readouterr().out


def test_shadow_rank_contract_rejects_missing_snapshot_or_gold():
    report = {
        "status": "SCOPED_FTS_LOCAL_PREVIEW_COMPLETED",
        "manifest_sha256": MANIFEST,
        "partition_sha256": PARTITION,
        "eligible_posts": 3,
        "eligible_sources": 1,
        "query_count": 1,
        "queries": [{
            "query_sha256": cli.sha256(b"gestao").hexdigest(),
            "manifest_sha256": MANIFEST,
            "hit_count": 1,
            "content_ids": ["secret"],
            "snapshot_ids": [],
            "gold_metrics": None,
            "scientifically_validated": False,
        }],
        "gold_relevance_judgments_available": False,
        "scientifically_validated": False,
        "database_mutated": False,
        "external_data_accessed": False,
        "scientific_admissions": 0,
        "full_preview_includes_scope_and_revalidation": True,
    }
    import pytest
    with pytest.raises(cli.RetrievalBaselineError, match="RESULT_INVALID"):
        cli._digest_ranked_evidence(report, MANIFEST, PARTITION, 3, 1, ["gestao"])
    report["queries"][0]["snapshot_ids"] = ["secret-snapshot"]
    report["queries"][0]["gold_metrics"] = {"recall_at_k": 1.0}
    with pytest.raises(cli.RetrievalBaselineError, match="RESULT_INVALID"):
        cli._digest_ranked_evidence(report, MANIFEST, PARTITION, 3, 1, ["gestao"])
