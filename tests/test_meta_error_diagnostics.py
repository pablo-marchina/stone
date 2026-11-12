"""Preserve safe Graph error codes without exposing provider payloads."""
import json
import httpx
import pytest
from tapi_gate0.connectors import ConnectorError, OfficialHttp, Platform

TOKEN = "mock-secret-token-never-log"


@pytest.mark.parametrize("status, expected", [(401, "PROVIDER_PERMISSION_DENIED"),
    (403, "PROVIDER_PERMISSION_DENIED"), (400, "PROVIDER_REQUEST_FAILED"),
    (429, "PROVIDER_RATE_LIMITED"), (500, "PROVIDER_REQUEST_FAILED")])
def test_numeric_meta_error_only(status, expected):
    def handler(req):
        return httpx.Response(status, json={"error": {"code": 190,
            "error_subcode": 463, "message": TOKEN, "fbtrace_id": TOKEN,
            "error_data": {"token": TOKEN}}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match=expected) as exc:
            OfficialHttp(client=client).get(Platform.INSTAGRAM, "12345", {"fields":"id"}, TOKEN)
    assert exc.value.provider_diagnostic == {"http_status":status,"code":190,"error_subcode":463}
    assert TOKEN not in str(exc.value) + json.dumps(exc.value.provider_diagnostic)


@pytest.mark.parametrize("body", [b"not JSON", b'{"error":{"code":true,"error_subcode":"secret"}}',
    b'{"error":{"code":-1,"error_subcode":2147483648}}', b'[' + b'['*2000])
def test_malformed_graph_diagnostic_fails_closed(body):
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(403, content=body))) as client:
        with pytest.raises(ConnectorError, match="PROVIDER_PERMISSION_DENIED") as exc:
            OfficialHttp(client=client).get(Platform.INSTAGRAM, "12345", {}, TOKEN)
    assert exc.value.provider_diagnostic == {"http_status":403}


def test_youtube_does_not_parse_meta_diagnostic():
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(403, json={"error":{"code":190}}))) as client:
        with pytest.raises(ConnectorError, match="PROVIDER_PERMISSION_DENIED") as exc:
            OfficialHttp(client=client).get(Platform.YOUTUBE, "channels", {}, TOKEN)
    assert exc.value.provider_diagnostic == {}
