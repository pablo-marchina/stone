"""Single bounded local draft render, no network and no implicit scheduling.

Explicit `--once`; the tenant comes from the operator's environment, never
from a queued job. The HTTP API only queues jobs; this worker performs FFmpeg.
"""
from __future__ import annotations

import argparse
import json
import os

from tapi_gate0.sa_store import engine_for
from tapi_gate0.studio_render_e6 import LocalDraftRenderer


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    if not args.once:
        parser.error('explicit --once required; never run a background loop by default')
    tenant=os.environ.get('TAPI_TENANT_ID')
    database=os.environ.get('TAPI_DATABASE_URL')
    if not tenant or not database:
        parser.error('TAPI_TENANT_ID and TAPI_DATABASE_URL are required')
    result=LocalDraftRenderer(engine_for(database)).process_next(tenant)
    print(json.dumps(result.model_dump() if result else {'status':'no_queued_jobs'},sort_keys=True))


if __name__=='__main__':main()
