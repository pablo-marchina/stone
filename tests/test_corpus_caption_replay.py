from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace

import pytest

from tapi_gate0 import corpus_caption_replay as replay
from tapi_gate0.evidence_lab import ReportRef
from tapi_gate0.domain import MetricsCreate

NOW = datetime(2026,11,17,tzinfo=timezone.utc)
CAPTION = "Vendas. Comente sua dúvida."
METRIC = MetricsCreate(snapshot_id="snap",tenant_id="tenant",content_id="post",
    observed_at=NOW,followers_measured_at=NOW,likes=1,comments=2,follower_count=100)


def test_opt_in_config_rejects_partial_or_invalid_viewer():
    assert replay.config_from_env({}) is None
    with pytest.raises(ValueError,match="CONFIG_INCOMPLETE"):
        replay.config_from_env({"TAPI_CAPTION_REPLAY_TENANT":"tenant"})
    env={"TAPI_CAPTION_REPLAY_TENANT":"tenant","TAPI_META_IG_ID":"12345"}
    for k in ("MANIFEST","AUDIENCE","TOPIC_CTA","PROOF_OFFER"):
        env["TAPI_CAPTION_REPLAY_"+k+"_NAME"]=k+".json"
        env["TAPI_CAPTION_REPLAY_"+k+"_SHA256"]="a"*64
    assert replay.config_from_env(env).viewer=="12345"


@pytest.fixture
def service(monkeypatch):
    refs=[ReportRef(str(i)+".json",str(i)*64) for i in range(1,5)]
    config=replay.ReplayConfig("tenant","12345",*refs)
    source=SimpleNamespace(username="source",expected_ig_id="23456")
    post=SimpleNamespace(content_id="post",caption=CAPTION)
    frame=SimpleNamespace(fingerprint=lambda:"f"*64)
    audience={"model_revision":replay.MODEL_REVISION,"model_weights_sha256":replay.MODEL_WEIGHTS,
        "local_caption_scope_allowed":True,"local_caption_scope_policy":"dec018-bd-caption-research.v1",
        "external_data_accessed":False}
    saved={"post":{"username":"source","caption_sha256":sha256(CAPTION.encode()).hexdigest(),
                    "grounding":{"reason":"fixture"}}}
    groups=[["tema_principal","tipo_cta"],["oferta_ou_beneficio_explicito","prova_social"]]
    def report_rows(report,*args,**kwargs):
        keys=groups[report["group"]]
        return keys,{"post":{"fields":[{"field":k,"reason":"fixture","evidence_spans":[]} for k in keys]}}
    monkeypatch.setattr(replay,"read_pinned",lambda root,ref: [{},audience,{"group":0},{"group":1}][refs.index(ref)])
    monkeypatch.setattr(replay,"BatchManifest",SimpleNamespace(model_validate=lambda _:frame))
    monkeypatch.setattr(replay,"audience_rows",lambda *args:saved)
    monkeypatch.setattr(replay,"rubric_rows",report_rows)
    monkeypatch.setattr(replay,"evidence_tier",lambda *args:"semantic_consensus_only")
    monkeypatch.setattr(replay,"revalidate_row",lambda *args:{k:("vendas" if k=="tema_principal" else None) for k in args[-1]})
    monkeypatch.setattr(replay,"require_scoped_research",lambda *args:None)
    def ready(*args,_record_observer):
        _record_observer(source,post,METRIC)
        return {"as_of":NOW.isoformat(),"first_blocking_stage":{"CAPTION_AVAILABLE_FOR_ASSESSMENT":1}}
    monkeypatch.setattr(replay,"readiness_report",ready)
    monkeypatch.setattr(replay,"_idle",lambda *args:None)
    monkeypatch.setattr(replay,"_rows",lambda *args:[(source,"ALREADY_PROVISIONED",{})])
    return replay.CaptionReplay(None,config),post


def test_replay_projects_only_sanitized_candidates(service):
    svc,post=service
    row={"source_account_id":"23456"}
    result=svc.detail(None,"tenant",row,post,[METRIC],NOW)
    assert result["status"]=="ready"
    assert result["fields"]["tema_principal"]["value"]=="vendas"
    assert result["fields"]["prova_social"]["state"]=="abstained"
    assert result["fields"]["prova_social"]["value"] is None
    assert result["fields"]["prova_social"]["claim_only"]
    assert not result["canonical"] and not result["model_predictions_reexecuted"]
    assert CAPTION not in str(result)
    assert svc.summary()["population"]==1
    result["fields"]["tema_principal"]["value"]="changed"
    assert svc.detail(None,"tenant",row,post,[METRIC],NOW)["fields"]["tema_principal"]["value"]=="vendas"


def test_replay_withholds_changed_caption_snapshot_source_and_scope(service,monkeypatch):
    svc,post=service
    row={"source_account_id":"23456"}
    assert svc.detail(None,"other",row,post,[METRIC],NOW)["status"]=="disabled"
    assert svc.detail(None,"tenant",row,SimpleNamespace(content_id="other"),[],NOW)["status"]=="outside_report_population"
    assert svc.detail(None,"tenant",row,SimpleNamespace(content_id="post",caption="changed"),[METRIC],NOW)["status"]=="stale_row"
    assert svc.detail(None,"tenant",row,post,[METRIC.model_copy(update={"likes":9})],NOW)["status"]=="stale_row"
    assert svc.detail(None,"tenant",{"source_account_id":"other"},post,[METRIC],NOW)["status"]=="stale_row"
    monkeypatch.setattr(replay,"_rows",lambda *args:[(None,"SCOPE_REVOKED",{})])
    blocked=svc.detail(None,"tenant",row,post,[METRIC],NOW)
    assert blocked["status"]=="scope_blocked" and "fields" not in blocked
