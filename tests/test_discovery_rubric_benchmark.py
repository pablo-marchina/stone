import pytest
from tapi_gate0.discovery_rubric_benchmark import CASES, FIELDS, UNKNOWN, candidate, run_rubric_challenge, score


class Abstain:
    def classify_text(self,text,heads):
        return {key:values[-1] for key,values in heads.items()}


class Malformed:
    def classify_text(self,text,heads):
        return {key:["bad"] for key in heads}


def test_synthetic_challenge_abstention_not_accuracy_or_recall():
    result=run_rubric_challenge(Abstain())
    assert result["synthetic_cases"]==len(CASES)==36
    assert set(result["fields"])==set(FIELDS)
    assert not result["real_caption_inference_allowed"] and not result["independent_gold"]
    assert result["rubric_assessments_written"]==0
    for group in result["fields"].values():
        m=group["variants"]["consensus"]
        assert m["candidates"]==0 and m["candidate_precision"] is None
        assert m["candidate_recall"]==0 and m["exact_matches"]==group["expected_unknown"]
    assert all("caption_sha256" in r and "caption" not in r for r in result["cases"])


def test_malformed_abstains_and_partition_rejected():
    assert candidate(Malformed(),"tipo_cta","teste","pt")==UNKNOWN
    rows=run_rubric_challenge(Abstain())["cases"]
    with pytest.raises(ValueError,match="PARTITION"):
        score(rows[:-1])
    rows[0]["predictions"]["consensus"]="vendas"
    with pytest.raises(ValueError,match="CONSENSUS"):
        score(rows)


def test_perfect_fixture_predictions():
    rows=[{"case_id":cid,"field":field,"expected":label,
           "predictions":dict.fromkeys(("pt","en","consensus"),label)}
          for cid,field,label,_ in CASES]
    for group in score(rows).values():
        m=group["variants"]["consensus"]
        assert m["exact_matches"]==group["cases"]
        assert m["candidate_precision"]==m["candidate_recall"]==1
        assert m["candidates_on_unknown"]==0
