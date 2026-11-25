from copy import deepcopy
from hashlib import sha256
import pytest

from tapi_gate0 import multimodal_asr as asr
from tapi_gate0 import asr_strict_diagnostic as diagnostic


def report_for(suite="baseline", *, candidate="medium"):
    speech, negatives, policy = diagnostic._fixture_contract(suite)
    cases = []
    for cid, ref, _ in speech:
        cases.append({"case_id": cid, "reference": ref,
                      "transcript": ref, **asr.word_errors(ref, ref)})
    for cid in negatives:
        cases.append({"case_id": cid, "reference": "", "transcript": "",
                      **asr.word_errors("", "")})
    evaluation = asr.evaluate_cases(cases, speech, negatives)
    digest = asr.MEDIUM_SHA256 if candidate == "medium" else asr.MODEL_SHA256
    ident = asr.MEDIUM_MODEL_ID if candidate == "medium" else asr.MODEL_ID
    revision = asr.MEDIUM_REVISION if candidate == "medium" else asr.MODEL_REVISION
    return {"status": "ASR_FIXTURE_BENCHMARK_COMPLETED",
            "suite": suite, "candidate": candidate, "policy_version": policy,
            "checkpoint": {"model_id": ident, "model_revision": revision,
                           "weights_sha256": digest, "weights_digest_verified": True},
            "synthetic_only": True, "asr_evaluated_on_synthetic": True,
            "asr_validated_on_real_speech": False, "independent_gold": False,
            "real_media_processed": 0, "real_media_processing_allowed": False,
            "external_data_accessed": False, "database_mutated": False,
            "rubric_assessments_written": 0, "scientific_admissions": 0,
            "production_approved": False,
            "exact_digital_silence_guard": suite == "guarded",
            "cases": cases, **evaluation}


def change_case(report, case_id, transcript):
    speech, negatives, _ = diagnostic._fixture_contract(report["suite"])
    case = next(c for c in report["cases"] if c["case_id"] == case_id)
    case["transcript"] = transcript
    case.update(asr.word_errors(case["reference"], transcript))
    report.update(asr.evaluate_cases(report["cases"], speech, negatives))


@pytest.mark.parametrize("suite", ["baseline", "challenge", "guarded"])
def test_valid_synthetic_report_scoped_without_release(suite):
    report = report_for(suite)
    original = deepcopy(report)
    result = diagnostic.diagnose_asr_report(report)
    assert report == original
    assert result["suite"] == suite
    assert result["engineering_gate_passed_in_source_report"] is True
    assert result["strict_failure_cases"] == []
    assert result["production_approved"] is False
    assert result["global_gates_released"] is False
    assert result["independently_attested_model"] is False
    assert len(result["cases"]) == len(report["cases"])
    assert all(len(r["edits"]) == 0 for r in result["cases"])


def test_failed_wer_is_explained_but_does_not_become_pass():
    report = report_for()
    change_case(report, "cta", "")
    assert report["engineering_gate_passed"] is False
    result = diagnostic.diagnose_asr_report(report)
    row = next(r for r in result["cases"] if r["case_id"] == "cta")
    assert row["wer"] == 1
    assert row["word_errors"] == len(asr.normalize_words(row_from_report(report,"cta")["reference"]))
    assert row["counts"]["deletion"] == row["word_errors"]
    assert row["strict_case_wer_exceeded"] is True
    assert result["strict_failure_cases"] == ["cta"]
    assert result["engineering_gate_passed_in_source_report"] is False
    assert result["production_approved"] is False


def row_from_report(report, case_id):
    return next(r for r in report["cases"] if r["case_id"] == case_id)


def test_negative_hallucination_is_counted_as_insertion():
    report = report_for()
    change_case(report, "silence", "Salve este post")
    result = diagnostic.diagnose_asr_report(report)
    row = next(r for r in result["cases"] if r["case_id"] == "silence")
    assert row["wer"] is None
    assert row["counts"] == {"substitution": 0, "deletion": 0, "insertion": 3}
    assert row["hallucinated_negative_words"] == 3
    assert row["case_id"] in result["strict_failure_cases"]
    assert result["engineering_gate_passed_in_source_report"] is False


def test_deterministic_alignment_produces_substitution_deletion_and_insertion():
    a = diagnostic._alignment("o fluxo de caixa", "fluxo do caixa agora")
    assert a["word_errors"] == asr.word_errors("o fluxo de caixa", "fluxo do caixa agora")["word_errors"]
    assert sum(a["counts"].values()) == a["word_errors"]
    assert all(e["operation"] in a["counts"] for e in a["edits"])
    assert diagnostic._alignment("Olá, você!", "olá você")["word_errors"] == 0


@pytest.mark.parametrize("change", [
    lambda r: r["cases"][0].update(reference="autor corrupto"),
    lambda r: r["cases"][0].update(word_errors=1, wer=0.25),
    lambda r: r["cases"].reverse(),
    lambda r: r.update(independent_gold=True),
    lambda r: r.update(external_data_accessed=True),
    lambda r: r.update(production_approved=True),
    lambda r: r.update(policy_version="wrong"),
    lambda r: r["checkpoint"].update(weights_sha256="0"*64),
    lambda r: r.update(engineering_gate_passed=False),
    lambda r: r.update(candidate="untrusted"),
])
def test_tampered_report_denied(change):
    report = report_for()
    change(report)
    with pytest.raises(diagnostic.ASRDiagnosticDenied, match="A02_ASR_SYNTHETIC_REPORT_INVALID"):
        diagnostic.diagnose_asr_report(report)


def test_failure_is_not_mistaken_for_corruption_if_metrics_match():
    report = report_for("challenge")
    change_case(report, "delivery", "")
    diag = diagnostic.diagnose_asr_report(report)
    assert not diag["engineering_gate_passed_in_source_report"]
    assert "delivery" in diag["strict_failure_cases"]


def test_one_invalid_type_fails_before_constructing_output():
    report = report_for()
    report["cases"][1]["transcript"] = None
    with pytest.raises(diagnostic.ASRDiagnosticDenied):
        diagnostic.diagnose_asr_report(report)


def test_pooled_only_failure_is_explicit_even_when_no_single_case_exceeds_limit():
    report = report_for()
    for cid, reference, _ in asr.SPEECH_FIXTURES:
        tokens = asr.normalize_words(reference)
        change_case(report, cid, " ".join(tokens[:int(len(tokens) * 0.60)]))
    assert all(case["wer"] <= asr.MAX_CASE_WER for case in report["cases"]
               if case["wer"] is not None)
    result = diagnostic.diagnose_asr_report(report)
    assert result["engineering_gate_passed_in_source_report"] is False
    assert result["strict_failure_cases"] == []
    assert result["strict_gate_failure_reasons"] == ["POOLED_WER_EXCEEDED"]
    assert result["production_approved"] is False
