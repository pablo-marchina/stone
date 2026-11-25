from types import SimpleNamespace as NS
import pytest
from tapi_gate0.discovery_audience_contextual import compare_candidate, paired_counts, CANDIDATES


def fixture(value=True, abstained=False):
    evidence = NS(fingerprint=lambda: "hash", observation=NS(locator="local-caption:fixture", sha256="hash"))
    decision = NS(field_id="mpe_targeted", value=value, abstained=abstained,
                  modality="caption", locator="local-caption:fixture")
    answer = NS(evidence_fingerprint="hash", is_scientific_review=False, decisions=[decision],
                model_id="fixture", model_version="v1", duration_ms=1)
    lexical = {"signal_status":"NO_EXPLICIT_SIGNAL_ABSTAIN", "caption_sha256":"hash"}
    return evidence, answer, lexical


@pytest.mark.parametrize("value,abstained,expected", [(True,False,CANDIDATES[0]),
    (False,False,CANDIDATES[1]),(None,True,CANDIDATES[2])])
def test_candidate(value, abstained, expected):
    result = compare_candidate(*fixture(value, abstained))
    assert result["status"] == expected
    assert result["scientific_admission"] is False and result["human_review"] is False
    assert result["targeting_decision"] == "not_assessed"


@pytest.mark.parametrize("change", ["fingerprint", "review", "field", "locator", "modality", "value", "caption_hash"])
def test_mismatch(change):
    e,a,l = fixture()
    if change == "fingerprint": a.evidence_fingerprint = "bad"
    elif change == "review": a.is_scientific_review = True
    elif change == "field": a.decisions[0].field_id = "tema_principal"
    elif change == "locator": a.decisions[0].locator = "bad"
    elif change == "modality": a.decisions[0].modality = "transcript"
    elif change == "value": a.decisions[0].value = "sim"
    else: l["caption_sha256"] = "bad"
    with pytest.raises(ValueError): compare_candidate(e,a,l)


def test_counts():
    r = compare_candidate(*fixture())
    matrix = paired_counts([r,r])
    assert sum(sum(x.values()) for x in matrix.values()) == 2
    assert matrix["NO_EXPLICIT_SIGNAL_ABSTAIN"][CANDIDATES[0]] == 2
    with pytest.raises(ValueError): paired_counts([dict(r,status="unknown")])
