import pytest
from hashlib import sha256
from tapi_gate0.discovery_rubric_benchmark import CASES, FIELDS, UNKNOWN
from tapi_gate0.discovery_rubric_grounded import (
    CHECK_CASES, grounded_field, rule_evidence, run_grounded_rubric_challenge,
)


class Abstain:
    def classify_text(self, text, heads):
        return {key: values[-1] for key, values in heads.items()}


class First:
    def classify_text(self, text, heads):
        return {key: values[0] for key, values in heads.items()}


@pytest.mark.parametrize("case", CASES + CHECK_CASES)
def test_rule_never_overclaims_authored_cases(case):
    _, field, expected, text = case
    row = rule_evidence(field, text)
    assert row["rule_value"] in (expected, UNKNOWN)
    for span in row["evidence_spans"]:
        assert 0 <= span["start"] < span["end"] <= len(text)
        assert span["sha256"] == sha256(text[span["start"]:span["end"]].encode()).hexdigest()


@pytest.mark.parametrize("text", [
    "Não comente.", "Comente e siga nosso perfil.",
    'O artigo cita "Comente" como exemplo.', "O link na bio foi atualizado.",
])
def test_cta_negative_ambiguous_quoted(text):
    assert rule_evidence("tipo_cta", text)["rule_value"] == UNKNOWN


def test_consensus_alone_cannot_create_candidate():
    row = grounded_field(First(), "tipo_cta", "O link na bio foi atualizado.")
    assert row["predictions"]["consensus"] == "comentar"
    assert row["candidate_value"] == UNKNOWN
    assert not row["scientific_admission"]


def test_valid_grounded_candidate_requires_agreement():
    assert grounded_field(First(), "tipo_cta", "Comente sua dúvida.")["candidate_value"] == "comentar"
    assert grounded_field(Abstain(), "tipo_cta", "Comente sua dúvida.")["candidate_value"] == UNKNOWN


def test_all_abstain_does_not_pass_any_gate():
    result = run_grounded_rubric_challenge(Abstain())
    assert result["synthetic_cases"] == len(CASES) + len(CHECK_CASES) == 62
    assert set(result["field_engineering_gate"]) == set(FIELDS)
    assert not any(result["field_engineering_gate"].values())
    assert result["rubric_assessments_written"] == result["scientific_admissions"] == 0
    assert not result["real_caption_inference_allowed"]
    assert all("caption" not in r for r in result["cases"])


def test_invalid_fields_and_caption_fail_closed():
    for field, text in [("hook_primeiros_3s", "Comente"), ("tipo_cta", ""), ("tipo_cta", "a"*10001)]:
        with pytest.raises(ValueError, match="INPUT_INVALID"):
            rule_evidence(field, text)


def test_grounded_rubric_cli_is_synthetic_only(tmp_path, monkeypatch, capsys):
    import json
    from contextlib import nullcontext
    from types import SimpleNamespace
    from scripts import a6_audience_contextual as runner
    from tapi_gate0.system_one_e1 import LocalGLiNERDecider
    monkeypatch.setenv("TAPI_SYSTEM_ONE_ENABLED", "1")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    model = tmp_path / "model"
    model.mkdir()
    checkpoint = {"manifest_present": True, "revision": "a"*40,
                  "files": {"model.safetensors": {"sha256": "b"*64}}}
    monkeypatch.setattr(runner, "_checkpoint_api", lambda: (lambda path: checkpoint, lambda path: None))
    monkeypatch.setattr(runner, "_model_runtime", lambda: (
        lambda path: LocalGLiNERDecider(path, _test_model=First()),
        SimpleNamespace(inference_mode=nullcontext)))
    assert runner.main(["--rubric-grounded-benchmark", "--model-dir", str(model),
                        "--report-name", "grounded-rubric.json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "GROUNDED_RUBRIC_BENCHMARK_COMPLETED"
    assert report["synthetic_cases"] == 62
    assert report["synthetic_only"] and not report["database_mutated"]
    assert not report["real_caption_inference_allowed"]
    assert "cases" not in report
    saved = json.loads((tmp_path/"artifacts"/"private"/"grounded-rubric.json").read_text(encoding="utf-8"))
    assert len(saved["cases"]) == 62
    assert runner.main(["--rubric-grounded-benchmark", "--manifest", "unused.json"]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "BD_AUDIENCE_BENCHMARK_SYNTHETIC_ONLY"
