import pytest
from decimal import Decimal
from tapi_gate0.baselines import Metric, engagement, top_decile_candidate

def test_engagement_official_formula_synthetic():
    assert engagement(Metric('fixture', 20, 5, 100)) == Decimal('0.25')

def test_zero_followers_rejected():
    with pytest.raises(ValueError): engagement(Metric('fixture', 10, 1, 0))

def test_negative_metrics_rejected():
    with pytest.raises(ValueError): engagement(Metric('fixture', -1, 1, 10))

def test_tie_break_candidate_explicit():
    values=[Metric(f'p-{i:02}', 10, 0, 100) for i in range(20)]
    assert [x[0] for x in top_decile_candidate(values)] == ['p-00','p-01']

def test_duplicate_post_id_rejected():
    with pytest.raises(ValueError): top_decile_candidate([Metric('same',1,2,10),Metric('same',3,4,20)])
