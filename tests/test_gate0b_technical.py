"""Gate0B read-only technical readiness, denied by default."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from tapi_gate0.gate0b_technical import assess_metadata_readiness
from tapi_gate0.secure_api import create_secure_app


def _grant(**overrides):
    now = datetime.now(timezone.utc)
    value = {
        "approval_reference": "formal-institutional-authorization",
        "enabled": 1,
        "expires_at": (now + timedelta(days=30)).isoformat(),
        "technical_verified_at": None,
    }
    value.update(overrides)
    return value


def _ready(grant):
    return assess_metadata_readiness(
        grant, credential_present=True, read_switch_enabled=True,
        zero_billing_operator_confirmed=True,
    )


def test_missing_grant_fails_even_when_token_switches_set():
    r = _ready(None)
    assert r.status == "BLOCKED"
    assert r.blockers == ["SOURCE_GRANT_REQUIRED"]
    assert r.can_attempt_validation is False
    assert r.production_approved is False


def test_expired_disabled_and_malformed_grants_blocked():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    for grant in (_grant(enabled=0), _grant(expires_at=past),
                  _grant(expires_at="bad"), _grant(approval_reference="")):
        result = _ready(grant)
        assert result.status == "BLOCKED"
        assert result.can_attempt_validation is False


def test_flags_and_credential_checked_independently():
    r = assess_metadata_readiness(
        _grant(), credential_present=False, read_switch_enabled=False,
        zero_billing_operator_confirmed=False,
    )
    assert set(r.blockers) == {
        "LOCAL_CREDENTIAL_MISSING", "OFFICIAL_READ_SWITCH_DISABLED",
        "ZERO_BILLING_NOT_CONFIRMED",
    }


def test_only_bounded_preflight_can_be_attempted():
    r = _ready(_grant())
    assert r.status == "READY_FOR_BOUNDED_PREFLIGHT"
    assert r.can_attempt_validation is True
    assert r.production_approved is False
    assert r.institutional_rights_audited_by_software is False
    old = datetime.now(timezone.utc).isoformat()
    previous = _ready(_grant(technical_verified_at=old))
    assert previous.status == "PREVIOUSLY_VERIFIED_RECHECK_REQUIRED"
    assert previous.production_approved is False


def test_connection_endpoint_reports_missing_grant_not_secret(tmp_path, monkeypatch):
    app = create_secure_app(
        f"sqlite:///{tmp_path/'g0b.sqlite'}",
        initialize_schema=True, allow_http_local=True,
    )
    app.state.identity_store.bootstrap(
        "tenantA", "Test tenant", "admin", "secure-password-12345",
    )
    for key in ("TAPI_INSTAGRAM_ACCESS_TOKEN", "TAPI_OFFICIAL_METADATA_READS",
                "TAPI_ZERO_BILLING_CONFIRMED"):
        monkeypatch.delenv(key, raising=False)
    with TestClient(app) as client:
        login = client.post("/v1/auth/sessions", json={
            "username":"admin", "password":"secure-password-12345",
            "tenant_id":"tenantA",
        })
        assert login.status_code == 200
        hdr = {"Authorization": "Bearer " + login.json()["access_token"]}
        path = "/v1/ingestion/connections/instagram/ungranted_id"
        response = client.get(path, headers=hdr)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "BLOCKED"
        assert "SOURCE_GRANT_REQUIRED" in data["blockers"]
        assert not data["can_attempt_validation"]
        assert not data["production_approved"]
        assert client.get(path).status_code == 401
        assert "access_token" not in str(data)
