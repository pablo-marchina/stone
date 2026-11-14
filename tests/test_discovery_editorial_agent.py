from fractions import Fraction
import pytest
from tapi_gate0.discovery_editorial_agent import build_agent_preview, cluster_contrast


def row(i, name, likes, topic, tier="semantic_consensus_only"):
    return {"content_id":f"p.{name}.{i}","username":name,"likes":likes,"comments":0,
            "followers":100,"tier":tier,"format":"reels","topic":topic,"cta":None,
            "age_band":"30-89","sector":"services","snapshot_id":f"s.{name}.{i}",
            "caption_sha256":"a"*64}


def dataset():
    return [row(i,name,i,"vendas" if i>=18 else "gestão")
            for name in ("a","b","c","d","e") for i in range(20)]


def test_cluster_contrast_is_equal_weighted_and_deterministic():
    rows=dataset()
    top={r["content_id"] for r in rows if r["topic"]=="vendas"}
    a=cluster_contrast(rows,top,"topic","vendas")
    assert a==cluster_contrast(rows,top,"topic","vendas")
    assert a["matched_profiles"]==5
    assert a["mean_difference_pp"]==100
    assert a["resampling_interval_pp"]==[100,100]
    assert not a["population_inference"]


def test_agent_outputs_real_references_and_five_drafts():
    rows=dataset()
    r=build_agent_preview(rows,tenant="tenant-a",as_of="2026-11-14T03:00:00+00:00",manifest_sha256="b"*64)
    assert r["action"]=="inspect_or_test_hypotheses"
    assert len(r["findings"])==1
    assert r["findings"][0]["value"]=="vendas"
    assert len(r["creatives"])==5
    refs={x["content_id"] for x in r["reference_posts"]}
    assert len(refs)==5 and refs.issubset({x["content_id"] for x in rows})
    for draft in r["creatives"]:
        assert set(draft["creative_spec"]["reference_content_ids"])==refs
        assert draft["status"]=="draft_hypothesis_not_approved"
        assert draft["format_and_cta_are_design_choices"]
    assert r["scientific_admissions"]==0 and not r["publication_approved"]


def test_no_semantic_evidence_abstains():
    rows=[{**r,"tier":"unresolved"} for r in dataset()]
    r=build_agent_preview(rows,tenant="tenant-a",as_of="2026-11-14T03:00:00+00:00",manifest_sha256="b"*64)
    assert r["action"]=="collect_more_evidence"
    assert not r["findings"] and not r["creatives"] and not r["reference_posts"]


def test_small_matched_clusters_no_interval():
    r=cluster_contrast([row(1,"a",1,"vendas"),row(2,"a",0,"gestão")],
                       {"p.a.1"},"topic","vendas")
    assert r["matched_profiles"]==1 and r["replicates"]==0
    assert r["resampling_interval_pp"] is None
