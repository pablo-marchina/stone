import json
import pytest
from tapi_gate0.discovery_audience_benchmark import (
    CASES, HEADS, POS, NEG, UNC, VARIANTS, run_challenge, score, semantic_candidates,
)


class Fake:
    def __init__(self, indexes):
        self.indexes = iter(indexes)

    def classify_text(self, text, heads):
        head, labels = next(iter(heads.items()))
        i = next(self.indexes)
        return {head: labels[i]} if i is not None else {head: "not a label"}


@pytest.mark.parametrize("indices,expected", [([0, 0], POS), ([1, 1], NEG), ([0, 1], UNC), ([0, None], UNC)])
def test_consensus(indices, expected):
    assert semantic_candidates(Fake(indices), "fixture")["semantic_consensus"] == expected


def test_challenge_reports_false_positives_and_never_exports_text():
    report = run_challenge(Fake([0, 0]*len(CASES)), lambda cid, text: UNC)
    assert report["synthetic_cases"] == 30
    assert report["expected_counts"] == {POS: 10, NEG: 8, UNC: 12}
    assert set(report["metrics"]) == set(VARIANTS)
    assert report["metrics"]["semantic_consensus"]["positive_on_negative"] == 8
    assert report["metrics"]["semantic_consensus"]["positive_on_uncertain"] == 12
    assert report["metrics"]["v1"]["exact_matches"] == 12
    assert not report["automatic_variant_selected"] and not report["independent_gold"]
    assert all(text not in json.dumps(report, ensure_ascii=False) for _, _, text in CASES)
    with pytest.raises(ValueError, match="PARTITION_MISMATCH"):
        score(report["cases"][:-1])
    report["cases"][0]["expected"] = NEG
    with pytest.raises(ValueError, match="LABEL_MISMATCH"):
        score(report["cases"])
