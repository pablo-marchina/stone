"""A04.6 diagnostic-only report linking; no operational DB, models or provider."""
import hashlib
import json

import pytest

from tapi_gate0.discovery_eval_handoff import link_private_reports

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
Q = "e" * 64


def evaluation():
    return {
        "schema_version": "tapi-imp069-local-eval-engine.v1",
        "reference_kind": "synthetic_fixture",
        "local_gate_scope": "synthetic_regression_only",
        "split": "validation", "evaluation_spec_sha256": A,
        "fixture_sha256": B, "deterministic_result_sha256": Q,
        "status": "PASS", "local_gate": "PASS",
        "reason_code": "EVAL_LOCAL_SYNTHETIC_PASS",
        "baseline_candidate_comparison_completed": True,
        **{key: False for key in (
            "sealed_test_queried", "independently_validated",
            "gold_relevance_judgments_available", "scientifically_validated",
            "gates_released", "global_gate_released", "external_data_accessed",
            "database_mutated", "production_approved", "dec006_decided",
            "candidate_selected_for_production")},
    }


def retrieval():
    return {
        "status": "SCOPED_FTS_LOCAL_PREVIEW_COMPLETED",
        "policy_version": "tapi-imp071-scoped-fts-preview.v1",
        "manifest_sha256": C, "partition_sha256": D,
        "eligible_posts": 3, "eligible_sources": 1,
        "query_count": 1, "queries": [{
            "query_sha256": Q, "manifest_sha256": C,
            "content_ids": ["post1"], "snapshot_ids": ["snapshot1"],
            "hit_count": 1, "gold_metrics": None,
            "scientifically_validated": False,
        }],
        "full_preview_includes_scope_and_revalidation": True,
        "latency_excludes_readiness_and_index_build": True,
        "recall_at_k": None, "ndcg_at_k": None,
        "scientific_admissions": 0,
        **{key: False for key in (
            "gold_relevance_judgments_available", "scientifically_validated",
            "external_data_accessed", "database_mutated", "production_approved",
            "editorial_recommendations_generated", "model_predictions_reexecuted")},
    }


def encode(x):
    raw = json.dumps(x, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return raw, hashlib.sha256(raw).hexdigest()


def check(e=None, r=None, *, tamper_eval=False, tamper_retrieval=False):
    ev, sha_ev = encode(e if e is not None else evaluation())
    rt, sha_rt = encode(r if r is not None else retrieval())
    if tamper_eval:
        sha_ev = "f" * 64
    if tamper_retrieval:
        sha_rt = "f" * 64
    return link_private_reports(ev, rt, evaluation_report_sha256=sha_ev,
                                retrieval_report_sha256=sha_rt,
                                evaluation_spec_sha256=A, fixture_sha256=B,
                                manifest_sha256=C, partition_sha256=D)


def test_verified_pair_is_private_diagnostic_only_not_a05_permission():
    result = check()
    assert result["status"] == "TECHNICAL_REPORTS_LINKED"
    assert result["permitted_use"] == "private_diagnostic_only"
    assert result["technical_reports_linked"] is True
    assert all(result[field] is False for field in (
        "tenant_scope_currently_verified", "source_rights_currently_verified",
        "independent_gold_available", "scientifically_validated",
        "a05_agent_handoff_allowed", "creative_handoff_allowed",
        "gates_released", "production_approved",
        "external_data_accessed", "database_mutated"))
    assert "post1" not in str(result) and "snapshot1" not in str(result)


@pytest.mark.parametrize("field,value,reason", [
    ("status", "FAIL", "A046_EVALUATION_NOT_PASS"),
    ("status", "BLOCKED", "A046_EVALUATION_NOT_PASS"),
    ("local_gate", "FAIL", "A046_EVALUATION_NOT_PASS"),
    ("split", "sealed_test", "A046_EVALUATION_PROVENANCE_INVALID"),
    ("evaluation_spec_sha256", D, "A046_EVALUATION_PROVENANCE_INVALID"),
    ("fixture_sha256", C, "A046_EVALUATION_PROVENANCE_INVALID"),
    ("sealed_test_queried", True, "A046_EVALUATION_UNSAFE_CLAIM"),
    ("gold_relevance_judgments_available", True, "A046_EVALUATION_UNSAFE_CLAIM"),
    ("production_approved", True, "A046_EVALUATION_UNSAFE_CLAIM"),
])
def test_evaluation_negative_contracts(field, value, reason):
    e = evaluation()
    e[field] = value
    result = check(e=e)
    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == reason
    assert result["a05_agent_handoff_allowed"] is False


@pytest.mark.parametrize("field,value,reason", [
    ("status", "OTHER", "A046_RETRIEVAL_PROVENANCE_INVALID"),
    ("partition_sha256", A, "A046_RETRIEVAL_PROVENANCE_INVALID"),
    ("manifest_sha256", A, "A046_RETRIEVAL_PROVENANCE_INVALID"),
    ("scientifically_validated", True, "A046_RETRIEVAL_UNSAFE_CLAIM"),
    ("database_mutated", True, "A046_RETRIEVAL_UNSAFE_CLAIM"),
    ("recall_at_k", 1.0, "A046_RETRIEVAL_CONTRACT_INVALID"),
    ("full_preview_includes_scope_and_revalidation", False, "A046_RETRIEVAL_CONTRACT_INVALID"),
    ("scientific_admissions", 1, "A046_RETRIEVAL_CONTRACT_INVALID"),
])
def test_retrieval_negative_contracts(field, value, reason):
    r = retrieval()
    r[field] = value
    result = check(r=r)
    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == reason


def test_retrieval_query_cannot_claim_gold_or_tenant_access():
    r = retrieval()
    r["queries"][0]["gold_metrics"] = {"recall": 1.0}
    assert check(r=r)["reason_code"] == "A046_RETRIEVAL_QUERY_CONTRACT_INVALID"
    r = retrieval()
    r["queries"][0]["snapshot_ids"] = ["other-tenant"] * 2
    assert check(r=r)["reason_code"] == "A046_RETRIEVAL_QUERY_CONTRACT_INVALID"
    r = retrieval()
    r["tenant_id"] = "untrusted-other-tenant"
    result = check(r=r)
    assert result["tenant_scope_currently_verified"] is False
    assert result["a05_agent_handoff_allowed"] is False
    assert "untrusted-other-tenant" not in str(result)


def test_reject_wrong_raw_hashes_without_releasing_ids():
    for kwargs in ({"tamper_eval": True}, {"tamper_retrieval": True}):
        result = check(**kwargs)
        assert result["reason_code"] == "A046_REPORT_SHA_MISMATCH"
        assert not result["technical_reports_linked"]


def test_reject_duplicate_json_key_and_non_object_without_leaking_payload():
    raw = b'{"status":"PASS","status":"FAIL"}'
    s = hashlib.sha256(raw).hexdigest()
    valid, vsha = encode(retrieval())
    result = link_private_reports(
        raw, valid, evaluation_report_sha256=s,
        retrieval_report_sha256=vsha, evaluation_spec_sha256=A,
        fixture_sha256=B, manifest_sha256=C, partition_sha256=D)
    assert result["reason_code"] == "A046_DUPLICATE_KEY"
    assert "FAIL" not in str(result)


def test_reject_missing_or_boolean_metrics_and_inconsistent_hits():
    r = retrieval()
    r["eligible_posts"] = True
    assert check(r=r)["reason_code"] == "A046_RETRIEVAL_CONTRACT_INVALID"
    r = retrieval()
    r["queries"][0]["hit_count"] = 2
    assert check(r=r)["reason_code"] == "A046_RETRIEVAL_QUERY_CONTRACT_INVALID"


def test_reference_datasets_are_not_conflated_or_promoted():
    e = evaluation()
    r = retrieval()
    r["eligible_posts"] = 1069
    r["eligible_sources"] = 27
    res = check(e=e, r=r)
    assert res["status"] == "TECHNICAL_REPORTS_LINKED"
    assert res["independent_gold_available"] is False
    assert res["source_rights_currently_verified"] is False
    assert res["creative_handoff_allowed"] is False
