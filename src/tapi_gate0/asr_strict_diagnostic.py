"""A02: explain Strict ASR WER failures from frozen, synthetic local reports.

Diagnostic-only: never transcribes, tunes thresholds, selects models, supplies
rights or upgrades a failed engineering gate. A report is self-reported evidence,
not independent model or checkpoint attestation.
"""
from __future__ import annotations

from hashlib import sha256
import json

from . import multimodal_asr as asr

VERSION = "tapi-a02-asr-strict-diagnostic.v1"
MAX_WORDS = 256


class ASRDiagnosticDenied(ValueError):
    def __init__(self):
        super().__init__("A02_ASR_SYNTHETIC_REPORT_INVALID")


def _fail():
    raise ASRDiagnosticDenied()


def _alignment(reference: str, hypothesis: str) -> dict:
    ref = asr.normalize_words(reference)
    hyp = asr.normalize_words(hypothesis)
    if len(ref) > MAX_WORDS or len(hyp) > MAX_WORDS:
        _fail()
    # Identical normalization and Levenshtein distance to production WER.
    dp = [[0] * (len(hyp) + 1) for _ in range(len(ref) + 1)]
    for i in range(len(ref) + 1):
        dp[i][0] = i
    for j in range(len(hyp) + 1):
        dp[0][j] = j
    for i, left in enumerate(ref, 1):
        for j, right in enumerate(hyp, 1):
            dp[i][j] = min(dp[i-1][j] + 1, dp[i][j-1] + 1,
                           dp[i-1][j-1] + (left != right))
    i, j = len(ref), len(hyp)
    edits = []
    counts = {"substitution": 0, "deletion": 0, "insertion": 0}
    while i or j:
        if i and j and ref[i-1] == hyp[j-1] and dp[i][j] == dp[i-1][j-1]:
            i -= 1
            j -= 1
        elif i and j and dp[i][j] == dp[i-1][j-1] + 1:
            edits.append({"operation": "substitution", "reference_index": i-1,
                          "hypothesis_index": j-1, "reference_word": ref[i-1],
                          "hypothesis_word": hyp[j-1]})
            counts["substitution"] += 1
            i -= 1
            j -= 1
        elif i and dp[i][j] == dp[i-1][j] + 1:
            edits.append({"operation": "deletion", "reference_index": i-1,
                          "hypothesis_index": j, "reference_word": ref[i-1],
                          "hypothesis_word": None})
            counts["deletion"] += 1
            i -= 1
        elif j and dp[i][j] == dp[i][j-1] + 1:
            edits.append({"operation": "insertion", "reference_index": i,
                          "hypothesis_index": j-1, "reference_word": None,
                          "hypothesis_word": hyp[j-1]})
            counts["insertion"] += 1
            j -= 1
        else:
            _fail()
    edits.reverse()
    if sum(counts.values()) != dp[-1][-1]:
        _fail()
    return {"counts": counts, "word_errors": dp[-1][-1], "edits": edits}


def _fixture_contract(suite: str):
    if suite == "baseline":
        return asr.SPEECH_FIXTURES, asr.NEGATIVE_FIXTURES, asr.VERSION
    if suite == "challenge":
        return asr.CHALLENGE_SPEECH, asr.CHALLENGE_NEGATIVE, asr.CHALLENGE_VERSION
    if suite == "guarded":
        return asr.CHALLENGE_SPEECH, asr.GUARDED_NEGATIVE, asr.GUARDED_VERSION
    _fail()


def diagnose_asr_report(report: dict) -> dict:
    """Explain a genuine-shaped report, including one with Strict FAIL.

    Do not require engineering_gate_passed True: a failed benchmark is precisely
    the report that must remain eligible for *diagnosis*, never for release.
    """
    if not isinstance(report, dict):
        _fail()
    try:
        if (report.get("status") != "ASR_FIXTURE_BENCHMARK_COMPLETED"
                or report.get("synthetic_only") is not True
                or report.get("asr_evaluated_on_synthetic") is not True
                or report.get("asr_validated_on_real_speech") is not False
                or report.get("independent_gold") is not False
                or report.get("real_media_processed") != 0
                or report.get("real_media_processing_allowed") is not False
                or report.get("external_data_accessed") is not False
                or report.get("database_mutated") is not False
                or report.get("rubric_assessments_written") != 0
                or report.get("scientific_admissions") != 0
                or report.get("production_approved") is not False
                or type(report.get("engineering_gate_passed")) is not bool):
            _fail()
        speech, negative, policy = _fixture_contract(report["suite"])
        if report["policy_version"] != policy:
            _fail()
        candidate = report["candidate"]
        if candidate == "small":
            model_id, revision, digest = asr.MODEL_ID, asr.MODEL_REVISION, asr.MODEL_SHA256
        elif candidate == "medium":
            model_id, revision, digest = asr.MEDIUM_MODEL_ID, asr.MEDIUM_REVISION, asr.MEDIUM_SHA256
        else:
            _fail()
        checkpoint = report["checkpoint"]
        if (not isinstance(checkpoint, dict)
                or checkpoint.get("model_id") != model_id
                or checkpoint.get("model_revision") != revision
                or checkpoint.get("weights_sha256") != digest
                or checkpoint.get("weights_digest_verified") is not True):
            _fail()
        if report.get("exact_digital_silence_guard") is not (report["suite"] == "guarded"):
            _fail()
        expected = [(cid, text) for cid, text, _ in speech] + [(cid, "") for cid in negative]
        rows = report["cases"]
        if (not isinstance(rows, list) or len(rows) != len(expected)
                or [row.get("case_id") for row in rows] != [cid for cid, _ in expected]):
            _fail()
        scored = []
        detailed = []
        for row, (cid, reference) in zip(rows, expected):
            hypothesis = row["transcript"]
            if not isinstance(hypothesis, str) or len(hypothesis) > 4000 or len(reference) > 4000:
                _fail()
            metrics = asr.word_errors(reference, hypothesis)
            if row["reference"] != reference or any(
                    type(row.get(k)) is not type(value) or row[k] != value
                    for k, value in metrics.items()):
                _fail()
            alignment = _alignment(reference, hypothesis)
            if alignment["word_errors"] != metrics["word_errors"]:
                _fail()
            scored.append({"case_id": cid, **metrics})
            detailed.append({
                "case_id": cid, "reference_sha256": sha256(reference.encode("utf-8")).hexdigest(),
                "hypothesis_sha256": sha256(hypothesis.encode("utf-8")).hexdigest(),
                "reference_words": metrics["reference_words"],
                "hypothesis_words": metrics["hypothesis_words"],
                "word_errors": metrics["word_errors"], "wer": metrics["wer"],
                "strict_case_wer_exceeded": (metrics["wer"] is not None
                                             and metrics["wer"] > asr.MAX_CASE_WER),
                "hallucinated_negative_words": (metrics["hypothesis_words"]
                                                if not reference else 0),
                **alignment,
            })
        gate = asr.evaluate_cases(scored, speech, negative)
        if (any(report.get(k) != gate[k] or type(report.get(k)) is not type(gate[k])
                for k in gate)):
            _fail()
        canonical = json.dumps(report, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), allow_nan=False)
        return {
            "schema_version": VERSION,
            "status": "SYNTHETIC_ASR_STRICT_DIAGNOSTIC_ONLY",
            "source_report_canonical_sha256": sha256(canonical.encode()).hexdigest(),
            "suite": report["suite"], "candidate": candidate,
            "cases": detailed,
            "engineering_gate_passed_in_source_report": gate["engineering_gate_passed"],
            "pooled_wer": gate["pooled_wer"],
            "strict_failure_cases": [row["case_id"] for row in detailed
                                     if row["strict_case_wer_exceeded"]
                                     or row["hallucinated_negative_words"]],
            "strict_thresholds_unchanged": True,
            "independently_attested_model": False,
            "independent_gold": False, "scientific_admissions": 0,
            "real_media_processed": 0, "external_data_accessed": False,
            "database_mutated": False, "production_approved": False,
            "global_gates_released": False,
        }
    except ASRDiagnosticDenied:
        raise
    except (KeyError, TypeError, AttributeError, IndexError, ValueError, OverflowError):
        _fail()
