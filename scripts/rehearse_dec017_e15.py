"""DEC-017 E1.5: no-network rehearsal with *simulated*, NOT human reviews.

No --input, --model-dir, --grant or production mode. Does not access authorized
posts; tests the future human-review contracts on authored artificial snippets.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from tapi_gate0.system_one_e1 import (
    DeterministicTextDecider, EvidenceBundle, ObservedText,
)
from tapi_gate0.system_one_e13 import NegationAwareTextDecider
from tapi_gate0.system_one_e14 import _choice
from tapi_gate0.system_one_e15 import (
    CTAHumanFinding, CTAReviewedCase, FrozenStudyProtocol,
    IndependentCTAReview, rehearse_e15_synthetic,
)

ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
T1 = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
T2 = datetime(2026, 10, 2, 13, tzinfo=timezone.utc)
T3 = datetime(2026, 10, 2, 15, tzinfo=timezone.utc)

# Handwritten dummy snippets. No sourced posts, public/private account data,
# human reviewers or assertions about presence/absence in a full video.
EXAMPLES = (
    ("Comente sua dúvida sobre vendas.", "affirmative_single", "comentar", "dev"),
    ("Não siga este perfil de teste.", "no_affirmative_in_observed_text", None, "dev"),
    ("Siga e salve este guia fictício.", "affirmative_multiple", None, "dev"),
    ("A palavra siga é um exemplo gramatical.", "no_affirmative_in_observed_text", None, "test"),
    ("Salve este roteiro inventado.", "affirmative_single", "salvar", "test"),
    ("O conteúdo foi publicado hoje.", "indeterminate", None, "test"),
)


def make_rehearsal() -> tuple[FrozenStudyProtocol, list[CTAReviewedCase]]:
    protocol = FrozenStudyProtocol(
        study_id="e15_rehearsal_fake_001", registered_at=T0,
        policy_names=["baseline_e1_original", "rule_negation_e13"],
    )
    cases: list[CTAReviewedCase] = []
    for i, (text, state, cta_type, split) in enumerate(EXAMPLES, 1):
        cid = f"e15_fake_{i:03d}"
        locator = f"fictional:{cid}#caption"
        evidence = EvidenceBundle(
            tenant_id="synthetic_e15",
            content_id=cid,
            creator_id=f"fake_creator_{i:03d}",
            source_kind="synthetic",
            observation=ObservedText(
                modality="caption", text=text, locator=locator,
                sha256=sha256(text.encode("utf-8")).hexdigest(),
            ),
        )
        finding = CTAHumanFinding(
            state=state, cta_type=cta_type, evidence_locator=locator,
            rationale="Fictional review outcome for dry-run contract verification.",
        )
        fp = evidence.fingerprint()
        first = IndependentCTAReview(
            reviewer_id="fake_reviewer_a", reviewed_at=T1,
            evidence_fingerprint=fp, blinded_to_model_outputs=True,
            finding=finding,
        )
        second = IndependentCTAReview(
            reviewer_id="fake_reviewer_b", reviewed_at=T2,
            evidence_fingerprint=fp, blinded_to_model_outputs=True,
            finding=finding,
        )
        third = None
        # Simulate a disagreement requiring a distinct arbitrator.
        if i == 5:
            second = second.model_copy(update={
                "finding": CTAHumanFinding(
                    state="indeterminate", evidence_locator=locator,
                    rationale="Simulated reviewer B uncertainty for workflow test.",
                ),
            })
            third = IndependentCTAReview(
                reviewer_id="fake_reviewer_c", reviewed_at=T3,
                evidence_fingerprint=fp, blinded_to_model_outputs=True,
                finding=finding,
            )
        cases.append(CTAReviewedCase(
            evidence=evidence, split=split, first=first, second=second,
            adjudication=third,
        ))
    return protocol, cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="E1.5 synthetic reviewer rehearsal; NO external data accepted",
    )
    parser.add_argument("--output", required=True, help="Aggregate JSON outside Git checkout")
    args = parser.parse_args(argv)
    output = Path(args.output).expanduser().resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error("E15_REHEARSAL_REPORT_OUTSIDE_GIT_REQUIRED")
    if output.exists():
        parser.error("E15_DO_NOT_OVERWRITE_FROZEN_REHEARSAL_REPORT")
    protocol, cases = make_rehearsal()
    baseline = DeterministicTextDecider()
    negation = NegationAwareTextDecider()
    predictions = {
        "baseline_e1_original": {
            c.evidence.fingerprint(): _choice(baseline.evaluate(c.evidence), c.evidence)
            for c in cases
        },
        "rule_negation_e13": {
            c.evidence.fingerprint(): _choice(negation.evaluate(c.evidence), c.evidence)
            for c in cases
        },
    }
    report = rehearse_e15_synthetic(cases, protocol, predictions)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("E1.5 SYNTHETIC REHEARSAL PASS:", report["n_total"],
          "fictional examples; independent human gold NOT available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
