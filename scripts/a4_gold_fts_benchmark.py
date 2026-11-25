"""A04 IMP-060: run a local synthetic-only FTS5/CT-04 benchmark.

Read only tests/fixtures/CT-04_fts_*.json, with caller-provided SHA256.
Print aggregate metrics, not IDs, captions, query text or sealed-test data.
No operational database, network, media, providers, model or admissions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tapi_gate0.discovery_gold_registry import GoldRegistryError
from tapi_gate0.discovery_gold_retrieval_eval import benchmark_synthetic_fts

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--split", default="validation",
                        choices=("development", "validation"))
    parser.add_argument("--k", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        allowed = (ROOT / "tests" / "fixtures").resolve()
        if (not args.fixture.is_file() or args.fixture.is_symlink()
                or args.fixture.resolve().parent != allowed
                or not args.fixture.name.startswith("CT-04_fts_")
                or args.fixture.suffix != ".json"):
            raise GoldRegistryError("GOLD_FTS_FIXTURE_SCOPE_DENIED")
        result = benchmark_synthetic_fts(
            args.fixture.read_bytes(),
            expected_sha256=args.expected_sha256,
            split=args.split,
            k=args.k,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (GoldRegistryError, OSError, ValueError):
        print(json.dumps({
            "status": "BLOCKED",
            "code": "GOLD_FTS_FIXTURE_INVALID_OR_DENIED",
            "database_mutated": False,
            "external_data_accessed": False,
            "production_approved": False,
        }))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
