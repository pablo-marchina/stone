"""EDD contract suite for synthetic-only domain API.

All fixtures are artificial and cannot be presented as real Stone/Instagram data.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tapi_gate0.api import create_app
from tapi_gate0.domain import (
    Campaign, Connection, ConversionEvent, EvidenceModality, EvidenceStatus,
    FieldEvidence, Publication, RubricAssessmentCreate, RubricFields,
    RUBRIC_FIELD_NAMES, DOMAIN_ENTITIES,
)

KEY="local-dev-only-test-secret-unique-at-least-32-characters"
NOW=datetime(2026,10,23,12,0,tzinfo=timezone.utc)
TENANT="local-research"


@pytest.fixture
def local_app(tmp_path):
    return create_app(local_domain=True,dev_key=KEY,db_path=str(tmp_path/"domain.sqlite3"))


@pytest.fixture
def client(local_app):
    with TestClient(local_app) as c:
        yield c


def auth(c,method,path,**kwargs):
    headers={"X-TAPI-Local-Key":KEY,**kwargs.pop("headers",{})}
    return getattr(c,method.lower())(path,headers=headers,**kwargs)


def creator(cid="creator-a",tenant=TENANT,origin="synthetic_local"):
    return {"creator_id":cid,"tenant_id":tenant,"origin":origin,"handle":"local-fixture"}


def post(pid="post-a",creator_id="creator-a", days_old=30, tenant=TENANT,origin="synthetic_local"):
    return {"content_id":pid,"tenant_id":tenant,"creator_id":creator_id,
            "origin":origin,"media_type":"reels","published_at":(NOW-timedelta(days=days_old)).isoformat(),
            "is_synthetic":origin=="synthetic_local"}


def metrics(mid="m-a",pid="post-a",likes=50,comments=0,followers=1000,seen=NOW,tenant=TENANT):
    return {"snapshot_id":mid,"tenant_id":tenant,"content_id":pid,"observed_at":seen.isoformat(),
            "followers_measured_at":seen.isoformat(),"likes":likes,"comments":comments,"follower_count":followers}


def seed(c,pid="post-a",cid="creator-a",likes=50,followers=1000):
    assert auth(c,"post","/v1/creators",json=creator(cid)).status_code==201
    assert auth(c,"post","/v1/content",json=post(pid,cid)).status_code==201
    assert auth(c,"post",f"/v1/content/{pid}/metrics",json=metrics("metrics-"+pid,pid,likes=likes,followers=followers)).status_code==201


def test_default_bootstrap_api_does_not_expose_local_entities():
    app=create_app()
    assert set(app.openapi()["paths"])=={"/healthz","/v1/gate0/status"}


def test_local_api_strong_key_is_mandatory():
    with pytest.raises(ValueError):
        create_app(local_domain=True,dev_key="weak")


def test_local_api_authentication_is_required(client):
    assert client.get("/v1/domain/catalog").status_code==401
    assert client.post("/v1/creators",json=creator()).status_code==401
    assert client.get("/v1/creators/a",headers={"X-TAPI-Local-Key":"wrong"}).status_code==401


def test_non_loopback_is_denied(local_app):
    @local_app.middleware("http")
    async def simulate_remote_client(request, call_next):
        request.scope["client"] = ("198.51.100.20", 5544)
        return await call_next(request)
    with TestClient(local_app) as c:
        r=auth(c,"get","/v1/domain/catalog")
        assert r.status_code==403
        assert r.json()["code"]=="LOCAL_ONLY"


def test_tenant_is_derived_from_local_principal(client):
    r=auth(client,"post","/v1/creators",json=creator(tenant="another-org"))
    assert r.status_code==403
    assert r.json()["code"]=="TENANT_MISMATCH"


@pytest.mark.parametrize("origin",["instagram","youtube","stone_internal"])
def test_external_content_cannot_be_ingested(client,origin):
    r=auth(client,"post","/v1/creators",json=creator(origin=origin))
    assert r.status_code==403
    assert r.json()["code"]=="SOURCE_PERMISSION_DENIED"


@pytest.mark.parametrize("endpoint",["/v1/collections","/v1/publications","/v1/campaigns","/v1/crm/conversions"])
def test_all_external_actions_are_explicitly_blocked(client,endpoint):
    r=auth(client,"post",endpoint,json={"tenant_id":TENANT,"source":"synthetic_local","request_id":"req-1"})
    assert r.status_code==403
    assert r.json()["type"]=="about:blank"
    assert r.json()["code"]=="SOURCE_PERMISSION_DENIED"


def test_policy_check_never_approves_external_data(client):
    r=auth(client,"post","/v1/policy/check",json={"source":"instagram_media","operation":"classify"})
    assert r.status_code==200
    assert r.json()["permitted"] is False


def test_create_and_read_synthetic_creator_and_post(client):
    assert auth(client,"post","/v1/creators",json=creator()).status_code==201
    r=auth(client,"get","/v1/creators/creator-a")
    assert r.status_code==200
    assert r.json()["origin"]=="synthetic_local"
    assert auth(client,"post","/v1/content",json=post()).status_code==201
    assert auth(client,"get","/v1/content/post-a").json()["content_id"]=="post-a"


def test_duplicate_ids_conflict_and_not_emit_duplicate_event(client):
    assert auth(client,"post","/v1/creators",json=creator()).status_code==201
    r=auth(client,"post","/v1/creators",json=creator())
    assert r.status_code==409
    assert r.json()["code"]=="DUPLICATE_ID"
    events=auth(client,"get","/v1/events").json()["events"]
    assert len(events)==1
    assert events[0]["aggregate_version"]==1


def test_foreign_key_invalid_relationship_fails(client):
    r=auth(client,"post","/v1/content",json=post())
    assert r.status_code==404
    assert len(auth(client,"get","/v1/events").json()["events"])==0


def test_cross_creator_origin_rejected(client):
    auth(client,"post","/v1/creators",json=creator())
    payload=post(origin="instagram")
    payload["source_url"]="https://example.org/owned-placeholder"
    r=auth(client,"post","/v1/content",json=payload)
    assert r.status_code==403


def test_invalid_post_timestamp_and_bool_are_rejected(client):
    auth(client,"post","/v1/creators",json=creator())
    x=post(); x["published_at"]="2026-10-01T10:00:00" # naive
    assert auth(client,"post","/v1/content",json=x).status_code==422
    x=post(); x["is_synthetic"]=False
    assert auth(client,"post","/v1/content",json=x).status_code==422


def test_path_payload_mismatch_is_rejected(client):
    seed(client)
    r=auth(client,"post","/v1/content/post-a/metrics",json=metrics(pid="other"))
    assert r.status_code==422
    assert r.json()["code"]=="PATH_PAYLOAD_MISMATCH"


def test_nonnegative_metrics_and_missing_denominator(client):
    seed(client)
    m=metrics(mid="neg",likes=-1)
    assert auth(client,"post","/v1/content/post-a/metrics",json=m).status_code==422
    assert auth(client,"post","/v1/content/post-a/metrics",json=metrics(mid="zero",followers=0)).status_code==201
    r=auth(client,"post","/v1/analyses/rankings",json={"tenant_id":TENANT,"as_of":NOW.isoformat()})
    assert r.status_code==200
    assert r.json()["n_posts"]==0
    assert r.json()["excluded_no_positive_denominator"]==1


def test_ranking_exact_fraction_tie_and_latest_snapshot(client):
    seed(client,"post-a","creator-a",likes=1,followers=3)
    seed(client,"post-b","creator-b",likes=2,followers=6)
    # exactly equal rational values; stable tie-break on post ID
    result=auth(client,"post","/v1/analyses/rankings",json={"tenant_id":TENANT,"as_of":NOW.isoformat()}).json()
    assert result["n_posts"]==2
    assert result["top_count"]==1
    assert [r["content_id"] for r in result["rows"]]==["post-a","post-b"]
    assert [r["is_top_decile"] for r in result["rows"]]==[True,False]
    assert result["metric_formula"]=="(likes+comments)/followers"
    # later snapshot within as_of changes rank; future snapshot must not
    m=metrics("zz-new","post-b",likes=90,followers=100,seen=NOW)
    assert auth(client,"post","/v1/content/post-b/metrics",json=m).status_code==201
    m=metrics("m-future","post-a",likes=999,followers=10,seen=NOW+timedelta(days=1))
    assert auth(client,"post","/v1/content/post-a/metrics",json=m).status_code==201
    result=auth(client,"post","/v1/analyses/rankings",json={"tenant_id":TENANT,"as_of":NOW.isoformat()}).json()
    assert result["rows"][0]["content_id"]=="post-b"


def test_ranking_age_and_missing_metrics(client):
    auth(client,"post","/v1/creators",json=creator())
    auth(client,"post","/v1/content",json=post(days_old=1))
    auth(client,"post","/v1/content",json=post("old-post",days_old=50))
    r=auth(client,"post","/v1/analyses/rankings",json={"tenant_id":TENANT,"as_of":NOW.isoformat()}).json()
    assert r["excluded_too_recent"]==1
    assert r["excluded_without_metrics"]==1
    assert r["top_count"]==0


def evidence(modality="caption",locator="synthetic://caption/1",timestamp=None):
    e={"status":"observed","modality":modality,"locator":locator}
    if timestamp is not None:e["timestamp_s"]=timestamp
    return e


def assessment(values,evidences=None):
    return {"assessment_id":"rub-a","tenant_id":TENANT,"content_id":"post-a","rubric_version":"candidate-v5",
            "values":values,"field_evidence":evidences or {},"assessor_kind":"human","assessor_ref":"local-reviewer"}


def test_rubric_has_exactly_twenty_fields():
    assert len(RUBRIC_FIELD_NAMES)==20
    assert set(RubricFields.model_fields)==set(RUBRIC_FIELD_NAMES)


def test_rubric_rejects_assertion_without_evidence(client):
    seed(client)
    r=auth(client,"post","/v1/content/post-a/assessments",json=assessment({"tipo_hook":"pergunta"}))
    assert r.status_code==422


def test_rubric_temporal_field_requires_video_timestamp(client):
    seed(client)
    for ev in [evidence("caption"),evidence("video")]:
        r=auth(client,"post","/v1/content/post-a/assessments",json=assessment({"hook_primeiros_3s":"começa com pergunta"},{"hook_primeiros_3s":ev}))
        assert r.status_code==422
    accepted=assessment({"hook_primeiros_3s":"começa com pergunta"},{"hook_primeiros_3s":evidence("video","synthetic://video/1",2.0)})
    assert auth(client,"post","/v1/content/post-a/assessments",json=accepted).status_code==201


def test_rubric_creator_identity_requires_external_proof(client):
    seed(client)
    assert auth(client,"post","/v1/content/post-a/assessments",json=assessment(
        {"criador_e_empreendedor_real":True},{"criador_e_empreendedor_real":evidence("caption")})).status_code==422


def test_rubric_fields_validate_bounds_and_relations():
    with pytest.raises(ValidationError):
        RubricFields(forca_hook_0a10=11)
    with pytest.raises(ValidationError):
        RubricFields(tem_cta=False,tipo_cta="seguir")
    with pytest.raises(ValidationError):
        RubricFields(elementos_top5=["x"]*6)


def test_unobserved_field_does_not_turn_into_false(client):
    seed(client)
    data=assessment({}, {"tem_rosto":{"status":"not_observable"}})
    assert auth(client,"post","/v1/content/post-a/assessments",json=data).status_code==201
    obj=auth(client,"get","/v1/content/post-a/assessments/latest").json()
    assert obj["values"]["tem_rosto"] is None
    assert obj["field_evidence"]["tem_rosto"]["status"]=="not_observable"


def test_insight_to_creative_has_complete_lineage(client):
    seed(client)
    insight={"insight_id":"insight-a","tenant_id":TENANT,"title":"Padrão observado local",
             "claim":"Exemplo sintético; não representa observação na Stone", "source_content_ids":["post-a"],
             "dataset_version":"synthetic-v1","analysis_kind":"descriptive"}
    assert auth(client,"post","/v1/insights",json=insight).status_code==201
    creative={"creative_id":"creative-a","tenant_id":TENANT,"based_on_insight_id":"insight-a",
              "objective":"Exemplo de teste","hook":"Abertura fictícia","script":"Texto sintético de roteiro",
              "caption":"Legenda fictícia","cta":"Veja mais", "reference_content_ids":["post-a"]}
    assert auth(client,"post","/v1/creatives",json=creative).status_code==201
    lineage=auth(client,"get","/v1/creatives/creative-a/lineage").json()
    assert lineage["insight"]["insight_id"]=="insight-a"
    assert lineage["reference_content"][0]["content_id"]=="post-a"


def test_creative_cannot_cite_post_not_in_insight(client):
    seed(client)
    insight={"insight_id":"insight-a","tenant_id":TENANT,"title":"A",
             "claim":"B", "source_content_ids":["post-a"],"dataset_version":"synthetic-v1"}
    auth(client,"post","/v1/insights",json=insight)
    cr={"creative_id":"creative-a","tenant_id":TENANT,"based_on_insight_id":"insight-a",
        "objective":"Test","hook":"Test","script":"Test","caption":"Test","cta":"Test",
        "reference_content_ids":["missing"]}
    r=auth(client,"post","/v1/creatives",json=cr)
    assert r.status_code==422 and r.json()["code"]=="DOMAIN_INTEGRITY"


def test_synthetic_flow_refuses_causal_claim_and_approved_creative(client):
    seed(client)
    insight={"insight_id":"insight-a","tenant_id":TENANT,"title":"A","claim":"B",
             "source_content_ids":["post-a"],"dataset_version":"synthetic-v1","analysis_kind":"causal_experiment"}
    r=auth(client,"post","/v1/insights",json=insight)
    assert r.status_code==403


def test_domain_events_are_persisted_across_process_restart(tmp_path):
    db=str(tmp_path/"state.sqlite3")
    with TestClient(create_app(local_domain=True,dev_key=KEY,db_path=db)) as first:
        seed(first)
        ev=auth(first,"get","/v1/events").json()["events"]
        assert len(ev)==3
    with TestClient(create_app(local_domain=True,dev_key=KEY,db_path=db)) as second:
        assert auth(second,"get","/v1/content/post-a").status_code==200
        ev2=auth(second,"get","/v1/events").json()["events"]
        assert [e["event_id"] for e in ev2]==[e["event_id"] for e in ev]
        assert len(auth(second,"get","/v1/events",params={"after_seq":ev[0]["seq"]}).json()["events"])==2


def test_status_and_source_rights_remain_blocked(client):
    assert client.get("/v1/gate0/status").json()["source_operations_enabled"] is False
    catalog=auth(client,"get","/v1/domain/catalog").json()
    assert catalog["external_actions_enabled"] is False
    assert catalog["budget_brl"]==0
    assert "production_auth" in catalog["not_yet_operational"]


def test_zero_cost_campaign_is_not_activatable():
    with pytest.raises(ValidationError):
        Campaign(campaign_id="x",tenant_id=TENANT,creative_id="y",max_spend_brl="0.01")
    with pytest.raises(ValidationError):
        Campaign(campaign_id="x",tenant_id=TENANT,creative_id="y",status="active")


def test_openapi_includes_real_request_response_schemas(local_app):
    schema=local_app.openapi()
    assert "/v1/creators" in schema["paths"]
    assert "/v1/analyses/rankings" in schema["paths"]
    assert "RubricAssessmentCreate" in schema["components"]["schemas"]
    assert "RankingResult" in schema["components"]["schemas"]
    assert "CreativeVersion" in schema["components"]["schemas"]
    assert len(DOMAIN_ENTITIES)>=15


def test_rest_of_unified_domain_is_typed_not_operational():
    from tapi_gate0.domain import (
        SourceUseGrant, MediaAsset, ContrastAnalysis, ResourceUsage, AgentToolCall, QualityEvidence,
        DatasetManifest, ReleaseManifest,
    )
    assert len(DOMAIN_ENTITIES) >= 30
    with pytest.raises(ValidationError):
        SourceUseGrant(grant_id="g",tenant_id=TENANT,origin="instagram",permitted_operations=["classify"],status="verified")
    with pytest.raises(ValidationError):
        MediaAsset(asset_id="a",tenant_id=TENANT,content_id="p",media_kind="video",storage_ref="/tmp/x",use_rights_status="pending")
    with pytest.raises(ValidationError):
        ContrastAnalysis(analysis_id="x",tenant_id=TENANT,dataset_version="v1",winning_group_size=1,
                         control_group_size=1,labeled_winners=1,labeled_controls=0,interpretation="associative",effect_estimate=0.9)
    with pytest.raises(ValidationError):
        ResourceUsage(usage_id="u",tenant_id=TENANT,component="inference",cpu_seconds=1,storage_bytes=100,billed_cost_brl="0.01")
    with pytest.raises(ValidationError):
        AgentToolCall(call_id="c",tenant_id=TENANT,run_id="r",tool_name="paid-api",cost_brl="0.01")
    with pytest.raises(ValidationError):
        QualityEvidence(evidence_id="e",tenant_id=TENANT,requirement_id="REQ1",iso_25010_characteristic="security",
                        test_id="T1",evaluation_status="passed")
    with pytest.raises(ValidationError):
        ReleaseManifest(release_id="r",tenant_id=TENANT,build_digest="sha256:a",approved_feature_ids=[],
                        quality_evidence_ids=[],production_ready=True)
