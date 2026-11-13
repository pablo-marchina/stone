import json
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, func, delete
from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_batch import BatchManifest
from tapi_gate0.discovery_reconcile_a6 import reconcile_identities, RESERVATION, RESULT
from tapi_gate0.ingestion import stable_id, source_grants, ingestion_records
from tapi_gate0.sa_store import engine_for, metadata, tenants, domain_events, outbox

TENANT = "test-reconcile"
VIEWER = "17841400000000001"
CYCLE = "a6identity-20261113014308-01234567"
OTHER = "a6identity-20261114014308-89abcdef"
DAY = "2026-11-13"
ID = "17841400000000003"


@pytest.fixture
def setup(tmp_path):
    engine = engine_for("sqlite:///" + (tmp_path / "reconcile.sqlite").as_posix())
    metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(insert(tenants).values(tenant_id=TENANT,name="Test"))
        db.execute(insert(tenants).values(tenant_id="other",name="Other"))
    base = BatchManifest.model_validate({"schema_version":"tapi-bd-technical-batch.v1", "sources":[
        {"username":"existing_source", "expected_ig_id":"17841400000000002", "status":"approved",
         "sampling_stratum":"finance", "audience_intent":"mpe_targeted", "source_evidence_reference":"fixture-source-evidence",
         "audience_rationale_reference":"fixture-audience-evidence", "approval_reference":"existing-grant-evidence",
         "expires_at":"2099-01-01T00:00:00Z", "allowed_operations":["business_discovery_metadata_read"]},
        {"username":"candidate_one", "sampling_stratum":"accounting", "audience_intent":"mpe_targeted",
         "source_evidence_reference":"fixture-source-evidence", "audience_rationale_reference":"fixture-audience-evidence"},
        {"username":"candidate_two", "sampling_stratum":"retail", "source_evidence_reference":"fixture-source-evidence"}]})
    yield engine, base
    engine.dispose()


def record(engine, base, *, handle="candidate_one", ident=ID, cycle=CYCLE, day=DAY,
           viewer=VIEWER, tenant=TENANT, outcome="IDENTIFIED", linked=True):
    key = stable_id("bd-identity-attempt", tenant, day, handle.casefold())
    reserve = {"cycle_key":cycle,"username":handle,"viewer_ig_id":viewer,
               "manifest_sha256":base.fingerprint(),"actor_id":"admin-fixture",
               "institutional_decision":"DEC-018","operation":"business_discovery_identity_read"}
    with engine.begin() as db:
        for version, kind, payload in [(1,RESERVATION,reserve),(2,RESULT,
            {"username":handle,"status":outcome, **({"instagram_id":ident} if outcome=="IDENTIFIED" else {"code":"PROVIDER_PERMISSION_DENIED"})})]:
            if version == 2 and outcome is None:
                break
            ev = db.execute(insert(domain_events).values(event_id=str(uuid4()),tenant_id=tenant,
                aggregate_type="bd_identity",aggregate_id=key,aggregate_version=version,event_type=kind,
                occurred_at=day+"T01:43:08+00:00",payload=json.dumps(payload)))
            if linked or version == 1:
                db.execute(insert(outbox).values(seq=ev.inserted_primary_key[0],attempts=0,dead_letter=0))


def test_reconcile_persisted_identity_only_preserves_approvals_and_db(setup):
    engine, base = setup
    record(engine, base)
    record(engine, base, handle="candidate_two", outcome=None)
    new, report = reconcile_identities(engine,TENANT,VIEWER,base,[CYCLE])
    assert new.sources[0] == base.sources[0]
    assert new.sources[1].expected_ig_id == ID and new.sources[1].status == "candidate"
    assert new.sources[1].allowed_operations == [] and new.sources[1].approval_reference is None
    assert new.sources[2] == base.sources[2]
    assert report["ids_added"] == 1 and report["approved"] == 1 and report["grants_created"] == 0
    assert report["skipped"][0]["reason"] == "NO_RESULT_RESERVED"
    assert report["manifest_sha256_after"] == new.fingerprint() != base.fingerprint()
    with engine.connect() as db:
        assert db.execute(select(func.count()).select_from(domain_events)).scalar_one() == 3
        assert db.execute(select(func.count()).select_from(source_grants)).scalar_one() == 0
        assert db.execute(select(func.count()).select_from(ingestion_records)).scalar_one() == 0


def test_blocked_only_cannot_reconcile(setup):
    engine, base = setup
    record(engine, base, outcome="BLOCKED")
    with pytest.raises(ConnectorError,match="BD_RECONCILE_NO_SUCCESSFUL_IDENTITIES"):
        reconcile_identities(engine,TENANT,VIEWER,base,[CYCLE])


@pytest.mark.parametrize("change", ["manifest", "viewer", "tenant", "outbox", "existing_id", "alias", "changed_id"])
def test_invalid_evidence_fails_closed(setup, change):
    engine, base = setup
    record(engine,base, ident=base.sources[0].expected_ig_id if change=="existing_id" else ID,
           linked=change!="outbox", tenant="other" if change=="tenant" else TENANT)
    if change=="alias":
        record(engine,base,handle="candidate_two",cycle=OTHER,day="2026-11-14")
    if change=="changed_id":
        record(engine,base,ident="17841400000000009",cycle=OTHER,day="2026-11-14")
    if change=="manifest":
        base=BatchManifest(schema_version=base.schema_version,sources=base.sources[:2])
    with pytest.raises(ConnectorError):
        reconcile_identities(engine,TENANT,"17841400000000009" if change=="viewer" else VIEWER,base,[CYCLE])


def test_cli_preview_and_exclusive_output(setup,tmp_path,monkeypatch,capsys):
    from scripts import a6_reconcile_identities as cli
    engine,base=setup
    record(engine,base)
    path=tmp_path/"manifest.json"; path.write_text(base.model_dump_json(),encoding="utf-8")
    monkeypatch.setenv("TAPI_DATABASE_URL",str(engine.url))
    monkeypatch.setenv("TAPI_TENANT_ID",TENANT)
    monkeypatch.setenv("TAPI_META_IG_ID",VIEWER)
    monkeypatch.delenv("TAPI_INSTAGRAM_ACCESS_TOKEN",raising=False)
    monkeypatch.setattr(cli,"__file__",str(tmp_path/"scripts"/"a6_reconcile_identities.py"))
    output=tmp_path/"artifacts"/"private"/"out.json"
    args=["--manifest",str(path),"--cycle",CYCLE]
    assert cli.main(args)==0
    assert json.loads(capsys.readouterr().out)["status"]=="IDENTITY_RECONCILIATION_PLANNED"
    assert not output.exists()
    assert cli.main(args+["--output",str(output)])==0
    assert json.loads(capsys.readouterr().out)["status"]=="IDENTITIES_RECONCILED"
    previous=output.read_bytes()
    assert cli.main(args+["--output",str(output)])==2
    assert output.read_bytes()==previous
