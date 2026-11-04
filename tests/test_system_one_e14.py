"""DEC-017 E1.4: contract, risk, privacy and model-gate regression tests."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark_system_one_e14 import main as benchmark_main
from build_e13_cta_challenges import make_cases
from tapi_gate0.system_one_e1 import LocalGLiNERDecider
from tapi_gate0.system_one_e13 import SyntheticRawRecorder
from tapi_gate0.system_one_e14 import (
    CAPTION_REFERENCES, CTAChoice, evaluate_e14_synthetic,
)


def _case(case_id):
    return next(c for c in make_cases() if c.evidence.content_id == case_id)


class FixedRawModel:
    """Synthetic stub, NOT a real checkpoint benchmark."""
    def __init__(self, presence="nao", cta_type="comentar"):
        self.presence = presence
        self.cta_type = cta_type
        self.calls = 0

    def classify_text(self, text, schema):
        self.calls += 1
        return {
            "tem_cta": self.presence,
            "tipo_cta": self.cta_type,
            "tema_principal": "vendas",
        }


def _recorded_model(monkeypatch, tmp_path, cases, *, cta_type="comentar"):
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    model = FixedRawModel(cta_type=cta_type)
    recorder = SyntheticRawRecorder(model)
    local = LocalGLiNERDecider(tmp_path, _test_model=recorder)
    bundles, raw = {}, {}
    for case in cases:
        key = case.evidence.fingerprint()
        bundles[key] = local.evaluate(case.evidence)
        raw[key] = recorder.by_text_sha[case.evidence.observation.sha256][-1]
    assert model.calls == len(cases)
    return bundles, raw


def test_e14_has_exactly_34_authored_references_independent_from_detector():
    cases = make_cases()
    assert len(cases) == len(CAPTION_REFERENCES) == 34
    assert {c.evidence.content_id for c in cases} == set(CAPTION_REFERENCES)
    assert CAPTION_REFERENCES["ptbr_012"] == ("negated_only", None)
    assert CAPTION_REFERENCES["e13_006"] == ("explicit_multiple", None)
    assert CAPTION_REFERENCES["e13_019"] == ("mixed_single", "salvar")
    assert not any(
        c.resolved()[0]["tem_cta"].value is False
        for c in cases
    )


def test_baseline_report_counts_support_and_never_claims_video_wide_absence():
    report = evaluate_e14_synthetic(make_cases())
    assert report["n_cases"] == 34
    assert report["model_evaluated"] is False
    assert report["scientifically_validated"] is False
    assert report["production_enabled"] is False
    assert report["decision"] == "NO_PRODUCTION_POLICY_SELECTED"
    assert len(report["policies"]) == 2
    support = report["reference_support"]
    assert support == {
        "explicit_multiple": 1, "explicit_single": 14,
        "mentioned_only": 4, "mixed_single": 3,
        "negated_only": 5, "undetermined": 7,
    }
    base = report["policies"]["baseline_e1_original"]
    assert base["caption_negative_support"] == 9
    assert base["known_positive_single_support"] == 17
    assert base["caption_negative_presence_claims"] > 0
    assert base["presence_claims"] + base["presence_abstentions"] == 34
    assert base["type_claims"] + base["type_abstentions"] == 34


def test_e14_choice_never_allows_false_or_type_without_presence():
    with pytest.raises(ValueError, match="E14_NEVER_ASSERT_CTA_ABSENCE"):
        CTAChoice(False, None)
    with pytest.raises(ValueError, match="E14_TYPED_CTA_REQUIRES_EVIDENCED_PRESENCE"):
        CTAChoice(None, "comentar")
    assert CTAChoice(True, "comentar").kind == "comentar"


def test_e14_raw_type_can_recover_with_explicit_caption_agreement(monkeypatch, tmp_path):
    cases = [
        _case("e13_003"),   # explicit comment action
        _case("e13_001"),   # prohibitive negation
        _case("e13_011"),   # quoted 'siga'
        _case("e13_006"),   # ambiguous two positive actions
    ]
    bundles, raw = _recorded_model(monkeypatch, tmp_path, cases)
    report = evaluate_e14_synthetic(
        cases, gliner_bundles=bundles, gliner_raw=raw,
    )
    assert len(report["policies"]) == 7
    original = report["policies"]["gliner_e1_original"]
    permissive = report["policies"]["e14_raw_type_text_agreement"]
    gated = report["policies"]["e14_raw_type_text_and_presence_agreement"]
    assert original["type_claims"] == 0  # raw presence head said "nao"
    assert permissive["type_claims"] == 1
    assert permissive["known_positive_correct_type"] == 1
    assert permissive["caption_negative_type_claims"] == 0
    assert permissive["explicit_multiple_type_claims"] == 0
    assert gated["type_claims"] == 0
    assert report["model_evaluated"] is True
    assert "Não siga" not in json.dumps(report, ensure_ascii=False)
    assert "fictitious_creator" not in json.dumps(report)


def test_e14_raw_type_agreement_refuses_unknown_and_model_disagreement(
    monkeypatch, tmp_path,
):
    case = _case("e13_003")
    bundles, raw = _recorded_model(monkeypatch, tmp_path, [case])
    key = case.evidence.fingerprint()
    raw[key]["tipo_cta"] = "a private unsafe string"
    report = evaluate_e14_synthetic(
        [case], gliner_bundles=bundles, gliner_raw=raw,
    )
    assert report["policies"]["e14_raw_type_text_agreement"]["type_claims"] == 0
    assert "a private unsafe string" not in json.dumps(report)
    raw[key]["tipo_cta"] = "seguir"  # in schema, but contradicted by caption
    report = evaluate_e14_synthetic(
        [case], gliner_bundles=bundles, gliner_raw=raw,
    )
    assert report["policies"]["e14_raw_type_text_agreement"]["type_claims"] == 0


def test_e14_rejects_incomplete_or_unpaired_real_model_records(monkeypatch, tmp_path):
    case = _case("e13_003")
    bundles, raw = _recorded_model(monkeypatch, tmp_path, [case])
    with pytest.raises(ValueError, match="E14_MODEL_AND_RAW_MUST_BE_PAIRED"):
        evaluate_e14_synthetic([case], gliner_bundles=bundles)
    with pytest.raises(ValueError, match="E14_GLINER_RECORDS_MUST_MATCH_CASES"):
        evaluate_e14_synthetic([case], gliner_bundles={}, gliner_raw=raw)


def test_e14_rejects_non_synthetic_or_unknown_reference():
    case = _case("e13_003")
    unauthorized = case.model_copy(update={"gold_kind": "human_consensus"})
    with pytest.raises(ValueError, match="E14_AUTHOR_REFERENCED_SYNTHETIC_ONLY"):
        evaluate_e14_synthetic([unauthorized])
    unknown_evidence = case.evidence.model_copy(
        update={"content_id": "unknown_case_id"},
    )
    unknown = case.model_copy(update={"evidence": unknown_evidence})
    with pytest.raises(ValueError, match="E14_AUTHOR_REFERENCED_SYNTHETIC_ONLY"):
        evaluate_e14_synthetic([unknown])


def test_e14_model_cannot_run_without_opt_in(monkeypatch, tmp_path):
    monkeypatch.delenv("TAPI_SYSTEM_ONE_ENABLED", raising=False)
    model = FixedRawModel()
    evidence = _case("e13_003").evidence
    local = LocalGLiNERDecider(tmp_path, _test_model=model)
    with pytest.raises(PermissionError, match="SYSTEM_ONE_EXPERIMENT_DISABLED"):
        local.evaluate(evidence)
    assert model.calls == 0


def test_e14_baseline_cli_executes_offline_and_exports_aggregates_only(tmp_path):
    out = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "benchmark_system_one_e14.py"),
            "--output", str(out), "--model", "baseline",
        ],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert "SYNTHETIC-ONLY COMPLETE" in result.stdout
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["n_cases"] == 34
    assert report["model_mode"] == "baseline"
    assert report["checkpoint"] is None
    assert report["scientifically_validated"] is False
    assert report["raw_caption_exported"] is False
    assert len(report["policies"]) == 2
    dumped = out.read_text(encoding="utf-8")
    assert "Comente aqui qual" not in dumped
    assert "criador_ficticio" not in dumped


def test_e14_cli_refuses_model_without_opt_in_and_no_output(monkeypatch, tmp_path):
    monkeypatch.delenv("TAPI_SYSTEM_ONE_ENABLED", raising=False)
    output = tmp_path / "gliner.json"
    with pytest.raises(SystemExit) as exc:
        benchmark_main([
            "--output", str(output), "--model", "both",
            "--model-dir", str(tmp_path),
        ])
    assert exc.value.code == 2
    assert not output.exists()


def test_e14_cli_cannot_write_output_inside_checkout(tmp_path):
    with pytest.raises(SystemExit) as exc:
        benchmark_main([
            "--output", str(ROOT / "e14_report_never_write.json"),
            "--model", "baseline",
        ])
    assert exc.value.code == 2


def test_e14_cannot_claim_scientific_precision_from_synthetic_labels():
    report = evaluate_e14_synthetic(make_cases())
    assert report["study_design"] == "paired_synthetic_caption_only_not_scientific"
    assert report["caption_reference_origin"] == "author_written_synthetic_not_human_gold"
    assert "no CTA in the video" in " ".join(report["limitations"])
    assert "raw" not in report
    assert "human_gold" not in report


def test_e14_integrated_summary_whitelists_metrics_only(tmp_path):
    from validate_dec017_e14_integrated import aggregate_report
    path = tmp_path / "e14_report.json"
    path.write_text(json.dumps({
        "schema_version": "tapi-dec017-e14-caption-cta.v1",
        "n_cases": 34,
        "model_mode": "baseline",
        "policies": {
            "baseline_e1_original": {
                "n_cases": 34,
                "type_claims": 7,
                "private_caption": "Comente sobre sua loja",
                "strata": {"secret": "raw_user_text"},
            },
        },
        "raw_text": "never publish this",
    }, ensure_ascii=False), encoding="utf-8")
    out = aggregate_report(path)
    dumped = json.dumps(out, ensure_ascii=False)
    assert out["policies"]["baseline_e1_original"]["type_claims"] == 7
    assert out["scientifically_validated"] is False
    assert out["decision"] == "NO_PRODUCTION_POLICY_SELECTED"
    assert "private_caption" not in dumped
    assert "Comente sobre sua loja" not in dumped
    assert "raw_user_text" not in dumped
    assert "never publish" not in dumped


def test_e14_integrated_runner_refuses_in_repo_output(monkeypatch):
    from validate_dec017_e14_integrated import main
    with pytest.raises(SystemExit) as exc:
        main(["--output-dir", str(ROOT / "validation_must_not_create")])
    assert exc.value.code == 2
    assert not (ROOT / "validation_must_not_create").exists()


def test_e14_integrated_no_stale_metrics_after_failed_stage(tmp_path):
    from validate_dec017_e14_integrated import aggregate_report
    path = tmp_path / "missing.json"
    assert aggregate_report(path) == {}
