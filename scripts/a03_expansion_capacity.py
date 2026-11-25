"""Read-only A03 capacity snapshot, no provider or media access."""
import argparse
import json
import os
from pathlib import Path
if __package__ in (None,""):
    from a00_baseline import check_checkout
else:
    from .a00_baseline import check_checkout
from tapi_gate0.discovery_expansion_capacity import inspect

ROOT=Path(__file__).resolve().parents[1]

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-head",required=True)
    a=p.parse_args(argv)
    try:
        check_checkout(ROOT,a.expected_head)
        report=inspect(os.environ.get("TAPI_DATABASE_URL",""),os.environ.get("TAPI_TENANT_ID",""))
        check_checkout(ROOT,a.expected_head)
        print(json.dumps({**report,"commit":a.expected_head},sort_keys=True))
        return 0
    except Exception as exc:
        code=str(exc)
        if not code.startswith(("A03_CAPACITY_","BASELINE_")):
            code="A03_CAPACITY_LOCAL_ERROR"
        print(json.dumps({"status":"BLOCKED","code":code,"external_calls":0,
                          "database_mutated":False,"execution_authorized":False}))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
