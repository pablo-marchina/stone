"""A2 opt-in first real Instagram metadata batch; no automatic grants.

Inputs only from trusted local environment. No API call unless --execute;
no content bodies, tokens or credentials printed to the console. Fails closed.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
from datetime import datetime, timezone

from tapi_gate0.connectors import ConnectorError, Platform
from tapi_gate0.ingestion import IngestionStore, IngestionRequest
from tapi_gate0.sa_store import engine_for


def preconditions(env: dict) -> list[str]:
    requirements = {
        "TAPI_DATABASE_URL": lambda x: x.startswith("sqlite:///") or x.startswith("postgresql+psycopg://"),
        "TAPI_TENANT_ID": bool,
        "TAPI_META_IG_ID": lambda x: x.isdecimal() and 5 <= len(x) <= 32,
        "TAPI_INSTAGRAM_ACCESS_TOKEN": bool,
        "TAPI_OFFICIAL_METADATA_READS": lambda x: x == "1",
        "TAPI_ZERO_BILLING_CONFIRMED": lambda x: x == "1",
    }
    return [name for name, valid in requirements.items()
            if not valid(env.get(name, ""))]


def main(argv=None):
    parser = argparse.ArgumentParser(description="One bounded official Meta metadata read, off by default")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=3, choices=(1, 2, 3))
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"NOT_EXECUTED","reason":"--execute is required",
                          "external_data_accessed":False}))
        return 0

    missing = preconditions(os.environ)
    if missing:
        print(json.dumps({"status":"BLOCKED","required_environment_names":missing,
                          "external_data_accessed":False}))
        return 2

    engine = engine_for(os.environ["TAPI_DATABASE_URL"])
    try:
        store = IngestionStore(engine)
        tenant = os.environ["TAPI_TENANT_ID"]
        account = os.environ["TAPI_META_IG_ID"]
        # Recheck the active DB grant before any network transport.
        grant = store.read_grant(tenant, Platform.INSTAGRAM, account)
        if not grant.get("approval_reference"):
            raise ConnectorError("SOURCE_GRANT_REFERENCE_REQUIRED", 403)
        key = "a2meta-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(4)
        result = store.run(tenant, IngestionRequest(
            platform=Platform.INSTAGRAM, source_account_id=account,
            run_key=key, limit=args.limit, min_age_days=14,
        ))
        print(json.dumps({
            "status":"BOUNDED_OFFICIAL_READ_COMPLETED",
            "run_key":result.run_key,
            "new_records":result.new_records,
            "refreshed_records":result.refreshed_records,
            "duplicate_records":result.duplicate_records,
            "excluded_too_recent":result.excluded_too_recent,
            "next_page_available":result.next_page_available,
            "metadata_only":result.metadata_only,
            "research_corpus_accepted":False,
            "scientific_eligible_count":0,
            "scientifically_validated":False,
            "production_approved":False,
        }, separators=(",", ":")))
        return 0
    except (ConnectorError, ValueError) as exc:
        print(json.dumps({"status":"DENIED_OR_FAILED",
                          "code":exc.code if isinstance(exc,ConnectorError)
                          else "INVALID_PILOT_CONFIGURATION",
                          "production_approved":False}))
        return 3
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
