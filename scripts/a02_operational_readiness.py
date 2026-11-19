"""Inspect configured local operational SQLite without writing or authorizing."""
import argparse
import json
import os
from pathlib import Path

from scripts.a00_baseline import check_checkout
from tapi_gate0.asset_operational_readiness import inspect

ROOT=Path(__file__).resolve().parents[1]


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-head",required=True)
    a=p.parse_args(argv)
    try:
        check_checkout(ROOT,a.expected_head)
        report=inspect(os.environ.get("TAPI_DATABASE_URL",""),os.environ.get("TAPI_TENANT_ID",""))
        check_checkout(ROOT,a.expected_head)
        print(json.dumps({**report,"commit":a.expected_head},ensure_ascii=True,sort_keys=True))
        return 0
    except Exception as exc:
        # Never echo DB URL, tenant, path, raw SQL or error message.
        code=str(exc)
        if not code.startswith(("A02_READINESS_","BASELINE_")):
            code="A02_READINESS_LOCAL_ERROR"
        print(json.dumps({"status":"BLOCKED","code":code,"exception_type":type(exc).__name__,
                          "media_enabled":False,"database_mutated":False,"global_gates_released":False}))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
