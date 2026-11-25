import pytest

from tapi_gate0.corpus_ranking_read import rank_rows, read_ranking, FIELDS
from tapi_gate0.connectors import ConnectorError


def rows():
    return [{"content_id":f"p{i:02d}","username":"a" if i<10 else "b",
             "tier":"semantic_consensus_only" if i<10 else "unresolved",
             "likes":100-i,"comments":0,"followers":1000,"format":"reels",
             "snapshot_id":f"s{i:02d}","observed_at":"2026-11-17T12:00:00+00:00",
             "followers_measured_at":"2026-11-17T12:00:00+00:00",
             "published_at":"2026-10-01T12:00:00+00:00","age_band":"30-89",
             "sector":"services","topic":None,"cta":None,
             "grounded_rubric":{f:"vendas" if i==0 and f=="tema_principal" else None for f in FIELDS}}
            for i in range(20)]


def test_rank_keeps_global_population_when_paginated_or_top_only():
    data=rows()
    r=rank_rows(data,cohort="technical_all",top_only=True,offset=0,limit=1)
    assert r["cohorts"]["technical_all"]["posts"]==20
    assert r["cohorts"]["semantic_exploratory"]["posts"]==10
    assert r["total"]==2 and r["next_offset"]==1
    assert r["items"][0]["rank"]==1 and r["items"][0]["er_percent"]==10
    assert r["items"][0]["top_decile"]
    assert not r["canonical"] and not r["database_mutated"]
    assert r["sensitivity"]["within_profile_top_count"]==2
    assert r["grounded_contrasts"]["tema_principal"]["global"]["top"]["unknown"]==1
    assert r["grounded_contrasts"]["tema_principal"]["global"]["rest"]["unknown"]==18
    r2=rank_rows(data,cohort="technical_all",top_only=False,offset=1,limit=1)
    assert r2["total"]==20 and r2["items"][0]["rank"]==2
    assert r2["cohorts"]==r["cohorts"]


def test_rank_semantic_empty_and_exact_tie_break():
    data=rows()
    data[1]["likes"]=data[0]["likes"]
    data.reverse()
    r=rank_rows(data,cohort="semantic_exploratory",top_only=True,offset=0,limit=25)
    assert r["total"]==1 and r["items"][0]["content_id"]=="p00"
    assert r["cohorts"]["semantic_exploratory"]["cutoff_tie"]
    for row in data:
        row["tier"]="unresolved"
    r=rank_rows(data,cohort="semantic_exploratory",top_only=False,offset=0,limit=25)
    assert r["total"]==0 and r["items"]==[]
    assert r["cohorts"]["semantic_exploratory"]["median_er_percent"] is None


def test_rank_rejects_duplicate_and_invalid_query():
    with pytest.raises(ConnectorError,match="STALE_REPLAY"):
        rank_rows(rows()+rows(),cohort="technical_all",top_only=True,offset=0,limit=25)
    with pytest.raises(ConnectorError,match="QUERY_INVALID"):
        rank_rows(rows(),cohort="other",top_only=True,offset=0,limit=25)
    assert read_ranking(None,"tenant",None,cohort="technical_all",top_only=True,offset=0,limit=25)["status"]=="disabled"


def test_read_ranking_requires_exact_current_population_and_snapshot(monkeypatch):
    from datetime import datetime, timezone, timedelta
    from hashlib import sha256
    from types import SimpleNamespace
    from contextlib import nullcontext
    from tapi_gate0 import corpus_ranking_read as module, corpus_inventory
    from tapi_gate0.domain import MediaType, MetricsCreate
    now=datetime(2026,11,17,tzinfo=timezone.utc)
    caption="Comente sua dúvida sobre vendas."
    post=SimpleNamespace(content_id="p",caption=caption,media_type=MediaType.REELS,published_at=now-timedelta(days=30))
    source=SimpleNamespace(expected_ig_id="12345",username="source",sampling_stratum="entrepreneurship_education")
    metric=MetricsCreate(snapshot_id="s",tenant_id="tenant",content_id="p",observed_at=now,
        followers_measured_at=now,likes=2,comments=1,follower_count=100)
    entry={"source_account_id":"12345","caption_sha256":sha256(caption.encode()).hexdigest(),
           "snapshot_id":"s","snapshot_payload_sha256":sha256(metric.model_dump_json().encode()).hexdigest(),
           "audience_tier":"semantic_consensus_only","fields":{k:{"value":None} for k in FIELDS}}
    replay=SimpleNamespace(config=SimpleNamespace(tenant="tenant",viewer="56789",topic_cta=SimpleNamespace(digest="c"*64),proof_offer=SimpleNamespace(digest="d"*64)),frame=object(),
        _entries={"p":entry},_provenance={"manifest_sha256":"a"*64,"audience_report_sha256":"b"*64})
    engine=SimpleNamespace(connect=lambda:nullcontext(None))
    checked=[]
    monkeypatch.setattr(module,"require_scoped_research",lambda *a:checked.append("scope"))
    monkeypatch.setattr(corpus_inventory,"_base",lambda *a:([({"source_account_id":"12345"},post,None)],0))
    monkeypatch.setattr(corpus_inventory,"_snapshots",lambda *a:{"p":[metric]})
    def readiness(*args,_record_observer):
        _record_observer(source,post,metric)
        return {"as_of":now.isoformat(),"first_blocking_stage":{"CAPTION_AVAILABLE_FOR_ASSESSMENT":1}}
    monkeypatch.setattr(module,"readiness_report",readiness)
    kwargs={"cohort":"technical_all","top_only":True,"offset":0,"limit":25}
    result=read_ranking(engine,"tenant",replay,**kwargs)
    assert checked==["scope","scope"] and result["population_reaudited"]==1
    assert result["full_population_rechecked"] and result["items"][0]["er_percent"]==3
    assert caption not in str(result)
    monkeypatch.setattr(corpus_inventory,"_snapshots",lambda *a:{"p":[metric.model_copy(update={"likes":999})]})
    with pytest.raises(ConnectorError,match="STALE_REPLAY"):
        read_ranking(engine,"tenant",replay,**kwargs)
    monkeypatch.setattr(corpus_inventory,"_snapshots",lambda *a:{"p":[metric]})
    monkeypatch.setattr(module,"readiness_report",lambda *a,**kw:{"as_of":now.isoformat(),"first_blocking_stage":{"CAPTION_AVAILABLE_FOR_ASSESSMENT":0}})
    with pytest.raises(ConnectorError,match="STALE_REPLAY"):
        read_ranking(engine,"tenant",replay,**kwargs)
    assert read_ranking(engine,"other",replay,**kwargs)["status"]=="disabled"
