"""Synthetic-only IMP-071 FTS baseline contracts; never project gold."""
import pytest

from tapi_gate0.discovery_retrieval_fts import (
    RetrievalBaselineError, TransientScopedFts,
    evaluate_complete_gold, p95_ms,
)

PIN = "a" * 64


def rows():
    return [
        {"content_id": "a", "snapshot_id": "s-a",
         "caption": "Gestão financeira para pequenos negócios."},
        {"content_id": "b", "snapshot_id": "s-b",
         "caption": "Preços e margem de lucro nas lojas."},
        {"content_id": "c", "snapshot_id": "s-c",
         "caption": "Gestao de pagamentos para negócios."},
    ]


def test_fts_accent_insensitive_and_private():
    with TransientScopedFts(rows(), manifest_sha256=PIN) as index:
        assert index.count == 3
        result = index.search("GESTAO negocios", limit=5)
        assert set(result["content_ids"]) == {"a", "c"}
        assert set(zip(result["content_ids"], result["snapshot_ids"])) == {("a", "s-a"), ("c", "s-c")}
        assert result["gold_metrics"] is None
        assert result["scientifically_validated"] is False
        assert result["manifest_sha256"] == PIN
        assert "caption" not in str(result)
        assert "Gestão financeira" not in str(result)
    with pytest.raises(RetrievalBaselineError, match="INDEX_CLOSED"):
        index.search("gestão")


def test_injection_is_not_an_fts_expression_and_no_raw_text():
    with TransientScopedFts(rows(), manifest_sha256=PIN) as index:
        # User input may contain FTS control syntax; it is reduced to
        # AND-combined literal terms, never executed as query grammar.
        query = 'gestão" OR *'
        result = index.search(query)
        assert result["content_ids"] == []
        assert "gestão" not in str(result)
        with pytest.raises(RetrievalBaselineError, match="QUERY_TOKENS"):
            index.search("!!!")
        with pytest.raises(RetrievalBaselineError, match="QUERY_LENGTH"):
            index.search("x" * 301)
        with pytest.raises(RetrievalBaselineError, match="LIMIT_INVALID"):
            index.search("negócios", limit=0)


def test_reject_missing_manifest_pin_and_duplicate_documents():
    with pytest.raises(RetrievalBaselineError, match="MANIFEST_PIN"):
        TransientScopedFts(rows(), manifest_sha256="broken")
    with pytest.raises(RetrievalBaselineError, match="DUPLICATE_CONTENT"):
        TransientScopedFts(rows() + [rows()[0]], manifest_sha256=PIN)
    with pytest.raises(RetrievalBaselineError, match="ROW_INVALID"):
        TransientScopedFts([{"content_id": "x", "snapshot_id": "s",
                             "caption": "   "}], manifest_sha256=PIN)


def test_gold_metrics_require_explicit_complete_judgments():
    ranked = ["irrelevant", "strong", "weak"]
    gold = {"irrelevant": 0, "strong": 3, "weak": 1}
    with pytest.raises(RetrievalBaselineError, match="GOLD_INCOMPLETE"):
        evaluate_complete_gold(ranked, gold, k=2)
    result = evaluate_complete_gold(
        ranked, gold, k=2, judgments_complete=True
    )
    assert result["recall_at_k"] == 0.5
    assert 0 < result["ndcg_at_k"] < 1
    assert result["independently_validated"] is False
    with pytest.raises(RetrievalBaselineError, match="GOLD_INVALID"):
        evaluate_complete_gold(ranked, {"irrelevant": 0}, k=2,
                               judgments_complete=True)
    with pytest.raises(RetrievalBaselineError, match="DUPLICATE_RANKING"):
        evaluate_complete_gold(["strong", "strong"], gold, k=2,
                               judgments_complete=True)


def test_p95_nearest_rank_and_empty_rejection():
    assert p95_ms([1, 2, 3, 4, 5]) == 5
    assert p95_ms([1] * 95 + [10] * 5) == 1
    with pytest.raises(RetrievalBaselineError, match="LATENCY_INVALID"):
        p95_ms([])
