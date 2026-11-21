"""A04.5: read-only Windows native ASR/VLM test-environment preflight.

Checks package metadata, explicit opt-in path *types*, and host headroom. It
never executes or loads models, reads model bytes, accesses providers or the
operational DB, writes files, or modifies resource/safety thresholds.
READY is not model certification or approval of any global gate.
"""
from __future__ import annotations

import argparse
from importlib import metadata
import json
from pathlib import Path
import re
import sys
from typing import Callable, Mapping

VERSION = "tapi-a045-native-preflight.v1"
ASR_PACKAGES = (
    "faster-whisper", "ctranslate2", "onnxruntime", "numpy",
    "tokenizers", "huggingface-hub", "av",
)
REQUIRED_ENV = {
    "asr": ("TAPI_ASR_TEST_MODEL_DIR",),
    "vlm": ("TAPI_VLM_TEST_MODEL_DIR", "TAPI_VLM_TEST_SERVER_EXE"),
}
# The source of authority for these limits is asset_windows_job.py. Values
# are repeated here only as assertions that catch drift, never as overrides.
EXPECTED_LIMITS = {
    "physical_mib": 4096,
    "asr_commit_mib": 7168,
    "vlm_commit_mib": 5120,
}


def _package_status(lookup: Callable[[str], str], name: str):
    try:
        value = lookup(name)
    except metadata.PackageNotFoundError:
        return "MISSING", None
    except Exception:
        return "METADATA_ERROR", None
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+!-]{0,79}", value):
        return "METADATA_INVALID", None
    if name == "faster-whisper" and value != "1.2.1":
        return "PIN_MISMATCH", value
    if name == "cryptography":
        matched = re.match(r"^(\d+)\.", value)
        if not matched or not 44 <= int(matched.group(1)) < 48:
            return "PIN_MISMATCH", value
    return "AVAILABLE", value


def _requirements(mode):
    if mode == "asr":
        return ("asr",)
    if mode == "vlm":
        return ("vlm",)
    if mode == "both":
        return ("asr", "vlm")
    raise ValueError("NATIVE_PREFLIGHT_MODE_INVALID")


def _memory_snapshot():
    from tapi_gate0 import asset_windows_job as jobs
    # Enforce the current production code's exact resource policy. If it
    # changes, require an explicit code review rather than silently passing.
    if (jobs.MODEL_MIN_PHYSICAL_MIB != EXPECTED_LIMITS["physical_mib"]
            or jobs.ModelFixtureLimits().memory_mib
                + jobs.MODEL_COMMIT_RESERVE_MIB != EXPECTED_LIMITS["asr_commit_mib"]
            or jobs.VlmFixtureLimits().memory_mib
                + jobs.MODEL_COMMIT_RESERVE_MIB != EXPECTED_LIMITS["vlm_commit_mib"]):
        raise ValueError("NATIVE_PREFLIGHT_POLICY_DRIFT")
    return jobs.model_host_capacity()


def preflight(mode: str = "both", *,
              version_lookup: Callable[[str], str] = metadata.version,
              memory_probe: Callable[[], Mapping[str, int]] = _memory_snapshot,
              env: Mapping[str, str] | None = None,
              platform: str | None = None,
              is_dir: Callable[[str], bool] | None = None,
              is_file: Callable[[str], bool] | None = None) -> dict:
    """Return aggregate diagnostics; no paths/credentials or model content."""
    import os
    tasks = _requirements(mode)
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    is_dir = (lambda p: Path(p).is_dir() and not Path(p).is_symlink()) if is_dir is None else is_dir
    is_file = (lambda p: Path(p).is_file() and not Path(p).is_symlink()) if is_file is None else is_file
    pkg_names = ("cryptography",) + (ASR_PACKAGES if "asr" in tasks else ())
    packages = {}
    for name in pkg_names:
        state, version = _package_status(version_lookup, name)
        packages[name] = {"status": state, "version": version}
    optins = {}
    for task in tasks:
        for var in REQUIRED_ENV[task]:
            raw = env.get(var)
            valid = isinstance(raw, str) and bool(raw.strip())
            try:
                if valid:
                    valid = (is_file(raw) if var.endswith("_EXE") else is_dir(raw))
            except (OSError, ValueError, RuntimeError):
                valid = False
            optins[var] = "AVAILABLE" if valid else "MISSING_OR_INVALID"
    memory = {}
    if platform != "win32":
        memory = {"status": "WINDOWS_X64_REQUIRED"}
    else:
        try:
            snapshot = memory_probe()
            if (not isinstance(snapshot, Mapping)
                    or any(type(snapshot.get(k)) is not int or snapshot[k] < 0
                           for k in ("available_physical_bytes", "available_commit_bytes"))):
                raise ValueError("INVALID_SNAPSHOT")
            physical = snapshot["available_physical_bytes"] // (1024 * 1024)
            commit = snapshot["available_commit_bytes"] // (1024 * 1024)
            minimum_commit = max(EXPECTED_LIMITS[f"{task}_commit_mib"] for task in tasks)
            ok = (physical >= EXPECTED_LIMITS["physical_mib"]
                  and commit >= minimum_commit)
            memory = {
                "status": "READY_SNAPSHOT" if ok else "HEADROOM_INSUFFICIENT",
                "available_physical_mib": physical,
                "available_commit_mib": commit,
                "required_physical_mib": EXPECTED_LIMITS["physical_mib"],
                "required_commit_mib": minimum_commit,
                "snapshot_not_reservation": True,
            }
        except Exception:
            memory = {"status": "MEMORY_PREFLIGHT_UNAVAILABLE"}
    reasons = []
    if any(v["status"] != "AVAILABLE" for v in packages.values()):
        reasons.append("PACKAGES_NOT_READY")
    if any(v != "AVAILABLE" for v in optins.values()):
        reasons.append("OPTINS_NOT_READY")
    if memory["status"] != "READY_SNAPSHOT":
        reasons.append("MEMORY_NOT_READY")
    return {
        "schema_version": VERSION,
        "status": "READY_FOR_NATIVE_TEST_ATTEMPT" if not reasons else "BLOCKED",
        "mode": mode,
        "reasons": reasons,
        "packages": packages,
        "optins": optins,
        "memory": memory,
        "models_loaded": False,
        "checkpoints_verified": False,
        "runtime_compatibility_verified": False,
        "operational_database_accessed": False,
        "network_accessed": False,
        "global_gates_released": False,
        "production_approved": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("asr", "vlm", "both"), default="both")
    args = parser.parse_args(argv)
    result = preflight(args.mode)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0 if result["status"] == "READY_FOR_NATIVE_TEST_ATTEMPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
