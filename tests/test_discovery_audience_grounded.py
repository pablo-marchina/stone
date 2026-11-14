import json
from hashlib import sha256
import pytest
from tapi_gate0.discovery_audience_grounded import (
    CASES, CHECK_CASES, POS, NEG, UNC, grounded_rule, grounded_candidate, run_grounded_challenge,
)


@pytest.mark.parametrize('cid,expected,text', CASES + CHECK_CASES)
def test_grounding_never_positive_for_negative_or_uncertain_fixture(cid, expected, text):
    result = grounded_rule(text)
    if expected != POS:
        assert result['rule_status'] != POS, cid
    for span in result['evidence_spans']:
        assert 0 <= span['start'] < span['end'] <= len(text)
        assert sha256(text[span['start']:span['end']].encode()).hexdigest() == span['sha256']
    assert text not in json.dumps(result, ensure_ascii=False)


def test_hybrid_requires_agreement_and_spans():
    text = 'MEI, aprenda a calcular sua margem.'
    assert grounded_candidate(text, POS)['status'] == POS
    assert grounded_candidate(text, NEG)['status'] == UNC
    assert grounded_candidate('O relatório para MEIs foi publicado.', POS)['status'] == UNC
    assert grounded_candidate('Não é para MEIs: curso exclusivo.', POS)['status'] == UNC
    assert grounded_candidate('Não é para MEIs: curso exclusivo.', NEG)['status'] == NEG


class Fake:
    def classify_text(self, text, heads):
        return {k: v[0] for k,v in heads.items()}


def test_challenge_counts_and_gate():
    report = run_grounded_challenge(Fake(), lambda cid, text: UNC)
    assert report['synthetic_cases'] == 48
    assert report['splits']['development']['cases'] == 30
    assert report['splits']['additional_synthetic']['cases'] == 18
    assert report['splits']['development']['metrics']['grounded_hybrid']['positive_on_uncertain'] == 0
    assert report['splits']['additional_synthetic']['metrics']['grounded_hybrid']['positive_on_negative'] == 0
    assert not report['scientifically_validated']
    assert all(text not in json.dumps(report, ensure_ascii=False) for _,_,text in CASES + CHECK_CASES)
