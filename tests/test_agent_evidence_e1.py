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


def test_secure_agent_api_uses_authenticated_tenant_and_abstains(tmp_path):
    from fastapi.testclient import TestClient
    from tapi_gate0.secure_api import create_secure_app

    app = create_secure_app(
        f"sqlite:///{tmp_path/'agent.sqlite'}",
        initialize_schema=True, allow_http_local=True,
    )
    password = "safe-demo-password-for-local-test-42"
    app.state.identity_store.bootstrap("tenantA", "Demo", "founder", password)
    with TestClient(app) as client:
        params = {
            "origin": "synthetic_local",
            "as_of": AS_OF.isoformat(),
            "min_age_days": 14,
        }
        assert client.post("/v1/agent/analyze-ranking", json=params).status_code == 401
        login = client.post("/v1/auth/sessions", json={
            "username":"founder", "password":password, "tenant_id":"tenantA",
        })
        assert login.status_code == 200
        hdr = {"Authorization":"Bearer " + login.json()["access_token"]}
        response = client.post("/v1/agent/analyze-ranking", headers=hdr, json=params)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["tenant_id"] == "tenantA"
        assert result["n_eligible_posts"] == 0
        assert result["action"] == "collect_more_evidence"
        assert result["findings"][0]["citations"] == []
        assert result["abstained_from_pattern_claim"] is True
        assert client.post("/v1/agent/analyze-ranking", headers=hdr,
                           json={**params,"tenant_id":"another"}).status_code == 422


def test_secure_agent_reads_real_database_snapshot_without_client_citations(tmp_path):
    from fastapi.testclient import TestClient
    from tapi_gate0.secure_api import create_secure_app

    app = create_secure_app(
        f"sqlite:///{tmp_path/'agent_with_records.sqlite'}",
        initialize_schema=True, allow_http_local=True,
    )
    password = "safe-demo-password-for-local-test-42"
    app.state.identity_store.bootstrap("tenantA", "Demo", "founder", password)
    with TestClient(app) as client:
        login = client.post("/v1/auth/sessions", json={
            "username":"founder", "password":password, "tenant_id":"tenantA",
        })
        hdr = {"Authorization":"Bearer " + login.json()["access_token"]}
        creator = client.post("/v1/creators", headers=hdr, json={
            "creator_id":"creator1", "tenant_id":"tenantA",
            "origin":"synthetic_local", "handle":"fictional_creator",
        })
        assert creator.status_code == 201, creator.text
        content = client.post("/v1/content", headers=hdr, json={
            "content_id":"post1", "tenant_id":"tenantA", "creator_id":"creator1",
            "origin":"synthetic_local", "media_type":"reels",
            "published_at":"2026-10-01T12:00:00+00:00",
            "is_synthetic":True,
        })
        assert content.status_code == 201, content.text
        metrics = client.post("/v1/content/post1/metrics", headers=hdr, json={
            "snapshot_id":"snapshot1", "tenant_id":"tenantA", "content_id":"post1",
            "observed_at":"2026-11-01T12:00:00+00:00",
            "followers_measured_at":"2026-11-01T12:00:00+00:00",
            "likes":20, "comments":5, "follower_count":1000,
        })
        assert metrics.status_code == 201, metrics.text
        response = client.post("/v1/agent/analyze-ranking", headers=hdr, json={
            "origin":"synthetic_local", "as_of":AS_OF.isoformat(),
        })
        assert response.status_code == 200, response.text
        output = response.json()
        assert output["n_eligible_posts"] == 1
        refs = output["findings"][0]["citations"]
        assert len(refs) == 1
        assert refs[0]["content_id"] == "post1"
        assert refs[0]["snapshot_id"] == "snapshot1"
        assert refs[0]["engagement_rate"] == "0.025"
        assert output["abstained_from_pattern_claim"] is True
