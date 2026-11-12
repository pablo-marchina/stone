from datetime import timedelta
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select, func

from tapi_gate0.connectors import ConnectorError, OfficialHttp
from tapi_gate0.discovery_batch import BatchManifest, BatchLimits
from tapi_gate0.discovery_continuous import plan_cycle
from tapi_gate0.discovery_identity_a6 import IdentityScope, execute_identity, plan_identity, RESERVATION
from tapi_gate0.identity import Principal
from tapi_gate0.ingestion import source_grants, ingestion_records
from tapi_gate0.sa_store import domain_events, outbox
from tapi_gate0.storage import now_utc
from scripts.a5_expand_source_frame import merge_candidates
from test_discovery_batch_a4 import db, manifest, TENANT, VIEWER, TOKEN

ADMIN = Principal(actor_id="admin-fixture", tenant_id=TENANT, role="admin")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    engine, store = db(tmp_path)
    for key in ("TAPI_BD_IDENTITY_ENABLED", "TAPI_OFFICIAL_METADATA_READS", "TAPI_ZERO_BILLING_CONFIRMED"):
        monkeypatch.setenv(key, "1")
    frame = manifest(approved=1)
    scope = IdentityScope(tenant_id=TENANT, viewer_ig_id=VIEWER, manifest_sha256=frame.fingerprint(),
        usernames=["mpe_example"], approval_reference="fixture identity attestation", expires_at=now_utc()+timedelta(hours=1),
        operation="business_discovery_identity_read")
    yield engine,store,frame,scope
    engine.dispose()


def test_candidate_expansion_preserves_approved_and_no_ids():
    path = Path(__file__).resolve().parents[1] / "evidence/acquisition/bd_a6_candidate_expansion_20261112.json"
    candidates = BatchManifest.model_validate_json(path.read_text(encoding="utf-8"))
    assert len(candidates.sources)==18
    assert all(s.status=="candidate" and not s.expected_ig_id and not s.allowed_operations for s in candidates.sources)
    base=manifest(approved=1)
    merged=merge_candidates(base,candidates)
    assert merged.sources[:2]==base.sources and len(merged.sources)==20


def test_identity_plan_is_read_only_and_explicit(setup):
    engine,store,frame,scope=setup
    plan,_=plan_identity(engine,TENANT,frame,VIEWER,["mpe_example"])
    assert plan["max_identity_requests"]==1 and plan["external_data_accessed"] is False
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(domain_events).where(domain_events.c.event_type==RESERVATION)).scalar_one()==0
    with pytest.raises(ConnectorError,match="BD_IDENTITY_SOURCE_NOT_ELIGIBLE"):
        plan_identity(engine,TENANT,frame,VIEWER,["sebrae"])


def test_identity_execution_reserves_and_shares_budget(setup):
    engine,store,frame,scope=setup
    calls=[]
    def handler(req):
        calls.append(req)
        assert req.url.host=="graph.facebook.com" and req.url.path=="/v26.0/"+VIEWER
        assert req.url.params["fields"]=="business_discovery.username(mpe_example){id,username}"
        assert req.headers["Authorization"]=="Bearer "+TOKEN
        return httpx.Response(200,json={"id":VIEWER,"business_discovery":{"id":"17841411111111111","username":"mpe_example"}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result=execute_identity(engine,ADMIN,frame,VIEWER,["mpe_example"],scope,token=TOKEN,http=OfficialHttp(client=client,instagram_version="v26.0"))
    assert len(calls)==1 and result["status"]=="IDENTITY_BATCH_COMPLETED" and TOKEN not in json.dumps(result)
    assert result["posts_collected"]==0 and result["grants_created"]==0
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(source_grants)).scalar_one()==2
        assert conn.execute(select(func.count()).select_from(ingestion_records)).scalar_one()==0
        seqs=conn.execute(select(domain_events.c.seq).where(domain_events.c.aggregate_type=="bd_identity")).scalars().all()
        assert len(seqs)==2 and conn.execute(select(func.count()).select_from(outbox).where(outbox.c.seq.in_(seqs))).scalar_one()==2
    assert plan_cycle(store,TENANT,frame,VIEWER,mode="history",limits=BatchLimits(persist_limit=40))[0]["conservative_reserved_pages_today"]==1
    with pytest.raises(ConnectorError,match="BD_IDENTITY_DAILY_ATTEMPT_EXISTS"):
        plan_identity(engine,TENANT,frame,VIEWER,["mpe_example"])


def test_identity_scope_and_provider_mismatch_fail_closed(setup,monkeypatch):
    engine,store,frame,scope=setup
    calls=[]
    def handler(req):
        calls.append(req)
        return httpx.Response(200,json={"id":VIEWER,"business_discovery":{"id":"17841411111111111","username":"wrong"}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        transport=OfficialHttp(client=client,instagram_version="v26.0")
        with pytest.raises(ConnectorError,match="BD_IDENTITY_SCOPE_MISMATCH"):
            execute_identity(engine,ADMIN,frame,VIEWER,["mpe_example"],scope.model_copy(update={"expires_at":now_utc()-timedelta(seconds=1)}),token=TOKEN,http=transport)
        assert not calls
        result=execute_identity(engine,ADMIN,frame,VIEWER,["mpe_example"],scope,token=TOKEN,http=transport)
        assert result["status"]=="IDENTITY_BATCH_STOPPED" and result["results"][0]["code"]=="BD_IDENTITY_TARGET_MISMATCH"
    assert len(calls)==1


def test_failure_stops_batch_and_keeps_all_reserved_slots(setup):
    engine,store,frame,scope=setup
    extra=frame.sources[1].model_copy(update={"username":"another_candidate","expected_ig_id":None})
    frame=BatchManifest(schema_version=frame.schema_version,sources=[*frame.sources,extra])
    handles=["mpe_example","another_candidate"]
    scope=scope.model_copy(update={"manifest_sha256":frame.fingerprint(),"usernames":handles})
    calls=[]
    def handler(req):
        calls.append(req)
        return httpx.Response(429,json={"error":{"code":4}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result=execute_identity(engine,ADMIN,frame,VIEWER,handles,scope,token=TOKEN,http=OfficialHttp(client=client,instagram_version="v26.0"))
    assert result["status"]=="IDENTITY_BATCH_STOPPED" and len(calls)==1 and result["reserved_requests"]==2
    with pytest.raises(ConnectorError,match="BD_IDENTITY_DAILY_ATTEMPT_EXISTS"):
        plan_identity(engine,TENANT,frame,VIEWER,["another_candidate"])
    assert plan_cycle(store,TENANT,frame,VIEWER,mode="history",limits=BatchLimits(persist_limit=40))[0]["conservative_reserved_pages_today"]==2


def test_admin_and_flags_are_required_before_network(setup,monkeypatch):
    engine,store,frame,scope=setup
    reader=Principal(actor_id="reader",tenant_id=TENANT,role="viewer")
    with pytest.raises(ConnectorError,match="BD_IDENTITY_ADMIN_REQUIRED"):
        execute_identity(engine,reader,frame,VIEWER,["mpe_example"],scope,token=TOKEN)
    monkeypatch.setenv("TAPI_BD_IDENTITY_ENABLED","0")
    with pytest.raises(ConnectorError,match="BD_IDENTITY_FLAGS_REQUIRED"):
        execute_identity(engine,ADMIN,frame,VIEWER,["mpe_example"],scope,token=TOKEN)
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(domain_events).where(domain_events.c.event_type==RESERVATION)).scalar_one()==0


def test_cli_plan_without_credentials(setup,tmp_path,monkeypatch,capsys):
    from scripts.a6_identify_sources import main
    engine,store,frame,scope=setup
    path=tmp_path/"manifest.json"
    path.write_text(frame.model_dump_json(),encoding="utf-8")
    monkeypatch.setenv("TAPI_DATABASE_URL",str(engine.url))
    monkeypatch.setenv("TAPI_TENANT_ID",TENANT)
    monkeypatch.setenv("TAPI_META_IG_ID",VIEWER)
    monkeypatch.delenv("TAPI_INSTAGRAM_ACCESS_TOKEN",raising=False)
    assert main(["--manifest",str(path),"--source","mpe_example"])==0
    assert json.loads(capsys.readouterr().out)["external_data_accessed"] is False
