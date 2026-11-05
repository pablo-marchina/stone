"""Run a single bounded local E7 job; no background loop or paid services."""
from __future__ import annotations
import argparse
import json
import os

from tapi_gate0.sa_store import engine_for
from tapi_gate0.studio_advanced_e7 import AdvancedStudioRenderer


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true")
    args=parser.parse_args()
    if not args.once:
        parser.error("--once is mandatory; no implicit background polling")
    tenant=os.environ.get("TAPI_TENANT_ID")
    database=os.environ.get("TAPI_DATABASE_URL")
    if not tenant or not database:
        parser.error("TAPI_TENANT_ID and TAPI_DATABASE_URL required")
    outcome=AdvancedStudioRenderer(engine_for(database)).process_next(tenant)
    print(json.dumps(outcome.model_dump() if outcome else {"status":"no_queued_jobs"},sort_keys=True))

if __name__=="__main__": main()
