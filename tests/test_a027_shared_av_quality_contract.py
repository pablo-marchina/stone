"""Contract tests for strict versus partial shared-AV ASR quality.

Pure synthetic failures: no native model, filesystem or external I/O.
"""
import pytest

from tapi_gate0 import asset_shared_av_fixture as shared
from tapi_gate0.asset_asr_fixture import ASRFixtureQualityError
from tapi_gate0.asset_processor_results import STRICT_QUALITY, PARTIAL_QUALITY


def _rejected(*_args, **_kwargs):
    # Four edits across seven reference words; model output is not exposed.
    raise ASRFixtureQualityError({
        "wer": 4 / 7,
        "vad_iou": 0.93,
        "vad_boundary_error_s": 0.18,
        "reference_words": 7,
        "hypothesis_words": 8,
        "hypothesis_sha256": "a" * 64,
        "vad_calls": 1,
        "asr_calls": 1,
    })


def test_strict_quality_propagates_failure_without_abstention(monkeypatch):
    monkeypatch.setattr(shared.asr, "result_from_output", _rejected)
    with pytest.raises(ASRFixtureQualityError, match="ASR_FIXTURE_WER_GATE") as caught:
        shared._asr_result({}, {}, STRICT_QUALITY)
    assert caught.value.quality["wer"] > 0.50


def test_partial_quality_records_typed_abstention_without_text_digest(monkeypatch):
    monkeypatch.setattr(shared.asr, "result_from_output", _rejected)
    observation, quality, rejection = shared._asr_result({}, {}, PARTIAL_QUALITY)
    assert observation.processor == "asr_vad"
    assert observation.state == "abstained"
    assert observation.reason == "fixture_quality_rejected"
    assert quality["reason"] == "ASR_FIXTURE_WER_GATE"
    assert quality["wer"] > 0.50
    assert "hypothesis_sha256" not in quality
    assert rejection.model_dump(mode="json") == quality
