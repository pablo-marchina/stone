"""Opt-in, read-only Meta account preflight for the first authorized Instagram batch.

Only fixed official Graph endpoints are called; nothing is persisted. Do not pass
credentials as CLI arguments. Fetches Page -> IG account -> at most 3-10 media.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys

import httpx

from tapi_gate0.connectors import ConnectorError, InstagramOfficial, OfficialHttp
from tapi_gate0.domain import MediaType

GRAPH_BASE = "https://graph.facebook.com/v23.0"
EXPECTED_PAGE_ID = "61595867706725"
EXPECTED_USERNAME = "academy_fellow_stone"


class MetaPreflightError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _read_pages(client: httpx.Client, token: str, page_id: str) -> dict:
    """At most three bounded pages; never follow provider-supplied URLs."""
    cursor = None
    visited = set()
    for _ in range(3):
        params = {"fields": "id,name,instagram_business_account", "limit": 50}
        if cursor is not None:
            params["after"] = cursor
        try:
            result = client.get(
                GRAPH_BASE + "/me/accounts", params=params,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise MetaPreflightError("GRAPH_UNAVAILABLE") from exc
        if result.is_redirect:
            raise MetaPreflightError("PROVIDER_REDIRECT_DENIED")
        if result.status_code in (401, 403):
            raise MetaPreflightError("PROVIDER_PERMISSION_DENIED")
        if result.status_code == 429:
            raise MetaPreflightError("PROVIDER_RATE_LIMITED")
        if result.status_code >= 400:
            raise MetaPreflightError("PROVIDER_REQUEST_FAILED")
        if len(result.content) > 256_000:
            raise MetaPreflightError("PROVIDER_RESPONSE_INVALID")
        try:
            payload = result.json()
        except ValueError as exc:
            raise MetaPreflightError("PROVIDER_RESPONSE_INVALID") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise MetaPreflightError("PROVIDER_RESPONSE_INVALID")
        for page in payload["data"]:
            if isinstance(page, dict) and str(page.get("id")) == page_id:
                return page
        paging = payload.get("paging") or {}
        if not isinstance(paging, dict):
            raise MetaPreflightError("PROVIDER_RESPONSE_INVALID")
        cursors = paging.get("cursors") or {}
        if not isinstance(cursors, dict):
            raise MetaPreflightError("PROVIDER_RESPONSE_INVALID")
        next_cursor = cursors.get("after") if paging.get("next") else None
        if not next_cursor:
            break
        if (not isinstance(next_cursor, str) or
            not re.fullmatch(r"[A-Za-z0-9_+/=-]{1,512}", next_cursor) or
            next_cursor in visited):
            raise MetaPreflightError("INVALID_PAGE_CURSOR")
        cursor = next_cursor
        visited.add(cursor)
    raise MetaPreflightError("EXPECTED_PAGE_NOT_FOUND")


def check_meta_account(token: str, *, page_id: str = EXPECTED_PAGE_ID,
                       expected_username: str = EXPECTED_USERNAME,
                       limit: int = 3, client: httpx.Client) -> dict:
    """Return a sanitized summary only; never return raw Graph JSON or the token."""
    if not re.fullmatch(r"[0-9]{5,32}", page_id):
        raise MetaPreflightError("INVALID_EXPECTED_PAGE_ID")
    if not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", expected_username):
        raise MetaPreflightError("INVALID_EXPECTED_USERNAME")
    if not 1 <= limit <= 10:
        raise MetaPreflightError("INVALID_PAGE_LIMIT")
    if not isinstance(token, str) or len(token) < 10:
        raise MetaPreflightError("CREDENTIAL_MISSING")

    page = _read_pages(client, token, page_id)
    ig_link = page.get("instagram_business_account")
    if not isinstance(ig_link, dict) or not re.fullmatch(
        r"[0-9]{5,32}", str(ig_link.get("id", ""))
    ):
        raise MetaPreflightError("PAGE_WITHOUT_CONNECTED_IG_PROFESSIONAL")
    ig_id = str(ig_link["id"])
    official = InstagramOfficial(OfficialHttp(client))
    try:
        verified = official.verify(ig_id, token)
        if verified["username"].casefold() != expected_username.casefold():
            raise MetaPreflightError("IG_USERNAME_MISMATCH")
        items, next_cursor = official.fetch_page(ig_id, token, verified, limit)
    except ConnectorError as exc:
        raise MetaPreflightError(exc.code) from exc
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    primary = [item for item in items if item.media_type in {
        MediaType.REELS, MediaType.CAROUSEL
    }]
    eligible = [item for item in primary if item.published_at <= cutoff and all(
        x is not None for x in (item.likes, item.comments, item.follower_count)
    ) and item.follower_count > 0]
    return {
        "status": "OFFICIAL_READ_CONFIRMED",
        "facebook_page_id": page_id,
        "instagram_user_id": ig_id,
        "instagram_username": verified["username"],
        "followers_observed_now": verified["followers_count"],
        "media_sample": {
            "returned_accepted_formats": len(items),
            "reels_and_carousels": len(primary),
            "eligible_reels_and_carousels_14d": len(eligible),
            "another_page_possible": bool(next_cursor),
        },
        "authorized_post_count_persisted": 0,
        "note": "Preflight only: not a rights grant, census, or persisted corpus.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Meta Instagram Graph preflight")
    parser.add_argument("--execute", action="store_true", help="Explicitly perform bounded API reads")
    parser.add_argument("--page-id", default=EXPECTED_PAGE_ID)
    parser.add_argument("--username", default=EXPECTED_USERNAME)
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "NOT_EXECUTED", "hint": "Use --execute and the official-read env guards"}))
        return 0
    if os.getenv("TAPI_OFFICIAL_METADATA_READS") != "1":
        print(json.dumps({"status": "BLOCKED", "code": "OFFICIAL_READS_DISABLED"}))
        return 2
    if os.getenv("TAPI_ZERO_BILLING_CONFIRMED") != "1":
        print(json.dumps({"status": "BLOCKED", "code": "PROVIDER_ZERO_BILLING_NOT_CONFIRMED"}))
        return 2
    token = os.getenv("TAPI_INSTAGRAM_ACCESS_TOKEN", "")
    if not token:
        print(json.dumps({"status": "BLOCKED", "code": "CREDENTIAL_MISSING"}))
        return 2
    try:
        with httpx.Client(timeout=httpx.Timeout(8), follow_redirects=False) as client:
            result = check_meta_account(
                token, page_id=args.page_id, expected_username=args.username,
                limit=args.limit, client=client)
    except MetaPreflightError as exc:
        print(json.dumps({"status": "FAILED", "code": exc.code}))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
