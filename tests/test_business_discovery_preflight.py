"""Business Discovery feasibility is bounded, credential-safe and non-persistent."""
from datetime import datetime, timezone
import httpx
import pytest

from tapi_gate0.business_discovery import BusinessDiscoveryProbe
from tapi_gate0.connectors import ConnectorError, OfficialHttp
from scripts.business_discovery_preflight import main

TOKEN = "mocked-meta-token-used-only-in-unit-tests"
VIEWER = "17841459971757521"
TARGET_ID = "17841400039600391"


def probe(responder, **kwargs):
    with httpx.Client(transport=httpx.MockTransport(responder)) as c:
        return BusinessDiscoveryProbe(OfficialHttp(c)).check(
            VIEWER, "instagram", TOKEN, now=datetime(2026, 11, 3, tzinfo=timezone.utc), **kwargs)


def media_item(suffix, media_type="VIDEO", media_product_type="REELS", **kwargs):
    result = {
        "id": "17841" + str(suffix).zfill(9),
        "media_type": media_type,
        "media_product_type": media_product_type,
        "permalink": "https://www.instagram.com/reel/testfixture/",
        "timestamp": "2026-09-01T00:00:00+00:00",
        "like_count": 20,
        "comments_count": 2,
    }
    result.update(kwargs)
    return result


def response(req, items, paging=None, followers=500, discovery_id=TARGET_ID):
    assert req.url.host == "graph.facebook.com"
    assert req.url.path.endswith("/" + VIEWER)
    assert req.headers["Authorization"] == "Bearer " + TOKEN
    assert "access_token" not in req.url.params
    fields = req.url.params["fields"]
    assert fields.startswith("business_discovery.username(instagram)")
    assert "media.limit(" in fields
    return httpx.Response(200, json={"id": VIEWER, "business_discovery": {
        "id": discovery_id, "username": "instagram", "followers_count": followers,
        "media_count": 8634, "media": {"data": items, "paging": paging or {}}
    }})


def test_real_shape_sample_is_only_read_and_audit_counts():
    items = [media_item(1), media_item(2, media_type="CAROUSEL_ALBUM", media_product_type=None),
             media_item(3, media_type="IMAGE", media_product_type=None)]
    calls = []
    def handler(req):
        calls.append(req.url.path)
        return response(req, items)
    result = probe(handler)
    assert calls == ["/v23.0/" + VIEWER]
    assert result["status"] == "DISCOVERY_SAMPLE_READ"
    assert result["target"]["id"] == TARGET_ID
    assert result["sample"]["eligible_14d"] == 2
    assert result["sample"]["reels"] == 1
    assert result["sample"]["carousels"] == 1
    assert result["sample"]["static_images"] == 1
    assert result["persisted_posts"] == 0
    assert result["rights_grant_recorded"] is False
    assert TOKEN not in str(result)


def test_missing_fields_and_zero_followers_do_not_invent_metrics():
    items = [media_item(1, like_count=None), media_item(2, timestamp="2026-11-02T20:00:00Z"),
             media_item(3)]
    result = probe(lambda req: response(req, items, followers=0))
    assert result["sample"]["missing_metrics"] == 1
    assert result["sample"]["too_recent"] == 1
    assert result["sample"]["invalid_denominator"] == 1
    assert result["sample"]["eligible_14d"] == 0
    assert result["target"]["followers_observed_now"] == 0


def test_cursor_uses_fixed_graph_host_and_never_follows_paging_next():
    requests = []
    def handler(req):
        fields = req.url.params["fields"]
        requests.append((str(req.url), fields))
        if ".after(opaque_SAFE_cursor)" in fields:
            return response(req, [media_item(2)])
        return response(req, [media_item(1)], paging={
            "next": "https://evil.invalid/steal", "cursors": {"after": "opaque_SAFE_cursor"}})
    result = probe(handler, limit=1, max_pages=2)
    assert result["sample"]["eligible_14d"] == 2
    assert result["pages_examined"] == 2
    assert not result["another_page_possible"]
    assert len(requests) == 2
    assert all("evil.invalid" not in url for url, _ in requests)


def test_invalid_target_is_rejected_before_network():
    def should_not_call(_req):
        raise AssertionError("Network must not occur")
    with httpx.Client(transport=httpx.MockTransport(should_not_call)) as c:
        probe_obj = BusinessDiscoveryProbe(OfficialHttp(c))
        for target in ["a){}", "a b", "../meta", ""]:
            with pytest.raises(ConnectorError) as error:
                probe_obj.check(VIEWER, target, TOKEN)
            assert error.value.code == "INVALID_TARGET_USERNAME"
        with pytest.raises(ConnectorError):
            probe_obj.check(VIEWER, "instagram", TOKEN, limit=100)
        with pytest.raises(ConnectorError):
            probe_obj.check(VIEWER, "instagram", TOKEN, max_pages=100)


def test_discovered_profile_mismatch_rejected():
    with pytest.raises(ConnectorError) as exc:
        probe(lambda req: response(req, [media_item(1)], discovery_id="invalid"))
    assert exc.value.code == "INVALID_DISCOVERED_ACCOUNT"


def test_unsafe_cursor_rejected_without_second_network_call():
    calls = []
    def handler(req):
        calls.append(req.url.path)
        return response(req, [media_item(1)], paging={
            "next": "https://evil.invalid", "cursors": {"after": "https://evil.invalid"}})
    with pytest.raises(ConnectorError) as exc:
        probe(handler, limit=1, max_pages=2)
    assert exc.value.code == "INVALID_DISCOVERY_CURSOR"
    assert len(calls) == 1


def test_missing_discovery_field_is_explicit_blocker():
    with pytest.raises(ConnectorError) as exc:
        probe(lambda req: httpx.Response(200, json={"id": VIEWER}))
    assert exc.value.code == "BUSINESS_DISCOVERY_NOT_AVAILABLE"


def test_cli_requires_explicit_execute_and_guards(monkeypatch, capsys):
    monkeypatch.delenv("TAPI_OFFICIAL_METADATA_READS", raising=False)
    assert main(["--target", "instagram", "--approval-reference", "test-contract-v1"]) == 0
    assert "NOT_EXECUTED" in capsys.readouterr().out
    assert main(["--target", "instagram", "--approval-reference", "test-contract-v1", "--execute"]) == 2
    assert "OFFICIAL_READS_DISABLED" in capsys.readouterr().out
    monkeypatch.setenv("TAPI_OFFICIAL_METADATA_READS", "1")
    monkeypatch.setenv("TAPI_ZERO_BILLING_CONFIRMED", "1")
    monkeypatch.setenv("TAPI_INSTAGRAM_ACCESS_TOKEN", TOKEN)
    assert main(["--target", "instagram", "--approval-reference", "bad", "--execute"]) == 2
    assert "APPROVAL_REFERENCE_REQUIRED" in capsys.readouterr().out
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: response(req, [media_item(1)]))) as c:
        result = main(["--target", "instagram", "--approval-reference", "test-contract-v1", "--execute"],
                      adapter=OfficialHttp(c))
    assert result == 0
    output = capsys.readouterr().out
    assert "DISCOVERY_SAMPLE_READ" in output
    assert TOKEN not in output


def test_cursor_without_paging_next_is_used_for_nested_discovery():
    # Business Discovery responses can expose only paging.cursors.after.
    calls = []
    def handler(req):
        fields = req.url.params["fields"]
        calls.append(fields)
        if ".after(opaque_SAFE_cursor)" in fields:
            return response(req, [media_item(2)])
        return response(req, [media_item(1)], paging={
            "cursors": {"after": "opaque_SAFE_cursor"},
        })
    result = probe(handler, limit=1, max_pages=2)
    assert len(calls) == 2
    assert "media.limit(1).after(opaque_SAFE_cursor)" in calls[1]
    assert result["sample"]["eligible_14d"] == 2
    assert result["pages_examined"] == 2
    assert result["pagination_status"] == "PARTIAL_PAGE_NO_CURSOR"


def test_full_page_without_cursor_must_not_claim_exhaustion():
    result = probe(lambda req: response(req, [
        media_item(1), media_item(2), media_item(3),
    ]), limit=3, max_pages=1)
    assert result["target"]["reported_media_count"] == 8634
    assert result["sample"]["returned"] == 3
    assert result["another_page_possible"] is False
    assert result["pagination_status"] == "UNVERIFIED_FULL_PAGE_NO_CURSOR"
    assert result["exhaustion_confirmed"] is False
    assert result["persisted_posts"] == 0


def test_explicit_next_without_cursor_is_invalid_paging():
    with pytest.raises(ConnectorError) as exc:
        probe(lambda req: response(req, [media_item(1)], paging={
            "next": "https://graph.facebook.com/anything",
        }), limit=1)
    assert exc.value.code == "DISCOVERY_PAGING_CURSOR_MISSING"


def test_cursor_on_partial_page_without_next_is_not_followed():
    calls = []
    def handler(req):
        calls.append(req.url.path)
        return response(req, [media_item(1)], paging={
            "cursors": {"after": "opaque_SAFE_cursor"},
        })
    result = probe(handler, limit=3, max_pages=3)
    assert len(calls) == 1
    assert result["pagination_status"] == "PARTIAL_PAGE_NO_CURSOR"
    assert result["another_page_possible"] is False
