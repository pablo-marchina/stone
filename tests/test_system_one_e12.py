"""DEC-017 E1.2: paired Portuguese benchmark and human gold contract tests.

No providers, weights, downloads or scientific-corpus writes in this suite.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_e12_ptbr_smoke import make_cases, EXAMPLES
from tapi_gate0.system_one_e12 import (
    E12Case, HumanReview, ReferenceLabel, evaluate_e12,
)
from tapi_gate0.system_one_e1 import (
    Decision, DecisionBundle, DeterministicTextDecider,
    EvidenceBundle, ObservedText, E1_FIELDS,
)


def _ref(field, value=None, *, locator="fixture:test#caption"):
    return ReferenceLabel(
        field_id=field,
        status="observed" if value is not None else "not_observable",
        value=value,
        evidence_locator=locator if value is not None else None,
        rationale="explicit synthetic review observation" if value is not None
                  else "insufficient textual observation",
    )


def _complete_labels(*, theme="vendas", locator="fixture:test#caption"):
    result = []
    for field in E1_FIELDS:
        result.append(_ref(field, theme if field == "tema_principal" else None,
                           locator=locator))
    return result


def _human_case(*, creator="independent_creator", content="unique_post",
                split="dev", first_theme="vendas", second_theme="vendas",
                adjudicated_theme=None, text="Dicas de vendas para a loja"):
    observed = ObservedText(
        modality="caption", text=text, locator="fixture:test#caption",
        sha256=sha256(text.encode("utf-8")).hexdigest(),
    )
    evidence = EvidenceBundle(
        tenant_id="authorized_test_tenant", content_id=content,
        creator_id=creator, source_kind="approved_local",
        rights_reference="operator-attested-local-usage-proof",
        allowed_operations=["offline_classification"],
        observation=observed,
    )
    themes = [first_theme, second_theme]
    if adjudicated_theme is not None:
        themes.append(adjudicated_theme)
    reviews = [
        HumanReview(
            reviewer_id="independent_human_" + str(i),
            reviewed_at=datetime(2026,11,4,9,0,tzinfo=timezone.utc),
            evidence_fingerprint=evidence.fingerprint(),
            labels=_complete_labels(theme=theme),
        )
        for i, theme in enumerate(themes, 1)
    ]
    return E12Case(
        evidence=evidence, split=split, gold_kind="human_consensus",
        gold_reference="operator-gold-review-evidence-record",
        human_reviews=reviews,
    )


def test_ptbr_fixture_has_fourteen_distinct_deterministic_synthetic_texts():
    cases = make_cases()
    assert len(cases) == len(EXAMPLES) == 14
    assert len({c.evidence.observation.sha256 for c in cases}) == len(cases)
    assert len({c.evidence.creator_id for c in cases}) == len(cases)
    assert all(c.split == "smoke" and c.gold_kind == "synthetic_fixture"
               for c in cases)
    assert all(set(x.field_id for x in c.synthetic_labels) == set(E1_FIELDS)
               for c in cases)
    assert all(c.resolved()[0]["tipo_hook"].status == "not_observable" for c in cases)


def test_paired_baseline_produces_observability_and_per_class_metrics():
    report = evaluate_e12(make_cases())
    assert report["n_cases"] == 14
    assert not report["scientifically_validated"]
    assert set(report["models"]) == {"baseline"}
    theme = report["models"]["baseline"]["fields"]["tema_principal"]
    assert theme["n_observed_gold"] >= 8
    assert theme["n_not_observable_gold"] >= 1
    assert theme["coverage_observable"] is not None
    assert theme["macro_f1_penalizing_abstention"] is not None
    assert "vendas" in theme["per_class"]
    assert report["inter_annotator"]["tema_principal"]["raw_agreement"] is None


def test_text_cannot_serve_as_video_first_three_seconds_gold():
    with pytest.raises(ValidationError, match="E12_CANNOT_GOLD_LABEL_FIRST_3_SECONDS_FROM_TEXT"):
        _ref("tipo_hook", "pergunta")


def test_text_cannot_prove_absence_of_cta_and_offer_in_video():
    with pytest.raises(ValidationError, match="E12_TEXT_CANNOT_PROVE_VIDEO_WIDE_ABSENCE"):
        _ref("tem_cta", False)
    with pytest.raises(ValidationError, match="E12_TEXT_CANNOT_PROVE_VIDEO_WIDE_ABSENCE"):
        _ref("oferta_ou_beneficio_explicito", False)


def test_missing_label_or_forged_locator_is_blocked():
    case = make_cases()[0]
    partial = list(case.synthetic_labels[:-1])
    with pytest.raises(ValidationError, match="E12_REQUIRES_SEVEN_UNIQUE"):
        E12Case(evidence=case.evidence, split="smoke",
                gold_kind="synthetic_fixture", synthetic_labels=partial)
    wrong = [p.model_copy(update={"evidence_locator": "invented:caption"})
             if p.status == "observed" else p for p in case.synthetic_labels]
    with pytest.raises(ValidationError, match="E12_GOLD_LOCATOR_MUST_MATCH_INPUT_TEXT"):
        E12Case(evidence=case.evidence, split="smoke",
                gold_kind="synthetic_fixture", synthetic_labels=wrong)


def test_human_reviews_need_approved_source_and_provenance():
    with pytest.raises(ValidationError, match="HUMAN_GOLD_REQUIRES_APPROVED"):
        case = make_cases()[0]
        E12Case(evidence=case.evidence, split="test",
                gold_kind="human_consensus", gold_reference="private-record-reference",
                human_reviews=[])


def test_two_independent_humans_agree_and_report_agreement():
    case = _human_case()
    labels, differences = case.resolved()
    assert not differences
    assert labels["tema_principal"].value == "vendas"
    report = evaluate_e12([case])
    stats = report["inter_annotator"]["tema_principal"]
    assert stats["n_double_reviewed"] == 1
    assert stats["raw_agreement"] == 1
    assert stats["n_adjudicated"] == 0
    assert report["scientifically_validated"] is False


def test_disagreement_cannot_be_silently_resolved_without_third_human():
    with pytest.raises(ValidationError, match="E12_UNRESOLVED_REVIEWER_DISAGREEMENT"):
        _human_case(second_theme="marketing")
    case = _human_case(second_theme="marketing", adjudicated_theme="vendas")
    labels, disagreement = case.resolved()
    assert disagreement == {"tema_principal"}
    assert labels["tema_principal"].value == "vendas"
    report = evaluate_e12([case])
    assert report["inter_annotator"]["tema_principal"]["raw_agreement"] == 0
    assert report["inter_annotator"]["tema_principal"]["n_adjudicated"] == 1


def test_reviewers_must_be_distinct_and_evidence_fingerprint_bound():
    case = _human_case()
    reviews = list(case.human_reviews)
    reviews[1] = reviews[1].model_copy(update={"reviewer_id": reviews[0].reviewer_id})
    with pytest.raises(ValidationError, match="DISTINCT_REVIEWERS"):
        case.model_copy(update={"human_reviews": reviews}).model_dump()
        E12Case.model_validate({**case.model_dump(), "human_reviews": [r.model_dump() for r in reviews]})
    reviews = list(case.human_reviews)
    reviews[1] = reviews[1].model_copy(update={"evidence_fingerprint": "a"*64})
    with pytest.raises(ValidationError, match="HUMAN_REVIEW_EVIDENCE_FINGERPRINT_MISMATCH"):
        E12Case.model_validate({**case.model_dump(), "human_reviews": [r.model_dump() for r in reviews]})


def test_human_gold_does_not_allow_creator_leakage_between_dev_test():
    a = _human_case(creator="same_creator", content="post_a", split="dev",
                    text="Dicas de vendas para a loja A")
    b = _human_case(creator="same_creator", content="post_b", split="test",
                    text="Dicas de vendas para a loja B")
    with pytest.raises(ValueError, match="E12_CREATOR_SPLIT_LEAKAGE"):
        evaluate_e12([a,b])


def test_same_text_across_different_creators_does_not_leak_into_test():
    a = _human_case(creator="creator_a", content="post_a", split="dev")
    b = _human_case(creator="creator_b", content="post_b", split="test")
    with pytest.raises(ValueError, match="E12_DUPLICATE_TEXT_SPLIT_LEAKAGE"):
        evaluate_e12([a,b])


def test_only_aggregates_are_exported_no_raw_text_no_creator_ids():
    case = _human_case()
    output = json.dumps(evaluate_e12([case]), ensure_ascii=False)
    assert "Dicas de vendas para a loja" not in output
    assert "independent_creator" not in output
    assert "independent_human" not in output
    assert "operator-attested-local" not in output
    assert "human_consensus" in output


class AlwaysClaimCTA:
    model_id = "e12-stub-claim-all"
    model_version = "e12-stub-v1"

    def evaluate(self, evidence, fields=E1_FIELDS):
        old = DeterministicTextDecider().evaluate(evidence, fields)
        updated = []
        for d in old.decisions:
            if d.field_id == "tem_cta":
                updated.append(Decision(
                    field_id="tem_cta", value=True, abstained=False,
                    reason="synthetic_test_unsafe_claim",
                    modality=evidence.observation.modality,
                    locator=evidence.observation.locator,
                ))
            else:
                updated.append(d)
        return DecisionBundle(
            evidence_fingerprint=evidence.fingerprint(),
            model_id=self.model_id, model_version=self.model_version,
            duration_ms=0, decisions=updated,
        )


def test_claims_on_unobservable_gold_are_counted_separately():
    report = evaluate_e12(make_cases(), models={"stub": AlwaysClaimCTA()})
    m = report["models"]["stub"]["fields"]["tem_cta"]
    assert m["n_not_observable_gold"] > 0
    assert m["claims_when_gold_unobservable"] == m["n_not_observable_gold"]


def test_model_cannot_use_provenance_from_another_caption():
    class WrongLocator(AlwaysClaimCTA):
        def evaluate(self, evidence, fields=E1_FIELDS):
            old = super().evaluate(evidence, fields)
            patched = [
                d.model_copy(update={"locator": "forged:caption"})
                if not d.abstained else d for d in old.decisions
            ]
            return old.model_copy(update={"decisions": patched})
    with pytest.raises(ValueError, match="E12_MODEL_UNSUPPORTED_EVIDENCE_LOCATOR"):
        evaluate_e12(make_cases()[:1], models={"forged": WrongLocator()})


def test_cli_generates_ptbr_and_runs_offline_baseline(tmp_path):
    fixture = tmp_path / "ptbr.jsonl"
    report_path = tmp_path / "aggregate.json"
    build = subprocess.run([
        sys.executable, str(ROOT / "scripts" / "build_e12_ptbr_smoke.py"),
        "--output", str(fixture)], cwd=ROOT, capture_output=True, text=True, check=True)
    run = subprocess.run([
        sys.executable, str(ROOT / "scripts" / "benchmark_system_one_e12.py"),
        "--input", str(fixture), "--output", str(report_path), "--model", "baseline",
    ], cwd=ROOT, capture_output=True, text=True, check=True)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "14" in build.stdout
    assert "14 cases" in run.stdout
    assert report["n_cases"] == 14
    assert report["scientifically_validated"] is False
    assert report["checkpoint"] is None
    assert "Como aumentar as vendas" not in report_path.read_text(encoding="utf-8")


def test_cli_real_model_requires_opt_in_not_a_download(tmp_path, monkeypatch):
    import benchmark_system_one_e12 as cli
    fixture = tmp_path / "ptbr.jsonl"
    fixture.write_text(
        "".join(case.model_dump_json()+"\n" for case in make_cases()),
        encoding="utf-8",
    )
    monkeypatch.delenv("TAPI_SYSTEM_ONE_ENABLED", raising=False)
    with pytest.raises(SystemExit) as err:
        cli.main(["--input", str(fixture), "--output", str(tmp_path/"out.json"),
                  "--model", "both", "--model-dir", str(tmp_path/"absent")])
    assert err.value.code == 2
    assert not (tmp_path/"out.json").exists()
