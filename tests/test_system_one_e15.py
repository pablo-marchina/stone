"""DEC-017 E1.5: simulated-reviewer tests; never real human gold."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from rehearse_dec017_e15 import (
    main as rehearsal_main, make_rehearsal, T0, T1, T2, T3,
)
from tapi_gate0.system_one_e1 import EvidenceBundle, ObservedText
from tapi_gate0.system_one_e14 import CTAChoice, _choice
from tapi_gate0.system_one_e15 import (
    AuthorizationEvidence, CTAHumanFinding, CTAReviewedCase, FrozenStudyProtocol,
    IndependentCTAReview, rehearse_e15_synthetic, validate_e15_study,
)
from tapi_gate0.system_one_e1 import DeterministicTextDecider
from tapi_gate0.system_one_e13 import NegationAwareTextDecider


def _predictions(cases):
    b, n = DeterministicTextDecider(), NegationAwareTextDecider()
    return {
        "baseline_e1_original": {
            c.evidence.fingerprint(): _choice(b.evaluate(c.evidence), c.evidence)
            for c in cases
        },
        "rule_negation_e13": {
            c.evidence.fingerprint(): _choice(n.evaluate(c.evidence), c.evidence)
            for c in cases
        },
    }


def test_e15_rehearsal_is_synthetic_with_two_reviews_and_adjudication():
    protocol, cases = make_rehearsal()
    assert len(cases) == 6
    assert {c.split for c in cases} == {"dev", "test"}
    assert all(c.evidence.source_kind == "synthetic" for c in cases)
    assert sum(c.was_adjudicated() for c in cases) == 1
    report = rehearse_e15_synthetic(cases, protocol, _predictions(cases))
    assert report["mode"] == "SYNTHETIC_REHEARSAL_ONLY"
    assert report["scientifically_validated"] is False
    assert report["rights_independently_verified_by_software"] is False
    assert report["holdout_claim_allowed"] is False
    assert report["production_enabled"] is False
    assert report["n_total"] == 6
    assert report["rehearsal_support_thresholds_would_pass"] is False
    assert report["dev"]["n_cases"] == 3
    assert report["test"]["n_cases"] == 3
    assert report["test"]["reviewer_agreement"]["n_adjudicated"] == 1
    assert report["dev"]["policies"]["baseline_e1_original"]["caption_negative_type_claims"] >= 1
    assert report["dev"]["policies"]["rule_negation_e13"]["caption_negative_type_claims"] == 0
    assert report["test"]["policies"]["rule_negation_e13"]["n_positive_correct"] == 1
    assert "Não siga" not in json.dumps(report, ensure_ascii=False)
    assert "fake_reviewer" not in json.dumps(report, ensure_ascii=False)


def test_e15_first_and_second_must_be_distinct_reviewers():
    _, cases = make_rehearsal()
    example = cases[0]
    copy = example.second.model_copy(update={"reviewer_id": example.first.reviewer_id})
    with pytest.raises(ValidationError, match="E15_INDEPENDENT_REVIEWER_IDS_REQUIRED"):
        CTAReviewedCase(
            evidence=example.evidence, split=example.split,
            first=example.first, second=copy,
        )


def test_e15_unresolved_disagreement_fails_closed():
    _, cases = make_rehearsal()
    contested = cases[4]
    with pytest.raises(ValidationError, match="E15_DISAGREEMENT_REQUIRES_THIRD_REVIEWER"):
        CTAReviewedCase(
            evidence=contested.evidence, split=contested.split,
            first=contested.first, second=contested.second,
        )


def test_e15_extraneous_or_early_adjudication_rejected():
    _, cases = make_rehearsal()
    agreed = cases[0]
    arb = cases[4].adjudication.model_copy(update={
        "evidence_fingerprint": agreed.evidence.fingerprint(),
        "finding": agreed.first.finding,
    })
    with pytest.raises(ValidationError, match="E15_UNNECESSARY_ADJUDICATION"):
        CTAReviewedCase(
            evidence=agreed.evidence, split=agreed.split,
            first=agreed.first, second=agreed.second, adjudication=arb,
        )
    contested = cases[4]
    early = contested.adjudication.model_copy(update={"reviewed_at": T1})
    with pytest.raises(ValidationError, match="E15_ADJUDICATION_MUST_FOLLOW_PRIMARY_REVIEWS"):
        CTAReviewedCase(
            evidence=contested.evidence, split=contested.split,
            first=contested.first, second=contested.second, adjudication=early,
        )


def test_e15_negative_text_not_video_absence_and_unique_type_rule():
    with pytest.raises(ValidationError, match="E15_NON_SINGLE_NEVER_ASSERTS_UNIQUE_TYPE"):
        CTAHumanFinding(
            state="no_affirmative_in_observed_text",
            cta_type="seguir", evidence_locator="fake:obs",
            rationale="No affirmative CTA in this fictional snippet",
        )
    with pytest.raises(ValidationError, match="E15_SINGLE_REQUIRES_ALLOWED_CTA_TYPE"):
        CTAHumanFinding(
            state="affirmative_single", evidence_locator="fake:obs",
            rationale="Clearly affirmative request for action",
        )
    assert CTAChoice(None, None).presence is None
    with pytest.raises(ValueError, match="E14_NEVER_ASSERT_CTA_ABSENCE"):
        CTAChoice(False, None)


def test_e15_review_requires_blind_model_agnostic_input_and_evidence_locator():
    _, cases = make_rehearsal()
    one = cases[0]
    with pytest.raises(ValidationError, match="Literal"):
        IndependentCTAReview(
            reviewer_id="fake_blinded", reviewed_at=T1,
            evidence_fingerprint=one.evidence.fingerprint(),
            blinded_to_model_outputs=False, finding=one.first.finding,
        )
    wrong = one.first.finding.model_copy(update={"evidence_locator": "wrong:caption"})
    forged = one.first.model_copy(update={"finding": wrong})
    with pytest.raises(ValidationError, match="E15_REVIEW_LOCATOR_MUST_MATCH_OBSERVED_TEXT"):
        CTAReviewedCase(
            evidence=one.evidence, split=one.split,
            first=forged, second=one.second,
        )


def test_e15_creator_and_duplicate_text_leakage_blocked():
    protocol, cases = make_rehearsal()
    one_dev, one_test = cases[0], cases[3]
    same_creator = one_test.evidence.model_copy(
        update={"creator_id": one_dev.evidence.creator_id}
    )
    fp = same_creator.fingerprint()
    changed = CTAReviewedCase(
        evidence=same_creator, split="test",
        first=one_test.first.model_copy(update={"evidence_fingerprint": fp}),
        second=one_test.second.model_copy(update={"evidence_fingerprint": fp}),
    )
    with pytest.raises(ValueError, match="E15_CREATOR_DEV_TEST_LEAKAGE"):
        validate_e15_study([*cases[:3], changed, *cases[4:]], protocol)

    # Text hash leakage, even when item IDs and creator IDs are distinct.
    source = one_dev.evidence.observation
    obs = one_test.evidence.observation.model_copy(
        update={"text": source.text, "sha256": source.sha256}
    )
    duplicate = one_test.evidence.model_copy(update={"observation": obs})
    fp2 = duplicate.fingerprint()
    revised = CTAReviewedCase(
        evidence=duplicate, split="test",
        first=one_test.first.model_copy(update={"evidence_fingerprint": fp2}),
        second=one_test.second.model_copy(update={"evidence_fingerprint": fp2}),
    )
    with pytest.raises(ValueError, match="E15_TEXT_DEV_TEST_LEAKAGE"):
        validate_e15_study([*cases[:3], revised, *cases[4:]], protocol)


def test_e15_protocol_preceding_review_and_exact_policy_names_enforced():
    protocol, cases = make_rehearsal()
    late_protocol = protocol.model_copy(update={"registered_at": T2})
    with pytest.raises(ValueError, match="E15_REGISTRATION_MUST_PRECEDE_BLINDED_REVIEWS"):
        validate_e15_study(cases, late_protocol)
    broken_policy = protocol.model_copy(update={
        "policy_names": ["rule_negation_e13", "rule_negation_e13"],
    })
    with pytest.raises(ValueError, match="E15_POLICY_SET_MISMATCH"):
        rehearse_e15_synthetic(cases, protocol, {"unexpected": {}})
    with pytest.raises(ValidationError, match="E15_POLICIES_MUST_BE_PREDECLARED"):
        FrozenStudyProtocol.model_validate(broken_policy.model_dump())


def test_e15_real_data_blocked_even_with_operator_attested_rights():
    protocol, cases = make_rehearsal()
    original = cases[0]
    evidence = EvidenceBundle(
        tenant_id=original.evidence.tenant_id,
        content_id=original.evidence.content_id,
        creator_id=original.evidence.creator_id,
        source_kind="approved_local",
        rights_reference="not-a-real-grant-for-test-only",
        allowed_operations=["offline_classification"],
        observation=original.evidence.observation,
    )
    fp = evidence.fingerprint()
    proof = AuthorizationEvidence(
        evidence_fingerprint=fp,
        rights_reference=evidence.rights_reference,
        proof_sha256="a" * 64,
        gate0b_record_reference="simulated-gate0b-record",
        verified_by="fake_offline_verifier",
        verified_at=T0 - timedelta(days=1),
        expires_at=T3 + timedelta(days=1),
        permitted_operations=[
            "offline_human_annotation", "offline_classification",
            "aggregate_evaluation",
        ],
    )
    swapped = CTAReviewedCase(
        evidence=evidence, split=original.split,
        first=original.first.model_copy(update={"evidence_fingerprint": fp}),
        second=original.second.model_copy(update={"evidence_fingerprint": fp}),
        authorization=proof,
    )
    with pytest.raises(PermissionError, match="E15_REAL_DATA_BLOCKED_PENDING_GATE0B"):
        rehearse_e15_synthetic([swapped, *cases[1:]], protocol, _predictions(cases))


def test_e15_never_accepts_incomplete_or_unpaired_predictions():
    protocol, cases = make_rehearsal()
    with pytest.raises(ValueError, match="E15_POLICY_SET_MISMATCH"):
        rehearse_e15_synthetic(
            cases, protocol, {"baseline_e1_original": {}},
        )
    predictions = _predictions(cases)
    del predictions["baseline_e1_original"][cases[0].evidence.fingerprint()]
    with pytest.raises(ValueError, match="E15_PAIRED_PREDICTIONS_REQUIRED"):
        rehearse_e15_synthetic(cases, protocol, predictions)


def test_e15_cli_writes_only_safe_aggregates_outside_checkout(tmp_path):
    target = tmp_path / "e15_report.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "rehearse_dec017_e15.py"),
         "--output", str(target)],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert "SYNTHETIC REHEARSAL PASS" in proc.stdout
    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["scientifically_validated"] is False
    dumped = target.read_text(encoding="utf-8")
    for sensitive in ("Comente sua dúvida", "fake_reviewer_a",
                      "fake_creator_001", "fictional:e15_fake_001"):
        assert sensitive not in dumped
    proc_second = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "rehearse_dec017_e15.py"),
         "--output", str(target)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert proc_second.returncode != 0
    assert "E15_DO_NOT_OVERWRITE_FROZEN_REHEARSAL_REPORT" in proc_second.stderr


def test_e15_cli_refuses_output_inside_repository():
    with pytest.raises(SystemExit) as result:
        rehearsal_main(["--output", str(ROOT / "e15_unauthorized.json")])
    assert result.value.code == 2
    assert not (ROOT / "e15_unauthorized.json").exists()
