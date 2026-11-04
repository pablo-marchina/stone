"""DEC-017 E1.3: local synthetic CTA experiments; no real posts or weights."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_e13_cta_challenges import make_cases, CHALLENGES
from diagnose_e13_cta import main as diagnose_main, _safe_raw
from tapi_gate0.system_one_e1 import (
    Decision, DecisionBundle, DeterministicTextDecider,
    E1_FIELDS, LocalGLiNERDecider, EvidenceBundle, ObservedText,
    to_rubric_assessment,
)
from tapi_gate0.system_one_e13 import (
    HybridTextCTADecider, NegationAwareTextDecider,
    SyntheticRawRecorder, evaluate_e13_synthetic,
    explicit_nonnegated_cta_types,
)
from tapi_gate0.system_one_e12 import E12Case


def _evidence(text):
    return EvidenceBundle(
        tenant_id="synthetic_e13", content_id="test_cta",
        creator_id="invented_person", source_kind="synthetic",
        observation=ObservedText(
            modality="caption", text=text, locator="synthetic:test#caption",
            sha256=sha256(text.encode("utf-8")).hexdigest(),
        ),
    )


def _decisions(result):
    return {decision.field_id: decision for decision in result.decisions}


def test_negation_detector_rejects_direct_negated_imperative():
    assert explicit_nonnegated_cta_types("NÃO siga este perfil.") == ()
    assert explicit_nonnegated_cta_types("Não salve esta publicação.") == ()
    assert explicit_nonnegated_cta_types("Nunca comente nem siga.") == ()


def test_negation_detector_does_not_suppress_independent_positive_cta():
    assert explicit_nonnegated_cta_types(
        "Não siga este perfil, mas comente a sua dúvida."
    ) == ("comentar",)


def test_negation_detector_keeps_affirmative_ctas():
    assert explicit_nonnegated_cta_types("Siga esta loja e comente aqui!") == (
        "comentar", "seguir",
    )


def test_original_baseline_retained_and_negation_variant_abstains():
    case = _evidence("NÃO siga este perfil.")
    original = _decisions(DeterministicTextDecider().evaluate(case))
    variant = _decisions(NegationAwareTextDecider().evaluate(case))
    assert original["tem_cta"].value is True
    assert original["tipo_cta"].value == "seguir"
    assert variant["tem_cta"].abstained
    assert variant["tipo_cta"].abstained
    assert variant["tem_cta"].value is None
    assert variant["tipo_cta"].value is None


def test_negation_variant_positive_type_and_same_evidence_proof():
    evidence = _evidence("Não siga o perfil anterior, mas comente esta dúvida.")
    result = NegationAwareTextDecider().evaluate(evidence)
    found = _decisions(result)
    assert found["tem_cta"].value is True
    assert found["tipo_cta"].value == "comentar"
    assert result.evidence_fingerprint == evidence.fingerprint()
    rubric = to_rubric_assessment(evidence, result)
    assert rubric.values.tem_cta is True
    assert rubric.values.tipo_cta == "comentar"
    assert rubric.values.hook_primeiros_3s is None


def test_negation_variant_never_claims_video_wide_cta_absence():
    result = NegationAwareTextDecider().evaluate(
        _evidence("Nenhuma legenda com CTA.")
    )
    found = _decisions(result)
    assert found["tem_cta"].abstained
    assert found["tipo_cta"].abstained


class StaticCTAClassifier:
    def __init__(self, *, raw_presence="nao", raw_kind="comentar"):
        self.raw_presence = raw_presence
        self.raw_kind = raw_kind
        self.calls = 0

    def classify_text(self, text, schema):
        self.calls += 1
        return {
            "tem_cta": self.raw_presence,
            "tipo_cta": self.raw_kind,
            "tema_principal": "vendas",
        }


def test_gliner_adapter_cascade_is_exposed_and_not_silently_redefined(monkeypatch, tmp_path):
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    evidence = _evidence("Comente aqui sua dúvida de vendas.")
    raw = StaticCTAClassifier(raw_presence="nao", raw_kind="comentar")
    recorder = SyntheticRawRecorder(raw)
    gliner = LocalGLiNERDecider(tmp_path, _test_model=recorder)
    original = _decisions(gliner.evaluate(evidence))
    hybrid = _decisions(HybridTextCTADecider(gliner).evaluate(evidence))
    assert original["tem_cta"].abstained
    assert original["tipo_cta"].reason == "cta_presence_not_corroborated"
    assert hybrid["tem_cta"].value is True
    assert hybrid["tipo_cta"].value == "comentar"
    assert hybrid["tipo_cta"].reason == "e13_explicit_text_cta_rule"
    assert original["tipo_cta"].abstained  # original E1 remains a control


def test_hybrid_must_not_force_type_when_caption_negates_it(monkeypatch, tmp_path):
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    evidence = _evidence("NÃO siga este perfil.")
    gliner = LocalGLiNERDecider(
        tmp_path, _test_model=StaticCTAClassifier(raw_presence="nao",raw_kind="seguir")
    )
    hybrid = _decisions(HybridTextCTADecider(gliner).evaluate(evidence))
    assert hybrid["tem_cta"].abstained
    assert hybrid["tipo_cta"].abstained


def test_raw_recorder_never_stores_text_or_out_of_schema_label():
    class EchoSensitive:
        def classify_text(self, text, schema):
            return {"tem_cta": "texto privado literal: " + text}
    recorder = SyntheticRawRecorder(EchoSensitive())
    recorder.classify_text("este texto fica apenas na entrada", {"tem_cta": ["sim", "nao"]})
    encoded = json.dumps(recorder.by_text_sha)
    assert "este texto fica apenas na entrada" not in encoded
    assert "texto privado literal" not in encoded
    assert "__out_of_schema__" in encoded


def test_raw_sanitization_accepts_only_schema_options():
    assert _safe_raw({"tem_cta":"sim"}, "tem_cta", ["sim","nao"]) == "sim"
    assert _safe_raw({"tem_cta":"unsupported text"}, "tem_cta", ["sim","nao"]) == "__out_of_schema__"


def test_synthetic_fixture_expanded_with_no_video_wide_false():
    cases = make_cases()
    assert len(cases) == 14 + len(CHALLENGES)
    assert len({c.evidence.observation.sha256 for c in cases}) == len(cases)
    assert all(c.gold_kind == "synthetic_fixture" for c in cases)
    assert all(c.resolved()[0]["tipo_hook"].status == "not_observable" for c in cases)
    assert all(
        c.resolved()[0]["tem_cta"].value is not False
        for c in cases
    )


def test_diagnostic_confusions_and_abstention_counts_are_aggregate_only():
    cases = make_cases()
    report = evaluate_e13_synthetic(cases, {
        "original": DeterministicTextDecider(),
        "negation_aware": NegationAwareTextDecider(),
    })
    assert report["n_cases"] == len(cases)
    assert report["scientifically_validated"] is False
    matrix = report["diagnostics"]["original"]["confusion_observed"]["tem_cta"]
    assert all(set(row) == {"gold", "predicted", "n"} for row in matrix)
    assert sum(row["n"] for row in matrix) == (
        report["models"]["original"]["fields"]["tem_cta"]["n_observed_gold"]
    )
    assert report["diagnostics"]["original"]["predictions_when_reference_unobservable"]["tipo_hook"]


def test_diagnostic_captures_raw_cta_cascade_counts(monkeypatch, tmp_path):
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    case = next(x for x in make_cases() if x.evidence.content_id == "e13_003")
    recorder = SyntheticRawRecorder(StaticCTAClassifier())
    gliner = LocalGLiNERDecider(tmp_path, _test_model=recorder)
    report = evaluate_e13_synthetic(
        [case], {
            "baseline_original": DeterministicTextDecider(),
            "gliner": gliner,
            "gliner_rule_assisted_experimental": HybridTextCTADecider(gliner),
        },
        raw_recorder=recorder,
    )
    assert report["n_cta_cascade_blocked"] == 1
    trace = report["synthetic_cta_trace"][0]
    assert trace["joint_raw_tem_cta"] == "nao"
    assert trace["joint_raw_tipo_cta"] == "comentar"
    assert trace["post_adapter_tipo_cta_reason"] == "cta_presence_not_corroborated"
    assert "Comente aqui" not in json.dumps(report)


def test_diagnostic_refuses_human_gold_even_if_authorized():
    case = make_cases()[0].model_copy(update={"gold_kind": "human_consensus"})
    with pytest.raises(ValueError, match="E13_SYNTHETIC_INPUT_ONLY"):
        evaluate_e13_synthetic([case], {"baseline": DeterministicTextDecider()})


def test_diagnostic_rejects_zero_models():
    with pytest.raises(ValueError, match="E13_MODELS_REQUIRED"):
        evaluate_e13_synthetic(make_cases()[:1], {})


def test_cli_baseline_generates_no_real_content_or_model_weights(tmp_path):
    fixture = tmp_path / "e13_synthetic.jsonl"
    output = tmp_path / "e13_aggregate.json"
    gen = subprocess.run([
        sys.executable, str(ROOT / "scripts" / "build_e13_cta_challenges.py"),
        "--output", str(fixture),
    ], cwd=ROOT, capture_output=True, text=True, check=True)
    run = subprocess.run([
        sys.executable, str(ROOT / "scripts" / "diagnose_e13_cta.py"),
        "--input", str(fixture), "--output", str(output), "--model", "baseline",
    ], cwd=ROOT, capture_output=True, text=True, check=True)
    assert "synthetic" in gen.stdout
    assert "SYNTHETIC ONLY PASS" in run.stdout
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["scientifically_validated"] is False
    assert result["n_cases"] == len(make_cases())
    assert result["model_checkpoint"] is None
    assert "NÃO siga este perfil" not in output.read_text(encoding="utf-8")


def test_cli_both_fails_closed_when_e13_flag_off(tmp_path, monkeypatch):
    monkeypatch.delenv("TAPI_SYSTEM_ONE_ENABLED", raising=False)
    fixture = tmp_path / "synthetic.jsonl"
    fixture.write_text(
        "".join(c.model_dump_json() + "\n" for c in make_cases()), encoding="utf-8",
    )
    output = tmp_path / "aggregate.json"
    with pytest.raises(SystemExit) as err:
        diagnose_main([
            "--input", str(fixture), "--output", str(output), "--model", "both",
            "--model-dir", str(tmp_path / "no_model"),
        ])
    assert err.value.code == 2
    assert not output.exists()


def test_ablation_requires_real_model_opt_in(tmp_path):
    fixture = tmp_path / "synthetic.jsonl"
    fixture.write_text(
        "".join(c.model_dump_json() + "\n" for c in make_cases()), encoding="utf-8",
    )
    with pytest.raises(SystemExit) as err:
        diagnose_main([
            "--input", str(fixture), "--output", str(tmp_path/"out.json"),
            "--model", "baseline", "--ablate-cta-heads",
        ])
    assert err.value.code == 2


def test_head_isolation_compares_joint_and_solo_without_exposing_text():
    from diagnose_e13_cta import _ablate_individual_cta_heads

    class IsolatedHeadClassifier:
        def classify_text(self, text, schema):
            if list(schema) == ["tem_cta"]:
                return {"tem_cta": "sim"}
            if list(schema) == ["tipo_cta"]:
                return {"tipo_cta": "comentar"}
            raise AssertionError("only isolated heads should be queried")

    case = next(x for x in make_cases() if x.evidence.content_id == "e13_003")
    joint = [{
        "synthetic_case_id": case.evidence.content_id,
        "joint_raw_tem_cta": "nao",
        "joint_raw_tipo_cta": "comentar",
    }]
    report = _ablate_individual_cta_heads(IsolatedHeadClassifier(), [case], joint)
    assert report["joint_vs_solo_changed"] == {"tem_cta": 1, "tipo_cta": 0}
    assert report["n_cases"] == 1
    assert "Comente aqui" not in json.dumps(report)


def test_e13_consolidated_direct_negative_and_double_negative():
    from tapi_gate0.system_one_e13 import directly_negated_cta_types
    assert directly_negated_cta_types("Não siga este perfil.") == ("seguir",)
    assert directly_negated_cta_types("Nunca comente sua senha.") == ("comentar",)
    assert directly_negated_cta_types("Não deixe de seguir este perfil.") == ()
    assert explicit_nonnegated_cta_types("Não deixe de seguir este perfil.") == ("seguir",)
    assert directly_negated_cta_types("Não comente sua senha; salve o guia.") == ("comentar",)
    assert explicit_nonnegated_cta_types("Não comente sua senha; salve o guia.") == ("salvar",)


def test_e13_consolidated_includes_unique_pr27_synthetic_cases():
    cases = make_cases()
    assert len(cases) == 34  # 14 E1.2 + 14 original PR28 + 6 PR27-only edge cases
    assert any(
        "Não clique no link na bio" in case.evidence.observation.text
        for case in cases
    )
    assert all(c.resolved()[0]["tem_cta"].value is not False for c in cases)


def test_e13_consolidated_cta_conflict_histograms_no_captions(monkeypatch, tmp_path):
    from tapi_gate0.system_one_e13 import summarize_e13_cta_evidence
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    case = next(c for c in make_cases() if c.evidence.content_id == "e13_003")
    recorder = SyntheticRawRecorder(StaticCTAClassifier(
        raw_presence="nao", raw_kind="comentar"
    ))
    gliner = LocalGLiNERDecider(tmp_path, _test_model=recorder)
    report = evaluate_e13_synthetic([case], {
        "baseline_original": DeterministicTextDecider(),
        "gliner": gliner,
    }, raw_recorder=recorder)
    consolidated = summarize_e13_cta_evidence([case], report)
    assert consolidated["scientifically_validated"] is False
    assert consolidated["joint_head_histograms"]["tem_cta"] == {"nao": 1}
    assert consolidated["joint_head_histograms"]["tipo_cta"] == {"comentar": 1}
    assert consolidated["cta_conflicts"]["suppressed_by_presence_dependency"] == 1
    assert consolidated["case_flags"][0]["adapter_type_suppressed_by_presence"] is True
    assert "Comente aqui" not in json.dumps(consolidated)


def test_e13_consolidated_head_histograms_in_ablation():
    from diagnose_e13_cta import _ablate_individual_cta_heads

    class IsolatedClassifier:
        def classify_text(self, text, schema):
            key = next(iter(schema))
            return {key: "sim" if key == "tem_cta" else "comentar"}

    case = next(c for c in make_cases() if c.evidence.content_id == "e13_003")
    result = _ablate_individual_cta_heads(IsolatedClassifier(), [case], [{
        "synthetic_case_id": case.evidence.content_id,
        "joint_raw_tem_cta": "nao",
        "joint_raw_tipo_cta": "comentar",
    }])
    assert result["head_value_histograms"]["tem_cta"]["joint"] == {"nao": 1}
    assert result["head_value_histograms"]["tem_cta"]["solo"] == {"sim": 1}
    assert result["head_value_histograms"]["tipo_cta"]["solo"] == {"comentar": 1}


def test_e13_cli_rejects_fake_synthetic_label_before_any_inference(tmp_path):
    cases = make_cases()
    forged_evidence = cases[0].evidence.model_copy(update={
        "content_id": "pretend_synthetic_private_item",
    })
    cases[0] = cases[0].model_copy(update={"evidence": forged_evidence})
    fixture = tmp_path / "forged_synthetic.jsonl"
    fixture.write_text(
        "".join(case.model_dump_json() + "\n" for case in cases),
        encoding="utf-8",
    )
    target = tmp_path / "out.json"
    with pytest.raises(SystemExit) as failure:
        diagnose_main([
            "--input", str(fixture), "--output", str(target),
            "--model", "baseline",
        ])
    assert failure.value.code == 2
    assert not target.exists()


@pytest.mark.parametrize(("text", "expected"), [
    ("Não esqueça de salvar.", ("salvar",)),
    ("Não deixe de seguir este perfil.", ("seguir",)),
    ("A palavra 'siga' aparece no exemplo de gramática.", ()),
    ("A palavra comente é um verbo no imperativo.", ()),
    ("Você pode seguir a lista de tarefas da empresa.", ()),
    ("Se quiser, poderá seguir esses passos; não é uma instrução para seguir o perfil.", ()),
    ("Não clique no link na bio: é um aviso de segurança.", ()),
    ("Siga esta loja e comente aqui!", ("comentar", "seguir")),
    ("Não comente sua senha; salve estas dicas de segurança.", ("salvar",)),
])
def test_e13_regressions_in_ptbr_cta_context(text, expected):
    assert explicit_nonnegated_cta_types(text) == expected


def test_e13_new_experimental_patterns_do_not_mutate_institutional_cta():
    from tapi_gate0.classification import CTA
    from tapi_gate0.system_one_e13 import E13_CTA_PATTERNS
    assert CTA["salvar"] == r"\bsalv[ea]\b"
    assert E13_CTA_PATTERNS["salvar"] != CTA["salvar"]
    assert "salvar" in explicit_nonnegated_cta_types("Não esqueça de salvar.")
