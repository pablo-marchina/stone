"""IMP-060: inspect one pinned, repository-local SYNTHETIC CT-04 fixture.

No real gold, human labels, external sources, backend writes or network. The
fixture must reside directly under tests/fixtures; print aggregates only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tapi_gate0.discovery_gold_registry import (
    GoldRegistryError, load_synthetic_registry_bytes,
)

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--expected-sha256", required=True)
    a = p.parse_args(argv)
    try:
        allowed = (ROOT / "tests" / "fixtures").resolve()
        if (not a.fixture.is_file() or a.fixture.is_symlink()
                or a.fixture.resolve().parent != allowed
                or not a.fixture.name.startswith("CT-04_")
                or a.fixture.suffix.lower() != ".json"):
            raise GoldRegistryError("GOLD_REGISTRY_FIXTURE_SCOPE_DENIED")
        registry = load_synthetic_registry_bytes(
            a.fixture.read_bytes(), expected_sha256=a.expected_sha256,
        )
        print(json.dumps({
            "status": "SYNTHETIC_GOLD_REGISTRY_CONTRACT_VERIFIED",
            **registry.summary(),
            "database_mutated": False,
            "external_data_accessed": False,
            "production_approved": False,
        }, ensure_ascii=False))
        return 0
    except (GoldRegistryError, OSError, ValueError):
        # Do not reveal paths, labels or raw JSON on error.
        print(json.dumps({
            "status": "BLOCKED",
            "code": "GOLD_REGISTRY_FIXTURE_INVALID_OR_DENIED",
            "database_mutated": False,
            "external_data_accessed": False,
            "production_approved": False,
        }))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
