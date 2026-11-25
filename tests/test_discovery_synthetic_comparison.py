"""IMP-060 / CT-04 comparison: synthetic-only lexical vs real FTS5."""
from hashlib import sha256
import json
from pathlib import Path

import pytest

from tapi_gate0.discovery_gold_registry import GoldRegistryError
from tapi_gate0 import discovery_synthetic_comparison as compare
from scripts import a4_synthetic_compare as cli

FIXTURE = Path(__file__).parent / "fixtures" / "CT-04_fts_synthetic.json"


def pinned():
    raw = FIXTURE.read_bytes()
    return raw, sha256(raw).hexdigest()


def test_two_distinct_retrievers_on_same_validation_fixture():
    raw, digest = pinned()
    result = compare.compare_synthetic_baseline_candidate(
        raw, expected_sha256=digest, split="validation", k=2,
    )
    assert result["status"] == "SYNTHETIC_BASELINE_CANDIDATE_COMPARISON_VERIFIED"
    assert result["baseline_policy_version"] != result["candidate_policy_version"]
    assert result["comparison_scope"] == "synthetic_validation_only"
    assert result["baseline_candidate_comparison_completed"] is True
    assert result["documents_evaluated"] == 2
    assert result["queries_evaluated"] == 1
    assert result["baseline_synthetic_recall_at_k"] == 1.0
    assert result["candidate_synthetic_recall_at_k"] == 1.0
    assert result["baseline_synthetic_ndcg_at_k"] == 1.0
    assert result["candidate_synthetic_ndcg_at_k"] == 1.0
    assert result["synthetic_recall_delta"] == 0
    assert result["synthetic_ndcg_delta"] == 0
    assert result["baseline_ranked_evidence_sha256"] == result[
        "candidate_ranked_evidence_sha256"
    ]
    assert result["candidate_selected_for_production"] is False
    assert result["dec006_decided"] is False
    for key in ("sealed_test_queried", "scientifically_validated",
                "gold_relevance_judgments_available", "gates_released",
                "production_approved", "database_mutated",
                "external_data_accessed", "independently_validated"):
        assert result[key] is False
    for value in ("sealed_test-query-1", "validation-content-1",
                  "fixture-tenant", "validation caixa"):
        assert value not in str(result)


def test_deterministic_rank_digests_same_between_replays():
    raw, digest = pinned()
    a = compare.compare_synthetic_baseline_candidate(
        raw, expected_sha256=digest,
    )
    b = compare.compare_synthetic_baseline_candidate(
        raw, expected_sha256=digest,
    )
    assert a["baseline_ranked_evidence_sha256"] == b[
        "baseline_ranked_evidence_sha256"]
    assert a["candidate_ranked_evidence_sha256"] == b[
        "candidate_ranked_evidence_sha256"]


def test_dev_split_different_without_sealed():
    raw, digest = pinned()
    result = compare.compare_synthetic_baseline_candidate(
        raw, expected_sha256=digest, split="development",
    )
    assert result["split"] == "development"
    assert result["sealed_test_queried"] is False
    assert result["baseline_synthetic_ndcg_at_k"] == 1.0
    assert result["candidate_synthetic_ndcg_at_k"] == 1.0


def test_sealed_split_and_bad_k_fail_before_benchmark(monkeypatch):
    raw, digest = pinned()
    calls = []
    monkeypatch.setattr(
        compare, "benchmark_synthetic_fts",
        lambda *_args, **_kwargs: calls.append(True),
    )
    for kwargs, expected_error in [
        ({"split": "sealed_test"}, "SEALED_SPLIT_FORBIDDEN"),
        ({"k": 0}, "K_INVALID"),
        ({"k": True}, "K_INVALID"),
    ]:
        with pytest.raises(GoldRegistryError, match=expected_error):
            compare.compare_synthetic_baseline_candidate(
                raw, expected_sha256=digest, **kwargs,
            )
    assert calls == []


def test_tampered_pin_and_creator_leakage_denied():
    raw, digest = pinned()
    with pytest.raises(GoldRegistryError, match="INPUT_SHA_MISMATCH"):
        compare.compare_synthetic_baseline_candidate(
            raw + b" ", expected_sha256=digest,
        )
    payload = json.loads(raw.decode("utf-8"))
    payload["registry"]["documents"][2]["creator_id"] = (
        payload["registry"]["documents"][0]["creator_id"]
    )
    new_raw = json.dumps(payload).encode("utf-8")
    with pytest.raises(GoldRegistryError, match="CREATOR_SPLIT_LEAKAGE"):
        compare.compare_synthetic_baseline_candidate(
            new_raw, expected_sha256=sha256(new_raw).hexdigest(),
        )


def test_candidate_false_gold_approval_is_rejected(monkeypatch):
    raw, digest = pinned()
    original = compare.benchmark_synthetic_fts

    def corrupted(*args, **kwargs):
        result = original(*args, **kwargs)
        result["scientifically_validated"] = True
        return result

    monkeypatch.setattr(compare, "benchmark_synthetic_fts", corrupted)
    with pytest.raises(GoldRegistryError, match="CANDIDATE_CONTRACT_INVALID"):
        compare.compare_synthetic_baseline_candidate(
            raw, expected_sha256=digest,
        )


def test_candidate_policy_drift_and_digest_spoof_fail(monkeypatch):
    raw, digest = pinned()
    original = compare.benchmark_synthetic_fts

    def corrupted(*args, **kwargs):
        result = original(*args, **kwargs)
        result["policy_version"] = "changed"
        return result

    monkeypatch.setattr(compare, "benchmark_synthetic_fts", corrupted)
    with pytest.raises(GoldRegistryError, match="CANDIDATE_CONTRACT_INVALID"):
        compare.compare_synthetic_baseline_candidate(
            raw, expected_sha256=digest,
        )
    monkeypatch.setattr(compare, "benchmark_synthetic_fts",
                        lambda *args, **kwargs: {
                            **original(*args, **kwargs),
                            "ranked_evidence_sha256": "not-a-hash",
                        })
    with pytest.raises(GoldRegistryError, match="CANDIDATE_RANKING_DIGEST_INVALID"):
        compare.compare_synthetic_baseline_candidate(
            raw, expected_sha256=digest,
        )


def cli_fixture(monkeypatch, tmp_path):
    fixture_dir = tmp_path / "tests" / "fixtures"
    fixture_dir.mkdir(parents=True)
    fixture = fixture_dir / "CT-04_fts_synthetic.json"
    raw, digest = pinned()
    fixture.write_bytes(raw)
    private = tmp_path / "artifacts" / "private"
    private.mkdir(parents=True)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    args = ["--fixture", str(fixture), "--expected-sha256", digest,
            "--split", "validation", "--k", "2",
            "--report-name", "synthetic-comparison.json"]
    return private, fixture, args


def test_cli_private_report_and_no_raw_refs(monkeypatch, tmp_path, capsys):
    private, fixture, args = cli_fixture(monkeypatch, tmp_path)
    assert cli.main(args) == 0
    stdout = capsys.readouterr().out
    report = json.loads(stdout)
    assert report["status"] == "SYNTHETIC_BASELINE_CANDIDATE_COMPARISON_VERIFIED"
    assert report["dec006_decided"] is False
    assert report["production_approved"] is False
    saved = json.loads((private / "synthetic-comparison.json").read_text("utf-8"))
    assert saved == report
    assert "sealed_test-content-1" not in stdout
    assert "validation-content-1" not in stdout
    assert "validation caixa" not in stdout
    assert cli.main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"


def test_cli_bad_pin_and_external_path_refused(monkeypatch, tmp_path, capsys):
    private, fixture, args = cli_fixture(monkeypatch, tmp_path)
    args[args.index("--expected-sha256") + 1] = "f" * 64
    assert cli.main(args) == 2
    assert not (private / "synthetic-comparison.json").exists()
    args[args.index("--expected-sha256") + 1] = sha256(fixture.read_bytes()).hexdigest()
    args[args.index("--fixture") + 1] = str(tmp_path / "outside.json")
    assert cli.main(args) == 2
    assert not (private / "synthetic-comparison.json").exists()
    assert "outside.json" not in capsys.readouterr().out


def test_candidate_nan_metric_or_latency_cannot_be_reported(monkeypatch):
    raw, digest = pinned()
    original = compare.benchmark_synthetic_fts
    for field, reason in [
        ("macro_synthetic_ndcg_at_k", "CANDIDATE_METRIC_INVALID"),
        ("query_latency_p95_ms", "CANDIDATE_LATENCY_INVALID"),
    ]:
        def corrupted(*args, **kwargs):
            result = original(*args, **kwargs)
            result[field] = float("nan")
            return result
        monkeypatch.setattr(compare, "benchmark_synthetic_fts", corrupted)
        with pytest.raises(GoldRegistryError, match=reason):
            compare.compare_synthetic_baseline_candidate(
                raw, expected_sha256=digest,
            )
