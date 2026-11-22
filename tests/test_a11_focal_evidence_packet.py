"""A11: fail-closed synthetic tests of the local validation packet builder.

Mocks subprocess returns. A PASS in these unit tests never claims tests on the
actual operator Windows host or releases G0-G6/IMP-131.
"""
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from scripts import a11_focal_evidence_packet as packet

HEAD = "a" * 40


def done(stdout="", returncode=0, stderr=""):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def node_report(passed=19, total=19, failed=0, skipped=0):
    return (f"ℹ tests {total}\nℹ suites 0\nℹ pass {passed}\n"
            f"ℹ fail {failed}\nℹ cancelled 0\nℹ skipped {skipped}\n"
            "ℹ todo 0\nℹ duration_ms 400\n")


def synthetic_runner(*, pytest_count=269, a06_count=34, a02_count=91,
                     node_count=19, chrome=True,
                     financial=True, syntax_ok=True, pytest_skip=0, git_dirty=False):
    calls = []
    def run(argv, *, timeout, cwd):
        calls.append(tuple(argv))
        if argv[:3] == ["git", "rev-parse", "HEAD"]:
            return done(HEAD + "\n")
        if argv[:2] == ["git", "status"]:
            return done(" M tracked.py\n" if git_dirty else "")
        if argv[-1] == "scripts/verify_zero_spend.py":
            assert argv[-4:] == [
                argv[0], "-X", "utf8", "scripts/verify_zero_spend.py",
            ], "Zero-spend subprocess must force UTF-8 in redirected Windows IO"
            return done("PASS — invariantes locais de gasto zero e bloqueio externo\n"
                        if financial else "FAILED\n", 0 if financial else 1)
        if argv[-1] == "scripts.a05_python_source_preflight":
            return done(json.dumps({
                "schema_version": "stone-python-source-preflight.v1",
                "status": "PASS" if syntax_ok else "BLOCKED",
                "python_grammar": "3.11",
                "files_checked": 364,
                "errors": [] if syntax_ok else [
                    {"path": "src/tapi_gate0/pep.py", "code": "SOURCE_SYNTAX_INVALID"}
                ],
                "deployment_authorized": False,
            }) + "\n", 0 if syntax_ok else 2)
        if "pytest" in argv:
            if "tests/test_asr_strict_diagnostic.py" in argv:
                return done(f"{a02_count} passed in 0.30s\n")
            if "tests/test_studio_synthetic_provenance_a067.py" in argv:
                return done(
                    f"{pytest_count} passed"
                    + (f", {pytest_skip} skipped" if pytest_skip else "")
                    + " in 1.20s\n"
                )
            if "tests/test_multimodal_system_one_bridge.py" in argv:
                return done(f"{a06_count} passed in 0.40s\n")
            return done("13 passed in 0.40s\n")
        if argv[0] == "node":
            return done(node_report(passed=node_count))
        if argv[-1] == "scripts/a07_browser_visual_parity.py":
            return done("A073_BROWSER_PARITY_PASS 7/7\n" if chrome
                        else "A073_BROWSER_INCOMPLETE A073_RUNNING\n",
                        0 if chrome else 1)
        raise AssertionError("Unexpected command " + repr(argv))
    return run, calls


@pytest.fixture
def local_files(tmp_path, monkeypatch):
    files = (
        "scripts/a11_focal_evidence_packet.py",
        "src/tapi_gate0/web/studio_export_e4.js",
    )
    for path in files:
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(("fictional fixture for " + path).encode("utf-8"))
    monkeypatch.setattr(packet, "SOURCE_FILES", files)
    return tmp_path


def test_packet_assembles_exact_local_counts_and_preserves_all_gate_denials(local_files):
    run, calls = synthetic_runner()
    receipt = packet.build_packet(root=local_files, expected_head=HEAD, run=run)
    assert receipt["schema_version"] == "tapi-a11-focal-evidence-packet.v1"
    assert receipt["git_head"] == HEAD
    assert receipt["git_status_reason"] == "A11_CLEAN_HEAD_VERIFIED"
    assert receipt["validation_status"] == "FOCAL_DIAGNOSTICS_VERIFIED_NO_GATE_RELEASE"
    assert receipt["zero_spend_check_observed"] is True
    assert len(receipt["checks"]) == 8
    assert [x["observed_pass_count"] for x in receipt["checks"]] == [1, 1, 91, 269, 34, 13, 19, 7]
    assert all(x["passed"] and x["observed_skip_count"] == 0
               for x in receipt["checks"])
    assert receipt["gate_status"] == {**{f"G{i}": "BLOCKED" for i in range(7)},
                                      "IMP-131": "BLOCKED"}
    for forbidden in ("imp131_accepted", "full_a00_validated_on_this_head",
                      "independent_gold_available", "external_reference_rights_verified",
                      "science_approved", "production_approved",
                      "studio_publication_approved"):
        assert receipt[forbidden] is False
    assert calls[2][1:] == (
        "-X", "utf8", "scripts/verify_zero_spend.py",
    )
    assert calls[3][-1] == "scripts.a05_python_source_preflight"
    assert all("http" not in " ".join(argv).lower() for argv in calls)


@pytest.mark.parametrize("changes,expected_id", [
    ({"a02_count": 90}, "python_a02_asr_diagnostic"),
    ({"pytest_count": 268}, "python_a05_a07"),
    ({"a06_count": 33}, "python_a06_e1"),
    ({"node_count": 18}, "node_a073"),
    ({"chrome": False}, "chrome_a073"),
    ({"pytest_skip": 1}, "python_a05_a07"),
])
def test_missing_results_and_skips_cannot_create_green_packet(
        local_files, changes, expected_id):
    run, _calls = synthetic_runner(**changes)
    receipt = packet.build_packet(root=local_files, run=run)
    assert receipt["validation_status"] == "BLOCKED_NOT_VALIDATED"
    bad = {check["check_id"] for check in receipt["checks"] if not check["passed"]}
    assert expected_id in bad
    assert receipt["gate_status"]["IMP-131"] == "BLOCKED"


def test_zero_spend_preflight_fails_before_any_tests_or_browser(local_files):
    run, calls = synthetic_runner(financial=False)
    receipt = packet.build_packet(root=local_files, run=run)
    assert receipt["validation_status"] == "BLOCKED_ZERO_SPEND_PREFLIGHT"
    assert receipt["zero_spend_check_observed"] is False
    assert len(receipt["checks"]) == 1
    assert len(calls) == 3  # git SHA, git status, zero-spend only


def test_dirty_worktree_and_wrong_head_never_execute_checks(local_files):
    run, calls = synthetic_runner(git_dirty=True)
    result = packet.build_packet(root=local_files, run=run)
    assert result["git_status_reason"] == "A11_TRACKED_WORKTREE_DIRTY"
    assert not result["checks"]
    assert len(calls) == 2
    run, calls = synthetic_runner()
    result = packet.build_packet(root=local_files, expected_head="b" * 40, run=run)
    assert result["git_status_reason"] == "A11_EXPECTED_HEAD_MISMATCH"
    assert not result["checks"]
    assert len(calls) == 2


def test_missing_critical_source_never_executes_any_check(local_files):
    run, calls = synthetic_runner()
    (local_files / "src/tapi_gate0/web/studio_export_e4.js").unlink()
    result = packet.build_packet(root=local_files, run=run)
    assert result["validation_status"] == "BLOCKED_SOURCE_MISSING"
    assert not result["checks"]
    assert len(calls) == 2


def test_raw_log_not_written_and_receipt_cannot_be_overwritten(local_files):
    run, _calls = synthetic_runner()
    receipt = packet.build_packet(root=local_files, run=run)
    location = local_files / "artifacts" / "a11-focal.json"
    digest = packet.write_packet(receipt, location)
    assert len(digest) == 64
    file_bytes = location.read_bytes()
    assert b"PASS \xe2\x80\x94" not in file_bytes
    assert "A073_BROWSER_PARITY_PASS 7/7" not in file_bytes.decode("utf-8")
    assert json.loads(file_bytes)["git_head"] == HEAD
    with pytest.raises(FileExistsError):
        packet.write_packet(receipt, location)


def test_pytest_node_and_chrome_require_complete_counts_and_zero_exit():
    def parse(output, kind, count, code=0):
        return packet._redacted_result(
            ["fixture"], done(output, code), kind=kind, expected_count=count,
        )
    assert parse("269 passed\n", "pytest", 269)["passed"] is True
    assert parse("32 passed\n", "pytest", 32)["passed"] is True
    assert parse("28 passed\n", "pytest", 29)["passed"] is False
    assert parse("269 passed, 1 skipped\n", "pytest", 269)["passed"] is False
    assert parse("269 passed\n", "pytest", 269, code=1)["passed"] is False
    assert parse(node_report(), "node", 19)["passed"] is True
    assert parse(node_report(skipped=1), "node", 19)["passed"] is False
    assert parse("A073_BROWSER_PARITY_PASS 7/7\n", "chrome", 7)["passed"] is True
    assert parse("A073_RUNNING\n", "chrome", 7)["passed"] is False
    assert parse("A073_BROWSER_PARITY_PASS 7/7\n", "chrome", 7, 1)["passed"] is False



def test_tap_marker_is_strict_and_non_tap_text_cannot_forge_summary():
    summary = node_report()
    assert packet._redacted_result(["node"], done(summary),
                                   kind="node", expected_count=19)["passed"] is True
    assert packet._redacted_result(["node"], done(
        summary.replace("ℹ tests 19", "not-a-tap tests 19")
    ), kind="node", expected_count=19)["passed"] is False
    assert packet._redacted_result(["node"], done(
        summary.replace("ℹ tests 19", "ℹ tests 19\nℹ tests 19")
    ), kind="node", expected_count=19)["passed"] is False


def test_zero_spend_stdout_requires_exact_utf8_receipt_and_success_exit():
    receipt = "PASS — invariantes locais de gasto zero e bloqueio externo\n"
    verify = lambda value, code=0: packet._redacted_result(
        ["python", "-X", "utf8", "scripts/verify_zero_spend.py"],
        done(value, code), kind="zero_spend",
    )["passed"]
    assert verify(receipt) is True
    assert verify(receipt.replace("—", "�")) is False
    assert verify(receipt, 1) is False
    assert verify("PASS") is False


def test_mandatory_python_syntax_preflight_stops_before_any_pytest_or_browser(
        local_files):
    run, calls = synthetic_runner(syntax_ok=False)
    receipt = packet.build_packet(root=local_files, run=run)
    assert receipt["validation_status"] == "BLOCKED_PYTHON_SYNTAX_PREFLIGHT"
    assert receipt["zero_spend_check_observed"] is True
    assert [c["check_id"] for c in receipt["checks"]] == [
        "zero_spend", "syntax_preflight",
    ]
    assert receipt["checks"][-1]["reason_code"] == (
        "A11_PYTHON_SYNTAX_PREFLIGHT_BLOCKED"
    )
    assert len(calls) == 4  # git SHA, git status, zero-spend, syntax only
    assert receipt["gate_status"]["IMP-131"] == "BLOCKED"
    assert receipt["production_approved"] is False


@pytest.mark.parametrize("data,rc", [
    ("PASS\n", 0),
    ('{"schema_version":"stone-python-source-preflight.v1","status":"PASS"}', 0),
    (json.dumps({
        "schema_version": "stone-python-source-preflight.v1",
        "status": "PASS", "python_grammar": "3.11",
        "files_checked": 299, "errors": [], "deployment_authorized": False,
    }), 0),
    (json.dumps({
        "schema_version": "stone-python-source-preflight.v1",
        "status": "PASS", "python_grammar": "3.11",
        "files_checked": 365, "errors": [], "deployment_authorized": True,
    }), 0),
    (json.dumps({
        "schema_version": "stone-python-source-preflight.v1",
        "status": "PASS", "python_grammar": "3.11",
        "files_checked": 365, "errors": [], "deployment_authorized": False,
    }), 1),
])
def test_syntax_preflight_rejects_incomplete_forged_or_failed_receipts(data, rc):
    receipt = packet._redacted_result(
        ["python", "-m", "scripts.a05_python_source_preflight"],
        done(data, rc), kind="syntax_preflight", expected_count=1,
    )
    assert receipt["passed"] is False
    assert receipt["reason_code"] == "A11_PYTHON_SYNTAX_PREFLIGHT_BLOCKED"


def test_a06_source_bridge_is_pinned_before_any_focal_execution(local_files):
    from hashlib import sha256
    run, calls = synthetic_runner()
    receipt = packet.build_packet(root=local_files, run=run)
    assert receipt["validation_status"] == "FOCAL_DIAGNOSTICS_VERIFIED_NO_GATE_RELEASE"
    a06 = [c for c in receipt["checks"]
           if c["check_id"] == "python_a06_e1"]
    assert len(a06) == 1
    assert a06[0]["observed_pass_count"] == 34
    assert "tests/test_multimodal_system_one_bridge.py" in calls[6]
    assert receipt["independent_gold_available"] is False
    assert receipt["external_reference_rights_verified"] is False
    assert receipt["production_approved"] is False



def test_a02_asr_strict_failure_diagnostics_are_pinned_but_not_gate_release(local_files):
    run, calls = synthetic_runner()
    receipt = packet.build_packet(root=local_files, run=run)
    assert receipt["validation_status"] == "FOCAL_DIAGNOSTICS_VERIFIED_NO_GATE_RELEASE"
    a02 = [c for c in receipt["checks"]
           if c["check_id"] == "python_a02_asr_diagnostic"]
    assert len(a02) == 1
    assert a02[0]["observed_pass_count"] == 91
    assert "tests/test_asr_strict_diagnostic.py" in calls[4]
    assert "tests/test_a02_asr_strict_diagnostic_cli.py" in calls[4]
    assert "tests/test_shared_av_asr_diagnostic.py" in calls[4]
    assert "tests/test_shared_av_asr_cli.py" in calls[4]
    assert receipt["independent_gold_available"] is False
    assert receipt["production_approved"] is False
