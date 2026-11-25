"""A04 IMP-060 / CT-04 synthetic FTS5 integration, no real gold."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from tapi_gate0.discovery_gold_registry import GoldRegistryError
from tapi_gate0.discovery_gold_retrieval_eval import benchmark_synthetic_fts
from scripts import a4_gold_fts_benchmark as cli

FIXTURE = Path(__file__).parent / "fixtures" / "CT-04_fts_synthetic.json"


def _pinned(payload=None):
    if payload is None:
        raw = FIXTURE.read_bytes()
    else:
        raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True)
               .encode("utf-8"))
    return raw, sha256(raw).hexdigest()


def _eval(payload=None, *, split="validation", k=2):
    raw, digest = _pinned(payload)
    return benchmark_synthetic_fts(
        raw, expected_sha256=digest, split=split, k=k,
    )


def test_sqlite_fts5_uses_real_search_and_registry_judgments():
    result = _eval()
    assert result["status"] == "SYNTHETIC_FTS_BENCHMARK_VERIFIED"
    assert result["split"] == "validation"
    assert result["queries_evaluated"] == 1
    assert result["documents_evaluated"] == 2
    assert result["macro_synthetic_recall_at_k"] == 1.0
    assert result["macro_synthetic_ndcg_at_k"] == 1.0
    assert result["query_latency_p95_ms"] >= 0
    assert result["latency_excludes_index_build"] is True
    assert result["sealed_test_queried"] is False
    assert result["gold_relevance_judgments_available"] is False
    assert result["scientifically_validated"] is False
    assert result["gates_released"] is False
    for sensitive in ("sealed_test-query-1", "sealed_test-content-1",
                      "validation-content-1", "validation caixa"):
        assert sensitive not in str(result)


def test_development_is_separate_and_sealed_never_a_search_split():
    result = _eval(split="development")
    assert result["macro_synthetic_recall_at_k"] == 1
    assert result["sealed_test_queried"] is False
    with pytest.raises(GoldRegistryError, match="SEALED_EVALUATION_DENIED"):
        _eval(split="sealed_test")
    with pytest.raises(GoldRegistryError, match="K_INVALID"):
        _eval(k=0)


def test_input_manifest_sha_pin_blocks_before_sqlite():
    raw, digest = _pinned()
    with pytest.raises(GoldRegistryError, match="INPUT_SHA_MISMATCH"):
        benchmark_synthetic_fts(
            raw + b" ", expected_sha256=digest,
        )
    with pytest.raises(GoldRegistryError, match="INPUT_PIN_INVALID"):
        benchmark_synthetic_fts(raw, expected_sha256="bad")


def test_content_or_query_text_tampering_blocked_even_with_new_manifest_sha():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["synthetic_inputs"]["documents"][2]["caption"] = "tampered fixture"
    with pytest.raises(GoldRegistryError, match="DOCUMENT_HASH_OR_REF_INVALID"):
        _eval(payload)
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["synthetic_inputs"]["queries"][1]["text"] = "tampered query"
    with pytest.raises(GoldRegistryError, match="QUERY_HASH_OR_REF_INVALID"):
        _eval(payload)


def test_missing_or_duplicate_inputs_rejected_without_partial_metrics():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["synthetic_inputs"]["documents"].pop()
    with pytest.raises(GoldRegistryError, match="DOCUMENT_POPULATION_DRIFT"):
        _eval(payload)
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["synthetic_inputs"]["queries"].append(
        deepcopy(payload["synthetic_inputs"]["queries"][0])
    )
    with pytest.raises(GoldRegistryError, match="QUERY_HASH_OR_REF_INVALID"):
        _eval(payload)


def test_creator_leakage_and_false_judgments_impact_fail_closed():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["registry"]["documents"][2]["creator_id"] = (
        payload["registry"]["documents"][0]["creator_id"]
    )
    with pytest.raises(GoldRegistryError, match="CREATOR_SPLIT_LEAKAGE"):
        _eval(payload)
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["registry"]["judgments"].pop()
    with pytest.raises(GoldRegistryError, match="FALSE_COMPLETENESS_CLAIM"):
        _eval(payload)


def test_declared_incomplete_validation_query_blocks_metrics():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["registry"]["queries"][1]["complete_judgments"] = False
    with pytest.raises(GoldRegistryError, match="JUDGMENTS_INCOMPLETE"):
        _eval(payload)


def test_non_synthetic_input_never_becomes_gold():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["registry"]["documents"][0]["origin"] = "instagram"
    with pytest.raises(GoldRegistryError, match="NON_SYNTHETIC_REFERENCE_DENIED"):
        _eval(payload)


def test_duplicate_json_key_refused_even_with_matching_pin():
    raw = b'{"version":"a","version":"b"}'
    with pytest.raises(GoldRegistryError, match="DUPLICATE_JSON_KEY"):
        benchmark_synthetic_fts(raw, expected_sha256=sha256(raw).hexdigest())


def test_cli_only_reads_pinned_synthetic_fixture_and_prints_aggregate(capsys):
    raw, digest = _pinned()
    assert cli.main([
        "--fixture", str(FIXTURE),
        "--expected-sha256", digest,
        "--split", "validation", "--k", "2",
    ]) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["status"] == "SYNTHETIC_FTS_BENCHMARK_VERIFIED"
    assert result["production_approved"] is False
    for secret in ("sealed_test-query-1", "validation-content-1",
                   "validation caixa", "fixture-tenant"):
        assert secret not in output
    assert cli.main([
        "--fixture", str(FIXTURE),
        "--expected-sha256", "f" * 64,
    ]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"


def test_cli_refuses_files_outside_fixture_tree(monkeypatch, tmp_path, capsys):
    source = tmp_path / "outside.json"
    source.write_text("private data", encoding="utf-8")
    assert cli.main([
        "--fixture", str(source),
        "--expected-sha256", sha256(source.read_bytes()).hexdigest(),
    ]) == 2
    output = capsys.readouterr().out
    assert "private data" not in output
    assert json.loads(output)["code"] == "GOLD_FTS_FIXTURE_INVALID_OR_DENIED"


def test_synthetic_ranked_evidence_digest_is_stable_without_exposing_ids():
    first = _eval()
    second = _eval()
    digest = first["ranked_evidence_sha256"]
    assert isinstance(digest, str)
    assert len(digest) == 64
    assert digest == second["ranked_evidence_sha256"]
    assert "validation-content-1" not in str(first)
    assert "sealed_test-content-1" not in str(first)
