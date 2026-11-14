"""Offline expansion ordering, reservation history and real provider fixture."""
import httpx
from tapi_gate0.discovery_batch import BatchManifest
from tapi_gate0.discovery_identity_expansion import plan_expansion
from tapi_gate0.discovery_identity_a6 import execute_identity
from tapi_gate0.identity import Principal
from tapi_gate0.connectors import OfficialHttp
from test_discovery_batch_a4 import db, manifest, TENANT, VIEWER, TOKEN


def test_expansion_prioritizes_distinct_uncovered_strata_and_never_retries(tmp_path,monkeypatch):
    engine,store=db(tmp_path)
    for flag in ("TAPI_BD_IDENTITY_ENABLED","TAPI_OFFICIAL_METADATA_READS","TAPI_ZERO_BILLING_CONFIRMED"):
        monkeypatch.setenv(flag,"1")
    for flag in ("TAPI_META_TOKEN_EXPIRES_AT","TAPI_META_DATA_ACCESS_EXPIRES_AT","TAPI_META_REQUIRE_TOKEN_EXPIRY"):
        monkeypatch.delenv(flag,raising=False)
    base=manifest(approved=1)
    candidate=base.sources[1]
    def new(name,stratum):
        return candidate.model_copy(update={"username":name,"expected_ig_id":None,
             "sampling_stratum":stratum,"audience_rationale_reference":"fixture-audience-rationale"})
    frame=BatchManifest(schema_version=base.schema_version,sources=[
        base.sources[0],new("a_food","food"),new("b_food","food"),
        new("c_retail","retail"),new("d_other",base.sources[0].sampling_stratum)])
    try:
        r=plan_expansion(engine,TENANT,frame,VIEWER,max_sources=3)
        assert r["selected_sources"]==["a_food","c_retail","d_other"]
        assert r["remaining_unattempted_candidates"]==1 and not r["database_mutated"]
        assert r["conservative_reserved_today"]==0
        def handler(req):
            return httpx.Response(200,json={"id":VIEWER,"business_discovery":
                   {"id":"17841411111111111","username":"a_food"}})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result=execute_identity(engine,Principal(actor_id="admin",tenant_id=TENANT,role="admin"),
                frame,VIEWER,["a_food"],token=TOKEN,http=OfficialHttp(client=client,instagram_version="v26.0"))
        assert result["status"]=="IDENTITY_BATCH_COMPLETED"
        r=plan_expansion(engine,TENANT,frame,VIEWER,max_sources=3)
        assert r["selected_sources"]==["b_food","c_retail","d_other"]
        assert r["pending_identity_actions"]==[{"username":"a_food","action":"RECONCILE_EXACT_MANIFEST",
                                              "matching_cycles":[result["cycle_key"]]}]
        assert r["identity_reserved_today"]==1
    finally:
        engine.dispose()
