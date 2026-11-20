"""A04 / IMP-060: write one versioned synthetic FTS replay report locally.

Use only repository-controlled synthetic CT-04 fixtures and SHA256-pinned bytes.
The report is created exclusively under artifacts/private and contains no
content IDs, snapshots, query text or judgments. Never overwrite a report.
No provider I/O, database writes, network, production or sealed search.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from tapi_gate0.discovery_gold_registry import GoldRegistryError
from tapi_gate0.discovery_synthetic_eval_run import replay_synthetic_fts

ROOT = Path(__file__).resolve().parents[1]
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json\Z")


def _fail(code):
    raise GoldRegistryError("GOLD_EVAL_RUN_" + code)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--split", choices=("development", "validation"),
                        default="validation")
    parser.add_argument("--k", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--report-name", required=True)
    a = parser.parse_args(argv)
    try:
        allowed = (ROOT / "tests" / "fixtures").resolve()
        private = ROOT / "artifacts" / "private"
        if (not a.fixture.is_file() or a.fixture.is_symlink()
                or a.fixture.resolve().parent != allowed
                or not a.fixture.name.startswith("CT-04_fts_")
                or a.fixture.suffix != ".json"):
            _fail("FIXTURE_SCOPE_DENIED")
        if not private.is_dir() or private.resolve() != private.absolute():
            _fail("PRIVATE_DIRECTORY_REQUIRED")
        if not _NAME.fullmatch(a.report_name):
            _fail("REPORT_NAME_INVALID")
        target = private / a.report_name
        if target.exists() or target.is_symlink():
            _fail("REPORT_ALREADY_EXISTS")
        result = replay_synthetic_fts(
            a.fixture.read_bytes(), expected_sha256=a.expected_sha256,
            split=a.split, k=a.k, repeats=a.repeats,
        )
        if (result["scientifically_validated"] is not False
                or result["gold_relevance_judgments_available"] is not False
                or result["gates_released"] is not False):
            _fail("UNSAFE_REPORT")
        report = {**result, "report_name": a.report_name}
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (GoldRegistryError, OSError, ValueError, TypeError, KeyError):
        print(json.dumps({
            "status": "BLOCKED",
            "code": "GOLD_EVAL_RUN_LOCAL_INVALID_OR_DENIED",
            "database_mutated": False,
            "external_data_accessed": False,
            "production_approved": False,
        }))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
