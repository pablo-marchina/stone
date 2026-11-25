import pytest
from tapi_gate0.discovery_audience_exploratory import evidence_tier, summarize, report_rows
from tapi_gate0.discovery_audience_grounded import grounded_candidate
from tapi_gate0.discovery_audience_signals import assess_caption
from tapi_gate0.discovery_audience_benchmark import POS, NEG, UNC


def row(text, pt, en, v1=UNC):
    lexical = assess_caption(text)
    consensus = pt if pt == en else UNC
    g = grounded_candidate(text, consensus)
    return {"caption_sha256": lexical["caption_sha256"], "lexical_status": lexical["signal_status"],
            "grounding": g, "status":g["status"], "v1_status":v1,
            "semantic_predictions":{"descriptive_pt":pt,"descriptive_en":en,"semantic_consensus":consensus},
            "human_review":False,"scientific_admission":False,"targeting_decision":"not_assessed"}


def test_tiers_and_tampering():
    text = "MEI, aprenda a calcular sua margem."
    assert evidence_tier(text, row(text, POS, POS)) == "grounded_positive"
    text = "Nossa equipe celebra mais uma conquista."
    r = row(text, POS, POS)
    assert evidence_tier(text,r) == "semantic_consensus_only"
    assert evidence_tier(text,row(text, POS, NEG)) == "single_model_or_lexical_signal"
    assert evidence_tier(text,row(text, NEG, NEG)) == "unresolved"
    with pytest.raises(ValueError, match="EVIDENCE_MISMATCH"):
        evidence_tier(text+"!",r)


def test_exact_ranking_and_cohort_partition():
    rows = [{"content_id":str(i),"username":"a" if i<10 else "b",
             "likes":i,"comments":0,"followers":100,
             "tier":"grounded_positive" if i==19 else "unresolved"} for i in range(20)]
    result = summarize(rows)
    assert result["cohorts"]["technical_all"]["top_decile_count"] == 2
    assert result["top_ids_private"]["technical_all"] == ["19","18"]
    assert result["cohorts"]["technical_all"]["median_er_percent"] == 9.5
    assert result["tier_counts"]["unresolved"] == 19
    assert result["scientific_admissions"] == 0
    with pytest.raises(ValueError, match="DUPLICATE"):
        summarize(rows+[rows[0]])


def test_report_rejects_wrong_manifest():
    with pytest.raises(ValueError, match="SCOPE_MISMATCH"):
        report_rows({"status":"GROUNDED_CONTEXTUAL_CANDIDATES",
                     "grounding_policy":"bd-audience-grounded.v1",
                     "manifest_sha256":"a"},"b")
