"""IMP-060: versioned synthetic FTS5 evaluation replay and private reporter."""
from hashlib import sha256
import json
from pathlib import Path

import pytest

from tapi_gate0.discovery_gold_registry import GoldRegistryError
from tapi_gate0 import discovery_synthetic_eval_run as replay
from scripts import a4_synthetic_eval_report as cli

FIXTURE = Path(__file__).parent / "fixtures" / "CT-04_fts_synthetic.json"


def pinned():
    raw = FIXTURE.read_bytes()
    return raw, sha256(raw).hexdigest()


def test_three_ft5_replays_have_stable_ranked_evidence_and_metric_signature():
    raw, digest = pinned()
    a = replay.replay_synthetic_fts(
        raw, expected_sha256=digest, split="validation", k=2, repeats=3,
    )
    b = replay.replay_synthetic_fts(
        raw, expected_sha256=digest, split="validation", k=2, repeats=2,
    )
    assert a["status"] == "SYNTHETIC_EVALUATION_REPLAY_VERIFIED"
    assert a["evaluation_method"] == "fts5_same_candidate_replay"
    assert a["all_rankings_and_metrics_equal"] is True
    assert a["ranked_evidence_sha256"] == b["ranked_evidence_sha256"]
    assert a["deterministic_result_sha256"] == b["deterministic_result_sha256"]
    assert a["macro_synthetic_recall_at_k"] == 1.0
    assert a["macro_synthetic_ndcg_at_k"] == 1.0
    assert len(a["query_p95_samples_ms"]) == 3
    assert a["sample_p95_is_exploratory_not_service_slo"] is True
    assert a["latency_excludes_index_build"] is True
    for key in ("sealed_test_queried", "scientifically_validated",
                "gold_relevance_judgments_available", "gates_released",
                "baseline_candidate_comparison_completed",
                "production_approved", "database_mutated",
                "external_data_accessed"):
        assert a[key] is False
    for ref in ("sealed_test-query-1", "sealed_test-content-1",
                "validation-content-1", "validation caixa", "fixture-tenant"):
        assert ref not in json.dumps(a)


def test_development_has_distinct_deterministic_signature_from_validation():
    raw, digest = pinned()
    dev = replay.replay_synthetic_fts(raw, expected_sha256=digest,
                                      split="development", repeats=2)
    val = replay.replay_synthetic_fts(raw, expected_sha256=digest,
                                      split="validation", repeats=2)
    assert dev["split"] == "development"
    assert dev["deterministic_result_sha256"] != val["deterministic_result_sha256"]
    assert dev["ranked_evidence_sha256"] != val["ranked_evidence_sha256"]


def test_invalid_k_repeat_and_sealed_split_fail_before_search(monkeypatch):
    raw, digest = pinned()
    called = []
    monkeypatch.setattr(replay, "benchmark_synthetic_fts",
                        lambda *_args, **_kwargs: called.append(True))
    for kwargs, reason in [
        ({"split": "sealed_test"}, "SEALED_SPLIT_FORBIDDEN"),
        ({"repeats": 1}, "REPETITIONS_INVALID"),
        ({"repeats": 6}, "REPETITIONS_INVALID"),
        ({"repeats": True}, "REPETITIONS_INVALID"),
        ({"k": 0}, "K_INVALID"),
    ]:
        with pytest.raises(GoldRegistryError, match=reason):
            replay.replay_synthetic_fts(raw, expected_sha256=digest, **kwargs)
    assert called == []


def test_repeated_rank_drift_blocks_without_accepting_equivalent_scores(monkeypatch):
    raw, digest = pinned()
    original = replay.benchmark_synthetic_fts
    calls = []

    def drift(*args, **kwargs):
        item = original(*args, **kwargs)
        calls.append(True)
        if len(calls) == 2:
            item["ranked_evidence_sha256"] = "f" * 64
        return item

    monkeypatch.setattr(replay, "benchmark_synthetic_fts", drift)
    with pytest.raises(GoldRegistryError, match="DETERMINISTIC_REPLAY_DRIFT"):
        replay.replay_synthetic_fts(raw, expected_sha256=digest, repeats=3)
    assert len(calls) == 2


def test_false_positive_gold_or_gate_flag_is_rejected(monkeypatch):
    raw, digest = pinned()
    original = replay.benchmark_synthetic_fts

    def unsafe(*args, **kwargs):
        item = original(*args, **kwargs)
        item["scientifically_validated"] = True
        item["gates_released"] = True
        return item

    monkeypatch.setattr(replay, "benchmark_synthetic_fts", unsafe)
    with pytest.raises(GoldRegistryError, match="CONTRACT_DRIFT"):
        replay.replay_synthetic_fts(raw, expected_sha256=digest, repeats=2)


def test_invalid_nan_latency_never_persists_evaluation(monkeypatch):
    raw, digest = pinned()
    original = replay.benchmark_synthetic_fts

    def unsafe(*args, **kwargs):
        item = original(*args, **kwargs)
        item["query_latency_p95_ms"] = float("nan")
        return item

    monkeypatch.setattr(replay, "benchmark_synthetic_fts", unsafe)
    with pytest.raises(GoldRegistryError, match="LATENCY_INVALID"):
        replay.replay_synthetic_fts(raw, expected_sha256=digest, repeats=2)


def local_cli_fixture(monkeypatch, tmp_path):
    fixtures = tmp_path / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    data = FIXTURE.read_bytes()
    path = fixtures / "CT-04_fts_synthetic.json"
    path.write_bytes(data)
    private = tmp_path / "artifacts" / "private"
    private.mkdir(parents=True)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    return path, private, sha256(data).hexdigest()


def test_cli_writes_private_once_and_prints_only_aggregate(monkeypatch, tmp_path, capsys):
    path, private, digest = local_cli_fixture(monkeypatch, tmp_path)
    args = ["--fixture", str(path), "--expected-sha256", digest,
            "--repeats", "2", "--split", "validation", "--k", "2",
            "--report-name", "synthetic-run.json"]
    assert cli.main(args) == 0
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["status"] == "SYNTHETIC_EVALUATION_REPLAY_VERIFIED"
    assert report["repetitions"] == 2
    assert report["scientifically_validated"] is False
    assert json.loads((private / "synthetic-run.json").read_text("utf-8")) == report
    assert (private / "synthetic-run.json").stat().st_size > 0
    for ref in ("sealed_test-query-1", "validation-content-1",
                "validation caixa", "fixture-tenant"):
        assert ref not in out
    assert cli.main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"


def test_cli_pin_and_path_fail_closed_without_report(monkeypatch, tmp_path, capsys):
    path, private, digest = local_cli_fixture(monkeypatch, tmp_path)
    args = ["--fixture", str(path), "--expected-sha256", "f" * 64,
            "--repeats", "2", "--report-name", "invalid.json"]
    assert cli.main(args) == 2
    assert not (private / "invalid.json").exists()
    args[3] = digest
    args[1] = str(tmp_path / "not-a-fixture.json")
    assert cli.main(args) == 2
    assert not (private / "invalid.json").exists()
    assert "private" not in capsys.readouterr().out


def test_cli_rejects_missing_private_directory(monkeypatch, tmp_path, capsys):
    path, private, digest = local_cli_fixture(monkeypatch, tmp_path)
    private.rmdir()
    assert cli.main(["--fixture", str(path),
                     "--expected-sha256", digest,
                     "--report-name", "missing.json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"
