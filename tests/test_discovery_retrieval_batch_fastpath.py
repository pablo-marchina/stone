"""Synthetic tests: proof-gated local batch-only experiment (no real DB)."""
from hashlib import sha256
import json
from types import SimpleNamespace as NS

from scripts import a6_retrieval_batch_fastpath as fast
from scripts import a6_retrieval_preview as qual
from scripts.a6_retrieval_shadow import _digest_ranked_evidence

MANIFEST = "a" * 64
PARTITION = "b" * 64
QUERY = "gestão financeira"


def fixture(monkeypatch, tmp_path):
    private = tmp_path / "artifacts" / "private"
    private.mkdir(parents=True)
    manifest = private / "source.json"
    manifest.write_text("fixture", encoding="utf-8")
    frame = NS(fingerprint=lambda: MANIFEST, sources=[NS(username="fixture")])
    monkeypatch.setattr(qual, "ROOT", tmp_path)
    monkeypatch.setattr(fast, "ROOT", tmp_path)
    monkeypatch.setattr(qual.BatchManifest, "model_validate_json",
                        lambda _: frame)
    monkeypatch.setattr(qual, "validate_existing_database_url",
                        lambda url: url)
    monkeypatch.setattr(fast, "validate_existing_database_url",
                        lambda url: url)
    calls = {"preview": [], "gates": 0, "engine": 0, "deny_final": False,
             "drift": False}

    def engine(_url):
        calls["engine"] += 1
        return NS(dispose=lambda: None)

    def preview(*_args, queries, trace_auditor=None, **_kwargs):
        name = "batched" if trace_auditor is fast.audit_run_batched else "original"
        calls["preview"].append(name)
        return {
            "status": "SCOPED_FTS_LOCAL_PREVIEW_COMPLETED",
            "policy_version": "tapi-imp071-scoped-fts-preview.v1",
            "manifest_sha256": MANIFEST,
            "partition_sha256": PARTITION,
            "eligible_posts": 3,
            "eligible_sources": 1,
            "query_count": len(queries),
            "queries": [{
                "query_sha256": sha256(query.encode("utf-8")).hexdigest(),
                "manifest_sha256": MANIFEST,
                "content_ids": ["private-id"],
                "snapshot_ids": ["private-changed" if calls["drift"] else
                                 "private-snapshot"],
                "hit_count": 1,
                "gold_metrics": None,
                "scientifically_validated": False,
            } for query in queries],
            "p95_search_latency_ms": 0.1,
            "full_preview_elapsed_ms": 100.0,
            "timing_breakdown_ms": {"first_readiness": 10.0},
            "full_preview_includes_scope_and_revalidation": True,
            "gold_relevance_judgments_available": False,
            "scientifically_validated": False,
            "production_approved": False,
            "scientific_admissions": 0,
            "database_mutated": False,
            "external_data_accessed": False,
        }

    def gate(*_args):
        calls["gates"] += 1
        if calls["deny_final"]:
            raise fast.RetrievalBaselineError("SCOPE_DENIED")

    for module in (qual, fast):
        monkeypatch.setattr(module, "engine_for", engine)
        monkeypatch.setattr(module, "preview_scoped_fts", preview)
        monkeypatch.setattr(module, "require_scoped_research", gate)
    monkeypatch.setenv("TAPI_TENANT_ID", "synthetic")
    monkeypatch.setenv("TAPI_META_IG_ID", "synthetic-viewer")
    monkeypatch.setenv("TAPI_DATABASE_URL", "sqlite:///never-opened.sqlite3")

    digest, _ = _digest_ranked_evidence(
        preview(queries=[QUERY]), MANIFEST, PARTITION, 3, 1, [QUERY],
    )
    calls["preview"].clear()
    qargs = [
        "--manifest", str(manifest),
        "--expected-manifest-sha256", MANIFEST,
        "--expected-partition-sha256", PARTITION,
        "--expected-ranking-sha256", digest,
        "--expected-posts", "3", "--expected-sources", "1",
        "--query", QUERY, "--top-k", "5",
        "--qualified-batched-local", "--repeat", "2",
        "--report-name", "qualified.json",
        "--confirm-all-ingestion-stopped", "--confirm-all-writers-stopped",
    ]
    assert qual.main(qargs) == 0
    assert calls["preview"] == ["original", "batched", "original", "batched"]
    proof_path = private / "qualified.json"
    proof_sha = sha256(proof_path.read_bytes()).hexdigest()
    calls["preview"].clear()
    calls["gates"] = 0
    calls["engine"] = 0
    args = [
        "--manifest", str(manifest),
        "--expected-manifest-sha256", MANIFEST,
        "--expected-partition-sha256", PARTITION,
        "--expected-ranking-sha256", digest,
        "--expected-posts", "3", "--expected-sources", "1",
        "--query", QUERY, "--top-k", "5",
        "--qualification-report-name", "qualified.json",
        "--expected-qualification-sha256", proof_sha,
        "--repeat", "2",
        "--report-name", "fast.json",
        "--confirm-all-ingestion-stopped", "--confirm-all-writers-stopped",
    ]
    return private, args, calls


def test_fastpath_only_runs_batch_and_never_writes_private_ids(
        monkeypatch, tmp_path, capsys):
    private, args, calls = fixture(monkeypatch, tmp_path)
    capsys.readouterr()
    assert fast.main(args) == 0
    assert calls == {"preview": ["batched", "batched"], "gates": 1,
                     "engine": 1, "deny_final": False, "drift": False}
    output = capsys.readouterr().out
    assert "private-id" not in output
    assert "private-snapshot" not in output
    assert QUERY not in output
    report = json.loads((private / "fast.json").read_text(encoding="utf-8"))
    assert report["status"] == "RETRIEVAL_BATCH_FASTPATH_LOCAL_VERIFIED"
    assert report["repetitions"] == 2
    assert report["full_preview_latency_samples_ms"] == [100.0, 100.0]
    assert report["single_batched_auditor_per_preview"] is True
    assert report["original_algorithm_unchanged_and_default"] is True
    assert report["production_approved"] is False
    assert "private-id" not in str(report)
    assert "private-snapshot" not in str(report)
    assert fast.main(args) == 2
    assert "FASTPATH_REPORT_ALREADY_EXISTS" in capsys.readouterr().out


def test_fastpath_wrong_qualification_sha_refuses_before_db(
        monkeypatch, tmp_path, capsys):
    private, args, calls = fixture(monkeypatch, tmp_path)
    i = args.index("--expected-qualification-sha256")
    args[i + 1] = "f" * 64
    assert fast.main(args) == 2
    assert calls["engine"] == 0
    assert calls["preview"] == []
    assert not (private / "fast.json").exists()
    assert "FASTPATH_PROOF_SHA_MISMATCH" in capsys.readouterr().out


def test_fastpath_forged_or_revoked_qualification_refuses_before_db(
        monkeypatch, tmp_path, capsys):
    private, args, calls = fixture(monkeypatch, tmp_path)
    path = private / "qualified.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["qualified_batched_local"]["all_rounds_equal_to_canonical"] = False
    path.write_text(json.dumps(payload), encoding="utf-8")
    i = args.index("--expected-qualification-sha256")
    args[i + 1] = sha256(path.read_bytes()).hexdigest()
    assert fast.main(args) == 2
    assert calls["engine"] == 0
    assert calls["preview"] == []
    assert not (private / "fast.json").exists()
    assert "FASTPATH_PROOF_NOT_QUALIFIED" in capsys.readouterr().out


def test_fastpath_snapshot_drift_refuses_before_report(
        monkeypatch, tmp_path, capsys):
    private, args, calls = fixture(monkeypatch, tmp_path)
    calls["drift"] = True
    assert fast.main(args) == 2
    assert calls["preview"] == ["batched"]
    assert not (private / "fast.json").exists()
    assert "FASTPATH_LIVE_RANKING_OR_SNAPSHOT_DRIFT" in capsys.readouterr().out


def test_fastpath_final_grants_denial_refuses_before_report(
        monkeypatch, tmp_path, capsys):
    private, args, calls = fixture(monkeypatch, tmp_path)
    calls["deny_final"] = True
    assert fast.main(args) == 2
    assert calls["preview"] == ["batched", "batched"]
    assert calls["gates"] == 1
    assert not (private / "fast.json").exists()
    assert "SCOPE_DENIED" in capsys.readouterr().out


def test_fastpath_requires_explicit_writers_stopped_before_proof(
        capsys):
    assert fast.main([
        "--manifest", "missing.json",
        "--expected-manifest-sha256", MANIFEST,
        "--expected-partition-sha256", PARTITION,
        "--expected-ranking-sha256", "c" * 64,
        "--expected-qualification-sha256", "d" * 64,
        "--qualification-report-name", "qualified.json",
        "--expected-posts", "3", "--expected-sources", "1",
        "--query", QUERY,
        "--report-name", "fast.json",
    ]) == 2
    assert "FASTPATH_STOP_CONFIRMATION_REQUIRED" in capsys.readouterr().out
