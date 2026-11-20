"""Synthetic contracts for IMP-071 scope-gated FTS preview, no live DB."""
from types import SimpleNamespace as NS
import pytest

from tapi_gate0 import discovery_retrieval_scoped as scoped
from tapi_gate0.discovery_retrieval_fts import RetrievalBaselineError

PIN = "b" * 64


def frame():
    return NS(sources=[NS(username="fixture")], fingerprint=lambda: PIN)


def fake_rows(monkeypatch, *, drift=False, invalid_source=False, bad_trace=False):
    runs = {"ready": 0, "scopes": 0}

    def gate(_engine, _tenant, _frame, _viewer):
        runs["scopes"] += 1
        return "dec018-bd-caption-research.v1"

    def readiness(_engine, _tenant, _frame, _viewer, *, _record_observer, _timing_observer=None):
        runs["ready"] += 1
        captions = [
            ("a", "s-a", "Gestão de pagamentos"),
            ("b", "s-b", "Vendas em pequenos negócios"),
            ("c", "s-c" if not drift or runs["ready"] == 1 else "s-new",
             "Gestão comercial e vendas"),
        ]
        for cid, sid, caption in captions:
            _record_observer(
                NS(username="fixture"),
                NS(content_id=cid, caption=caption),
                NS(snapshot_id=sid),
            )
        if _timing_observer is not None:
            _timing_observer({
                "source_gate_and_inventory_ms": 1.0,
                "domain_read_and_decode_ms": 2.0,
                "technical_trace_audit_ms": 3.0,
                "eligibility_and_observers_ms": 4.0,
                "summary_ms": 5.0,
                "canonical_data_card_ms": 6.0,
                "profile_is_performance_diagnostic_only": True,
            })
        return {
            "status": "CORPUS_READINESS_PLANNED",
            "manifest_sha256": PIN,
            "first_blocking_stage": {"CAPTION_AVAILABLE_FOR_ASSESSMENT": 3},
            "completed_runs_without_valid_bd_trace": 1 if bad_trace else 0,
            "new_scientific_admissions": 0,
            "database_mutated": False,
            "external_data_accessed": False,
            "sources": [{"source_gate":
                         "MANIFEST_SOURCE_EXPIRED" if invalid_source
                         else "TECHNICAL_SCOPE_MATCHED"}],
        }

    monkeypatch.setattr(scoped, "require_scoped_research", gate)
    monkeypatch.setattr(scoped, "readiness_report", readiness)
    return runs


def call():
    return scoped.preview_scoped_fts(
        object(), "tenant", frame(), "viewer",
        queries=["gestao", "vendas"], expected_posts=3,
        expected_sources=1, limit=3,
    )


def test_realistic_ephemeral_preview_gates_twice_without_captions(monkeypatch):
    runs = fake_rows(monkeypatch)
    result = call()
    assert runs == {"ready": 2, "scopes": 3}
    assert result["eligible_posts"] == 3
    assert result["eligible_sources"] == 1
    assert result["manifest_sha256"] == PIN
    assert result["partition_sha256"]
    assert result["status"] == "SCOPED_FTS_LOCAL_PREVIEW_COMPLETED"
    assert result["query_count"] == 2
    assert all(hit["gold_metrics"] is None for hit in result["queries"])
    assert result["p95_search_latency_ms"] >= 0
    assert result["full_preview_elapsed_ms"] >= 0
    assert result["full_preview_includes_scope_and_revalidation"]
    assert result["performance_sample_is_exploratory"]
    assert len(result["timing_breakdown_ms"]) == 6
    assert all(v >= 0 for v in result["timing_breakdown_ms"].values())
    assert result["latency_excludes_readiness_and_index_build"]
    assert result["recall_at_k"] is None and result["ndcg_at_k"] is None
    assert not result["scientifically_validated"]
    assert not result["database_mutated"]
    assert not result["external_data_accessed"]
    assert "Gestão de pagamentos" not in str(result)


def test_denied_first_scope_prevents_eligibility_read(monkeypatch):
    runs = fake_rows(monkeypatch)
    def deny(*_):
        runs["scopes"] += 1
        raise RetrievalBaselineError("RETRIEVAL_SCOPE_DENIED")
    monkeypatch.setattr(scoped, "require_scoped_research", deny)
    with pytest.raises(RetrievalBaselineError, match="SCOPE_DENIED"):
        call()
    assert runs == {"ready": 0, "scopes": 1}


def test_denied_second_scope_does_not_return_hits(monkeypatch):
    runs = fake_rows(monkeypatch)
    def gate(*_):
        runs["scopes"] += 1
        if runs["scopes"] == 2:
            raise RetrievalBaselineError("RETRIEVAL_SCOPE_REVOKED")
    monkeypatch.setattr(scoped, "require_scoped_research", gate)
    with pytest.raises(RetrievalBaselineError, match="SCOPE_REVOKED"):
        call()
    assert runs == {"ready": 1, "scopes": 2}


def test_snapshot_drift_is_fail_closed(monkeypatch):
    runs = fake_rows(monkeypatch, drift=True)
    with pytest.raises(RetrievalBaselineError, match="PARTITION_DRIFT"):
        call()
    assert runs == {"ready": 2, "scopes": 3}


@pytest.mark.parametrize("fault", ["invalid_source", "bad_trace"])
def test_expired_source_or_missing_trace_rejects_data(monkeypatch, fault):
    runs = fake_rows(monkeypatch, **{fault: True})
    with pytest.raises(RetrievalBaselineError,
                       match="SCOPE_OR_POPULATION_MISMATCH"):
        call()
    assert runs == {"ready": 1, "scopes": 1}


def test_requires_expected_population_and_bounded_queries(monkeypatch):
    runs = fake_rows(monkeypatch)
    with pytest.raises(RetrievalBaselineError, match="SCOPE_EXPECTATION_INVALID"):
        scoped.preview_scoped_fts(
            object(), "tenant", frame(), "viewer",
            queries=["vendas"], expected_posts=0, expected_sources=1,
        )
    with pytest.raises(RetrievalBaselineError, match="QUERY_BATCH_INVALID"):
        scoped.preview_scoped_fts(
            object(), "tenant", frame(), "viewer",
            queries=[], expected_posts=3, expected_sources=1,
        )
    assert runs == {"ready": 0, "scopes": 0}


def test_cli_requires_operator_stop_confirmation(monkeypatch, capsys):
    from scripts.a6_retrieval_preview import main
    assert main(["--manifest", "missing.json",
                 "--expected-manifest-sha256", PIN,
                 "--expected-posts", "3", "--expected-sources", "1",
                 "--query", "gestão", "--report-name", "test.json"]) == 2
    assert "RETRIEVAL_STOP_CONFIRMATION_REQUIRED" in capsys.readouterr().out


def test_cli_creates_private_exclusive_report_and_only_prints_aggregate(
        monkeypatch, tmp_path, capsys):
    from scripts import a6_retrieval_preview as cli
    private = tmp_path / "artifacts" / "private"
    private.mkdir(parents=True)
    manifest = private / "scope.json"
    manifest.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli.BatchManifest, "model_validate_json",
                        lambda _text: NS(fingerprint=lambda: PIN))
    monkeypatch.setattr(cli, "validate_existing_database_url",
                        lambda url: url)
    engine = NS(dispose=lambda: None)
    monkeypatch.setattr(cli, "engine_for", lambda _url: engine)
    monkeypatch.setattr(cli, "preview_scoped_fts",
                        lambda *_args, **_kwargs: {
                            "status": "SCOPED_FTS_LOCAL_PREVIEW_COMPLETED",
                            "policy_version": scoped.VERSION,
                            "manifest_sha256": PIN,
                            "partition_sha256": "c" * 64,
                            "eligible_posts": 3, "eligible_sources": 1,
                            "query_count": 1,
                            "queries": [{"query_sha256": "d" * 64,
                                         "hit_count": 1,
                                         "content_ids": ["private-id"],
                                         "snapshot_ids": ["snapshot"]}],
                            "p95_search_latency_ms": 0.3,
                            "full_preview_elapsed_ms": 7.5,
                            "timing_breakdown_ms": {"first_readiness": 3.0},
                        })
    monkeypatch.setenv("TAPI_TENANT_ID", "fixture-tenant")
    monkeypatch.setenv("TAPI_META_IG_ID", "12345")
    monkeypatch.setenv("TAPI_DATABASE_URL", "sqlite:///fixture.sqlite3")
    argv = ["--manifest", str(manifest),
            "--expected-manifest-sha256", PIN,
            "--expected-posts", "3", "--expected-sources", "1",
            "--query", "gestão", "--report-name", "preview.json",
            "--confirm-all-ingestion-stopped", "--confirm-all-writers-stopped"]
    assert cli.main(argv) == 0
    output = capsys.readouterr().out
    assert "private-id" not in output
    assert "gestão" not in output
    assert (private / "preview.json").exists()
    assert "private-id" in (private / "preview.json").read_text(encoding="utf-8")
    assert cli.main(argv) == 2
    assert "RETRIEVAL_REPORT_ALREADY_EXISTS" in capsys.readouterr().out


def test_invalid_query_rejected_before_scoped_database_access(monkeypatch):
    runs = fake_rows(monkeypatch)
    with pytest.raises(RetrievalBaselineError, match="QUERY_TOKENS"):
        scoped.preview_scoped_fts(
            object(), "tenant", frame(), "viewer",
            queries=["!!!"], expected_posts=3, expected_sources=1,
        )
    with pytest.raises(RetrievalBaselineError, match="LIMIT_INVALID"):
        scoped.preview_scoped_fts(
            object(), "tenant", frame(), "viewer",
            queries=["gestão"], expected_posts=3,
            expected_sources=1, limit=51,
        )
    assert runs == {"ready": 0, "scopes": 0}


def test_cli_summary_has_full_timing_without_private_identifiers(
        monkeypatch, tmp_path, capsys):
    from scripts import a6_retrieval_preview as cli
    private = tmp_path / "artifacts" / "private"
    private.mkdir(parents=True)
    manifest = private / "scope.json"
    manifest.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli.BatchManifest, "model_validate_json",
                        lambda _text: NS(fingerprint=lambda: PIN))
    monkeypatch.setattr(cli, "validate_existing_database_url", lambda url: url)
    monkeypatch.setattr(cli, "engine_for", lambda _url: NS(dispose=lambda: None))
    monkeypatch.setattr(cli, "preview_scoped_fts",
                        lambda *_args, **_kwargs: {
                            "status": "SCOPED_FTS_LOCAL_PREVIEW_COMPLETED",
                            "policy_version": scoped.VERSION,
                            "manifest_sha256": PIN,
                            "partition_sha256": "c" * 64,
                            "eligible_posts": 3, "eligible_sources": 1,
                            "query_count": 1,
                            "queries": [{"query_sha256": "d" * 64,
                                         "hit_count": 1,
                                         "content_ids": ["private-id"],
                                         "snapshot_ids": ["private-snapshot"]}],
                            "p95_search_latency_ms": 0.3,
                            "full_preview_elapsed_ms": 7.5,
                            "timing_breakdown_ms": {"first_readiness": 3.0},
                        })
    monkeypatch.setenv("TAPI_TENANT_ID", "fixture")
    monkeypatch.setenv("TAPI_META_IG_ID", "12345")
    monkeypatch.setenv("TAPI_DATABASE_URL", "sqlite:///fixture.sqlite3")
    argv = ["--manifest", str(manifest),
            "--expected-manifest-sha256", PIN,
            "--expected-posts", "3", "--expected-sources", "1",
            "--query", "gestão", "--report-name", "preview.json",
            "--confirm-all-ingestion-stopped", "--confirm-all-writers-stopped"]
    assert cli.main(argv) == 0
    output = capsys.readouterr().out
    assert "full_preview_elapsed_ms" in output
    assert '"full_preview_elapsed_ms": 7.5' in output
    assert "private-id" not in output
    assert "private-snapshot" not in output
    assert "gestão" not in output


def _repeat_fixture(monkeypatch, tmp_path, *, drift=False):
    from scripts import a6_retrieval_preview as cli
    private = tmp_path / "artifacts" / "private"
    private.mkdir(parents=True)
    manifest = private / "scope.json"
    manifest.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli.BatchManifest, "model_validate_json",
                        lambda _text: NS(fingerprint=lambda: PIN))
    monkeypatch.setattr(cli, "validate_existing_database_url", lambda url: url)
    monkeypatch.setattr(cli, "engine_for", lambda _url: NS(dispose=lambda: None))
    n = {"calls": 0}

    def simulate(*_args, **_kwargs):
        n["calls"] += 1
        return {
            "status": "SCOPED_FTS_LOCAL_PREVIEW_COMPLETED",
            "policy_version": scoped.VERSION,
            "manifest_sha256": PIN,
            "partition_sha256": "c" * 64,
            "eligible_posts": 3, "eligible_sources": 1,
            "query_count": 1,
            "queries": [{"query_sha256": "d" * 64,
                         "hit_count": 1,
                         "content_ids": ["private-id"],
                         "snapshot_ids": ["changed" if drift and n["calls"] > 1
                                          else "private-snapshot"]}],
            "p95_search_latency_ms": 0.3,
            "full_preview_elapsed_ms": float(10 - n["calls"]),
            "timing_breakdown_ms": {"first_readiness": 3.0},
            "readiness_profile": ({
                "first_readiness": {"technical_trace_audit_ms": 3.0},
                "second_readiness": {"technical_trace_audit_ms": 4.0},
            } if _kwargs.get("profile_readiness") else None),
        }

    monkeypatch.setattr(cli, "preview_scoped_fts", simulate)
    monkeypatch.setenv("TAPI_TENANT_ID", "fixture-tenant")
    monkeypatch.setenv("TAPI_META_IG_ID", "12345")
    monkeypatch.setenv("TAPI_DATABASE_URL", "sqlite:///fixture.sqlite3")
    argv = ["--manifest", str(manifest),
            "--expected-manifest-sha256", PIN,
            "--expected-posts", "3", "--expected-sources", "1",
            "--query", "gestão", "--report-name", "repeat.json",
            "--repeat", "3",
            "--confirm-all-ingestion-stopped", "--confirm-all-writers-stopped"]
    return cli, argv, n, private


def test_repeat_full_path_reports_samples_and_stable_private_hits(
        monkeypatch, tmp_path, capsys):
    import json
    cli, argv, n, private = _repeat_fixture(monkeypatch, tmp_path)
    assert cli.main(argv) == 0
    assert n["calls"] == 3
    stdout = capsys.readouterr().out
    assert "private-id" not in stdout
    assert "private-snapshot" not in stdout
    assert "gestão" not in stdout
    report = json.loads((private / "repeat.json").read_text(encoding="utf-8"))
    samples = report["repeat_experiment"]
    assert samples["repetitions"] == 3
    assert samples["full_path_latency_samples_ms"] == [9.0, 8.0, 7.0]
    assert samples["full_path_p50_ms"] == 8.0
    assert samples["full_path_p95_ms"] == 9.0
    assert samples["partition_and_hits_stable"] is True
    assert "private-id" in str(report["queries"])


def test_repeat_changed_evidence_ref_blocks_entire_report(
        monkeypatch, tmp_path, capsys):
    cli, argv, n, private = _repeat_fixture(monkeypatch, tmp_path, drift=True)
    assert cli.main(argv) == 2
    assert n["calls"] == 2
    assert not (private / "repeat.json").exists()
    assert "RETRIEVAL_REPEAT_PARTITION_OR_HITS_DRIFT" in capsys.readouterr().out


def test_repeat_bounds_reject_before_database_read(monkeypatch, capsys):
    from scripts.a6_retrieval_preview import main
    assert main(["--manifest", "missing.json",
                 "--expected-manifest-sha256", PIN,
                 "--expected-posts", "3", "--expected-sources", "1",
                 "--query", "gestão", "--report-name", "repeat.json",
                 "--repeat", "11",
                 "--confirm-all-ingestion-stopped",
                 "--confirm-all-writers-stopped"]) == 2
    assert "RETRIEVAL_REPEAT_BOUNDS" in capsys.readouterr().out


def test_optional_readiness_phase_profile_keeps_same_guards_and_hits(monkeypatch):
    runs = fake_rows(monkeypatch)
    report = scoped.preview_scoped_fts(
        object(), "tenant", frame(), "viewer",
        queries=["gestao", "vendas"],
        expected_posts=3, expected_sources=1, limit=3,
        profile_readiness=True,
    )
    assert runs == {"ready": 2, "scopes": 3}
    profile = report["readiness_profile"]
    assert profile["timing_is_diagnostic_only"]
    assert profile["first_readiness"]["technical_trace_audit_ms"] == 3.0
    assert profile["second_readiness"]["canonical_data_card_ms"] == 6.0
    assert len(profile["first_readiness"]) == 7
    assert report["gold_relevance_judgments_available"] is False
    assert report["database_mutated"] is False

    with pytest.raises(RetrievalBaselineError, match="PROFILE_FLAG_INVALID"):
        scoped.preview_scoped_fts(
            object(), "tenant", frame(), "viewer",
            queries=["gestao"], expected_posts=3, expected_sources=1,
            profile_readiness="yes",
        )


def test_cli_profile_option_only_adds_aggregate_timing(
        monkeypatch, tmp_path, capsys):
    import json
    cli, argv, runs, private = _repeat_fixture(monkeypatch, tmp_path)
    argv.append("--profile-readiness")
    assert cli.main(argv) == 0
    assert runs["calls"] == 3
    stdout = capsys.readouterr().out
    assert "technical_trace_audit_ms" in stdout
    assert "private-id" not in stdout
    assert "private-snapshot" not in stdout
    assert "gestão" not in stdout
    report = json.loads((private / "repeat.json").read_text(encoding="utf-8"))
    assert report["readiness_profile"]["first_readiness"]["technical_trace_audit_ms"] == 3.0
    assert report["readiness_profile"]["second_readiness"]["technical_trace_audit_ms"] == 4.0
    samples = report["repeat_experiment"]["readiness_profile_samples"]
    assert len(samples) == 3
    assert all(item["first_readiness"]["technical_trace_audit_ms"] == 3.0
               and item["second_readiness"]["technical_trace_audit_ms"] == 4.0
               for item in samples)


def test_private_shadow_auditor_is_used_on_both_readiness_passes(monkeypatch):
    calls = fake_rows(monkeypatch)
    canonical = scoped.readiness_report
    sentinel = lambda *_args, **_kwargs: None
    auditors = []

    def wrapped(*args, **kwargs):
        auditors.append(kwargs.pop("_trace_auditor", None))
        return canonical(*args, **kwargs)

    monkeypatch.setattr(scoped, "readiness_report", wrapped)
    result = scoped.preview_scoped_fts(
        object(), "tenant", frame(), "viewer",
        queries=["gestao"], expected_posts=3, expected_sources=1,
        trace_auditor=sentinel,
    )
    assert auditors == [sentinel, sentinel]
    assert calls == {"ready": 2, "scopes": 3}
    assert result["query_count"] == 1
    assert result["production_approved"] is False

    with pytest.raises(RetrievalBaselineError, match="TRACE_AUDITOR_INVALID"):
        scoped.preview_scoped_fts(
            object(), "tenant", frame(), "viewer",
            queries=["gestao"], expected_posts=3,
            expected_sources=1, trace_auditor="unsafe",
        )
    assert calls == {"ready": 2, "scopes": 3}
