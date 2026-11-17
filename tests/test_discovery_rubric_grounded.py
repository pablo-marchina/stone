import pytest
from hashlib import sha256
from tapi_gate0.discovery_rubric_benchmark import CASES, FIELDS, UNKNOWN
from tapi_gate0.discovery_rubric_grounded import (
    CHECK_CASES, grounded_field, rule_evidence, run_grounded_rubric_challenge,
)


class Abstain:
    def classify_text(self, text, heads):
        return {key: values[-1] for key, values in heads.items()}


class First:
    def classify_text(self, text, heads):
        return {key: values[0] for key, values in heads.items()}


@pytest.mark.parametrize("case", CASES + CHECK_CASES)
def test_rule_never_overclaims_authored_cases(case):
    _, field, expected, text = case
    row = rule_evidence(field, text)
    assert row["rule_value"] in (expected, UNKNOWN)
    for span in row["evidence_spans"]:
        assert 0 <= span["start"] < span["end"] <= len(text)
        assert span["sha256"] == sha256(text[span["start"]:span["end"]].encode()).hexdigest()


@pytest.mark.parametrize("text", [
    "Não comente.", "Comente e siga nosso perfil.",
    'O artigo cita "Comente" como exemplo.', "O link na bio foi atualizado.",
])
def test_cta_negative_ambiguous_quoted(text):
    assert rule_evidence("tipo_cta", text)["rule_value"] == UNKNOWN


def test_consensus_alone_cannot_create_candidate():
    row = grounded_field(First(), "tipo_cta", "O link na bio foi atualizado.")
    assert row["predictions"]["consensus"] == "comentar"
    assert row["candidate_value"] == UNKNOWN
    assert not row["scientific_admission"]


def test_valid_grounded_candidate_requires_agreement():
    assert grounded_field(First(), "tipo_cta", "Comente sua dúvida.")["candidate_value"] == "comentar"
    assert grounded_field(Abstain(), "tipo_cta", "Comente sua dúvida.")["candidate_value"] == UNKNOWN


def test_all_abstain_does_not_pass_any_gate():
    result = run_grounded_rubric_challenge(Abstain())
    assert result["synthetic_cases"] == len(CASES) + len(CHECK_CASES) == 62
    assert set(result["field_engineering_gate"]) == set(FIELDS)
    assert not any(result["field_engineering_gate"].values())
    assert result["rubric_assessments_written"] == result["scientific_admissions"] == 0
    assert not result["real_caption_inference_allowed"]
    assert all("caption" not in r for r in result["cases"])


def test_invalid_fields_and_caption_fail_closed():
    for field, text in [("hook_primeiros_3s", "Comente"), ("tipo_cta", ""), ("tipo_cta", "a"*10001)]:
        with pytest.raises(ValueError, match="INPUT_INVALID"):
            rule_evidence(field, text)
