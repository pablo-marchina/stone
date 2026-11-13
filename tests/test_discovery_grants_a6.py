import pytest
from sqlalchemy import select, func, update
from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_grants_a6 import provision, PREFIX
from tapi_gate0.identity import Principal
from tapi_gate0.ingestion import source_grants, ingestion_records
from tapi_gate0.sa_store import domain_events
from test_discovery_reconcile_a6 import setup, record, TENANT, VIEWER, ID
from tapi_gate0.discovery_reconcile_a6 import reconcile_identities
from test_discovery_reconcile_a6 import CYCLE

ADMIN = Principal(actor_id="admin",tenant_id=TENANT,role="admin")


def test_preview_provision_and_idempotent_recovery(setup):
    engine, base = setup
    record(engine,base)
    frame,_=reconcile_identities(engine,TENANT,VIEWER,base,[CYCLE])
    _, preview=provision(engine,TENANT,VIEWER,frame,["candidate_one"])
    assert preview["grants_created"]==0 and preview["grants_to_create"]==1
    with engine.connect() as db:
        assert db.execute(select(func.count()).select_from(source_grants)).scalar_one()==0
    updated,report=provision(engine,TENANT,VIEWER,frame,["candidate_one"],principal=ADMIN)
    assert report["grants_created"]==1 and report["approved"]==2
    assert updated.sources[0]==frame.sources[0] and updated.sources[1].approval_reference==PREFIX+VIEWER+":"+ID
    assert updated.sources[1].allowed_operations==["business_discovery_metadata_read"]
    with engine.connect() as db:
        grant=db.execute(select(source_grants)).mappings().one()
        assert grant["technical_verified_at"] is None and grant["expires_at"]==updated.sources[1].expires_at.isoformat()
        assert db.execute(select(func.count()).select_from(ingestion_records)).scalar_one()==0
        assert db.execute(select(func.count()).select_from(domain_events).where(domain_events.c.event_type=="ingestion.grant.created")).scalar_one()==1
    again,report=provision(engine,TENANT,VIEWER,frame,["candidate_one"],principal=ADMIN)
    assert report["grants_created"]==0 and again==updated


def test_invalid_selection_atomic_and_admin_required(setup):
    engine,base=setup
    record(engine,base)
    frame,_=reconcile_identities(engine,TENANT,VIEWER,base,[CYCLE])
    with pytest.raises(ConnectorError):
        provision(engine,TENANT,VIEWER,frame,["candidate_one","candidate_two"],principal=ADMIN)
    with pytest.raises(ConnectorError):
        provision(engine,TENANT,VIEWER,frame,["candidate_one"],principal=Principal(actor_id="a",tenant_id=TENANT,role="viewer"))
    with pytest.raises(ConnectorError):
        provision(engine,TENANT,VIEWER,frame,["candidate_one"],principal=Principal(actor_id="a",tenant_id="other",role="admin"))
    with engine.connect() as db:
        assert db.execute(select(func.count()).select_from(source_grants)).scalar_one()==0


def test_revoked_not_reenabled(setup):
    engine,base=setup
    record(engine,base)
    frame,_=reconcile_identities(engine,TENANT,VIEWER,base,[CYCLE])
    provision(engine,TENANT,VIEWER,frame,["candidate_one"],principal=ADMIN)
    with engine.begin() as db:
        db.execute(update(source_grants).values(enabled=0))
    with pytest.raises(ConnectorError,match="BD_GRANT_EXISTING_CONFLICT_OR_EXPIRED"):
        provision(engine,TENANT,VIEWER,frame,["candidate_one"],principal=ADMIN)


def test_technical_grant_denies_generic_route_and_other_viewer(setup,monkeypatch):
    from tapi_gate0.connectors import Platform
    from tapi_gate0.ingestion import IngestionStore, IngestionRequest, ingestion_runs
    from tapi_gate0.discovery_technical import TechnicalDiscoveryService, TechnicalDiscoveryRequest
    engine,base=setup
    record(engine,base)
    frame,_=reconcile_identities(engine,TENANT,VIEWER,base,[CYCLE])
    provision(engine,TENANT,VIEWER,frame,["candidate_one"],principal=ADMIN)
    for flag in ("TAPI_OFFICIAL_METADATA_READS","TAPI_ZERO_BILLING_CONFIRMED","TAPI_BD_TECHNICAL_INGEST"):
        monkeypatch.setenv(flag,"1")
    monkeypatch.delenv("TAPI_INSTAGRAM_ACCESS_TOKEN",raising=False)
    store=IngestionStore(engine)
    with pytest.raises(ConnectorError,match="BD_GRANT_TECHNICAL_ROUTE_ONLY"):
        store.run(TENANT,IngestionRequest(platform=Platform.INSTAGRAM,source_account_id=ID,run_key="generic-run-001"))
    with pytest.raises(ConnectorError,match="BD_GRANT_VIEWER_MISMATCH"):
        TechnicalDiscoveryService(store).execute(TENANT,TechnicalDiscoveryRequest(username="candidate_one",expected_ig_id=ID,
            viewer_ig_id="17841400000000009",run_key="technical-run-001"))
    with engine.connect() as db:
        assert db.execute(select(func.count()).select_from(ingestion_runs)).scalar_one()==0


def test_cli_preview_without_token(setup,tmp_path,monkeypatch,capsys):
    import json
    from scripts import a6_provision_grants as cli
    engine,base=setup
    record(engine,base)
    frame,_=reconcile_identities(engine,TENANT,VIEWER,base,[CYCLE])
    path=tmp_path/"frame.json"
    path.write_text(frame.model_dump_json(),encoding="utf-8")
    monkeypatch.setenv("TAPI_DATABASE_URL",str(engine.url))
    monkeypatch.setenv("TAPI_TENANT_ID",TENANT)
    monkeypatch.setenv("TAPI_META_IG_ID",VIEWER)
    monkeypatch.delenv("TAPI_INSTAGRAM_ACCESS_TOKEN",raising=False)
    assert cli.main(["--manifest",str(path),"--source","candidate_one"])==0
    assert json.loads(capsys.readouterr().out)["status"]=="TECHNICAL_GRANTS_PLANNED"
