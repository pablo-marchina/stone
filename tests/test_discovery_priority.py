from tapi_gate0.discovery_priority import HistoryCandidate as C, compare_history_selection
import pytest


def compare(rows, capacity=3):
    strata = {}
    for c in rows:
        sources, posts = strata.get(c.stratum, (0, 0))
        strata[c.stratum] = (sources + int(c.technical_posts > 0), posts + c.technical_posts)
    return compare_history_selection(rows, strata, capacity)


def sample():
    return [C("a", "finance", "01", 100), C("b", "finance", "02", 90),
            C("c", "finance", "03", 80), C("d", "food", "04", 0),
            C("e", "services", "05", 5)]


def test_coverage_improves_diversity_in_paired_fixture():
    r = compare(sample())
    assert r["recency_baseline"]["selected_sources"] == ["a", "b", "c"]
    assert r["coverage_policy"]["selected_sources"] == ["a", "d", "e"]
    assert r["recency_baseline"]["distinct_strata"] == 1
    assert r["coverage_policy"]["distinct_strata"] == 3
    assert r["coverage_policy"]["sources_without_observations"] == 1
    assert r["scientific_admissions"] == 0 and r["predicted_yield"] is None


def test_replay_and_manifest_order_independent():
    rows = sample()
    assert compare(rows) == compare(list(reversed(rows)))


@pytest.mark.parametrize("capacity", [0, 1, 2, 20])
def test_budget_and_fairness(capacity):
    r = compare(sample(), capacity)
    a = r["coverage_policy"]["selected_sources"]
    assert len(a) == min(capacity, len(sample())) == len(set(a))
    if capacity:
        assert a[0] == r["recency_baseline"]["selected_sources"][0]


def test_empty():
    assert compare([], 3)["coverage_policy"]["selected_sources"] == []


def test_stratum_coverage_includes_non_due_inventory():
    rows = [C("a", "base", "01", 2), C("b", "food", "02", 0), C("c", "services", "03", 0)]
    r = compare_history_selection(rows, {"base": (1, 2), "food": (4, 200), "services": (0, 0)}, 2)
    assert r["coverage_policy"]["selected_sources"] == ["a", "c"]


@pytest.mark.parametrize("rows, strata, capacity", [
    ([C("a", "x", "", 0), C("a", "x", "", 0)], {"x": (0, 0)}, 1),
    ([C("a", "x", "", -1)], {"x": (0, 0)}, 1),
    ([C("a", "x", "", 1)], {}, 1),
    ([], {}, -1),
])
def test_invalid_inputs(rows, strata, capacity):
    with pytest.raises(ValueError):
        compare_history_selection(rows, strata, capacity)
