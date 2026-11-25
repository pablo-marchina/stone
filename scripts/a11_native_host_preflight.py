"""A11: offline, fail-closed Windows native ASR/VLM host preflight.

This checks ONLY runtime prerequisites; it never loads models, opens a
database, fetches media, starts subprocess workers or authorizes production.
Native fixtures MUST still validate checkpoint VAD pins, actual rights,
headroom at execution, bounded job limits and measured output independently.
"""
from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import sys

from .a00_baseline import check_checkout

ROOT = Path(__file__).resolve().parents[1]
VERSION = "tapi-a11-windows-native-prerequisites.v1"
ASR_DISTRIBUTIONS = (
    "faster-whisper", "ctranslate2", "onnxruntime", "numpy",
    "tokenizers", "huggingface-hub", "av",
)
ENV_KEYS = (
    "TAPI_ASR_TEST_MODEL_DIR",
    "TAPI_OCR_TEST_TESSDATA",
    "TAPI_VLM_TEST_MODEL_DIR",
    "TAPI_VLM_TEST_SERVER_EXE",
)
# These constants match asset_windows_job.py. Runtime limits are inspected
# directly before execution; this preflight can never replace that guard.
REQUIRED_PHYSICAL_MIB = 4096
REQUIRED_ASR_COMMIT_MIB = 6144 + 1024
REQUIRED_VLM_COMMIT_MIB = 4096 + 1024
MIB = 1024 * 1024


def assess(*, windows: bool, distributions: dict,
           paths_configured: dict, physical_mib: int | None,
           commit_mib: int | None, memory_error: str | None = None) -> dict:
    """Pure deterministic decision; tests never need real models or Windows."""
    if not isinstance(distributions, dict) or not isinstance(paths_configured, dict):
        raise ValueError("A11_NATIVE_OBSERVATIONS_INVALID")
    packages_missing = sorted(n for n in ASR_DISTRIBUTIONS
                              if distributions.get(n) is None)
    version_pinned = distributions.get("faster-whisper") == "1.2.1"
    path_flags = {k: paths_configured.get(k) is True for k in ENV_KEYS}
    asr_paths = path_flags["TAPI_ASR_TEST_MODEL_DIR"]
    vlm_paths = (path_flags["TAPI_VLM_TEST_MODEL_DIR"]
                 and path_flags["TAPI_VLM_TEST_SERVER_EXE"])
    has_memory = (type(physical_mib) is int and type(commit_mib) is int
                  and physical_mib >= 0 and commit_mib >= 0
                  and memory_error is None)
    physical_ok = bool(has_memory and physical_mib >= REQUIRED_PHYSICAL_MIB)
    asr_commit_ok = bool(has_memory and commit_mib >= REQUIRED_ASR_COMMIT_MIB)
    vlm_commit_ok = bool(has_memory and commit_mib >= REQUIRED_VLM_COMMIT_MIB)
    asr_possible = (windows and not packages_missing and version_pinned
                    and asr_paths and physical_ok and asr_commit_ok)
    vlm_possible = windows and vlm_paths and physical_ok and vlm_commit_ok
    blockers = []
    if not windows:
        blockers.append("WINDOWS_X64_HOST_REQUIRED")
    if packages_missing:
        blockers.append("ASR_DISTRIBUTIONS_MISSING")
    if not version_pinned:
        blockers.append("FASTER_WHISPER_1_2_1_REQUIRED")
    if not asr_paths:
        blockers.append("ASR_MODEL_CONFIG_NOT_PRESENT")
    if not vlm_paths:
        blockers.append("VLM_MODEL_CONFIG_NOT_PRESENT")
    if memory_error or not has_memory:
        blockers.append("NATIVE_MEMORY_SNAPSHOT_UNAVAILABLE")
    elif not physical_ok:
        blockers.append("NATIVE_PHYSICAL_MEMORY_BELOW_REQUIRED")
    if has_memory and not asr_commit_ok:
        blockers.append("ASR_COMMIT_MEMORY_BELOW_REQUIRED")
    if has_memory and not vlm_commit_ok:
        blockers.append("VLM_COMMIT_MEMORY_BELOW_REQUIRED")
    return {
        "schema_version": VERSION,
        "status": ("PREREQUISITES_OBSERVED_NOT_AUTHORIZATION"
                   if asr_possible and vlm_possible else
                   "BLOCKED_NATIVE_PREREQUISITES"),
        "asr_prerequisites": bool(asr_possible),
        "vlm_prerequisites": bool(vlm_possible),
        "missing_distributions": packages_missing,
        "faster_whisper_pinned_1_2_1": version_pinned,
        "model_paths_configured": path_flags,
        "available_physical_mib": physical_mib if has_memory else None,
        "available_commit_mib": commit_mib if has_memory else None,
        "required_physical_mib": REQUIRED_PHYSICAL_MIB,
        "required_asr_commit_mib": REQUIRED_ASR_COMMIT_MIB,
        "required_vlm_commit_mib": REQUIRED_VLM_COMMIT_MIB,
        "blockers": blockers,
        "checks_only": True,
        "native_work_performed": False,
        "network_calls_performed": False,
        "database_mutated": False,
        "scientific_admissions": 0,
        "model_calls_performed": 0,
        "production_approved": False,
        "global_gates_released": False,
    }


def snapshot() -> dict:
    dist = {}
    for package in ASR_DISTRIBUTIONS:
        try:
            dist[package] = version(package)
        except PackageNotFoundError:
            dist[package] = None
    configured = {key: bool(os.environ.get(key)) for key in ENV_KEYS}
    windows = sys.platform == "win32" and sys.maxsize > 2**32
    physical = commit = None
    err = None
    if windows:
        try:
            from tapi_gate0.asset_windows_job import model_host_capacity
            memory = model_host_capacity()
            physical = memory["available_physical_bytes"] // MIB
            commit = memory["available_commit_bytes"] // MIB
        except Exception:
            # Deliberately redact OS exception detail, which may contain host
            # or path information, and refuse an unverifiable capacity report.
            err = "NATIVE_MEMORY_SNAPSHOT_FAILED"
    return assess(windows=windows, distributions=dist,
                  paths_configured=configured,
                  physical_mib=physical, commit_mib=commit,
                  memory_error=err)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-head", required=True)
    args = p.parse_args(argv)
    try:
        check_checkout(ROOT, args.expected_head)
        report = snapshot()
        check_checkout(ROOT, args.expected_head)
        report["commit"] = args.expected_head
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
        return 0 if report["status"] == "PREREQUISITES_OBSERVED_NOT_AUTHORIZATION" else 2
    except Exception as exc:
        # No untrusted input, paths, tokens, database URLs or exception detail.
        print(json.dumps({
            "schema_version": VERSION, "status": "BLOCKED_LOCAL_PRECHECK_ERROR",
            "exception_type": type(exc).__name__,
            "checks_only": True, "native_work_performed": False,
            "network_calls_performed": False, "database_mutated": False,
            "production_approved": False, "global_gates_released": False,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
