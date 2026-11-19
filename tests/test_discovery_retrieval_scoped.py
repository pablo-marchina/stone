"""Synthetic contracts for IMP-071 scope-gated FTS preview, no live DB."""
from types import SimpleNamespace as NS
import pytest

from tapi_gate0 import discovery_retrieval_scoped as scoped
from tapi_gate0.discovery_retrieval_fts import RetrievalBaselineError

PIN = "b" * 64


def frame():
    return NS(sources=[NS(username="fixture")], fingerprint=lambda: PIN)


def fake_rows(monkeypatch, *, drift=False, invalid_source=False, bad_trace=False):
    runs = {"ready": 0, "scopes": 0}

    def gate(_engine, _tenant, _frame, _viewer):
        runs["scopes"] += 1
        return "dec018-bd-caption-research.v1"

    def readiness(_engine, _tenant, _frame, _viewer, *, _record_observer):
        runs["ready"] += 1
        captions = [
            ("a", "s-a", "Gestão de pagamentos"),
            ("b", "s-b", "Vendas em pequenos negócios"),
            ("c", "s-c" if not drift or runs["ready"] == 1 else "s-new",
             "Gestão comercial e vendas"),
        ]
        for cid, sid, caption in captions:
            _record_observer(
                NS(username="fixture"),
                NS(content_id=cid, caption=caption),
                NS(snapshot_id=sid),
            )
        return {
            "status": "CORPUS_READINESS_PLANNED",
            "manifest_sha256": PIN,
            "first_blocking_stage": {"CAPTION_AVAILABLE_FOR_ASSESSMENT": 3},
            "completed_runs_without_valid_bd_trace": 1 if bad_trace else 0,
            "new_scientific_admissions": 0,
            "database_mutated": False,
            "external_data_accessed": False,
            "sources": [{"source_gate":
                         "MANIFEST_SOURCE_EXPIRED" if invalid_source
                         else "TECHNICAL_SCOPE_MATCHED"}],
        }

    monkeypatch.setattr(scoped, "require_scoped_research", gate)
    monkeypatch.setattr(scoped, "readiness_report", readiness)
    return runs


def call():
    return scoped.preview_scoped_fts(
        object(), "tenant", frame(), "viewer",
        queries=["gestao", "vendas"], expected_posts=3,
        expected_sources=1, limit=3,
    )


def test_realistic_ephemeral_preview_gates_twice_without_captions(monkeypatch):
    runs = fake_rows(monkeypatch)
    result = call()
    assert runs == {"ready": 2, "scopes": 3}
    assert result["eligible_posts"] == 3
    assert result["eligible_sources"] == 1
    assert result["manifest_sha256"] == PIN
    assert result["partition_sha256"]
    assert result["status"] == "SCOPED_FTS_LOCAL_PREVIEW_COMPLETED"
    assert result["query_count"] == 2
    assert all(hit["gold_metrics"] is None for hit in result["queries"])
    assert result["p95_search_latency_ms"] >= 0
    assert result["latency_excludes_readiness_and_index_build"]
    assert result["recall_at_k"] is None and result["ndcg_at_k"] is None
    assert not result["scientifically_validated"]
    assert not result["database_mutated"]
    assert not result["external_data_accessed"]
    assert "Gestão de pagamentos" not in str(result)


def test_denied_first_scope_prevents_eligibility_read(monkeypatch):
    runs = fake_rows(monkeypatch)
    def deny(*_):
        runs["scopes"] += 1
        raise RetrievalBaselineError("RETRIEVAL_SCOPE_DENIED")
    monkeypatch.setattr(scoped, "require_scoped_research", deny)
    with pytest.raises(RetrievalBaselineError, match="SCOPE_DENIED"):
        call()
    assert runs == {"ready": 0, "scopes": 1}


def test_denied_second_scope_does_not_return_hits(monkeypatch):
    runs = fake_rows(monkeypatch)
    def gate(*_):
        runs["scopes"] += 1
        if runs["scopes"] == 2:
            raise RetrievalBaselineError("RETRIEVAL_SCOPE_REVOKED")
    monkeypatch.setattr(scoped, "require_scoped_research", gate)
    with pytest.raises(RetrievalBaselineError, match="SCOPE_REVOKED"):
        call()
    assert runs == {"ready": 1, "scopes": 2}


def test_snapshot_drift_is_fail_closed(monkeypatch):
    runs = fake_rows(monkeypatch, drift=True)
    with pytest.raises(RetrievalBaselineError, match="PARTITION_DRIFT"):
        call()
    assert runs == {"ready": 2, "scopes": 3}


@pytest.mark.parametrize("fault", ["invalid_source", "bad_trace"])
def test_expired_source_or_missing_trace_rejects_data(monkeypatch, fault):
    runs = fake_rows(monkeypatch, **{fault: True})
    with pytest.raises(RetrievalBaselineError,
                       match="SCOPE_OR_POPULATION_MISMATCH"):
        call()
    assert runs == {"ready": 1, "scopes": 1}


def test_requires_expected_population_and_bounded_queries(monkeypatch):
    runs = fake_rows(monkeypatch)
    with pytest.raises(RetrievalBaselineError, match="SCOPE_EXPECTATION_INVALID"):
        scoped.preview_scoped_fts(
            object(), "tenant", frame(), "viewer",
            queries=["vendas"], expected_posts=0, expected_sources=1,
        )
    with pytest.raises(RetrievalBaselineError, match="QUERY_BATCH_INVALID"):
        scoped.preview_scoped_fts(
            object(), "tenant", frame(), "viewer",
            queries=[], expected_posts=3, expected_sources=1,
        )
    assert runs == {"ready": 0, "scopes": 0}
