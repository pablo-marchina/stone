"""CAP-001: replayable, offline history selection; never a scientific score."""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter

POLICY_VERSION = "bd-history-coverage.v1"


@dataclass(frozen=True)
class HistoryCandidate:
    username: str
    stratum: str
    last_checkpoint: str
    technical_posts: int


def compare_history_selection(candidates: list[HistoryCandidate],
                              stratum_coverage: dict[str, tuple[int, int]],
                              capacity: int) -> dict:
    """Compare identical eligible candidates/budget; coverage tuples are (sources, posts).

    One slot preserves oldest-first fairness. Remaining slots favor distinct strata
    in this cycle, then sources with no observations, then undercovered strata and
    sources. Counts describe technical inventory, not relevance or predicted yield.
    """
    if capacity < 0 or len({c.username for c in candidates}) != len(candidates):
        raise ValueError("BD_PRIORITY_INVALID_INPUT")
    if any(c.technical_posts < 0 or c.stratum not in stratum_coverage for c in candidates):
        raise ValueError("BD_PRIORITY_INVALID_COVERAGE")
    if any(s < 0 or p < 0 for s, p in stratum_coverage.values()):
        raise ValueError("BD_PRIORITY_INVALID_COVERAGE")
    baseline = sorted(candidates, key=lambda c: (c.last_checkpoint, c.username))
    remaining = list(baseline)
    selected = []
    slots: Counter[str] = Counter()
    decisions = []
    for i in range(min(capacity, len(remaining))):
        def key(c):
            observed_sources, posts = stratum_coverage[c.stratum]
            return (slots[c.stratum], c.technical_posts > 0, observed_sources,
                    posts, c.technical_posts, c.last_checkpoint, c.username)
        chosen = remaining[0] if i == 0 else min(remaining, key=key)
        decisions.append({"username": chosen.username,
                          "rule": "oldest_fairness_slot" if i == 0 else "coverage_lexicographic",
                          "stratum_slots_before": slots[chosen.stratum]})
        remaining.remove(chosen)
        selected.append(chosen)
        slots[chosen.stratum] += 1

    def summarize(items):
        return {"selected_sources": [c.username for c in items],
                "distinct_strata": len({c.stratum for c in items}),
                "sources_without_observations": sum(c.technical_posts == 0 for c in items),
                "existing_technical_posts_sum": sum(c.technical_posts for c in items)}

    return {"policy_version": POLICY_VERSION, "capacity": capacity,
            "coverage_kind": "technical_metadata_only_not_scientific",
            "inputs": [{"username": c.username, "stratum": c.stratum,
                        "last_checkpoint": c.last_checkpoint, "technical_posts": c.technical_posts}
                       for c in baseline],
            "stratum_coverage": {k: {"observed_sources": v[0], "technical_posts_sum": v[1]}
                                 for k, v in sorted(stratum_coverage.items())},
            "recency_baseline": summarize(baseline[:capacity]),
            "coverage_policy": summarize(selected), "decisions": decisions,
            "predicted_yield": None, "scientific_admissions": 0}
