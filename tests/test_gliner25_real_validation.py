"""DEC-017 E1.1 guardrails for real-weight validation; all tests offline.

Mocks in these tests are not evidence of working GLiNER weights.
"""
from __future__ import annotations

from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from prepare_gliner25_local_checkpoint import (
    _not_inside_project, validate_local_checkpoint, main as prepare_main,
)
from validate_gliner25_real_e1 import (
    _load_synthetic, _run_inference, _percentile,
)

from tapi_gate0.system_one_e1 import DeterministicTextDecider
from tapi_gate0.system_one_benchmark import BenchmarkCase
from tapi_gate0.system_one_e1 import EvidenceBundle, ObservedText


def fixture():
    return ROOT / "evidence" / "experiments" / "dec017_e1_synthetic_smoke.jsonl"


def test_existing_synthetic_input_is_validated_offline():
    cases = _load_synthetic(fixture())
    assert len(cases) == 4
    assert all(c.evidence.source_kind == "synthetic" for c in cases)


def test_no_public_checkpoint_download_without_explicit_flag(tmp_path):
    with pytest.raises(SystemExit) as exc:
        prepare_main(["--model-dir", str(tmp_path / "weights")])
    assert exc.value.code == 2
    assert not (tmp_path / "weights").exists()


def test_model_checkpoint_must_be_outside_repository():
    with pytest.raises(ValueError, match="OUTSIDE_PROJECT"):
        _not_inside_project(ROOT / "weights")
    _not_inside_project(Path.home() / "tapi-checkpoints" / "gliner")


def test_local_checkpoint_does_not_accept_missing_or_partial_weights(tmp_path):
    with pytest.raises(ValueError, match="CHECKPOINT_REQUIRED_FILE_MISSING"):
        validate_local_checkpoint(tmp_path)
    (tmp_path / "config.json").write_text(json.dumps({
        "architecture": "boundary",
        "model_name": "microsoft/mdeberta-v3-base"}), encoding="utf-8")
    (tmp_path / "model.safetensors").write_bytes(b"fake")
    (tmp_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="CHECKPOINT_WEIGHTS_TRUNCATED"):
        validate_local_checkpoint(tmp_path)


def test_validation_uses_only_synthetic_fixture(tmp_path):
    cases = [BenchmarkCase(
        evidence=EvidenceBundle(
            tenant_id="test", content_id="post", creator_id="creator",
            source_kind="approved_local",
            rights_reference="private-approval-document",
            allowed_operations=["offline_classification"],
            observation=ObservedText(
                modality="caption", text="texto",
                locator="authorized:caption",
                sha256=sha256(b"texto").hexdigest())),
        gold_kind="human_reviewed", gold_reference="independent-human-review",
        gold={"tem_cta": True}, split="test")]
    file = tmp_path / "human_gold.jsonl"
    file.write_text("\n".join(c.model_dump_json() for c in cases), encoding="utf-8")
    with pytest.raises(ValueError, match="E11_REQUIRES_SYNTHETIC_SMOKE_ONLY"):
        _load_synthetic(file)


def test_validation_flag_off_blocks_before_any_checkpoint_access(monkeypatch, tmp_path):
    monkeypatch.delenv("TAPI_SYSTEM_ONE_ENABLED", raising=False)
    with pytest.raises(PermissionError, match="SYSTEM_ONE_EXPERIMENT_DISABLED"):
        _run_inference(model_dir=tmp_path, cases=_load_synthetic(fixture()), repeats=1, warmup=0)


def test_percentile_interpolates():
    assert _percentile([1., 3., 5.], .50) == 3.0
    assert _percentile([1., 3., 5.], .95) == 4.8


class StubExtractor:
    def classify_text(self, text, schema):
        if "topic" in schema:
            return {"topic": "vendas"}
        return {}


class StubDecider(DeterministicTextDecider):
    def __init__(self, model_dir):
        self.model_dir = model_dir

    def _load(self):
        return StubExtractor()


def test_report_shape_with_mocked_inference_is_not_real_model_proof(monkeypatch, tmp_path):
    # Mock test checks reporting semantics only; it does not load any weights.
    import validate_gliner25_real_e1 as runner
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    monkeypatch.setattr(runner, "_not_inside_project", lambda path: None)
    monkeypatch.setattr(runner, "validate_local_checkpoint", lambda path: {
        "repository":"fastino/GLiNER2.5-multi-Decide",
        "revision": None, "architecture": "boundary",
        "files":{"model.safetensors":{"sha256":"a"*64,"bytes":1_150_000_000}},
        "tensor_count":500, "manifest_present":False,
    })
    monkeypatch.setattr(runner, "LocalGLiNERDecider", StubDecider)
    monkeypatch.setattr(runner, "_rss_megabytes", lambda: 1024.0)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        inference_mode=nullcontext,
        cuda=SimpleNamespace(is_available=lambda:False),
    ))
    report = runner._run_inference(
        model_dir=tmp_path, cases=_load_synthetic(fixture()),
        repeats=2, warmup=1,
    )
    assert report["schema_version"] == "tapi-gliner-e11-real-validation.v1"
    assert report["scientifically_validated"] is False
    assert report["execution"]["measured_calls"] == 8
    assert report["execution"]["external_api_inference_calls"] == 0
    assert report["execution"]["n_consistency_disagreements"] == 0
    assert set(report["paired_synthetic_smoke"]["models"]) == {
        "baseline", "local_gliner",
    }
