"""Synthetic, offline tests for A11 native host prerequisites.

No real ASR/VLM process or model is invoked. This suite deliberately proves
that missing native capabilities remain blockers, not accepted outcomes.
"""
import json
from scripts import a11_native_host_preflight as gate


VERSIONS = {
    n: "test-installed" for n in gate.ASR_DISTRIBUTIONS
} | {"faster-whisper": "1.2.1"}
PATHS = {n: True for n in gate.ENV_KEYS}


def observe(**changes):
    base = dict(windows=True, distributions=VERSIONS,
                paths_configured=PATHS, physical_mib=8192,
                commit_mib=12288)
    base.update(changes)
    return gate.assess(**base)


def test_complete_prerequisites_never_release_any_production_gate():
    r = observe()
    assert r["status"] == "PREREQUISITES_OBSERVED_NOT_AUTHORIZATION"
    assert r["asr_prerequisites"] is True
    assert r["vlm_prerequisites"] is True
    assert not r["blockers"]
    for flag in ("native_work_performed", "network_calls_performed",
                 "database_mutated", "production_approved",
                 "global_gates_released", "model_calls_performed"):
        assert r[flag] is False or r[flag] == 0
    assert r["scientific_admissions"] == 0


def test_missing_faster_whisper_fails_asr_but_not_vlm():
    installed = {**VERSIONS, "faster-whisper": None}
    r = observe(distributions=installed)
    assert r["status"] == "BLOCKED_NATIVE_PREREQUISITES"
    assert r["asr_prerequisites"] is False
    assert r["vlm_prerequisites"] is True
    assert r["missing_distributions"] == ["faster-whisper"]
    assert "ASR_DISTRIBUTIONS_MISSING" in r["blockers"]


def test_pinned_whisper_version_required():
    r = observe(distributions={**VERSIONS, "faster-whisper": "1.2.0"})
    assert r["asr_prerequisites"] is False
    assert r["vlm_prerequisites"] is True
    assert "FASTER_WHISPER_1_2_1_REQUIRED" in r["blockers"]


def test_insufficient_physical_memory_blocks_both_without_lowering_limits():
    r = observe(physical_mib=1800, commit_mib=5900)
    assert r["asr_prerequisites"] is False
    assert r["vlm_prerequisites"] is False
    assert "NATIVE_PHYSICAL_MEMORY_BELOW_REQUIRED" in r["blockers"]
    assert r["required_physical_mib"] == 4096
    assert r["required_asr_commit_mib"] == 7168
    assert r["required_vlm_commit_mib"] == 5120


def test_asr_and_vlm_commit_require_distinct_budgets():
    r = observe(physical_mib=8192, commit_mib=5900)
    assert r["asr_prerequisites"] is False
    assert r["vlm_prerequisites"] is True
    assert "ASR_COMMIT_MEMORY_BELOW_REQUIRED" in r["blockers"]


def test_missing_fixture_optins_only_block_corresponding_adapter():
    r = observe(paths_configured={
        **PATHS, "TAPI_ASR_TEST_MODEL_DIR": False,
    })
    assert r["asr_prerequisites"] is False
    assert r["vlm_prerequisites"] is True
    r = observe(paths_configured={
        **PATHS, "TAPI_VLM_TEST_SERVER_EXE": False,
    })
    assert r["asr_prerequisites"] is True
    assert r["vlm_prerequisites"] is False


def test_os_or_memory_probe_unavailable_blocks_admission():
    assert not observe(windows=False)["asr_prerequisites"]
    assert not observe(windows=False)["vlm_prerequisites"]
    r = observe(physical_mib=None, commit_mib=None,
                memory_error="WIN32_PROBE_FAILED")
    assert "NATIVE_MEMORY_SNAPSHOT_UNAVAILABLE" in r["blockers"]
    assert r["available_physical_mib"] is None
    assert not r["asr_prerequisites"] and not r["vlm_prerequisites"]


def test_preflight_cli_does_not_echo_paths_or_exception_messages(
        monkeypatch, capsys):
    monkeypatch.setattr(gate, "check_checkout", lambda *_: None)
    monkeypatch.setattr(gate, "snapshot", lambda: observe())
    assert gate.main(["--expected-head", "a" * 40]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["commit"] == "a" * 40
    assert receipt["production_approved"] is False

    def fail():
        raise RuntimeError("sensitive path C:\\Users\\private")
    monkeypatch.setattr(gate, "snapshot", fail)
    assert gate.main(["--expected-head", "a" * 40]) == 2
    output = capsys.readouterr().out
    assert "private" not in output
    assert json.loads(output)["status"] == "BLOCKED_LOCAL_PRECHECK_ERROR"
