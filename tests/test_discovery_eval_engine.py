"""IMP-069 A04.4: synthetic-only local evaluation contract tests."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from tapi_gate0 import discovery_eval_engine as engine
from scripts import a4_eval_engine as cli

FIXTURE = Path(__file__).parent / "fixtures" / "CT-04_fts_synthetic.json"


def pinned():
    raw = FIXTURE.read_bytes()
    return raw, sha256(raw).hexdigest()


def evaluate(**kwargs):
    raw, pin = pinned()
    return engine.evaluate_versioned_synthetic(
        raw, expected_sha256=pin, evaluation_version="a04.4-v1", **kwargs,
    )


def test_local_pass_versions_digest_and_no_global_approval():
    first = evaluate()
    second = evaluate()
    assert first["status"] == "PASS"
    assert first["local_gate"] == "PASS"
    assert first["baseline_policy_version"] != first["candidate_policy_version"]
    assert first["baseline_candidate_comparison_completed"] is True
    assert first["deterministic_result_sha256"] == second["deterministic_result_sha256"]
    assert first["evaluation_spec_sha256"] == second["evaluation_spec_sha256"]
    assert first["documents_evaluated"] == 2
    assert first["queries_evaluated"] == 1
    for field in ("global_gate_released", "sealed_test_queried",
                  "gold_relevance_judgments_available", "scientifically_validated",
                  "gates_released", "external_data_accessed", "database_mutated",
                  "production_approved", "candidate_selected_for_production"):
        assert first[field] is False
    dumped = json.dumps(first)
    for secret in ("fixture-tenant", "validation-content-1", "validation caixa",
                   "sealed_test-content-1", "sealed_test-query-1"):
        assert secret not in dumped


def test_negative_metric_threshold_produces_real_fail():
    result = evaluate(min_recall_delta=0.1, min_ndcg_delta=0.1)
    assert result["status"] == "FAIL"
    assert result["local_gate"] == "FAIL"
    assert result["reason_code"] == "EVAL_THRESHOLD_NOT_MET"
    assert result["baseline_candidate_comparison_completed"] is True
    assert result["synthetic_recall_delta"] == 0
    assert result["global_gate_released"] is False


def test_plan_only_is_not_evaluated(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("comparison must not run")
    monkeypatch.setattr(engine, "compare_synthetic_baseline_candidate", unexpected)
    result = evaluate(plan_only=True)
    assert result["status"] == "NOT_RUN"
    assert result["local_gate"] == "NOT_EVALUATED"
    assert result["baseline_candidate_comparison_completed"] is False
    assert "deterministic_result_sha256" not in result


def test_invalid_pin_split_and_contract_are_blocked_before_comparator(monkeypatch):
    raw, pin = pinned()
    called = []
    monkeypatch.setattr(engine, "compare_synthetic_baseline_candidate",
                        lambda *a, **kw: called.append(1))
    cases = [
        ({"expected_sha256": "0" * 64}, "EVAL_INPUT_SHA_MISMATCH"),
        ({"split": "sealed_test"}, "EVAL_SPEC_INVALID"),
        ({"k": True}, "EVAL_SPEC_INVALID"),
        ({"min_ndcg_delta": float("nan")}, "EVAL_SPEC_INVALID"),
        ({"min_recall_delta": 4}, "EVAL_SPEC_INVALID"),
        ({"evaluation_version": "unsafe/../x"}, "EVAL_SPEC_INVALID"),
    ]
    for change, reason in cases:
        arguments = {"expected_sha256": pin, "evaluation_version": "v1"}
        arguments.update(change)
        record = engine.evaluate_versioned_synthetic(raw, **arguments)
        assert record["status"] == "BLOCKED"
        assert record["reason_code"] == reason
        assert record["global_gate_released"] is False
    assert called == []


def test_version_threshold_change_changes_spec_fingerprint():
    a = evaluate()
    b = evaluate(min_ndcg_delta=0.2)
    c = evaluate(split="development")
    assert a["evaluation_spec_sha256"] != b["evaluation_spec_sha256"]
    assert a["evaluation_spec_sha256"] != c["evaluation_spec_sha256"]


def test_tampered_comparison_is_blocked_without_false_pass(monkeypatch):
    original = engine.compare_synthetic_baseline_candidate
    for field, bad_value, expected_reason in (
        ("candidate_policy_version", "unknown", "EVAL_COMPARISON_CONTRACT_INVALID"),
        ("sealed_test_queried", True, "EVAL_COMPARISON_CONTRACT_INVALID"),
        ("candidate_synthetic_recall_at_k", float("nan"), "EVAL_METRIC_INVALID"),
        ("candidate_ranked_evidence_sha256", "spoof", "EVAL_RANK_DIGEST_INVALID"),
        ("synthetic_ndcg_delta", 0.9, "EVAL_DELTA_MISMATCH"),
    ):
        def corrupted(*args, **kwargs):
            return {**original(*args, **kwargs), field: bad_value}
        monkeypatch.setattr(engine, "compare_synthetic_baseline_candidate", corrupted)
        report = evaluate()
        assert report["status"] == "BLOCKED"
        assert report["reason_code"] == expected_reason
        assert report["global_gate_released"] is False


def test_unexpected_exception_is_generic_and_never_leaks(monkeypatch):
    def failure(*args, **kwargs):
        raise RuntimeError("secret token fixture-tenant validation-content-1")
    monkeypatch.setattr(engine, "compare_synthetic_baseline_candidate", failure)
    result = evaluate()
    assert result["status"] == "ERROR"
    assert result["reason_code"] == "EVAL_RUNTIME_ERROR"
    assert "secret" not in str(result)


def fixture_cli(monkeypatch, tmp_path, *, report_name="imp069.json"):
    raw, pin = pinned()
    fixture_dir = tmp_path / "tests" / "fixtures"
    fixture_dir.mkdir(parents=True)
    fixture = fixture_dir / "CT-04_fts_synthetic.json"
    fixture.write_bytes(raw)
    private = tmp_path / "artifacts" / "private"
    private.mkdir(parents=True)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    args = ["--fixture", str(fixture), "--expected-sha256", pin,
            "--evaluation-version", "a04.4-v1", "--report-name", report_name]
    return private, fixture, args


def test_cli_persists_pass_and_is_write_once(monkeypatch, tmp_path, capsys):
    private, _, args = fixture_cli(monkeypatch, tmp_path)
    assert cli.main(args) == 0
    stdout = json.loads(capsys.readouterr().out)
    report_file = private / "imp069.json"
    saved = json.loads(report_file.read_text("utf-8"))
    assert saved == stdout
    assert saved["status"] == "PASS"
    assert cli.main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"
    assert json.loads(report_file.read_text("utf-8")) == saved
    if os.name == "posix":
        assert (report_file.stat().st_mode & 0o777) == 0o600


def test_cli_persists_fail_and_returns_nonzero(monkeypatch, tmp_path, capsys):
    private, _, args = fixture_cli(monkeypatch, tmp_path, report_name="negative.json")
    args += ["--min-ndcg-delta", "0.5"]
    assert cli.main(args) == 2
    saved = json.loads((private / "negative.json").read_text("utf-8"))
    assert saved["status"] == "FAIL"
    assert saved["reason_code"] == "EVAL_THRESHOLD_NOT_MET"
    assert saved["local_gate"] == "FAIL"
    assert json.loads(capsys.readouterr().out) == saved


def test_cli_persists_blocked_wrong_hash(monkeypatch, tmp_path, capsys):
    private, _, args = fixture_cli(monkeypatch, tmp_path, report_name="blocked.json")
    args[args.index("--expected-sha256") + 1] = "a" * 64
    assert cli.main(args) == 2
    saved = json.loads((private / "blocked.json").read_text("utf-8"))
    assert saved["status"] == "BLOCKED"
    assert saved["reason_code"] == "EVAL_INPUT_SHA_MISMATCH"
    assert "validation caixa" not in capsys.readouterr().out


def test_cli_denies_external_fixture_but_records_block(monkeypatch, tmp_path, capsys):
    private, _, args = fixture_cli(monkeypatch, tmp_path, report_name="out-of-scope.json")
    args[args.index("--fixture") + 1] = str(tmp_path / "other.json")
    assert cli.main(args) == 2
    saved = json.loads((private / "out-of-scope.json").read_text("utf-8"))
    assert saved["reason_code"] == "EVAL_FIXTURE_SCOPE_DENIED"
    assert "other.json" not in capsys.readouterr().out


def test_cli_plan_only_persisted_not_run(monkeypatch, tmp_path, capsys):
    private, _, args = fixture_cli(monkeypatch, tmp_path, report_name="plan.json")
    assert cli.main(args + ["--plan-only"]) == 2
    saved = json.loads((private / "plan.json").read_text("utf-8"))
    assert saved["status"] == "NOT_RUN"
    assert saved["local_gate"] == "NOT_EVALUATED"
    capsys.readouterr()


def test_cli_refuses_symlink_private_and_path_traversal(monkeypatch, tmp_path, capsys):
    private, _, args = fixture_cli(monkeypatch, tmp_path)
    args[args.index("--report-name") + 1] = "../outside.json"
    assert cli.main(args) == 2
    assert not (tmp_path / "artifacts" / "outside.json").exists()
    args[args.index("--report-name") + 1] = "proper.json"
    private.rmdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    try:
        private.symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("creating directory symlinks requires privileges")
    assert cli.main(args) == 2
    assert not (elsewhere / "proper.json").exists()
    capsys.readouterr()


def test_concurrent_write_only_one_succeeds(tmp_path):
    private = tmp_path / "private"
    private.mkdir()
    report = {"status": "BLOCKED", "scientifically_validated": False}
    def write(_):
        try:
            cli.persist_private_report(report, directory=private, report_name="race.json")
            return True
        except FileExistsError:
            return False
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(write, range(2)))
    assert sorted(results) == [False, True]
    assert json.loads((private / "race.json").read_text("utf-8"))["status"] == "BLOCKED"
