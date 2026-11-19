"""IMP-071 / CAP-009: transient SQLite FTS5 baseline over already scoped captions.

This module accepts *only caller-provided* eligible rows; it never touches the
operational database, network, files, or persistent indexes. Callers MUST check
DEC-018 local scope and live source grants before preparing rows and again
before exposing results. Gold evaluation is unavailable without complete
explicit judgments; synthetic tests never constitute project relevance gold.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from hashlib import sha256
from math import ceil, log2
import re
import sqlite3
from time import perf_counter

POLICY_VERSION = "tapi-imp071-fts5-local.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_WORD = re.compile(r"[^\W_]+", flags=re.UNICODE)


class RetrievalBaselineError(ValueError):
    """Typed local retrieval contract failure."""


def _fts_query(query: str) -> str:
    if not isinstance(query, str) or not 1 <= len(query) <= 300:
        raise RetrievalBaselineError("RETRIEVAL_QUERY_LENGTH")
    words = _WORD.findall(query.casefold())
    if not 1 <= len(words) <= 25:
        raise RetrievalBaselineError("RETRIEVAL_QUERY_TOKENS")
    # Never pass a caller's raw FTS expression to SQLite MATCH.
    return " AND ".join('"' + word + '"' for word in words)


class TransientScopedFts:
    """Ephemeral lexical search. The caller is responsible for scope gating."""

    def __init__(self, rows: Iterable[Mapping[str, str]], *, manifest_sha256: str):
        if not isinstance(manifest_sha256, str) or not _SHA256.fullmatch(manifest_sha256):
            raise RetrievalBaselineError("RETRIEVAL_MANIFEST_PIN_REQUIRED")
        self.manifest_sha256 = manifest_sha256
        self._conn = sqlite3.connect(":memory:")
        self._closed = False
        try:
            self._conn.execute(
                "CREATE VIRTUAL TABLE docs USING fts5("
                "content_id UNINDEXED, snapshot_id UNINDEXED, caption, "
                "tokenize='unicode61 remove_diacritics 2')"
            )
            seen = set()
            for row in rows:
                cid, sid, caption = row["content_id"], row["snapshot_id"], row["caption"]
                if (not isinstance(cid, str) or not cid or len(cid) > 256
                        or not isinstance(sid, str) or not sid or len(sid) > 256
                        or not isinstance(caption, str) or not caption.strip()
                        or len(caption) > 100_000):
                    raise RetrievalBaselineError("RETRIEVAL_ROW_INVALID")
                if cid in seen:
                    raise RetrievalBaselineError("RETRIEVAL_DUPLICATE_CONTENT")
                seen.add(cid)
                self._conn.execute(
                    "INSERT INTO docs(content_id,snapshot_id,caption) VALUES(?,?,?)",
                    (cid, sid, caption)
                )
            self.count = len(seen)
        except Exception:
            self.close()
            raise

    def search(self, query: str, *, limit: int = 5) -> dict:
        if self._closed:
            raise RetrievalBaselineError("RETRIEVAL_INDEX_CLOSED")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
            raise RetrievalBaselineError("RETRIEVAL_LIMIT_INVALID")
        expression = _fts_query(query)
        start = perf_counter()
        hits = self._conn.execute(
            "SELECT content_id,snapshot_id,bm25(docs) AS rank "
            "FROM docs WHERE docs MATCH ? "
            "ORDER BY rank ASC, content_id ASC LIMIT ?",
            (expression, limit)
        ).fetchall()
        elapsed = (perf_counter() - start) * 1000
        # Never emit retrieved caption text; IDs are local evidence references.
        return {"query_sha256": sha256(query.encode("utf-8")).hexdigest(),
                "content_ids": [r[0] for r in hits],
                "snapshot_ids": [r[1] for r in hits],
                "hit_count": len(hits),
                "latency_ms": round(elapsed, 6),
                "gold_metrics": None,
                "policy_version": POLICY_VERSION,
                "manifest_sha256": self.manifest_sha256,
                "scientifically_validated": False}

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def evaluate_complete_gold(ranked_ids: list[str], relevance: Mapping[str, int],
                           *, k: int, judgments_complete: bool = False) -> dict:
    """Compute binary recall and graded nDCG only for a genuinely complete pool.

    This cannot certify the supplied judgments. Consumers must independently
    establish source provenance, relevance judgments and sealed evaluation
    splits. Partial judgments cannot be treated as relevant negatives.
    """
    if not judgments_complete:
        raise RetrievalBaselineError("RETRIEVAL_GOLD_INCOMPLETE")
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise RetrievalBaselineError("RETRIEVAL_K_INVALID")
    if len(ranked_ids) != len(set(ranked_ids)):
        raise RetrievalBaselineError("RETRIEVAL_DUPLICATE_RANKING")
    if (not relevance or any(not isinstance(v, int) or isinstance(v, bool)
                             or not 0 <= v <= 3 for v in relevance.values())
            or any(cid not in relevance for cid in ranked_ids[:k])):
        raise RetrievalBaselineError("RETRIEVAL_GOLD_INVALID")
    relevant = {cid for cid, grade in relevance.items() if grade > 0}
    top = ranked_ids[:k]
    recall = sum(cid in relevant for cid in top) / len(relevant) if relevant else None
    dcg = sum((2 ** relevance[cid] - 1) / log2(rank + 2)
              for rank, cid in enumerate(top))
    ideal = sorted(relevance.values(), reverse=True)[:k]
    idcg = sum((2 ** grade - 1) / log2(rank + 2)
               for rank, grade in enumerate(ideal))
    return {"recall_at_k": round(recall, 6) if recall is not None else None,
            "ndcg_at_k": round(dcg / idcg, 6) if idcg else None,
            "k": k, "judgments_complete_claimed_by_caller": True,
            "independently_validated": False}


def p95_ms(samples: list[float]) -> float:
    if not samples or any(not isinstance(v, (float, int)) or v < 0
                          for v in samples):
        raise RetrievalBaselineError("RETRIEVAL_LATENCY_INVALID")
    return round(sorted(samples)[ceil(0.95 * len(samples)) - 1], 6)
