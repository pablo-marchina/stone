"""IMP-069 A04.4: write-once synthetic evaluation run with local-only gate.

No external requests, operational DB writes, sealed queries or release. Every
validly named invocation writes a terminal result (including FAIL/BLOCKED).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from tapi_gate0.discovery_eval_engine import evaluate_versioned_synthetic

ROOT = Path(__file__).resolve().parents[1]
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json\Z")


def persist_private_report(report: dict, *, directory: Path,
                           report_name: str) -> None:
    """Only an existing, non-symlink private directory; never overwrite."""
    if (not _NAME.fullmatch(report_name)
            or not directory.is_dir() or directory.is_symlink()
            or directory.resolve() != directory.absolute()):
        raise ValueError("EVAL_PRIVATE_PATH_INVALID")
    target = directory / report_name
    # Build bytes before opening so JSON exceptions cannot truncate a report.
    payload = (json.dumps({**report, "report_name": report_name},
                          ensure_ascii=False, sort_keys=True, indent=2,
                          allow_nan=False) + "\n").encode("utf-8")
    # O_EXCL prevents overwrite and symlink redirection at the target path.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--evaluation-version", required=True)
    parser.add_argument("--split", default="validation")
    parser.add_argument("--k", type=int, default=2)
    parser.add_argument("--min-recall-delta", type=float, default=0.0)
    parser.add_argument("--min-ndcg-delta", type=float, default=0.0)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--report-name", required=True)
    a = parser.parse_args(argv)

    private = ROOT / "artifacts" / "private"
    try:
        # Avoid all provider input; only repo-controlled synthetic CT-04 files.
        fixture_dir = (ROOT / "tests" / "fixtures").resolve()
        allowed = (a.fixture.is_file() and not a.fixture.is_symlink()
                   and a.fixture.resolve().parent == fixture_dir
                   and a.fixture.name.startswith("CT-04_fts_")
                   and a.fixture.suffix == ".json")
        raw = a.fixture.read_bytes() if allowed else b""
        result = evaluate_versioned_synthetic(
            raw, expected_sha256=a.expected_sha256,
            evaluation_version=a.evaluation_version, split=a.split,
            k=a.k, min_recall_delta=a.min_recall_delta,
            min_ndcg_delta=a.min_ndcg_delta, plan_only=a.plan_only,
        )
        if not allowed:
            result.update(status="BLOCKED", reason_code="EVAL_FIXTURE_SCOPE_DENIED",
                          local_gate="BLOCKED")
        persist_private_report(result, directory=private, report_name=a.report_name)
        print(json.dumps({**result, "report_name": a.report_name},
                         ensure_ascii=False, allow_nan=False))
        return 0 if result["status"] == "PASS" else 2
    except (OSError, ValueError, TypeError):
        print(json.dumps({"status": "BLOCKED",
                          "reason_code": "EVAL_LOCAL_REPORT_NOT_PERSISTED",
                          "scientifically_validated": False,
                          "gates_released": False,
                          "production_approved": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
