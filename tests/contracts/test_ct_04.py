"""CT-04 / U04: isolated synthetic EDD fixtures; NOT a scientific gold test."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from tapi_gate0.discovery_gold_registry import (
    GoldRegistryError, load_synthetic_registry_bytes,
    build_synthetic_registry,
)

ROOT = Path(__file__).resolve().parents[1] / "fixtures"


def _positive():
    raw = (ROOT / "CT-04_positive.json").read_bytes()
    manifest = json.loads(raw)
    return manifest, load_synthetic_registry_bytes(
        raw, expected_sha256=sha256(raw).hexdigest(),
    )


def test_ct04_synthetic_fixture_reproduces_manifest_pin_and_splits():
    payload, reg = _positive()
    assert payload["reference_kind"] == "synthetic_fixture"
    assert reg.summary()["split_document_counts"] == {
        "development": 2, "validation": 2, "sealed_test": 2,
    }
    assert reg.summary()["scientifically_validated"] is False
    assert reg.summary()["gold_relevance_judgments_available"] is False
    assert reg.summary()["gates_released"] is False


def test_ct04_development_prompts_exclude_sealed_test():
    _, reg = _positive()
    safe = reg.prompt_references(split="development")
    assert reg.assert_prompt_isolation(safe) is True
    assert all("sealed_test" not in cid for cid in safe["document_refs"])
    assert all("sealed_test" not in qid for qid in safe["query_refs"])
    with pytest.raises(GoldRegistryError, match="SEALED_PROMPT_LEAKAGE"):
        reg.assert_prompt_isolation({"messages": [
            {"role": "user", "content": "Please use sealed_test-query-1"},
        ]})
    with pytest.raises(GoldRegistryError, match="SEALED_PROMPT_ACCESS_DENIED"):
        reg.prompt_references(split="sealed_test")


def test_ct04_sealed_baseline_candidate_regression_is_synthetic_only():
    _, reg = _positive()
    baseline = {"sealed_test-query-1": [
        "sealed_test-content-2", "sealed_test-content-1",
    ]}
    candidate = {"sealed_test-query-1": [
        "sealed_test-content-1", "sealed_test-content-2",
    ]}
    assert reg.compare_synthetic_sealed(
        baseline, candidate, k=2, explicit_sealed_evaluation=True,
    )["candidate_not_worse_on_fixture"]
    assert reg.summary()["gold_relevance_judgments_available"] is False


def test_ct04_manifest_negative_cases_fail_closed():
    raw = (ROOT / "CT-04_negative.json").read_bytes()
    negative = json.loads(raw)
    assert negative["reference_kind"] == "synthetic_fixture"
    assert negative["schema_version"] == "tapi-imp060-ct04-negative-fixtures.v1"
    positive, _ = _positive()
    assert len(negative["cases"]) >= 4
    for case in negative["cases"]:
        payload = deepcopy(positive)
        if case.get("action") == "remove_last_judgment":
            payload["judgments"].pop()
        else:
            target = payload[case["target"]][case["index"]]
            if case.get("source"):
                origin = case["source"]
                value = payload[origin["target"]][origin["index"]][origin["field"]]
            else:
                value = case["value"]
            target[case["field"]] = value
        with pytest.raises(GoldRegistryError, match=case["expected_error"]):
            build_synthetic_registry(payload, manifest_sha256="a" * 64)
