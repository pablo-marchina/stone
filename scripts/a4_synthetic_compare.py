"""Run a synthetic-only lexical baseline against in-memory SQLite FTS5.

Reads one SHA-pinned CT-04_fts_*.json from repository fixtures, with no
provider access or operational database. Writes aggregate-only evidence to
artifacts/private with O_EXCL. Never evaluates the sealed_test split.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from tapi_gate0.discovery_gold_registry import GoldRegistryError
from tapi_gate0.discovery_synthetic_comparison import (
    compare_synthetic_baseline_candidate,
)

ROOT = Path(__file__).resolve().parents[1]
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json\Z")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--split", choices=("development", "validation"),
                        default="validation")
    parser.add_argument("--k", type=int, default=2)
    parser.add_argument("--report-name", required=True)
    a = parser.parse_args(argv)
    try:
        fixture_dir = (ROOT / "tests" / "fixtures").resolve()
        private = ROOT / "artifacts" / "private"
        if (not a.fixture.is_file() or a.fixture.is_symlink()
                or a.fixture.resolve().parent != fixture_dir
                or not a.fixture.name.startswith("CT-04_fts_")
                or a.fixture.suffix != ".json"):
            raise GoldRegistryError("GOLD_COMPARE_FIXTURE_SCOPE_DENIED")
        if not private.is_dir() or private.resolve() != private.absolute():
            raise GoldRegistryError("GOLD_COMPARE_PRIVATE_DIRECTORY_REQUIRED")
        if not _NAME.fullmatch(a.report_name):
            raise GoldRegistryError("GOLD_COMPARE_REPORT_NAME_INVALID")
        target = private / a.report_name
        if target.exists() or target.is_symlink():
            raise GoldRegistryError("GOLD_COMPARE_REPORT_EXISTS")
        comparison = compare_synthetic_baseline_candidate(
            a.fixture.read_bytes(), expected_sha256=a.expected_sha256,
            split=a.split, k=a.k,
        )
        if (comparison["scientifically_validated"] is not False
                or comparison["gates_released"] is not False
                or comparison["sealed_test_queried"] is not False
                or comparison["dec006_decided"] is not False):
            raise GoldRegistryError("GOLD_COMPARE_UNSAFE_RESULT")
        report = {**comparison, "report_name": a.report_name}
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2,
                      allow_nan=False)
        print(json.dumps(report, ensure_ascii=False, allow_nan=False))
        return 0
    except (GoldRegistryError, OSError, ValueError, KeyError, TypeError):
        print(json.dumps({
            "status": "BLOCKED",
            "code": "GOLD_COMPARE_LOCAL_INVALID_OR_DENIED",
            "database_mutated": False,
            "external_data_accessed": False,
            "production_approved": False,
        }))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
