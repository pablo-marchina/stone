"""Pinned offline analysis of an authored ASR fixture benchmark report.

Only a local, already-existing private JSON source and an unused private JSON
output are accepted. This does not infer speech or release a failed Strict gate.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

from .a00_baseline import check_checkout
from tapi_gate0.asr_strict_diagnostic import diagnose_asr_report
from tapi_gate0.shared_av_asr_diagnostic import diagnose_shared_av_asr

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2_000_000
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")


def _private_file(name: str) -> Path:
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError("A02_PRIVATE_REPORT_NAME_INVALID")
    folder = ROOT / "artifacts" / "private"
    if (not folder.is_dir() or folder.is_symlink()
            or folder.resolve(strict=True) != folder.absolute()):
        raise ValueError("A02_PRIVATE_DIRECTORY_REQUIRED")
    path = folder / name
    if path.is_symlink() or path.resolve() != path.absolute():
        raise ValueError("A02_PRIVATE_REPORT_PATH_INVALID")
    return path


def _unique_pairs(items):
    obj = {}
    for key, value in items:
        if key in obj:
            raise ValueError("A02_DUPLICATE_JSON_KEY")
        obj[key] = value
    return obj


def _read_pinned(path: Path, expected_digest: str) -> dict:
    if not isinstance(expected_digest, str) or not HEX.fullmatch(expected_digest):
        raise ValueError("A02_INPUT_DIGEST_INVALID")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                 | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES:
            raise ValueError("A02_INPUT_REPORT_INVALID")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read(MAX_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) > MAX_BYTES or sha256(data).hexdigest() != expected_digest:
        raise ValueError("A02_INPUT_DIGEST_MISMATCH")
    return json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError("A02_NONFINITE_JSON")))


def _write_new(path: Path, report: dict) -> str:
    data = (json.dumps(report, ensure_ascii=False, allow_nan=False,
                       sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if not 0 < len(data) <= MAX_BYTES:
        raise ValueError("A02_DIAGNOSTIC_OUTPUT_TOO_LARGE")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    return sha256(data).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--report-kind", choices=("asr_fixture", "shared_av"), default="asr_fixture")
    parser.add_argument("--input-name", required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--output-name", required=True)
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", args.expected_head):
            raise ValueError("A02_HEAD_INVALID")
        check_checkout(ROOT, args.expected_head)
        input_path = _private_file(args.input_name)
        output_path = _private_file(args.output_name)
        if input_path == output_path or output_path.exists():
            raise ValueError("A02_OUTPUT_EXISTS")
        report = _read_pinned(input_path, args.input_sha256)
        diagnostic = (diagnose_asr_report(report) if args.report_kind == "asr_fixture"
                      else diagnose_shared_av_asr(report))
        # Re-read and reject changing input bytes, as well as repository drift,
        # immediately before creating output; no approval on any path.
        if _read_pinned(input_path, args.input_sha256) != report:
            raise ValueError("A02_INPUT_CHANGED")
        check_checkout(ROOT, args.expected_head)
        result_sha = _write_new(output_path, diagnostic)
        summary = {
            "status": diagnostic["status"],
            "schema_version": diagnostic["schema_version"],
            "report_kind": args.report_kind,
            "case_count": len(diagnostic["cases"]),
            "output_name": args.output_name, "output_sha256": result_sha,
            "production_approved": False, "global_gates_released": False,
        }
        if args.report_kind == "asr_fixture":
            summary.update({
                "suite": diagnostic["suite"], "candidate": diagnostic["candidate"],
                "strict_failure_case_count": len(diagnostic["strict_failure_cases"]),
                "strict_gate_failure_reasons": diagnostic["strict_gate_failure_reasons"],
                "engineering_gate_passed_in_report": diagnostic["engineering_gate_passed_in_source_report"],
            })
        else:
            summary.update({
                "suite": "shared_av", "candidate": "medium",
                "shared_gate_passed_in_report": diagnostic["source_shared_engineering_gate_passed"],
                "diagnostic_observation_reasons": diagnostic["failure_and_observation_reasons"],
                "strict_thresholds_are_informational_only": True,
            })
        print(json.dumps(summary, sort_keys=True))
        return 0
    except Exception:
        # Never echo a report's transcript, filesystem location, checkpoint
        # details, stack trace, or tokens to a shared console.
        print(json.dumps({"status": "BLOCKED", "code": "A02_ASR_DIAGNOSTIC_BLOCKED",
                          "production_approved": False, "global_gates_released": False},
                         sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
