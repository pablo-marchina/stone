"""Operator-only Meta Business Discovery real sample; never logs any token.

Use --execute for a bounded live read. --audit RUN_KEY performs a read-only
query against already recorded tenant/source events (no token required).
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
from datetime import datetime, timezone

from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_technical import (
    TechnicalDiscoveryRequest, TechnicalDiscoveryService, audit_run)
from tapi_gate0.ingestion import IngestionStore
from tapi_gate0.sa_store import engine_for


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded Meta Business Discovery technical ingestion")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--audit", metavar="RUN_KEY")
    parser.add_argument("--username", default="sebrae")
    parser.add_argument("--target-ig-id", default="17841403133066329")
    parser.add_argument("--page-limit", type=int, default=10, choices=range(1,11))
    parser.add_argument("--max-pages", type=int, default=4, choices=range(1,5))
    parser.add_argument("--persist-limit", type=int, default=3, choices=(1,2,3))
    args = parser.parse_args(argv)
    if not args.execute and not args.audit:
        print(json.dumps({"status":"NOT_EXECUTED", "external_data_accessed":False}))
        return 0
    if args.execute and args.audit:
        parser.error("Choose either --execute or --audit")
    required = ("TAPI_DATABASE_URL", "TAPI_TENANT_ID")
    if args.execute:
        required += ("TAPI_META_IG_ID", "TAPI_INSTAGRAM_ACCESS_TOKEN",
                     "TAPI_OFFICIAL_METADATA_READS", "TAPI_ZERO_BILLING_CONFIRMED",
                     "TAPI_BD_TECHNICAL_INGEST")
    missing = [name for name in required if not os.environ.get(name)]
    flags = ("TAPI_OFFICIAL_METADATA_READS", "TAPI_ZERO_BILLING_CONFIRMED",
             "TAPI_BD_TECHNICAL_INGEST")
    if args.execute:
        missing.extend(name for name in flags if os.environ.get(name) not in (None,"", "1"))
    if missing:
        print(json.dumps({"status":"BLOCKED","required_environment_names":sorted(set(missing)),
                          "external_data_accessed":False}))
        return 2
    url = os.environ["TAPI_DATABASE_URL"]
    if not url.startswith(("sqlite:///", "postgresql+psycopg://")):
        print(json.dumps({"status":"BLOCKED","code":"LOCAL_DB_URL_REQUIRED",
                          "external_data_accessed":False}))
        return 2
    engine = engine_for(url)
    try:
        tenant = os.environ["TAPI_TENANT_ID"]
        if args.audit:
            print(json.dumps(audit_run(engine, tenant, args.audit), ensure_ascii=False))
            return 0
        req = TechnicalDiscoveryRequest(
            username=args.username, expected_ig_id=args.target_ig_id,
            viewer_ig_id=os.environ["TAPI_META_IG_ID"],
            run_key=("bdmeta-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                     + "-" + secrets.token_hex(4)),
            page_limit=args.page_limit, max_pages=args.max_pages,
            persist_limit=args.persist_limit,
        )
        result = TechnicalDiscoveryService(IngestionStore(engine)).execute(tenant, req)
        result["audit"] = audit_run(engine, tenant, req.run_key)
        print(json.dumps(result, ensure_ascii=False))
        return (0 if result["audit"]["all_traces_valid"]
                and result["audit"]["has_persisted_observations"] else 4)
    except ConnectorError as exc:
        print(json.dumps({"status":"DENIED_OR_FAILED","code":exc.code}))
        return 3
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
