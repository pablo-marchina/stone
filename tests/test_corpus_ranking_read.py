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
