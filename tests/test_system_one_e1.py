"""DEC-017 E1: offline contracts, evidence integrity, safe abstention and paired metrics."""
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from tapi_gate0.system_one_e1 import (
    Decision, EvidenceBundle, ObservedText, DeterministicTextDecider,
    LocalGLiNERDecider, to_rubric_assessment,
)
from tapi_gate0.system_one_benchmark import BenchmarkCase, evaluate_paired


def evidence(text="Como vender mais? Comente sua dúvida!", *, modality="caption",
             source_kind="synthetic", creator_id="creator1", content_id="post1",
             rights_reference=None, allowed_operations=None):
    return EvidenceBundle(
        tenant_id="testenant", creator_id=creator_id, content_id=content_id,
        source_kind=source_kind, rights_reference=rights_reference,
        allowed_operations=allowed_operations or [],
        observation=ObservedText(
            modality=modality, text=text, locator="fixture:post1#"+modality,
            sha256=sha256(text.encode()).hexdigest()),
    )


def result_map(result):
    return {d.field_id: d for d in result.decisions}


def test_baseline_positive_caption_and_evidence_rubric():
    data = evidence()
    model = DeterministicTextDecider()
    first = model.evaluate(data)
    assert first.evidence_fingerprint == model.evaluate(data).evidence_fingerprint
    assert result_map(first)["tema_principal"].value == "vendas"
    assert result_map(first)["tem_cta"].value is True
    assert result_map(first)["tipo_cta"].value == "comentar"
    assert result_map(first)["mpe_targeted"].abstained
    rubric = to_rubric_assessment(data, first)
    assert len(type(rubric.values).model_fields) == 20
    assert rubric.values.tem_cta is True
    assert rubric.values.tipo_cta == "comentar"
    assert rubric.values.tema_principal == "vendas"
    assert rubric.values.hook_primeiros_3s is None
    assert rubric.values.tem_rosto is None
    assert rubric.field_evidence["tema_principal"].modality.value == "caption"
    assert rubric.field_evidence["hook_primeiros_3s"].status.value == "not_observable"
    assert rubric.assessor_kind == "model"


def test_no_caption_no_video_features_no_absence_claims():
    data = EvidenceBundle(tenant_id="testenant", creator_id="creator1",
                          content_id="post1", source_kind="synthetic")
    result = DeterministicTextDecider().evaluate(data)
    assert all(d.abstained and d.value is None and d.locator is None for d in result.decisions)
    rubric = to_rubric_assessment(data, result)
    assert rubric.values.tem_cta is None and rubric.values.tem_rosto is None


def test_ambiguous_topic_no_invented_single_label():
    found = result_map(DeterministicTextDecider().evaluate(
        evidence("Aumentar vendas e melhorar o fluxo de caixa é difícil")))
    assert found["tema_principal"].abstained
    assert found["tem_cta"].abstained
    assert found["tipo_cta"].abstained


def test_transcript_is_not_video_temporal_grounding():
    data = evidence("Como vender mais? Comente sua dúvida!", modality="transcript")
    found = result_map(DeterministicTextDecider().evaluate(data))
    assert found["tema_principal"].modality == "transcript"
    assert found["tipo_hook"].abstained
    assessment = to_rubric_assessment(data, DeterministicTextDecider().evaluate(data))
    assert assessment.values.hook_primeiros_3s is None


def test_hash_tampering_denied():
    with pytest.raises(ValidationError, match="TEXT_EVIDENCE_SHA256_MISMATCH"):
        ObservedText(modality="caption", text="text one",
                     locator="fixture:one", sha256="a"*64)


def test_source_rights_gated_even_offline():
    with pytest.raises(ValidationError, match="LOCAL_CLASSIFICATION_RIGHTS_REFERENCE_REQUIRED"):
        evidence(source_kind="approved_local")
    with pytest.raises(ValidationError, match="LOCAL_CLASSIFICATION_SCOPE_REQUIRED"):
        evidence(source_kind="approved_local", rights_reference="private-approval-reference-2026")
    good = evidence(source_kind="approved_local", rights_reference="private-approval-reference-2026",
                    allowed_operations=["offline_classification"])
    assert good.source_kind == "approved_local"


def test_reject_invalid_decision_and_unsupported_video_evidence():
    with pytest.raises(ValidationError, match="FIRST_SECONDS_NOT_OBSERVED_BY_E1"):
        Decision(field_id="tipo_hook", value="pergunta", abstained=False,
                 reason="candidate", modality="caption", locator="fixture:caption")
    with pytest.raises(ValidationError, match="TEXT_ONLY_CANNOT_ASSERT_VIDEO_WIDE_ABSENCE"):
        Decision(field_id="tem_cta", value=False, abstained=False,
                 reason="candidate", modality="caption", locator="fixture:caption")
    with pytest.raises(ValidationError, match="ABSTENTION_CANNOT_CLAIM_EVIDENCE_OR_VALUE"):
        Decision(field_id="tem_cta", value=True, abstained=True, reason="unknown")


def test_cannot_map_predictions_to_different_evidence():
    a = evidence("Como vender mais? Comente sua dúvida!")
    b = evidence("Marketing para empreendedores e clientes")
    with pytest.raises(ValueError, match="DECISIONS_EVIDENCE_MISMATCH"):
        to_rubric_assessment(b, DeterministicTextDecider().evaluate(a))


class StubLocalModel:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def classify_text(self, text, schema):
        self.calls.append((text, schema))
        return self.result


def test_local_adapter_disabled_by_default_no_model_calls(monkeypatch, tmp_path):
    fake = StubLocalModel({"tema_principal": "vendas"})
    model = LocalGLiNERDecider(tmp_path, _test_model=fake)
    monkeypatch.delenv("TAPI_SYSTEM_ONE_ENABLED", raising=False)
    with pytest.raises(PermissionError, match="SYSTEM_ONE_EXPERIMENT_DISABLED"):
        model.evaluate(evidence())
    assert not fake.calls


def test_local_adapter_whitelisted_labels_no_scores_or_temporal_claims(monkeypatch, tmp_path):
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    fake = StubLocalModel({
        "tema_principal": "vendas", "tom": "técnico", "tem_cta": "sim",
        "tipo_cta": "comentar", "oferta_ou_beneficio_explicito": "nao",
        "mpe_targeted": "sim",
    })
    result = LocalGLiNERDecider(tmp_path, _test_model=fake).evaluate(evidence())
    d = result_map(result)
    assert d["tema_principal"].value == "vendas"
    assert d["tom"].value == "técnico"
    assert d["tipo_cta"].value == "comentar"
    assert d["oferta_ou_beneficio_explicito"].abstained
    assert d["tipo_hook"].abstained
    assert d["mpe_targeted"].value is True
    assert d["tema_principal"].confidence is None
    assert "tipo_hook" not in fake.calls[0][1]
    rubric = to_rubric_assessment(evidence(), result)
    assert rubric.values.tema_principal == "vendas"
    assert "mpe_targeted" not in rubric.values.model_dump()


def test_local_adapter_invalid_labels_abstains(monkeypatch, tmp_path):
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    fake = StubLocalModel({"tema_principal": "invalid", "tom": "indefinido",
                           "tem_cta": "nao", "tipo_cta": "comentar", "mpe_targeted": True})
    d = result_map(LocalGLiNERDecider(tmp_path, _test_model=fake).evaluate(evidence()))
    assert d["tema_principal"].abstained
    assert d["tom"].abstained
    assert d["tem_cta"].abstained
    assert d["tipo_cta"].abstained
    assert d["mpe_targeted"].value is True


def test_local_adapter_local_path_required_no_remote_identifier():
    with pytest.raises(ValueError, match="LOCAL_SYSTEM_ONE_WEIGHTS_DIRECTORY_REQUIRED"):
        LocalGLiNERDecider("fastino/GLiNER2.5-multi-Decide")


def test_e1_benchmark_reports_synthetic_smoke_not_quality_proof():
    cases = [
        BenchmarkCase(evidence=evidence(content_id="post1"),
                      gold={"tema_principal": "vendas", "tem_cta": True, "tipo_cta": "comentar"}),
        BenchmarkCase(evidence=evidence("Sem descrição informativa", content_id="post2"),
                      gold={"tema_principal": "vendas"}),
    ]
    report = evaluate_paired(cases)
    assert report["scientifically_validated"] is False
    assert report["n_cases"] == 2
    metrics = report["models"]["baseline"]["field_metrics"]
    assert metrics["tema_principal"]["n_gold"] == 2
    assert metrics["tema_principal"]["coverage"] == .5
    assert metrics["tem_cta"]["coverage"] == 1.0
    assert report["models"]["baseline"]["external_api_calls"] == 0
    assert report["models"]["baseline"]["model_downloads"] == 0


def test_benchmark_reject_duplicate_ids_and_forged_human_gold():
    c = BenchmarkCase(evidence=evidence(), gold={"tema_principal": "vendas"})
    with pytest.raises(ValueError, match="DUPLICATE_E1_CONTENT"):
        evaluate_paired([c, c])
    with pytest.raises(ValidationError, match="HUMAN_GOLD_PROVENANCE_REQUIRED"):
        BenchmarkCase(evidence=evidence(), gold_kind="human_reviewed",
                      gold_reference="self-declared-review", gold={"tema_principal": "vendas"})


def test_benchmark_does_not_accept_invalid_gold_label():
    with pytest.raises(ValidationError, match="INVALID_E1_GOLD_LABEL"):
        BenchmarkCase(evidence=evidence(), gold={"tema_principal": "lucro_inventado"})


def test_rubric_rejects_forged_field_locator():
    data = evidence()
    result = DeterministicTextDecider().evaluate(data)
    corrupted = result.model_copy(update={
        "decisions": [d.model_copy(update={"locator": "forged:another-file"})
                      if not d.abstained else d for d in result.decisions]
    })
    with pytest.raises(ValueError, match="DECISION_LOCATOR_NOT_IN_EVIDENCE_BUNDLE"):
        to_rubric_assessment(data, corrupted)


def test_benchmark_computes_paired_different_model_metrics(monkeypatch, tmp_path):
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    local = LocalGLiNERDecider(tmp_path, _test_model=StubLocalModel({
        "tema_principal": "marketing", "tom": "indefinido", "tem_cta": "sim",
        "tipo_cta": "comentar", "oferta_ou_beneficio_explicito": "nao",
        "mpe_targeted": "sim"}))
    c = BenchmarkCase(evidence=evidence(), gold={"tema_principal": "vendas"})
    report = evaluate_paired([c], {"baseline": DeterministicTextDecider(), "local": local})
    assert report["models"]["baseline"]["field_metrics"]["tema_principal"]["accuracy_over_all"] == 1
    assert report["models"]["local"]["field_metrics"]["tema_principal"]["accuracy_over_all"] == 0
    assert not report["scientifically_validated"]


def test_cli_synthetic_fixture_report_is_aggregate_only(tmp_path):
    import json
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    fixture = root / 'evidence' / 'experiments' / 'dec017_e1_synthetic_smoke.jsonl'
    output = tmp_path / 'report.json'
    proc = subprocess.run([
        sys.executable, str(root / 'scripts' / 'benchmark_system_one_e1.py'),
        '--input', str(fixture), '--output', str(output), '--model', 'baseline',
    ], cwd=root, capture_output=True, text=True, check=True)
    report = json.loads(output.read_text(encoding='utf-8'))
    assert 'n=4' in proc.stdout
    assert report['n_cases'] == 4
    assert report['scientifically_validated'] is False
    assert 'Como vender mais?' not in output.read_text(encoding='utf-8')
