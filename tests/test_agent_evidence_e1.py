"""IMP-071/076: evidence-first ranking tool and conservative analysis."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tapi_gate0.agent_evidence_e1 import analyze_with_ranking
from tapi_gate0.domain import Origin, RankingResult, RankingRow


AS_OF = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)


def _result(rows=None, origin=Origin.SYNTHETIC, *, n_posts=None, top_count=None):
    rows = rows or []
    return RankingResult(
        origin=origin,
        n_posts=len(rows) if n_posts is None else n_posts,
        n_creators=len({r.creator_id for r in rows}),
        top_count=sum(r.is_top_decile for r in rows) if top_count is None else top_count,
        rows=rows, excluded_no_positive_denominator=0,
        excluded_too_recent=0, excluded_without_metrics=0,
    )


def _row(content_id, creator_id, top, rate):
    return RankingRow(
        content_id=content_id, creator_id=creator_id,
        likes=20, comments=5, followers=1000,
        engagement_rate=Decimal(rate), snapshot_id="snapshot_" + content_id,
        is_top_decile=top,
    )


class SpyTool:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def ranking(self, request):
        self.requests.append(request)
        return self.result


def _analyze(tool, **params):
    return analyze_with_ranking(
        tool, tenant_id="tenantA", origin=Origin.SYNTHETIC,
        as_of=AS_OF, **params,
    )


def test_agent_abstains_without_rankable_posts():
    tool = SpyTool(_result())
    output = _analyze(tool)
    assert output.action == "collect_more_evidence"
    assert output.abstained_from_pattern_claim is True
    assert output.n_eligible_posts == 0
    assert output.findings[0].citations == []
    assert tool.requests[0].tenant_id == "tenantA"
    assert tool.requests[0].min_age_days == 14


def test_agent_cites_exact_content_and_snapshot_without_inventing_link():
    rows = [_row("post1", "creator1", True, "0.025"),
            _row("post2", "creator2", False, "0.010")]
    tool = SpyTool(_result(rows))
    response = _analyze(tool, min_age_days=21)
    assert response.action == "inspect_ranked_examples"
    assert response.abstained_from_pattern_claim
    assert response.findings[0].citations[0].content_id == "post1"
    assert response.findings[0].citations[0].snapshot_id == "snapshot_post1"
    assert response.findings[0].citations[0].engagement_rate == "0.025"
    assert tool.requests[0].min_age_days == 21
    assert "causa de desempenho" in response.findings[0].statement
    assert "Amostra pequena" in " ".join(response.limitations)


def test_agent_uses_only_top_decile_as_reference():
    rows = [_row("post1", "creator1", True, "0.08"),
            _row("post2", "creator2", False, "0.02"),
            _row("post3", "creator3", False, "0.01")]
    result = _analyze(SpyTool(_result(rows)))
    assert [x.content_id for x in result.findings[0].citations] == ["post1"]


def test_agent_rejects_tool_origin_mismatch_and_inconsistent_counts():
    other = SpyTool(_result(origin=Origin.INSTAGRAM))
    with pytest.raises(ValueError, match="AGENT_TOOL_ORIGIN_MISMATCH"):
        _analyze(other)
    broken = SpyTool(_result([_row("p1", "c1", True, "0.1")], n_posts=9))
    with pytest.raises(ValueError, match="AGENT_TOOL_RANKING_INTEGRITY_FAILURE"):
        _analyze(broken)
    no_top = SpyTool(_result([_row("p1", "c1", False, "0.1")]))
    with pytest.raises(ValueError, match="AGENT_NONEMPTY_RANKING_NEEDS_TOP_DECILE"):
        _analyze(no_top)


def test_agent_rejects_duplicate_content_refs():
    rows = [_row("same", "c1", True, "0.2"),
            _row("same", "c2", False, "0.1")]
    with pytest.raises(ValueError, match="AGENT_TOOL_DUPLICATE_CONTENT"):
        _analyze(SpyTool(_result(rows)))
