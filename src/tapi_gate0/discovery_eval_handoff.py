"""A04.6: link *private technical reports*, never grant an A05/Studio handoff.

Synthetic evaluation and a scoped retrieval preview describe different datasets.
Even authentic pinned reports are historical observations, not current rights,
independent gold, a tenant authorization, or a recommendation. No IO here.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re

VERSION = "tapi-a046-private-report-link.v1"
EVAL_VERSION = "tapi-imp069-local-eval-engine.v1"
RETRIEVAL_VERSION = "tapi-imp071-scoped-fts-preview.v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_BYTES = 2_000_000
_FALSE_EVAL = (
    "sealed_test_queried", "independently_validated",
    "gold_relevance_judgments_available", "scientifically_validated",
    "gates_released", "global_gate_released", "external_data_accessed",
    "database_mutated", "production_approved", "dec006_decided",
    "candidate_selected_for_production",
)
_FALSE_PREVIEW = (
    "gold_relevance_judgments_available", "scientifically_validated",
    "external_data_accessed", "database_mutated", "production_approved",
    "editorial_recommendations_generated", "model_predictions_reexecuted",
)


class ReportLinkRejected(ValueError):
    """Internal fixed diagnostic, never includes report or caption content."""


def _reject(code):
    raise ReportLinkRejected("A046_" + code)


def _sha(value):
    return type(value) is str and _SHA.fullmatch(value) is not None


def _decode(raw, pin):
    if not _sha(pin) or type(raw) is not bytes or not 0 < len(raw) <= _MAX_BYTES:
        _reject("INPUT_INVALID")
    if sha256(raw).hexdigest() != pin:
        _reject("REPORT_SHA_MISMATCH")

    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                _reject("DUPLICATE_KEY")
            obj[key] = value
        return obj

    try:
        report = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                            parse_constant=lambda _value: _reject("JSON_CONSTANT"))
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError) as exc:
        if isinstance(exc, ReportLinkRejected):
            raise
        _reject("JSON_INVALID")
    if type(report) is not dict:
        _reject("SCHEMA_INVALID")
    return report


def link_private_reports(evaluation_raw: bytes, retrieval_raw: bytes, *,
                         evaluation_report_sha256: str,
                         retrieval_report_sha256: str,
                         evaluation_spec_sha256: str,
                         fixture_sha256: str,
                         manifest_sha256: str,
                         partition_sha256: str) -> dict:
    """Validate a research audit pair without claiming shared gold or live rights.

    Returns no content IDs, snapshots, captions, query strings or tenant IDs.
    A linked pair is *only* eligible for private diagnostic inspection; it is
    never a recommendation, CreativeSpec or a permission for an A05 tool.
    """
    result = {
        "schema_version": VERSION,
        "status": "BLOCKED", "reason_code": "A046_NOT_STARTED",
        "permitted_use": "none", "technical_reports_linked": False,
        "tenant_scope_currently_verified": False,
        "source_rights_currently_verified": False,
        "independent_gold_available": False,
        "scientifically_validated": False,
        "a05_agent_handoff_allowed": False,
        "creative_handoff_allowed": False,
        "gates_released": False,
        "production_approved": False,
        "external_data_accessed": False,
        "database_mutated": False,
    }
    try:
        if not all(_sha(v) for v in (
                evaluation_report_sha256, retrieval_report_sha256,
                evaluation_spec_sha256, fixture_sha256,
                manifest_sha256, partition_sha256)):
            _reject("PIN_INVALID")
        ev = _decode(evaluation_raw, evaluation_report_sha256)
        rt = _decode(retrieval_raw, retrieval_report_sha256)
        if (ev.get("schema_version") != EVAL_VERSION
                or ev.get("reference_kind") != "synthetic_fixture"
                or ev.get("local_gate_scope") != "synthetic_regression_only"
                or ev.get("split") not in ("development", "validation")
                or ev.get("evaluation_spec_sha256") != evaluation_spec_sha256
                or ev.get("fixture_sha256") != fixture_sha256
                or not _sha(ev.get("deterministic_result_sha256"))):
            _reject("EVALUATION_PROVENANCE_INVALID")
        if (ev.get("status") != "PASS" or ev.get("local_gate") != "PASS"
                or ev.get("reason_code") != "EVAL_LOCAL_SYNTHETIC_PASS"
                or ev.get("baseline_candidate_comparison_completed") is not True):
            _reject("EVALUATION_NOT_PASS")
        if any(ev.get(k) is not False for k in _FALSE_EVAL):
            _reject("EVALUATION_UNSAFE_CLAIM")
        if (rt.get("status") != "SCOPED_FTS_LOCAL_PREVIEW_COMPLETED"
                or rt.get("policy_version") != RETRIEVAL_VERSION
                or rt.get("manifest_sha256") != manifest_sha256
                or rt.get("partition_sha256") != partition_sha256
                or not _sha(rt.get("partition_sha256"))):
            _reject("RETRIEVAL_PROVENANCE_INVALID")
        if any(rt.get(k) is not False for k in _FALSE_PREVIEW):
            _reject("RETRIEVAL_UNSAFE_CLAIM")
        if (rt.get("recall_at_k") is not None or rt.get("ndcg_at_k") is not None
                or rt.get("scientific_admissions") != 0
                or rt.get("full_preview_includes_scope_and_revalidation") is not True
                or rt.get("latency_excludes_readiness_and_index_build") is not True
                or type(rt.get("eligible_posts")) is not int
                or type(rt.get("eligible_sources")) is not int
                or not 1 <= rt["eligible_sources"] <= rt["eligible_posts"]
                or type(rt.get("query_count")) is not int
                or not 1 <= rt["query_count"] <= 10
                or type(rt.get("queries")) is not list
                or len(rt["queries"]) != rt["query_count"]):
            _reject("RETRIEVAL_CONTRACT_INVALID")
        for q in rt["queries"]:
            if (type(q) is not dict or not _sha(q.get("query_sha256"))
                    or q.get("manifest_sha256") != manifest_sha256
                    or q.get("gold_metrics") is not None
                    or q.get("scientifically_validated") is not False
                    or type(q.get("hit_count")) is not int
                    or type(q.get("content_ids")) is not list
                    or type(q.get("snapshot_ids")) is not list
                    or not 0 <= q["hit_count"] == len(q["content_ids"]) == len(q["snapshot_ids"])
                    or any(type(x) is not str or not x or len(x) > 256
                           for x in q["content_ids"] + q["snapshot_ids"])
                    or len(set(q["content_ids"])) != len(q["content_ids"])):
                _reject("RETRIEVAL_QUERY_CONTRACT_INVALID")
        # These reports have distinct sources and timestamps, and neither
        # is a current tenant-bound rights grant. Linking is not admission.
        result.update(status="TECHNICAL_REPORTS_LINKED",
                      reason_code="A046_PRIVATE_DIAGNOSTIC_ONLY",
                      permitted_use="private_diagnostic_only",
                      technical_reports_linked=True)
    except ReportLinkRejected as exc:
        result["reason_code"] = str(exc)
    except Exception:
        result["reason_code"] = "A046_UNEXPECTED_INVALID_REPORT"
    return result
