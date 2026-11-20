"""IMP-060 synthetic registry contracts; these fixtures are NEVER real gold."""
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from tapi_gate0.discovery_gold_registry import (
    GoldRegistryError, VERSION, build_synthetic_registry,
    load_synthetic_registry_bytes,
)


def _sha(value):
    return sha256(value.encode("utf-8")).hexdigest()


def manifest():
    docs = []
    queries = []
    judgments = []
    for split in ("development", "validation", "sealed_test"):
        for idx in (1, 2):
            docs.append({
                "content_id": f"{split}-content-{idx}",
                "creator_id": f"{split}-creator-{idx}",
                "content_sha256": _sha(f"{split}-text-{idx}"),
                "split": split,
                "origin": "synthetic_local",
            })
        queries.append({
            "query_id": f"{split}-query-1",
            "query_sha256": _sha(f"{split}-query-text"),
            "split": split,
            "complete_judgments": True,
        })
        for idx, grade in ((1, 3), (2, 0)):
            judgments.append({
                "query_id": f"{split}-query-1",
                "content_id": f"{split}-content-{idx}",
                "grade": grade,
                "reference_kind": "synthetic_oracle",
            })
    return {
        "schema_version": VERSION,
        "dataset_id": "ct04-synthetic",
        "tenant_id": "fixture-tenant",
        "dataset_version": "v1",
        "reference_kind": "synthetic_fixture",
        "documents": docs,
        "queries": queries,
        "judgments": judgments,
    }


def registry(payload=None):
    return build_synthetic_registry(
        manifest() if payload is None else payload,
        manifest_sha256="a" * 64,
    )


def test_summary_never_claims_real_gold_or_scientific_validation():
    result = registry().summary()
    assert result["split_document_counts"] == {
        "development": 2, "validation": 2, "sealed_test": 2,
    }
    assert result["split_query_counts"] == {
        "development": 1, "validation": 1, "sealed_test": 1,
    }
    assert result["judgment_count"] == 6
    assert result["evaluation_status"] == "SYNTHETIC_CONTRACT_ONLY"
    assert result["gold_relevance_judgments_available"] is False
    assert result["scientifically_validated"] is False
    assert result["gates_released"] is False
    assert "sealed_test-content-1" not in str(result)


def test_manifest_raw_sha256_pin_and_duplicate_key_rejected():
    raw = json.dumps(manifest(), ensure_ascii=False).encode("utf-8")
    result = load_synthetic_registry_bytes(
        raw, expected_sha256=sha256(raw).hexdigest(),
    )
    assert result.summary()["reference_kind"] == "synthetic_fixture"
    with pytest.raises(GoldRegistryError, match="MANIFEST_SHA_MISMATCH"):
        load_synthetic_registry_bytes(raw + b" ", expected_sha256=sha256(raw).hexdigest())
    duplicate = b'{"schema_version":"a","schema_version":"b"}'
    with pytest.raises(GoldRegistryError, match="DUPLICATE_JSON_KEY"):
        load_synthetic_registry_bytes(
            duplicate, expected_sha256=sha256(duplicate).hexdigest(),
        )
    with pytest.raises(GoldRegistryError, match="HASH_INVALID"):
        load_synthetic_registry_bytes(raw, expected_sha256="not-a-hash")


def test_only_development_validation_refs_can_enter_prompts():
    reg = registry()
    dev = reg.prompt_references()
    val = reg.prompt_references(split="validation")
    assert dev["document_refs"] == ("development-content-1", "development-content-2")
    assert val["query_refs"] == ("validation-query-1",)
    assert reg.assert_prompt_isolation({"refs": dev}) is True
    with pytest.raises(GoldRegistryError, match="SEALED_PROMPT_ACCESS_DENIED"):
        reg.prompt_references(split="sealed_test")
    for forbidden in ("sealed_test-content-1", "sealed_test-query-1",
                      _sha("sealed_test-text-1"), _sha("sealed_test-query-text"),
                      "sealed_test-creator-1"):
        with pytest.raises(GoldRegistryError, match="SEALED_PROMPT_LEAKAGE"):
            reg.assert_prompt_isolation({"prompt": "Search " + forbidden})
    with pytest.raises(GoldRegistryError, match="PROMPT_PAYLOAD_INVALID"):
        reg.assert_prompt_isolation({"function": object()})


def test_creator_overlap_is_leakage_even_with_distinct_posts():
    payload = manifest()
    payload["documents"][2]["creator_id"] = payload["documents"][0]["creator_id"]
    with pytest.raises(GoldRegistryError, match="CREATOR_SPLIT_LEAKAGE"):
        registry(payload)


def test_duplicate_content_fingerprint_and_query_are_denied():
    payload = manifest()
    payload["documents"][2]["content_sha256"] = payload["documents"][0]["content_sha256"]
    with pytest.raises(GoldRegistryError, match="DUPLICATE_DOCUMENT_OR_FINGERPRINT"):
        registry(payload)
    payload = manifest()
    payload["queries"][1]["query_sha256"] = payload["queries"][0]["query_sha256"]
    with pytest.raises(GoldRegistryError, match="DUPLICATE_QUERY"):
        registry(payload)


def test_wrong_split_or_orphan_label_is_denied():
    payload = manifest()
    payload["judgments"][0]["content_id"] = "sealed_test-content-1"
    with pytest.raises(GoldRegistryError, match="CROSS_SPLIT_JUDGMENT_DENIED"):
        registry(payload)
    payload = manifest()
    payload["judgments"][0]["content_id"] = "unknown-content"
    with pytest.raises(GoldRegistryError, match="ORPHAN_JUDGMENT"):
        registry(payload)
    payload = manifest()
    payload["judgments"][1] = deepcopy(payload["judgments"][0])
    with pytest.raises(GoldRegistryError, match="DUPLICATE_JUDGMENT"):
        registry(payload)


def test_reject_false_complete_and_absent_labels():
    payload = manifest()
    payload["judgments"] = payload["judgments"][:-1]
    with pytest.raises(GoldRegistryError, match="FALSE_COMPLETENESS_CLAIM"):
        registry(payload)
    payload["queries"][-1]["complete_judgments"] = False
    reg = registry(payload)
    with pytest.raises(GoldRegistryError, match="SEALED_EVALUATION_DENIED"):
        reg.evaluate_synthetic_query(
            "sealed_test-query-1", ["sealed_test-content-1"]
        )
    payload["judgments"] = payload["judgments"][:-1]
    reg = registry(payload)
    with pytest.raises(GoldRegistryError, match="JUDGMENTS_INCOMPLETE"):
        reg.evaluate_synthetic_query(
            "validation-query-1", ["validation-content-1"]
        )


def test_reject_non_synthetic_sources_judgments_and_boolean_grade():
    payload = manifest()
    payload["documents"][0]["origin"] = "instagram"
    with pytest.raises(GoldRegistryError, match="NON_SYNTHETIC_REFERENCE_DENIED"):
        registry(payload)
    payload = manifest()
    payload["reference_kind"] = "independent_human_gold"
    with pytest.raises(GoldRegistryError, match="NON_SYNTHETIC_REFERENCE_DENIED"):
        registry(payload)
    payload = manifest()
    payload["judgments"][0]["reference_kind"] = "human"
    with pytest.raises(GoldRegistryError, match="NON_SYNTHETIC_REFERENCE_DENIED"):
        registry(payload)
    payload = manifest()
    payload["judgments"][0]["grade"] = True
    with pytest.raises(GoldRegistryError, match="GRADE_INVALID"):
        registry(payload)


def test_synthetic_metrics_are_explicitly_not_domain_gold():
    reg = registry()
    result = reg.evaluate_synthetic_query(
        "validation-query-1", ["validation-content-2", "validation-content-1"],
        k=1,
    )
    assert result["synthetic_recall_at_k"] == 0.0
    assert result["synthetic_ndcg_at_k"] == 0.0
    assert result["status"] == "SYNTHETIC_FIXTURE_ONLY"
    assert result["scientifically_validated"] is False
    assert result["gold_relevance_judgments_available"] is False
    with pytest.raises(GoldRegistryError, match="CROSS_SPLIT_RANKING_DENIED"):
        reg.evaluate_synthetic_query(
            "validation-query-1", ["sealed_test-content-1"]
        )


def test_sealed_regression_explicit_and_aggregate_only():
    reg = registry()
    before = {"sealed_test-query-1": [
        "sealed_test-content-2", "sealed_test-content-1",
    ]}
    after = {"sealed_test-query-1": [
        "sealed_test-content-1", "sealed_test-content-2",
    ]}
    with pytest.raises(GoldRegistryError, match="SEALED_EVALUATION_DENIED"):
        reg.compare_synthetic_sealed(before, after, k=2)
    result = reg.compare_synthetic_sealed(
        before, after, k=2, explicit_sealed_evaluation=True,
    )
    assert result["candidate_not_worse_on_fixture"] is True
    assert result["candidate_synthetic_ndcg_at_k"] > result["baseline_synthetic_ndcg_at_k"]
    assert result["evaluated_query_count"] == 1
    assert result["scientifically_validated"] is False
    assert result["gates_released"] is False
    assert "sealed_test-query-1" not in str(result)
    with pytest.raises(GoldRegistryError, match="SEALED_CANDIDATES_INVALID"):
        reg.compare_synthetic_sealed(
            {"development-query-1": []}, after,
            explicit_sealed_evaluation=True,
        )


def test_missing_split_or_incorrect_schema_rejected():
    payload = manifest()
    payload["queries"].pop()
    with pytest.raises(GoldRegistryError, match="SPLIT_COVERAGE_INCOMPLETE"):
        registry(payload)
    payload = manifest()
    payload["unknown"] = "silent drift"
    with pytest.raises(GoldRegistryError, match="SCHEMA_INVALID"):
        registry(payload)
