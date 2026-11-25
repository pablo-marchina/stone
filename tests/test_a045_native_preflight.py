"""A04.5 read-only preflight contract, independent of hardware/runtime."""
from importlib import metadata
import json

import pytest

from scripts import a045_native_preflight as p


PACKAGES = {"cryptography": "45.0.0", "faster-whisper": "1.2.1",
            "ctranslate2": "4.6.0", "onnxruntime": "1.22.0", "numpy": "2.0.0",
            "tokenizers": "0.21.0", "huggingface-hub": "0.34.0", "av": "14.0.0"}
ENVS = {"TAPI_ASR_TEST_MODEL_DIR": "local-asr",
        "TAPI_VLM_TEST_MODEL_DIR": "local-vlm",
        "TAPI_VLM_TEST_SERVER_EXE": "local-server.exe"}


def kw(*, pkgs=None, memory=(8192, 9000), env=None, platform="win32"):
    packages = PACKAGES if pkgs is None else pkgs
    provided_env = ENVS if env is None else env
    def lookup(name):
        if name not in packages:
            raise metadata.PackageNotFoundError(name)
        return packages[name]
    return dict(version_lookup=lookup, memory_probe=lambda: {
        "available_physical_bytes": memory[0] * 1024 ** 2,
        "available_commit_bytes": memory[1] * 1024 ** 2,
    }, env=provided_env, platform=platform,
    is_dir=lambda s:s in ("local-asr", "local-vlm"),
    is_file=lambda s:s == "local-server.exe")


def test_ready_both_and_no_unsafe_claims():
    r = p.preflight("both", **kw())
    assert r["status"] == "READY_FOR_NATIVE_TEST_ATTEMPT"
    assert r["reasons"] == []
    assert r["memory"]["required_commit_mib"] == 7168
    assert r["memory"]["snapshot_not_reservation"] is True
    for field in ("models_loaded", "checkpoints_verified", "runtime_compatibility_verified",
                  "operational_database_accessed", "network_accessed",
                  "global_gates_released", "production_approved"):
        assert r[field] is False
    assert "local-asr" not in str(r) and "local-vlm" not in str(r)


def test_missing_faster_and_low_headroom_have_two_reasons():
    packages={k:v for k,v in PACKAGES.items() if k != "faster-whisper"}
    r=p.preflight("both", **kw(pkgs=packages,memory=(2500,6010)))
    assert r["status"] == "BLOCKED"
    assert r["packages"]["faster-whisper"]["status"] == "MISSING"
    assert set(r["reasons"]) == {"PACKAGES_NOT_READY", "MEMORY_NOT_READY"}
    assert r["memory"]["required_physical_mib"] == 4096
    assert r["memory"]["required_commit_mib"] == 7168


def test_vlm_only_does_not_require_faster_whisper():
    r=p.preflight("vlm", **kw(pkgs={"cryptography":"46.0.0"},memory=(4096,5120)))
    assert r["status"] == "READY_FOR_NATIVE_TEST_ATTEMPT"
    assert "faster-whisper" not in r["packages"]
    assert r["memory"]["required_commit_mib"] == 5120


def test_asr_requires_exact_pinned_distribution_and_more_commit():
    packages={**PACKAGES,"faster-whisper":"1.2.0"}
    r=p.preflight("asr", **kw(pkgs=packages,memory=(4096,6500)))
    assert r["status"] == "BLOCKED"
    assert r["packages"]["faster-whisper"]["status"] == "PIN_MISMATCH"
    assert r["memory"]["required_commit_mib"] == 7168
    assert "TAPI_VLM_TEST_MODEL_DIR" not in r["optins"]


def test_crypto_version_pin_and_invalid_optins():
    r=p.preflight("vlm", **kw(pkgs={"cryptography":"43.0"}, env={}))
    assert r["status"] == "BLOCKED"
    assert "PACKAGES_NOT_READY" in r["reasons"]
    assert "OPTINS_NOT_READY" in r["reasons"]
    assert r["packages"]["cryptography"]["status"] == "PIN_MISMATCH"


def test_non_windows_or_memory_probe_failure_blocked_without_false_pass():
    r=p.preflight("vlm", **kw(platform="linux"))
    assert r["memory"]["status"] == "WINDOWS_X64_REQUIRED"
    o=kw();o["memory_probe"]=lambda: 1/0
    r=p.preflight("vlm", **o)
    assert r["memory"]["status"] == "MEMORY_PREFLIGHT_UNAVAILABLE"
    assert "MEMORY_NOT_READY" in r["reasons"]


def test_bad_mode_rejected_and_versions_not_injected_as_errors():
    with pytest.raises(ValueError, match="MODE_INVALID"):
        p.preflight("sealed_test", **kw())
    o=kw();o["version_lookup"]=lambda _: (_ for _ in ()).throw(
        RuntimeError("do not leak secret"))
    r=p.preflight("asr", **o)
    assert r["status"] == "BLOCKED"
    assert "do not leak secret" not in json.dumps(r)


def test_snapshot_invalid_rejected():
    o=kw();o["memory_probe"]=lambda: {"available_physical_bytes":float("nan"),
                                      "available_commit_bytes":0}
    r=p.preflight("vlm", **o)
    assert r["memory"] == {"status":"MEMORY_PREFLIGHT_UNAVAILABLE"}
