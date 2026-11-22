"""A02: fail-closed ASR error analysis of the seven authored shared AV fixtures.

This is not a model run, proof of original decoded media, a canonical rubric or a
Strict gate override. Failed shared fusion reports are allowed for diagnosis only.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re

from . import multimodal_asr as asr
from . import multimodal_fusion as fusion
from . import multimodal_shared_fixture as shared
from .asr_strict_diagnostic import _alignment

VERSION = "tapi-a02-shared-av-asr-diagnostic.v1"
SHA256 = re.compile(r"[a-f0-9]{64}\Z")


class SharedAVDiagnosticDenied(ValueError):
    def __init__(self):
        super().__init__("A02_SHARED_AV_REPORT_INVALID")


def _fail():
    raise SharedAVDiagnosticDenied()


def diagnose_shared_av_asr(report: dict) -> dict:
    """Recompute source/case consistency without requiring a passing fusion gate.

    Checks internal report integrity (not independent source-byte provenance).
    Do not reuse this diagnostic as a way to validate an A06 input for science.
    """
    if not isinstance(report, dict):
        _fail()
    try:
        start = json.dumps(report, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
        if (report.get("status") != "SHARED_MULTIMODAL_FIXTURE_BENCHMARK_COMPLETED"
                or report.get("policy_version") != shared.VERSION
                or report.get("fusion_policy") != fusion.VERSION
                or report.get("synthetic_only") is not True
                or type(report.get("engineering_gate_passed")) is not bool
                or report.get("temporal_integrity_passed") is not True
                or report.get("ocr_language_data_sha256") != shared.BEST_HASHES
                or report.get("vad_asset_sha256") != shared.VAD_HASH
                or report.get("auxiliary_hashes_match_operator_baseline") is not True
                or report.get("auxiliary_hashes_independently_verified") is not False
                or report.get("vlm_evaluated") is not False
                or report.get("semantic_scores_calibrated") is not False
                or any(report.get(k) is not False for k in (
                    "real_media_processing_allowed", "external_data_accessed",
                    "database_mutated", "production_approved"))
                or any(type(report.get(k)) is not int or report[k] != 0 for k in (
                    "real_media_processed", "scientific_admissions",
                    "rubric_assessments_written"))):
            _fail()
        checkpoint = report["checkpoint"]
        if (not isinstance(checkpoint, dict)
                or checkpoint.get("model_id") != asr.MEDIUM_MODEL_ID
                or checkpoint.get("model_revision") != asr.MEDIUM_REVISION
                or checkpoint.get("weights_sha256") != asr.MEDIUM_SHA256
                or checkpoint.get("weights_digest_verified") is not True):
            _fail()
        cases = report["cases"]
        if (not isinstance(cases, list) or len(cases) != len(shared.CASES)
                or type(report.get("case_count")) is not int
                or report["case_count"] != len(shared.CASES)):
            _fail()
        if len({row["media_sha256"] for row in cases}) != len(cases):
            _fail()
        details = []
        total_words = 0
        total_errors = 0
        negative_words = 0
        negative_calls = 0
        for row, fixture in zip(cases, shared.CASES):
            cid, caption, reference, _screen, _late, _geometry, topic, cta, has_text = fixture
            if (row["case_id"] != cid or row["caption"] != caption
                    or row["expected"] != {"tema_principal": topic,
                                           "tipo_cta": cta, "texto_na_tela": has_text}
                    or row["duration_s"] != shared.DURATION
                    or row["source_pixels_and_pcm_verified"] is not True
                    or row["temporal_passed"] is not True
                    or row["asset_binding_verified"] is not True
                    or not isinstance(row["media_sha256"], str)
                    or not SHA256.fullmatch(row["media_sha256"])
                    or row["caption_sha256"] != fusion.digest(caption)):
                _fail()
            if shared.validate_asset_binding(row) is not True:
                _fail()
            audio = row["audio"]
            intervals = row["vad"]["intervals"]
            chunks = audio["chunks"]
            segments = audio["segments"]
            if (not isinstance(intervals, list) or not isinstance(chunks, list)
                    or not isinstance(segments, list) or len(chunks) > 32
                    or len(segments) > 128 or audio["asr_calls"] != len(chunks)
                    or audio["asr_calls"] != len(intervals)
                    or audio["inference_attempted"] is not bool(intervals)
                    or audio["pcm_sha256"] != row["decoded_pcm_sha256"]
                    or row["vad"]["pcm_sha256"] != row["decoded_pcm_sha256"]
                    or audio["duration_s"] != shared.DURATION
                    or audio["timestamp_kind"] != "model_estimate_mapped_to_decoded_pcm_not_original_pts"):
                _fail()
            for chunk, region in zip(chunks, intervals):
                if (chunk["start_sample"] != region["start"]
                        or chunk["end_sample"] != region["end"]
                        or not isinstance(chunk["pcm_sha256"], str)
                        or not SHA256.fullmatch(chunk["pcm_sha256"])):
                    _fail()
                segment_text = [seg["text"] for seg in segments
                                if seg["region_start_sample"] == chunk["start_sample"]
                                and seg["region_end_sample"] == chunk["end_sample"]]
                if chunk["transcript"] != " ".join(segment_text):
                    _fail()
            hypothesis = audio["transcript"]
            if (not isinstance(hypothesis, str) or len(hypothesis) > 4000
                    or hypothesis != " ".join(c["transcript"] for c in chunks
                                                if c["transcript"])):
                _fail()
            expected_arms = {name: fusion.fuse(row["media_sha256"],
                                               row["fragments"], modalities)
                             for name, modalities in fusion.ARMS.items()}
            if row["arms"] != expected_arms:
                _fail()
            metrics = asr.word_errors(reference, hypothesis)
            alignment = _alignment(reference, hypothesis)
            if alignment["word_errors"] != metrics["word_errors"]:
                _fail()
            if reference:
                total_errors += metrics["word_errors"]
                total_words += metrics["reference_words"]
            else:
                negative_words += metrics["hypothesis_words"]
                negative_calls += audio["asr_calls"]
            details.append({
                "case_id": cid,
                "media_sha256": row["media_sha256"],
                "reference_sha256": sha256(reference.encode("utf-8")).hexdigest(),
                "hypothesis_sha256": sha256(hypothesis.encode("utf-8")).hexdigest(),
                **metrics, **alignment,
                "negative_asr_calls": audio["asr_calls"] if not reference else 0,
                "case_wer_exceeds_reference_threshold": metrics["wer"] is not None
                    and metrics["wer"] > asr.MAX_CASE_WER,
            })
        score = fusion.evaluate(cases)
        for key, value in score.items():
            if key != "engineering_gate_passed" and report.get(key) != value:
                _fail()
        if (type(report.get("negative_asr_calls")) is not int
                or report["negative_asr_calls"] != negative_calls
                or report["temporal_integrity_passed"] is not True):
            _fail()
        fused_gate = bool(score["engineering_gate_passed"] and negative_calls == 0)
        if report["engineering_gate_passed"] is not fused_gate:
            _fail()
        after = json.dumps(report, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
        if start != after:
            _fail()
        pooled_wer = total_errors / total_words if total_words else None
        reasons = []
        if not score["engineering_gate_passed"]:
            reasons.append("FUSION_GATE_FAILED")
        if negative_calls:
            reasons.append("NEGATIVE_ASR_CALLS")
        # Reference Strict thresholds are *informational* for shared-AV; the
        # shared benchmark uses the fusion gate, NOT ASR standalone gate.
        if pooled_wer is not None and pooled_wer > asr.MAX_POOLED_WER:
            reasons.append("INFORMATIONAL_POOLED_WER_EXCEEDED")
        if any(r["case_wer_exceeds_reference_threshold"] for r in details):
            reasons.append("INFORMATIONAL_CASE_WER_EXCEEDED")
        if negative_words:
            reasons.append("NEGATIVE_TRANSCRIPT_WORDS")
        return {
            "schema_version": VERSION,
            "status": "SHARED_AV_ASR_DIAGNOSTIC_ONLY",
            "source_report_canonical_sha256": sha256(start.encode("utf-8")).hexdigest(),
            "source_case_count": len(details),
            "cases": details,
            "pooled_wer_diagnostic": pooled_wer,
            "negative_transcript_words": negative_words,
            "negative_asr_calls": negative_calls,
            "failure_and_observation_reasons": reasons,
            "source_shared_engineering_gate_passed": fused_gate,
            "reference_asr_thresholds_informational_only": {
                "max_pooled_wer": asr.MAX_POOLED_WER,
                "max_case_wer": asr.MAX_CASE_WER,
            },
            "source_bytes_independently_verified": False,
            "checkpoint_independently_attested": False,
            "independent_gold": False,
            "scientific_admissions": 0,
            "external_data_accessed": False,
            "database_mutated": False,
            "production_approved": False,
            "global_gates_released": False,
        }
    except SharedAVDiagnosticDenied:
        raise
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError):
        _fail()
