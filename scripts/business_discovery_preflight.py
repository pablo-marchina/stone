"""Opt-in Business Discovery read feasibility, zero-persistence and bounded.

Run only after checking that this use is permitted and financially free.
Requires a user-supplied target, documented approval reference and an existing
Facebook User Access Token available in the local process environment.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from tapi_gate0.business_discovery import BusinessDiscoveryProbe
from tapi_gate0.connectors import ConnectorError, OfficialHttp

DEFAULT_VIEWER = "17841459971757521"


def main(argv=None, *, adapter=None):
    parser = argparse.ArgumentParser(description="Authorized Instagram Business Discovery sample")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--viewer-id", default=DEFAULT_VIEWER)
    parser.add_argument("--target", required=True, help="Known, permitted professional username")
    parser.add_argument("--approval-reference", required=True,
                        help="Non-secret per-account research approval reference")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--max-pages", type=int, default=1)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "NOT_EXECUTED"}))
        return 0
    if os.getenv("TAPI_OFFICIAL_METADATA_READS") != "1":
        print(json.dumps({"status": "BLOCKED", "code": "OFFICIAL_READS_DISABLED"}))
        return 2
    if os.getenv("TAPI_ZERO_BILLING_CONFIRMED") != "1":
        print(json.dumps({"status": "BLOCKED", "code": "PROVIDER_ZERO_BILLING_NOT_CONFIRMED"}))
        return 2
    if not re.fullmatch(r"[A-Za-z0-9._:/#-]{12,128}", args.approval_reference):
        print(json.dumps({"status": "BLOCKED", "code": "APPROVAL_REFERENCE_REQUIRED"}))
        return 2
    token = os.getenv("TAPI_INSTAGRAM_ACCESS_TOKEN", "")
    if not token:
        print(json.dumps({"status": "BLOCKED", "code": "CREDENTIAL_MISSING"}))
        return 2
    owns = adapter is None
    http = adapter or OfficialHttp()
    try:
        result = BusinessDiscoveryProbe(http).check(args.viewer_id, args.target, token,
                            limit=args.limit, max_pages=args.max_pages)
    except ConnectorError as exc:
        print(json.dumps({"status": "FAILED", "code": exc.code}))
        return 1
    finally:
        if owns:
            http.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
