"""E1.3: safely diagnose CTA cascade without real posts or network."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_e13_ptbr_cta_smoke import CTA_CASES, make_cases
from diagnose_system_one_e13 import load_synthetic, main as diagnosis_main
from tapi_gate0.system_one_e13 import (
    diagnose_synthetic_cta, direct_negative_imperative, label_bucket,
)


class ContradictoryModel:
    """The model gives a CTA type, but multi-head presence says 'nao'."""
    calls = 0

    def classify_text(self, text, schema):
        self.calls += 1
        if "tem_cta" in schema and "tipo_cta" in schema:
            return {
                "tem_cta": "nao", "tipo_cta": "comentar",
                "tema_principal": "vendas", "tom": "indefinido",
                "oferta_ou_beneficio_explicito": "nao",
                "mpe_targeted": "indefinido",
            }
        if "tem_cta" in schema:
            return {"tem_cta": "sim"}
        if "tipo_cta" in schema:
            return {"tipo_cta": "comentar"}
        raise ValueError("unrecognized test schema")


def test_e13_contains_14_new_cta_cases_and_14_prior_synthetics():
    cases = make_cases()
    assert len(CTA_CASES) == 14
    assert len(cases) == 28
    assert len({c.evidence.observation.sha256 for c in cases}) == len(cases)
    assert all(c.gold_kind == "synthetic_fixture" and c.split == "smoke" for c in cases)


@pytest.mark.parametrize(("sentence", "flagged"), [
    ("Não siga este perfil: é um alerta.", ["seguir"]),
    ("Nunca comente sua senha.", ["comentar"]),
    ("Não comente dados privados; salve o guia.", ["comentar"]),
    ("Não deixe de seguir este perfil.", []),
    ("Não esqueça de salvar.", []),
    ("Comente sua experiência.", []),
])
def test_direct_negation_is_only_a_heuristic_alert(sentence, flagged):
    result = direct_negative_imperative(sentence)
    assert result == flagged


def test_raw_label_sanitization_does_not_echo_unknown_strings():
    allowed = {"tipo_cta": ["comentar", "salvar", "indefinido"]}
    assert label_bucket("private user caption", "tipo_cta", allowed) == "out_of_schema"
    assert label_bucket(None, "tipo_cta", allowed) == "missing"
    assert label_bucket({}, "tipo_cta", allowed) == "invalid_type"


def test_cascade_is_attributed_to_adapter_dependency_not_model_inability(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    cases = make_cases()[:4]
    extractor = ContradictoryModel()
    report = diagnose_synthetic_cta(cases, extractor, tmp_path)
    assert report["n_cases"] == 4
    assert report["scientifically_validated"] is False
    assert extractor.calls == 3 * len(cases)  # joint + presence only + type only
    assert report["cta_conflicts"]["suppressed_by_presence_dependency"] == 4
    assert report["cta_conflicts"]["presence_multi_vs_single_disagree"] == 4
    assert report["cta_stage_histograms"]["multi_presence"] == {"nao": 4}
    assert report["cta_stage_histograms"]["single_presence"] == {"sim": 4}
    assert report["cta_stage_histograms"]["adapter_type_reason"] == {
        "cta_presence_not_corroborated": 4,
    }
    assert all(row["adapter_type"] == "ABSTAIN" for row in report["case_diagnostics"])


def test_reporting_has_observed_confusion_and_separate_unobservable_support(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    result = diagnose_synthetic_cta(make_cases()[:14], ContradictoryModel(), tmp_path)
    assert result["observed_confusion"]["baseline"]["tem_cta"]["n_observed_gold"] > 0
    assert result["observed_confusion"]["local_gliner"]["tem_cta"]["n_observed_gold"] > 0
    assert result["paired_metrics"]["models"]["local_gliner"]["fields"]["tem_cta"]["coverage_observable"] == 0
    assert result["paired_metrics"]["scientifically_validated"] is False
    output = json.dumps(result, ensure_ascii=False)
    assert "Como aumentar as vendas" not in output
    assert "Não siga este perfil" not in output
    assert "criador_ficticio" not in output


def test_model_not_enabled_stops_before_any_classification(monkeypatch, tmp_path):
    monkeypatch.delenv("TAPI_SYSTEM_ONE_ENABLED", raising=False)
    extractor = ContradictoryModel()
    with pytest.raises(PermissionError, match="SYSTEM_ONE_EXPERIMENT_DISABLED"):
        diagnose_synthetic_cta(make_cases()[:1], extractor, tmp_path)
    assert extractor.calls == 0


def test_e13_rejects_human_or_non_smoke_inputs(monkeypatch, tmp_path):
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    case = make_cases()[0]
    forged = case.model_copy(update={"split": "test", "gold_kind": "human_consensus"})
    with pytest.raises(ValueError, match="E13_SYNTHETIC_SMOKE_ONLY"):
        diagnose_synthetic_cta([forged], ContradictoryModel(), tmp_path)


def test_e13_input_loader_rejects_non_synthetic_fixtures(tmp_path):
    target = tmp_path / "cases.jsonl"
    cases = make_cases()[:2]
    target.write_text("".join(case.model_dump_json()+"\n" for case in cases),
                      encoding="utf-8")
    assert len(load_synthetic(target)) == 2
    target.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(Exception):
        load_synthetic(target)


def test_e13_cli_stays_off_when_flag_not_set(monkeypatch, tmp_path):
    monkeypatch.delenv("TAPI_SYSTEM_ONE_ENABLED", raising=False)
    with pytest.raises(SystemExit) as exc:
        diagnosis_main([
            "--input", str(tmp_path / "not-there.jsonl"),
            "--output", str(tmp_path / "report.json"),
            "--model-dir", str(tmp_path / "weights"),
        ])
    assert exc.value.code == 2
    assert not (tmp_path / "report.json").exists()


def test_mixed_negated_and_positive_actions_are_not_claimed_as_false_positives(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    all_cases = make_cases()
    negative_only = next(c for c in all_cases if
        c.evidence.observation.text.startswith("Não siga este perfil: é um alerta sobre golpes"))
    mixed = next(c for c in all_cases if
        c.evidence.observation.text.startswith("Não comente sua senha; salve"))
    report = diagnose_synthetic_cta([negative_only, mixed], ContradictoryModel(), tmp_path)
    assert report["cta_conflicts"]["baseline_claims_cta_with_only_directly_negated_candidates"] == 1
    assert report["cta_conflicts"]["mixed_negated_and_other_cta_candidates"] == 1
    assert report["case_diagnostics"][0]["has_other_cta_regex_candidate"] is False
    assert report["case_diagnostics"][1]["has_other_cta_regex_candidate"] is True
