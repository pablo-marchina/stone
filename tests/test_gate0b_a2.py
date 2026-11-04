"""A2: administrative grant lifecycle, durable audit and safe Meta runner."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from tapi_gate0.connectors import Platform, ConnectorError
from tapi_gate0.ingestion import IngestionStore, GrantCreate, source_grants
from tapi_gate0.sa_store import domain_events, outbox
from tapi_gate0.secure_api import create_secure_app
from scripts.a2_meta_first_batch import main as meta_main, preconditions

PASS = "correct-horse-secure-admin-password-12345"


def setup_app(tmp_path):
    app = create_secure_app(
        f"sqlite:///{tmp_path/'a2.sqlite'}",
        initialize_schema=True, allow_http_local=True,
    )
    app.state.identity_store.bootstrap("tenantA", "Demo", "founder", PASS)
    return app


def auth(client):
    result = client.post("/v1/auth/sessions", json={
        "username": "founder", "password": PASS, "tenant_id": "tenantA",
    })
    assert result.status_code == 200
    return {"Authorization": "Bearer " + result.json()["access_token"]}


def payload(account="17841400000000001"):
    return {
        "platform": "instagram", "source_account_id": account,
        "approval_reference": "DEC-018-formal-institutional-approval",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
    }


def test_admin_grant_creation_revoke_and_audit(tmp_path):
    app = setup_app(tmp_path)
    with TestClient(app) as client:
        hdr = auth(client)
        created = client.post("/v1/ingestion/grants", json=payload(), headers=hdr)
        assert created.status_code == 201, created.text
        revoked = client.post(
            "/v1/ingestion/grants/instagram/17841400000000001/revoke", headers=hdr)
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["audit_recorded"] is True
        assert client.post(
            "/v1/ingestion/grants/instagram/17841400000000001/revoke", headers=hdr).status_code == 404
        check = client.get(
            "/v1/ingestion/connections/instagram/17841400000000001", headers=hdr)
        assert check.status_code == 200
        assert check.json()["status"] == "BLOCKED"
        assert not check.json()["grant_active"]
        with pytest.raises(ConnectorError, match="VALID_SOURCE_GRANT_REQUIRED"):
            app.state.ingestion_store.read_grant(
                "tenantA", Platform.INSTAGRAM, "17841400000000001")
    with app.state.ingestion_store.engine.connect() as db:
        events = db.execute(select(domain_events).where(
            domain_events.c.aggregate_type == "ingestion_source_grant",
            domain_events.c.tenant_id == "tenantA").order_by(
                domain_events.c.aggregate_version)).mappings().all()
        assert [row["event_type"] for row in events] == [
            "ingestion.grant.created", "ingestion.grant.revoked",
        ]
        assert [row["aggregate_version"] for row in events] == [1, 2]
        assert db.execute(select(func.count()).select_from(outbox).where(
            outbox.c.seq.in_([row["seq"] for row in events]))).scalar_one() == 2
        assert not db.execute(select(source_grants.c.enabled).where(
            source_grants.c.tenant_id == "tenantA")).scalar_one()


def test_revoke_is_tenant_scoped(tmp_path):
    app = setup_app(tmp_path)
    store = app.state.ingestion_store
    store.grant("tenantA", "founder", GrantCreate.model_validate(payload()))
    with pytest.raises(ConnectorError, match="ACTIVE_SOURCE_GRANT_REQUIRED"):
        store.revoke_grant("otherTenant", "otherActor", Platform.INSTAGRAM,
                           "17841400000000001")
    assert store.read_grant("tenantA", Platform.INSTAGRAM,
                            "17841400000000001")["enabled"] == 1


def test_meta_runner_is_denied_by_default(capsys, monkeypatch):
    assert meta_main([]) == 0
    assert "NOT_EXECUTED" in capsys.readouterr().out
    for name in ("TAPI_DATABASE_URL", "TAPI_TENANT_ID", "TAPI_META_IG_ID",
                 "TAPI_INSTAGRAM_ACCESS_TOKEN", "TAPI_OFFICIAL_METADATA_READS",
                 "TAPI_ZERO_BILLING_CONFIRMED"):
        monkeypatch.delenv(name, raising=False)
    assert meta_main(["--execute"]) == 2
    text = capsys.readouterr().out
    assert "BLOCKED" in text
    assert "TAPI_INSTAGRAM_ACCESS_TOKEN" in text
    assert "local-test-placeholder" not in text


def test_preconditions_require_read_switch_and_no_billing():
    values = {
        "TAPI_DATABASE_URL": "sqlite:////tmp/tapi-offline.sqlite",
        "TAPI_TENANT_ID": "tenantA",
        "TAPI_META_IG_ID": "17841400000000001",
        "TAPI_INSTAGRAM_ACCESS_TOKEN": "local-test-placeholder",
        "TAPI_OFFICIAL_METADATA_READS": "1",
        "TAPI_ZERO_BILLING_CONFIRMED": "1",
    }
    assert preconditions(values) == []
    for key in values:
        removed = dict(values)
        removed.pop(key)
        assert key in preconditions(removed)
