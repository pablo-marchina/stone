"""A3 offline verification of the live Meta Business Discovery technical path.

The fixture metadata matches selected fields observed by the user in the
4 Nov 2026 @sebrae Graph API Explorer capture; NOT a new live Meta read.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import httpx
import pytest
from sqlalchemy import insert, select, func, update

from tapi_gate0.connectors import ConnectorError, OfficialHttp, Platform
from tapi_gate0.discovery_technical import (
    TechnicalDiscoveryRequest, TechnicalDiscoveryService, audit_run)
from tapi_gate0.ingestion import (IngestionStore, GrantCreate, ingestion_records,
                                  ingestion_runs, source_grants)
from tapi_gate0.sa_store import (metadata, tenants, engine_for, content_items,
                                domain_events, outbox, metrics_snapshots)

VIEWER = "17841459971757521"
TARGET = "17841403133066329"
TOKEN = "local-fixture-secret-not-real"
TENANT = "local-research"
CAPTURE_AS_OF = datetime(2026, 11, 5, 1, 16, tzinfo=timezone.utc)
NOW = datetime.now(timezone.utc)
# Replay original capture intervals relative to this run, not as live data.
# The captured date literals remain in the fixture for traceability.


def row(mid, kind, date, likes, comments, url):
    return {"id":mid, "media_type":kind,
            "media_product_type":"REELS" if kind=="VIDEO" else "FEED",
            "timestamp":(NOW + (datetime.fromisoformat(date) - CAPTURE_AS_OF)).isoformat(),
            "like_count":likes,"comments_count":comments,
            "permalink":url,"caption":"Observação sobre MEI e negócios menores."}

RECENT = [
    row("17960459316014145","CAROUSEL_ALBUM", "2026-11-04T13:57:30+0000",394,17,
        "https://www.instagram.com/p/DfUndNyFI9Q/"),
    row("18033486020885325","VIDEO", "2026-11-03T18:50:06+0000",36,8,
        "https://www.instagram.com/reel/DfSkN-_hxxG/"),
]
OLD = [
    row("18117154925105084","CAROUSEL_ALBUM", "2026-10-21T14:26:55+0000",2498,402,
        "https://www.instagram.com/p/DewnseEDgrc/"),
    row("18071804876768582","CAROUSEL_ALBUM", "2026-10-16T23:56:39+0000",1138,131,
        "https://www.instagram.com/p/Dekw62_Dh3E/"),
]


def setup(tmp_path, *, grant=True):
    engine=engine_for("sqlite:///" + str(tmp_path/"technical.sqlite"))
    metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(insert(tenants).values(tenant_id=TENANT,name="Demo tenant"))
        db.execute(insert(tenants).values(tenant_id="another-tenant",name="Other tenant"))
    store=IngestionStore(engine)
    if grant:
        store.grant(TENANT,"admin",GrantCreate(
            platform=Platform.INSTAGRAM,source_account_id=TARGET,
            approval_reference="DEC-018-verified-operator-scope",
            expires_at=datetime.now(timezone.utc)+timedelta(days=30)))
    return engine,store


def request(key="bdmeta-test001", *, persist=2, pages=2):
    return TechnicalDiscoveryRequest(
        username="sebrae",expected_ig_id=TARGET,viewer_ig_id=VIEWER,
        run_key=key,page_limit=2,max_pages=pages,persist_limit=persist)


def transport(pages=None, *, wrong_target=False, fail_after=None):
    pages=pages or [RECENT,OLD]
    calls=[]
    def callback(req):
        calls.append(req)
        assert req.url.host == "graph.facebook.com"
        assert req.url.path == f"/v26.0/{VIEWER}"
        assert req.headers["Authorization"] == "Bearer " + TOKEN
        assert "access_token" not in req.url.params
        assert "business_discovery.username(sebrae)" in req.url.params["fields"]
        assert "caption" in req.url.params["fields"]
        ix=len(calls)-1
        if fail_after and ix >= fail_after:
            return httpx.Response(429, json={"error":{"code":4}})
        assert ix<len(pages)
        if ix:
            assert ".after(PAGE" in req.url.params["fields"]
        else:
            assert ".after(" not in req.url.params["fields"]
        return httpx.Response(200,json={
            "id":VIEWER,
            "business_discovery":{
                "id":"17841411111111111" if wrong_target else TARGET,
                "username":"sebrae", "followers_count":2330917,
                "media_count":10644,
                "media":{"data":pages[ix],
                         "paging":{"cursors":{"after":f"PAGE{ix+1}"}}},
            }
        })
    client=httpx.Client(transport=httpx.MockTransport(callback))
    return OfficialHttp(client=client, instagram_version="v26.0"),calls,client


@pytest.fixture(autouse=True)
def switches(monkeypatch):
    monkeypatch.setenv("TAPI_BD_TECHNICAL_INGEST","1")
    monkeypatch.setenv("TAPI_OFFICIAL_METADATA_READS","1")
    monkeypatch.setenv("TAPI_ZERO_BILLING_CONFIRMED","1")


def test_realistic_metadata_creates_content_snapshots_audit_and_outbox(tmp_path):
    engine,store=setup(tmp_path)
    transport_obj,calls,client=transport()
    result=TechnicalDiscoveryService(store).execute(TENANT,request(),token=TOKEN,http=transport_obj)
    assert len(calls)==2
    assert result["new_records"]==2
    assert result["sample"]["counts"]["too_recent"]==2
    assert result["metadata_only"] and not result["research_corpus_accepted"]
    report=audit_run(engine,TENANT,request().run_key)
    assert report["status"]=="completed"
    assert report["observations"]==2
    assert report["all_traces_valid"]
    assert {x["source_account_id"] for x in report["items"]}=={TARGET}
    assert {x["viewer_ig_id"] for x in report["items"]}=={VIEWER}
    assert all(x["scientific_eligibility"]=="NOT_ASSESSED" for x in report["items"])
    with engine.connect() as db:
        grant_verified = db.execute(select(source_grants.c.technical_verified_at).where(
            source_grants.c.tenant_id == TENANT,
            source_grants.c.platform == Platform.INSTAGRAM.value,
            source_grants.c.source_account_id == TARGET,
        )).scalar_one()
        assert grant_verified is not None  # does not confer scientific admission
        assert db.execute(select(func.count()).select_from(content_items)).scalar_one()==2
        assert db.execute(select(func.count()).select_from(metrics_snapshots)).scalar_one()==2
        assert db.execute(select(func.count()).select_from(ingestion_records)).scalar_one()==2
        assert db.execute(select(func.count()).select_from(domain_events).where(
            domain_events.c.event_type=="business_discovery.metadata_observed")).scalar_one()==2
        assert db.execute(select(func.count()).select_from(outbox)).scalar_one()==5
        rows=db.execute(select(metrics_snapshots.c.payload)).scalars().all()
        assert sorted(json.loads(x)["likes"] for x in rows)==[1138,2498]
        assert sorted(json.loads(x)["follower_count"] for x in rows)==[2330917,2330917]
        event_payloads=db.execute(select(domain_events.c.payload).where(
            domain_events.c.event_type=="business_discovery.metadata_observed")).scalars().all()
        assert len(event_payloads)==2
        assert all(TOKEN not in ev and "PAGE" not in ev for ev in event_payloads)
    client.close()
    engine.dispose()


def test_grant_missing_denies_before_provider_request(tmp_path):
    engine,store=setup(tmp_path,grant=False)
    t,calls,client=transport()
    with pytest.raises(ConnectorError, match="VALID_SOURCE_GRANT_REQUIRED"):
        TechnicalDiscoveryService(store).execute(TENANT,request(),token=TOKEN,http=t)
    assert calls==[]
    client.close();engine.dispose()


def test_opt_in_flags_fail_closed_before_network(tmp_path,monkeypatch):
    engine,store=setup(tmp_path)
    t,calls,client=transport()
    monkeypatch.delenv("TAPI_BD_TECHNICAL_INGEST")
    with pytest.raises(ConnectorError, match="BD_TECHNICAL_INGEST_DISABLED"):
        TechnicalDiscoveryService(store).execute(TENANT,request(),token=TOKEN,http=t)
    assert calls==[]
    client.close();engine.dispose()


def test_target_mismatch_fails_run_without_persisting(tmp_path):
    engine,store=setup(tmp_path)
    t,calls,client=transport(wrong_target=True)
    with pytest.raises(ConnectorError, match="BD_TARGET_ACCOUNT_MISMATCH"):
        TechnicalDiscoveryService(store).execute(TENANT,request(),token=TOKEN,http=t)
    assert len(calls)==1
    assert audit_run(engine,TENANT,request().run_key)["status"]=="failed"
    with engine.connect() as db:
        assert db.execute(select(func.count()).select_from(content_items)).scalar_one()==0
        assert db.execute(select(source_grants.c.technical_verified_at).where(
            source_grants.c.tenant_id == TENANT,
            source_grants.c.platform == Platform.INSTAGRAM.value,
            source_grants.c.source_account_id == TARGET,
        )).scalar_one() is None
    client.close();engine.dispose()


def test_repeating_read_keeps_content_and_audits_new_observation(tmp_path):
    engine,store=setup(tmp_path)
    t1,_,c1=transport()
    first=TechnicalDiscoveryService(store).execute(TENANT,request(),token=TOKEN,http=t1)
    assert first["new_records"]==2
    t2,_,c2=transport()
    second=TechnicalDiscoveryService(store).execute(TENANT,request("bdmeta-test002"),token=TOKEN,http=t2)
    assert second["new_records"]==0
    assert second["duplicate_records"]==2
    assert audit_run(engine,TENANT,"bdmeta-test002")["observations"]==2
    with engine.connect() as db:
        assert db.execute(select(func.count()).select_from(content_items)).scalar_one()==2
        assert db.execute(select(func.count()).select_from(metrics_snapshots)).scalar_one()==2
    c1.close();c2.close();engine.dispose()


def test_metrics_changed_append_snapshot_no_overwrite(tmp_path):
    engine,store=setup(tmp_path)
    a,_,c1=transport(pages=[OLD])
    TechnicalDiscoveryService(store).execute(TENANT,request(pages=1),token=TOKEN,http=a)
    changed=[dict(OLD[0],like_count=2700),OLD[1]]
    b,_,c2=transport(pages=[changed])
    result=TechnicalDiscoveryService(store).execute(TENANT,request("bdmeta-test003",pages=1),token=TOKEN,http=b)
    assert result["refreshed_records"]==1
    assert result["duplicate_records"]==1
    with engine.connect() as db:
        assert db.execute(select(func.count()).select_from(metrics_snapshots)).scalar_one()==3
        assert sorted(json.loads(x)["likes"] for x in db.execute(select(metrics_snapshots.c.payload)).scalars())==[1138,2498,2700]
    c1.close();c2.close();engine.dispose()


def test_revoked_after_request_cannot_persist(tmp_path):
    engine,store=setup(tmp_path)
    def revoke_callback(req):
        store.revoke_grant(TENANT,"admin",Platform.INSTAGRAM,TARGET)
        return httpx.Response(200,json={"id":VIEWER,"business_discovery":{
            "id":TARGET,"username":"sebrae","followers_count":2330917,
            "media":{"data":OLD}}})
    c=httpx.Client(transport=httpx.MockTransport(revoke_callback))
    t=OfficialHttp(client=c,instagram_version="v26.0")
    with pytest.raises(ConnectorError, match="VALID_SOURCE_GRANT_REQUIRED"):
        TechnicalDiscoveryService(store).execute(TENANT,request(pages=1),token=TOKEN,http=t)
    with engine.connect() as db:
        assert db.execute(select(func.count()).select_from(content_items)).scalar_one()==0
    c.close();engine.dispose()


def test_tenant_isolation_on_audit(tmp_path):
    engine,store=setup(tmp_path)
    t,_,c=transport(pages=[OLD])
    TechnicalDiscoveryService(store).execute(TENANT,request(pages=1),token=TOKEN,http=t)
    with pytest.raises(ConnectorError,match="BD_RUN_NOT_FOUND"):
        audit_run(engine,"another-tenant",request().run_key)
    c.close();engine.dispose()


def test_api_version_allowlist_and_cursor_safety():
    with pytest.raises(ValueError,match="UNSUPPORTED_META_GRAPH_VERSION"):
        OfficialHttp(instagram_version="v27.0")
    req=request()
    assert req.persist_limit==2 and req.min_age_days==14
    with pytest.raises(ValueError,match="DISCOVERY_VIEWER_MUST_DIFFER_FROM_TARGET"):
        TechnicalDiscoveryRequest(username="sebrae",expected_ig_id=TARGET,
          viewer_ig_id=TARGET,run_key="bdmeta-denied")


def test_script_without_execute_does_not_use_token(monkeypatch,capsys):
    from importlib.util import module_from_spec, spec_from_file_location
    path=Path(__file__).parent.parent/"scripts"/"a3_business_discovery_first_batch.py"
    spec=spec_from_file_location("a3",path)
    mod=module_from_spec(spec);spec.loader.exec_module(mod)
    monkeypatch.delenv("TAPI_INSTAGRAM_ACCESS_TOKEN",raising=False)
    assert mod.main([])==0
    assert json.loads(capsys.readouterr().out)["status"]=="NOT_EXECUTED"
    assert mod.main(["--execute"])==2
    data=json.loads(capsys.readouterr().out)
    assert "TAPI_INSTAGRAM_ACCESS_TOKEN" in data["required_environment_names"]


def test_no_eligible_media_is_truthfully_reported(tmp_path):
    engine,store=setup(tmp_path)
    t,_,client=transport(pages=[RECENT])
    result=TechnicalDiscoveryService(store).execute(TENANT,
        request(pages=1), token=TOKEN, http=t)
    assert result["status"]=="BD_TECHNICAL_NO_ELIGIBLE_MEDIA"
    assert result["new_records"]==0
    report=audit_run(engine,TENANT,request().run_key)
    assert report["status"]=="completed"
    assert report["observations"]==0
    assert not report["has_persisted_observations"]
    client.close();engine.dispose()


def test_secure_router_requires_admin_and_exposes_read_only_audit(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from tapi_gate0.secure_api import create_secure_app
    from tapi_gate0.identity import MemberCreate, Principal

    app=create_secure_app("sqlite:///"+str(tmp_path/"api.sqlite"),
                          initialize_schema=True,allow_http_local=True)
    app.state.identity_store.bootstrap(TENANT,"Example tenant", "admin", "secure-password-12345")
    admin=Principal(actor_id="founder",tenant_id=TENANT,role="admin")
    app.state.identity_store.add_member(admin, MemberCreate(
        user_id="viewer",username="viewer",role="viewer",password="secure-password-12345"))
    with TestClient(app) as client:
        endpoint="/v1/ingestion/business-discovery/technical-runs"
        assert client.post(endpoint,json=request().model_dump()).status_code==401
        login=client.post("/v1/auth/sessions",json={
            "tenant_id":TENANT,"username":"viewer","password":"secure-password-12345"})
        assert login.status_code==200
        viewer_headers={"Authorization":"Bearer "+login.json()["access_token"]}
        assert client.post(endpoint,headers=viewer_headers,json=request().model_dump()).status_code==403
        login=client.post("/v1/auth/sessions",json={
            "tenant_id":TENANT,"username":"admin","password":"secure-password-12345"})
        assert login.status_code==200
        admin_headers={"Authorization":"Bearer "+login.json()["access_token"]}
        monkeypatch.delenv("TAPI_BD_TECHNICAL_INGEST",raising=False)
        blocked=client.post(endpoint,headers=admin_headers,json=request().model_dump())
        assert blocked.status_code==403 and blocked.json()["code"]=="BD_TECHNICAL_INGEST_DISABLED"
        assert client.get(endpoint+"/bdmeta-test001/audit",headers=viewer_headers).status_code==403
        assert client.get(endpoint+"/bdmeta-test001/audit",headers=admin_headers).status_code==404


def test_old_reel_and_image_format_from_real_capture(tmp_path):
    engine,store=setup(tmp_path)
    rows=[
        row("17906758752569754","VIDEO","2026-10-16T21:00:09+0000",131,8,
            "https://www.instagram.com/reel/DekcxdLhQii/"),
        row("18119801084115824","IMAGE","2026-10-21T22:04:14+0000",1284,130,
            "https://www.instagram.com/p/Dexb7nJOhUN/"),
    ]
    t,_,client=transport(pages=[rows])
    result=TechnicalDiscoveryService(store).execute(TENANT,request(pages=1),token=TOKEN,http=t)
    assert result["new_records"]==2
    with engine.connect() as db:
        blobs=db.execute(select(content_items.c.payload)).scalars().all()
        assert {json.loads(blob)["media_type"] for blob in blobs}=={"reels","imagem"}
    client.close();engine.dispose()

 
def test_technical_source_verification_never_admits_scientific_corpus(tmp_path):
    from tapi_gate0.corpus import CorpusProfileCreate, register_profile, corpus_data_card

    engine, store = setup(tmp_path)
    register_profile(engine, TENANT, CorpusProfileCreate(
        platform=Platform.INSTAGRAM, source_account_id=TARGET,
        sector="other", sampling_stratum="external-sector-organization",
        evidence_reference="manual-scope-evidence-DEC018"))
    t, _, client = transport(pages=[OLD])
    outcome = TechnicalDiscoveryService(store).execute(
        TENANT, request(pages=1), token=TOKEN, http=t)
    assert outcome["new_records"] == 2
    assert outcome["scientifically_validated"] is False
    assert outcome["production_approved"] is False
    data_card = corpus_data_card(engine, TENANT)
    assert data_card["sampling_frame"]["with_prior_technical_verification"] == 1
    assert data_card["observed"]["technically_eligible_instagram_posts"] == 2
    assert data_card["observed"]["scientifically_eligible_instagram_posts"] == 0
    assert data_card["observed"]["excluded_source_context_missing"] == 2
    assert data_card["target_reached"] is False
    client.close(); engine.dispose()
