"""Offline renewal of existing A6 grants, preserving their scope and audit."""
from datetime import timedelta
import json

import pytest
from sqlalchemy import select, update, delete, func

from tapi_gate0.connectors import ConnectorError, Platform
from tapi_gate0.discovery_grants_a6 import provision
from tapi_gate0 import discovery_grant_renewal as renewal
from tapi_gate0.discovery_history import cycle_lease
from tapi_gate0.discovery_reconcile_a6 import reconcile_identities, RESULT
from tapi_gate0.identity import Principal
from tapi_gate0.ingestion import IngestionStore, source_grants
from tapi_gate0.sa_store import domain_events, outbox
from test_discovery_reconcile_a6 import setup, record, TENANT, VIEWER, ID, CYCLE

ADMIN = Principal(actor_id="admin", tenant_id=TENANT, role="admin")


@pytest.fixture
def granted(setup):
    engine, base = setup
    record(engine,base)
    frame,_ = reconcile_identities(engine,TENANT,VIEWER,base,[CYCLE])
    updated,_ = provision(engine,TENANT,VIEWER,frame,["candidate_one"],principal=ADMIN)
    return engine, updated


def clock(monkeypatch, manifest, *, remaining=5):
    instant = manifest.sources[1].expires_at - timedelta(days=remaining)
    monkeypatch.setattr(renewal,"now_utc",lambda: instant)
    return instant


def test_not_due_and_legacy_unchanged(granted):
    engine, frame = granted
    updated, report = renewal.renew_due(engine,TENANT,VIEWER,frame)
    assert updated == frame and report["grants_to_renew"] == 0
    assert report["skipped"][0]["reason"] == "NOT_DUE"
    assert report["external_data_accessed"] is False
    with engine.connect() as db:
        assert db.execute(select(func.count()).select_from(domain_events).where(
            domain_events.c.event_type == renewal.RENEWAL)).scalar_one() == 0


@pytest.mark.parametrize("remaining",[5,-1])
def test_due_renewal_and_manifest_replay(granted,monkeypatch,remaining):
    engine, frame = granted
    instant = clock(monkeypatch,frame,remaining=remaining)
    preview, report = renewal.renew_due(engine,TENANT,VIEWER,frame)
    assert report["grants_to_renew"] == 1 and report["grants_renewed"] == 0
    with engine.connect() as db:
        original = db.execute(select(source_grants)).mappings().one()
        assert original["expires_at"] == frame.sources[1].expires_at.isoformat()
    updated, report = renewal.renew_due(engine,TENANT,VIEWER,frame,principal=ADMIN)
    assert updated == preview and report["grants_renewed"] == 1
    assert updated.sources[0] == frame.sources[0]
    assert updated.sources[1] == frame.sources[1].model_copy(update={"expires_at":instant+timedelta(days=30)})
    with engine.connect() as db:
        grant = db.execute(select(source_grants)).mappings().one()
        assert {k:v for k,v in grant.items() if k!="expires_at"} == {k:v for k,v in original.items() if k!="expires_at"}
        event = db.execute(select(domain_events).where(domain_events.c.event_type==renewal.RENEWAL)).mappings().one()
        payload = json.loads(event["payload"])
        assert payload["manifest_sha256_before"] == frame.fingerprint()
        assert payload["manifest_sha256_after"] == updated.fingerprint()
        assert payload["identity_result_seq"] == db.execute(select(domain_events.c.seq).where(
            domain_events.c.event_type==RESULT)).scalar_one()
        assert db.execute(select(outbox.c.seq).where(outbox.c.seq==event["seq"])).scalar_one()==event["seq"]
    replay, report = renewal.renew_due(engine,TENANT,VIEWER,frame,principal=ADMIN)
    assert replay == updated and report["grants_renewed"] == 0
    assert report["changes"][0]["action"] == "reconcile_manifest"
    # Revocation still uses its original event stream and is never reversed.
    IngestionStore(engine).revoke_grant(TENANT,ADMIN.actor_id,Platform.INSTAGRAM,ID)
    _, report = renewal.renew_due(engine,TENANT,VIEWER,updated,principal=ADMIN)
    assert report["grants_renewed"] == 0 and report["skipped"][0]["reason"]=="REVOKED"


def test_unexplained_divergence_blocks_renewal(granted,monkeypatch):
    engine,frame=granted
    clock(monkeypatch,frame)
    with engine.begin() as db:
        db.execute(update(source_grants).values(expires_at=(frame.sources[1].expires_at+timedelta(days=1)).isoformat()))
    with pytest.raises(ConnectorError,match="BD_GRANT_RENEWAL_MANIFEST_MISMATCH"):
        renewal.renew_due(engine,TENANT,VIEWER,frame,principal=ADMIN)


def test_identity_trace_and_admin_required(granted,monkeypatch):
    engine,frame=granted
    clock(monkeypatch,frame)
    with pytest.raises(ConnectorError,match="BD_GRANT_ADMIN_REQUIRED"):
        renewal.renew_due(engine,TENANT,VIEWER,frame,principal=Principal(actor_id="reader",tenant_id=TENANT,role="viewer"))
    with pytest.raises(ConnectorError,match="BD_GRANT_RENEWAL_SCOPE_MISMATCH"):
        renewal.renew_due(engine,TENANT,"17841400000000009",frame,principal=ADMIN)
    with engine.begin() as db:
        seq=db.execute(select(domain_events.c.seq).where(domain_events.c.event_type==RESULT)).scalar_one()
        db.execute(delete(outbox).where(outbox.c.seq==seq))
    with pytest.raises(ConnectorError,match="BD_RECONCILE_INVALID_IDENTITY_TRACE"):
        renewal.renew_due(engine,TENANT,VIEWER,frame,principal=ADMIN)


def test_active_lease_blocks_renewal(granted,monkeypatch):
    engine,frame=granted
    clock(monkeypatch,frame)
    with cycle_lease(engine,TENANT,"fixture-active"):
        with pytest.raises(ConnectorError,match="BD_GRANT_INGESTION_ACTIVE"):
            renewal.renew_due(engine,TENANT,VIEWER,frame,principal=ADMIN)


def test_cli_preview_without_token(granted,tmp_path,monkeypatch,capsys):
    from scripts import a6_provision_grants as cli
    engine,frame=granted
    path=tmp_path/"manifest.json"
    path.write_text(frame.model_dump_json(),encoding="utf-8")
    monkeypatch.setenv("TAPI_DATABASE_URL",str(engine.url))
    monkeypatch.setenv("TAPI_TENANT_ID",TENANT)
    monkeypatch.setenv("TAPI_META_IG_ID",VIEWER)
    monkeypatch.delenv("TAPI_INSTAGRAM_ACCESS_TOKEN",raising=False)
    assert cli.main(["--manifest",str(path),"--renew-due"])==0
    assert json.loads(capsys.readouterr().out)["status"]=="TECHNICAL_GRANT_RENEWAL_PLANNED"
