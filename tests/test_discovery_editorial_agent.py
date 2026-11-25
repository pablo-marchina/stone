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


def test_finding_exposes_coverage_and_noncausal_limits():
    r = build_agent_preview(dataset(), tenant="tenant-a",
                            as_of="2026-11-14T03:00:00+00:00",
                            manifest_sha256="b"*64)
    limits = r["findings"][0]["evidence_limits"]
    assert not limits["four_views_are_independent_replications"]
    assert not limits["scientific_or_causal_claim_supported"]
    assert not limits["editorial_recommendation_approved"]
    assert limits["observables_provenance"] == "caption_lexical_not_grounded_rubric"
    assert len(limits["coverage"]) == 4
    assert all(v["top_coverage_fraction"] == 1
               and v["rest_coverage_fraction"] == 1
               for v in limits["coverage"].values())
    assert all(v["interval_includes_zero"] is False
               and not v["interval_is_population_confidence_interval"]
               for v in limits["sensitivity"].values())


def test_finding_limits_do_not_hide_sparse_coverage_or_zero_crossing():
    from tapi_gate0.discovery_editorial_agent import (
        COHORTS, SCOPES, describe_finding_limits,
    )
    views = {(c, s): {"top_total": 100, "top_observed": 5,
                      "rest_total": 900, "rest_observed": 20}
             for c in COHORTS for s in SCOPES}
    sensitivity = {
        "technical_all": {"matched_profiles": 14,
                          "resampling_interval_pp": [-0.8, 41.2]},
        "semantic_exploratory": {"matched_profiles": 7,
                                "resampling_interval_pp": [-9.4, 59.8]},
    }
    limits = describe_finding_limits(views, sensitivity)
    assert all(x["top_coverage_fraction"] == 0.05
               and x["rest_coverage_fraction"] == round(20/900, 6)
               and x["unknown_is_not_negative"]
               for x in limits["coverage"].values())
    assert all(x["interval_includes_zero"] is True
               for x in limits["sensitivity"].values())
    assert not limits["editorial_recommendation_approved"]

    with pytest.raises(ValueError, match="PARTITION_MISMATCH"):
        describe_finding_limits({}, sensitivity)
    invalid = {**views}
    invalid[("technical_all", "observables_global")] = {
        **views[("technical_all", "observables_global")],
        "top_observed": 101,
    }
    with pytest.raises(ValueError, match="COVERAGE_INVALID"):
        describe_finding_limits(invalid, sensitivity)
