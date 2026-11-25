"""Declared expiration hints must never be treated as OAuth validation."""
from datetime import datetime, timezone
import json

import httpx
import pytest
from sqlalchemy import select, func

from tapi_gate0.connectors import ConnectorError, OfficialHttp
from tapi_gate0 import discovery_credential_expiry as expiry
from tapi_gate0.discovery_technical import TechnicalDiscoveryService
from tapi_gate0.ingestion import ingestion_runs
from test_discovery_auth_guard import request, TOKEN
from test_discovery_batch_a4 import db, TENANT

NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def config(monkeypatch):
    for var in (expiry.TOKEN_EXPIRY, expiry.DATA_EXPIRY, expiry.REQUIRE_EXPIRY):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(expiry,"now_utc",lambda:NOW)


def test_missing_expiry_is_unknown_not_verified(monkeypatch):
    report=expiry.expiry_status()
    assert report["status"]=="UNKNOWN" and not report["blocked"] and not report["provider_verified"]
    monkeypatch.setenv(expiry.REQUIRE_EXPIRY,"1")
    assert expiry.expiry_status()["reason_code"]=="BD_META_TOKEN_EXPIRY_REQUIRED"
    with pytest.raises(ConnectorError,match="BD_META_TOKEN_EXPIRY_REQUIRED"):
        expiry.require_expiry_available()


@pytest.mark.parametrize("value",["2026-11-13T12:00:00","not-a-date-secret", "2026-02-30T01:00:00Z"])
def test_invalid_expiry_fails_closed_without_echo(monkeypatch,value):
    monkeypatch.setenv(expiry.TOKEN_EXPIRY,value)
    report=expiry.expiry_status()
    assert report["blocked"] and report["status"]=="INVALID_CONFIGURATION"
    assert value not in json.dumps(report)


def test_earliest_expiration_and_timezone(monkeypatch):
    monkeypatch.setenv(expiry.TOKEN_EXPIRY,"2026-12-13T12:00:00Z")
    monkeypatch.setenv(expiry.DATA_EXPIRY,"2026-11-19T09:00:00-03:00")
    report=expiry.expiry_status()
    assert report["status"]=="EXPIRING_SOON" and not report["blocked"]
    assert report["earliest_expires_at"]=="2026-11-19T12:00:00+00:00"
    assert not report["provider_verified"]
    monkeypatch.delenv(expiry.DATA_EXPIRY)
    assert expiry.expiry_status()["status"]=="WITHIN_DECLARED_WINDOW"


@pytest.mark.parametrize("var",[expiry.TOKEN_EXPIRY,expiry.DATA_EXPIRY])
def test_expired_declared_time_blocks_before_network_and_reservation(tmp_path,monkeypatch,var):
    monkeypatch.setenv(var,"2026-11-13T09:00:00-03:00")
    for flag in ("TAPI_BD_TECHNICAL_INGEST","TAPI_OFFICIAL_METADATA_READS","TAPI_ZERO_BILLING_CONFIRMED"):
        monkeypatch.setenv(flag,"1")
    engine,store=db(tmp_path)
    calls=[]
    def unexpected(req):
        calls.append(req)
        raise AssertionError("network must not be reached")
    client=httpx.Client(transport=httpx.MockTransport(unexpected))
    transport=OfficialHttp(client,instagram_version="v26.0")
    try:
        with pytest.raises(ConnectorError,match="BD_META_DECLARED_CREDENTIAL_EXPIRED"):
            TechnicalDiscoveryService(store).execute(TENANT,request(0,"expiry-block-001"),token=TOKEN,http=transport)
        assert calls==[]
        with engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(ingestion_runs)).scalar_one()==0
    finally:
        client.close();engine.dispose()


def test_invalid_strict_setting_and_partial_metadata(monkeypatch):
    monkeypatch.setenv(expiry.REQUIRE_EXPIRY,"true")
    assert expiry.expiry_status()["status"]=="INVALID_CONFIGURATION"
    monkeypatch.setenv(expiry.REQUIRE_EXPIRY,"1")
    monkeypatch.setenv(expiry.DATA_EXPIRY,"2026-12-13T12:00:00Z")
    assert expiry.expiry_status()["status"]=="EXPIRY_REQUIRED"
    monkeypatch.setenv(expiry.TOKEN_EXPIRY,"2026-12-14T12:00:00Z")
    assert expiry.expiry_status()["status"]=="WITHIN_DECLARED_WINDOW"
