"""IMP-060 / CT-04: synthetic-only, immutable evaluation reference registry.

DEC-018 expressly does NOT authorize claims of independent human gold.
This module registers synthetic contract fixtures only. It never opens a
provider connection, writes a domain DB, performs I/O or exports sealed
references to prompt-building clients. No API, MCP or production wiring.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from collections import defaultdict
from collections.abc import Mapping

from .discovery_retrieval_fts import RetrievalBaselineError, evaluate_complete_gold

VERSION = "tapi-imp060-synthetic-registry.v1"
SPLITS = ("development", "validation", "sealed_test")
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_MAX_MANIFEST_BYTES = 2_000_000


class GoldRegistryError(ValueError):
    """Typed fail-closed validation errors, no raw fixture data in messages."""


def _fail(code):
    raise GoldRegistryError("GOLD_REGISTRY_" + code)


def _exact(obj, keys):
    if not isinstance(obj, dict) or set(obj) != set(keys):
        _fail("SCHEMA_INVALID")


def _id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        _fail("IDENTIFIER_INVALID")
    return value


def _sha(value):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        _fail("HASH_INVALID")
    return value


def _split(value):
    if value not in SPLITS or not isinstance(value, str):
        _fail("SPLIT_INVALID")
    return value


@dataclass(frozen=True)
class _Document:
    content_id: str
    creator_id: str
    content_sha256: str
    split: str


@dataclass(frozen=True)
class _Query:
    query_id: str
    query_sha256: str
    split: str
    complete_judgments: bool


@dataclass(frozen=True)
class SyntheticGoldRegistry:
    """Validated immutable references; do not serialize this instance to prompts."""

    dataset_id: str
    tenant_id: str
    dataset_version: str
    manifest_sha256: str
    _documents: tuple[_Document, ...]
    _queries: tuple[_Query, ...]
    _judgments: tuple[tuple[str, str, int], ...]

    def summary(self):
        return {
            "schema_version": VERSION,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "manifest_sha256": self.manifest_sha256,
            "reference_kind": "synthetic_fixture",
            "split_document_counts": {
                name: sum(d.split == name for d in self._documents)
                for name in SPLITS
            },
            "split_query_counts": {
                name: sum(q.split == name for q in self._queries)
                for name in SPLITS
            },
            "judgment_count": len(self._judgments),
            "sealed_test_hidden_from_prompts": True,
            "gold_relevance_judgments_available": False,
            "independently_validated": False,
            "scientifically_validated": False,
            "evaluation_status": "SYNTHETIC_CONTRACT_ONLY",
            "gates_released": False,
        }

    def prompt_references(self, *, split="development"):
        """Only safe development/validation references; no raw text or labels."""
        if split not in ("development", "validation"):
            _fail("SEALED_PROMPT_ACCESS_DENIED")
        return {
            "reference_kind": "synthetic_fixture",
            "split": split,
            "document_refs": tuple(
                d.content_id for d in self._documents if d.split == split
            ),
            "query_refs": tuple(
                q.query_id for q in self._queries if q.split == split
            ),
            "gold_relevance_judgments_available": False,
        }

    def assert_prompt_isolation(self, payload):
        """Reject explicit sealed IDs/hashes; cannot detect semantic paraphrases."""
        try:
            serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            _fail("PROMPT_PAYLOAD_INVALID")
        if len(serialized) > 1_000_000:
            _fail("PROMPT_PAYLOAD_TOO_LARGE")
        forbidden = {
            token for d in self._documents if d.split == "sealed_test"
            for token in (d.content_id, d.creator_id, d.content_sha256)
        }
        forbidden.update(
            token for q in self._queries if q.split == "sealed_test"
            for token in (q.query_id, q.query_sha256)
        )
        # Whole JSON serialization makes both keys and values visible.
        if any(token in serialized for token in forbidden):
            _fail("SEALED_PROMPT_LEAKAGE")
        return True

    def _score(self, query_id, ranked_ids, k, *, allow_sealed=False):
        q = next((item for item in self._queries if item.query_id == query_id), None)
        if q is None:
            _fail("QUERY_NOT_REGISTERED")
        if q.split == "sealed_test" and not allow_sealed:
            _fail("SEALED_EVALUATION_DENIED")
        if not q.complete_judgments:
            _fail("JUDGMENTS_INCOMPLETE")
        if (type(k) is not int or not 1 <= k <= 50
                or not isinstance(ranked_ids, (list, tuple))
                or any(not isinstance(cid, str) for cid in ranked_ids)):
            _fail("RANKING_INVALID")
        if len(ranked_ids) != len(set(ranked_ids)):
            _fail("RANKING_INVALID")
        eligible = {
            d.content_id for d in self._documents if d.split == q.split
        }
        if any(cid not in eligible for cid in ranked_ids):
            _fail("CROSS_SPLIT_RANKING_DENIED")
        judgments = {
            cid: grade for qid, cid, grade in self._judgments if qid == query_id
        }
        if set(judgments) != eligible:
            _fail("JUDGMENTS_INCOMPLETE")
        try:
            return evaluate_complete_gold(
                list(ranked_ids), judgments, k=k, judgments_complete=True,
            )
        except RetrievalBaselineError:
            _fail("EVALUATION_INVALID")

    def evaluate_synthetic_query(self, query_id, ranked_ids, *, k=5):
        result = self._score(query_id, ranked_ids, k)
        return {
            "status": "SYNTHETIC_FIXTURE_ONLY",
            "synthetic_recall_at_k": result["recall_at_k"],
            "synthetic_ndcg_at_k": result["ndcg_at_k"],
            "k": k,
            "reference_kind": "synthetic_oracle",
            "gold_relevance_judgments_available": False,
            "scientifically_validated": False,
            "gates_released": False,
        }

    def compare_synthetic_sealed(self, baseline, candidate, *,
                                 k=5, explicit_sealed_evaluation=False):
        """Aggregate-only, explicitly requested synthetic sealed regression.

        Not an independent gold review. Never returns sealed references or
        individual judgments. Caller must never feed results into prompts.
        """
        if explicit_sealed_evaluation is not True:
            _fail("SEALED_EVALUATION_DENIED")
        names = {q.query_id for q in self._queries if q.split == "sealed_test"}
        if (not isinstance(baseline, dict) or not isinstance(candidate, dict)
                or set(baseline) != names or set(candidate) != names):
            _fail("SEALED_CANDIDATES_INVALID")
        before = []
        after = []
        for qid in sorted(names):
            a = self._score(qid, baseline[qid], k, allow_sealed=True)
            b = self._score(qid, candidate[qid], k, allow_sealed=True)
            if a["ndcg_at_k"] is None or b["ndcg_at_k"] is None:
                _fail("SEALED_NDCG_UNAVAILABLE")
            before.append(a["ndcg_at_k"])
            after.append(b["ndcg_at_k"])
        baseline_avg = round(sum(before) / len(before), 6)
        candidate_avg = round(sum(after) / len(after), 6)
        return {
            "status": "SYNTHETIC_SEALED_COMPARISON_ONLY",
            "reference_kind": "synthetic_oracle",
            "evaluated_query_count": len(names),
            "baseline_synthetic_ndcg_at_k": baseline_avg,
            "candidate_synthetic_ndcg_at_k": candidate_avg,
            "candidate_not_worse_on_fixture": candidate_avg >= baseline_avg,
            "k": k,
            "scientifically_validated": False,
            "gold_relevance_judgments_available": False,
            "gates_released": False,
        }


def _strict_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            _fail("DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def load_synthetic_registry_bytes(raw: bytes, *, expected_sha256: str):
    """SHA256-pin original bytes before parsing; all inputs synthetic and local."""
    _sha(expected_sha256)
    if not isinstance(raw, bytes) or not 0 < len(raw) <= _MAX_MANIFEST_BYTES:
        _fail("MANIFEST_SIZE_INVALID")
    if sha256(raw).hexdigest() != expected_sha256:
        _fail("MANIFEST_SHA_MISMATCH")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_pairs,
                             parse_constant=lambda _: _fail("JSON_CONSTANT_INVALID"))
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError) as exc:
        if isinstance(exc, GoldRegistryError):
            raise
        _fail("MANIFEST_JSON_INVALID")
    return build_synthetic_registry(payload, manifest_sha256=expected_sha256)


def build_synthetic_registry(payload: dict, *, manifest_sha256: str):
    """Validate complete referential integrity; never infer missing judgments."""
    _sha(manifest_sha256)
    _exact(payload, (
        "schema_version", "dataset_id", "tenant_id", "dataset_version",
        "reference_kind", "documents", "queries", "judgments",
    ))
    if payload["schema_version"] != VERSION or payload["reference_kind"] != "synthetic_fixture":
        _fail("NON_SYNTHETIC_REFERENCE_DENIED")
    dataset_id = _id(payload["dataset_id"])
    tenant_id = _id(payload["tenant_id"])
    dataset_version = _id(payload["dataset_version"])
    for field in ("documents", "queries", "judgments"):
        if not isinstance(payload[field], list) or len(payload[field]) > 20_000:
            _fail("COLLECTION_INVALID")

    docs = []
    ids, fingerprints = set(), set()
    by_content, creator_splits = {}, defaultdict(set)
    for d in payload["documents"]:
        _exact(d, ("content_id", "creator_id", "content_sha256", "split", "origin"))
        if d["origin"] != "synthetic_local":
            _fail("NON_SYNTHETIC_REFERENCE_DENIED")
        doc = _Document(
            _id(d["content_id"]), _id(d["creator_id"]),
            _sha(d["content_sha256"]), _split(d["split"]),
        )
        if doc.content_id in ids or doc.content_sha256 in fingerprints:
            _fail("DUPLICATE_DOCUMENT_OR_FINGERPRINT")
        ids.add(doc.content_id)
        fingerprints.add(doc.content_sha256)
        creator_splits[doc.creator_id].add(doc.split)
        docs.append(doc)
        by_content[doc.content_id] = doc
    if any(len(splits) > 1 for splits in creator_splits.values()):
        _fail("CREATOR_SPLIT_LEAKAGE")

    queries = []
    qids, query_hashes = set(), set()
    for q in payload["queries"]:
        _exact(q, ("query_id", "query_sha256", "split", "complete_judgments"))
        if type(q["complete_judgments"]) is not bool:
            _fail("JUDGMENT_COMPLETENESS_INVALID")
        query = _Query(_id(q["query_id"]), _sha(q["query_sha256"]),
                       _split(q["split"]), q["complete_judgments"])
        if query.query_id in qids or query.query_sha256 in query_hashes:
            _fail("DUPLICATE_QUERY")
        queries.append(query)
        qids.add(query.query_id)
        query_hashes.add(query.query_sha256)
    if (any(not any(d.split == s for d in docs) for s in SPLITS)
            or any(not any(q.split == s for q in queries) for s in SPLITS)):
        _fail("SPLIT_COVERAGE_INCOMPLETE")

    q_by_id = {q.query_id: q for q in queries}
    judgments, judgment_pairs = [], set()
    by_query = defaultdict(set)
    for j in payload["judgments"]:
        _exact(j, ("query_id", "content_id", "grade", "reference_kind"))
        if j["reference_kind"] != "synthetic_oracle":
            _fail("NON_SYNTHETIC_REFERENCE_DENIED")
        qid, cid = _id(j["query_id"]), _id(j["content_id"])
        grade = j["grade"]
        if type(grade) is not int or not 0 <= grade <= 3:
            _fail("GRADE_INVALID")
        if qid not in q_by_id or cid not in by_content:
            _fail("ORPHAN_JUDGMENT")
        if q_by_id[qid].split != by_content[cid].split:
            _fail("CROSS_SPLIT_JUDGMENT_DENIED")
        if (qid, cid) in judgment_pairs:
            _fail("DUPLICATE_JUDGMENT")
        judgment_pairs.add((qid, cid))
        by_query[qid].add(cid)
        judgments.append((qid, cid, grade))
    for q in queries:
        if q.complete_judgments:
            required = {d.content_id for d in docs if d.split == q.split}
            if by_query[q.query_id] != required:
                _fail("FALSE_COMPLETENESS_CLAIM")
    return SyntheticGoldRegistry(
        dataset_id, tenant_id, dataset_version, manifest_sha256,
        tuple(docs), tuple(queries), tuple(judgments),
    )
