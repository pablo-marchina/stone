import pytest
from tapi_gate0.discovery_editorial_descriptive import (
    analyze_editorial, analyze_cohort, caption_features, age_band, _profile_percentiles,
)


def post(i, name, likes, topic=None, tier="semantic_consensus_only"):
    return {"content_id":str(i), "username":name, "likes":likes, "comments":0,
            "followers":100, "tier":tier,"format":"reels","topic":topic,"cta":None,
            "age_band":"30-89","sector":"services"}


def test_caption_unknown_and_single_signal():
    topics={"vendas":("vender",),"gestão":("gestão",)}
    cta={"comentar":"comente","salvar":"salve"}
    assert caption_features("vender, comente",topics,cta)=={"topic":"vendas","cta":"comentar"}
    assert caption_features("vender e gestão, comente e salve",topics,cta)=={"topic":None,"cta":None}
    assert caption_features("olá",topics,cta)=={"topic":None,"cta":None}


def test_midrank_ties_exact():
    from fractions import Fraction
    rows=[post(1,"a",0),post(2,"a",10),post(3,"a",10),post(4,"a",30)]
    assert _profile_percentiles(rows)=={"1":Fraction(0),"2":Fraction(1,2),"3":Fraction(1,2),"4":Fraction(1)}


def test_profile_sensitivity_and_coverage():
    rows=[post(i,"large",100+i,"vendas") for i in range(10)]
    rows += [post(10+i,"small",i,None) for i in range(10)]
    rows += [post(20,"tiny",200,"gestão")]
    result, private=analyze_cohort(rows)
    assert result["global_top_count"]==3
    assert result["within_profile_supported_posts"]==20
    assert result["within_profile_excluded_posts"]==1
    assert result["within_profile_top_count"]==2
    assert result["top_overlap_count"]==1
    assert result["top_jaccard"]==pytest.approx(1/3,abs=1e-6)
    assert private["within_profile_top"]==["19","9"]
    assert result["observables_within_profile"]["topic"]["top"]["unknown"]==1
    assert len(result["leave_one_profile_out"])==3


def test_empty_cohort_and_separation():
    r=analyze_editorial([post(1,"a",2,tier="unresolved")])
    assert r["cohorts"]["semantic_exploratory"]["status"]=="EMPTY_COHORT"
    assert r["cohorts"]["technical_all"]["posts"]==1
    assert not r["editorial_recommendations_generated"]
    assert r["scientific_admissions"]==0


def test_age_and_invalid_metrics():
    assert [age_band(x) for x in (14,30,90,365)]==["14-29","30-89","90-364","365+"]
    with pytest.raises(ValueError,match="IMMATURE"):
        age_band(13)
    with pytest.raises(ValueError,match="DUPLICATE"):
        analyze_cohort([post(1,"a",1),post(1,"b",2)])
    with pytest.raises(ValueError,match="INVALID_METRIC"):
        analyze_cohort([{**post(1,"a",1),"followers":0}])
