"""Preflight must never follow URLs and must never expose token contents."""
from datetime import datetime, timezone
import httpx

from scripts.meta_preflight import (MetaPreflightError, check_meta_account, main)

TOKEN = "mock-token-meta-very-long-and-never-logged"
PAGE = "61595867706725"
IG = "17891111111111111"


def _response(req):
    assert req.url.host == "graph.facebook.com"
    assert req.headers["Authorization"] == "Bearer " + TOKEN
    if req.url.path.endswith("/me/accounts"):
        return httpx.Response(200, json={"data": [{
            "id": PAGE, "name": "TAPI Test Page", "instagram_business_account": {"id": IG},
        }]})
    if req.url.path.endswith("/" + IG):
        return httpx.Response(200, json={
            "id": IG, "username": "academy_fellow_stone", "followers_count": 500,
        })
    if req.url.path.endswith("/" + IG + "/media"):
        return httpx.Response(200, json={"data": [{
            "id": "179001", "media_type": "VIDEO", "media_product_type": "REELS",
            "permalink": "https://www.instagram.com/reel/s1/",
            "timestamp": "2024-01-01T00:00:00Z", "like_count": 100, "comments_count": 1,
        }, {
            "id": "179002", "media_type": "IMAGE",
            "permalink": "https://www.instagram.com/p/p1/",
            "timestamp": "2024-01-01T00:00:00Z", "like_count": 50, "comments_count": 3,
        }], "paging": {"next": "https://forbidden.invalid/", "cursors": {"after": "safe_cursor"}}})
    raise AssertionError("Unexpected host/path")


def test_preflight_only_reports_account_and_eligibility():
    with httpx.Client(transport=httpx.MockTransport(_response)) as client:
        result = check_meta_account(TOKEN, client=client)
    assert result["status"] == "OFFICIAL_READ_CONFIRMED"
    assert result["facebook_page_id"] == PAGE
    assert result["instagram_user_id"] == IG
    assert result["media_sample"]["eligible_reels_and_carousels_14d"] == 1
    assert result["media_sample"]["reels_and_carousels"] == 1
    assert result["authorized_post_count_persisted"] == 0
    assert TOKEN not in str(result)


def test_wrong_page_or_missing_link_fails_closed():
    def other_page(req):
        return httpx.Response(200, json={"data": [{"id": "123456"}]})
    with httpx.Client(transport=httpx.MockTransport(other_page)) as client:
        try:
            check_meta_account(TOKEN, client=client)
        except MetaPreflightError as exc:
            assert exc.code == "EXPECTED_PAGE_NOT_FOUND"
        else:
            assert False, "Expected an error"
    def missing_link(req):
        return httpx.Response(200, json={"data": [{"id": PAGE}]})
    with httpx.Client(transport=httpx.MockTransport(missing_link)) as client:
        try:
            check_meta_account(TOKEN, client=client)
        except MetaPreflightError as exc:
            assert exc.code == "PAGE_WITHOUT_CONNECTED_IG_PROFESSIONAL"
        else:
            assert False, "Expected an error"


def test_invalid_username_and_unsafe_cursor_fail_closed():
    with httpx.Client(transport=httpx.MockTransport(_response)) as client:
        try:
            check_meta_account(TOKEN, client=client, expected_username="different_account")
        except MetaPreflightError as exc:
            assert exc.code == "IG_USERNAME_MISMATCH"
        else:
            assert False, "Expected an error"
    def unsafe(req):
        return httpx.Response(200, json={"data": [], "paging": {
            "next": "https://forbidden.invalid/sensitive", "cursors": {"after": "https://forbidden.invalid"}}})
    with httpx.Client(transport=httpx.MockTransport(unsafe)) as client:
        try:
            check_meta_account(TOKEN, client=client)
        except MetaPreflightError as exc:
            assert exc.code == "INVALID_PAGE_CURSOR"
        else:
            assert False, "Expected an error"


def test_cli_defaults_to_no_network(monkeypatch, capsys):
    monkeypatch.delenv("TAPI_INSTAGRAM_ACCESS_TOKEN", raising=False)
    assert main([]) == 0
    assert "NOT_EXECUTED" in capsys.readouterr().out
    assert main(["--execute"]) == 2
    assert "OFFICIAL_READS_DISABLED" in capsys.readouterr().out
