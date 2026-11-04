"""DEC-017 E1.4: experimental, synthetic-only CTA policy comparison.

Compares caption-grounded decisions, not actual video-wide CTA presence.
No I/O, provider access, scientific adjudication, threshold calibration,
production selection, or modification to E1/E1.3 classifiers occurs here.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping

from .system_one_e1 import (
    DecisionBundle, DeterministicTextDecider, E1_LABELS, EvidenceBundle,
)
from .system_one_e12 import E12Case, validate_e12_dataset
from .system_one_e13 import (
    HybridTextCTADecider, NegationAwareTextDecider, explicit_nonnegated_cta_types,
)

E14_VERSION = "tapi-dec017-e14-caption-cta.v1"
KNOWN_NEGATIVE = frozenset({"negated_only", "mentioned_only"})
KNOWN_SINGLE = frozenset({"explicit_single", "mixed_single"})
STRATA = frozenset({
    "explicit_single", "mixed_single", "explicit_multiple",
    "negated_only", "mentioned_only", "undetermined",
})

# Authored text-only challenge labels. These are NOT human-reviewed gold.
# None in negative/undetermined rows means "no explicit CTA in THIS CAPTION",
# never "the post/video has no CTA". All 34 references are hardcoded separately
# from the E1.3 rule detector: the detector is not used to construct expected labels.
CAPTION_REFERENCES: dict[str, tuple[str, str | None]] = {
    "ptbr_001": ("explicit_single", "comentar"),
    "ptbr_002": ("explicit_single", "salvar"),
    "ptbr_003": ("explicit_single", "seguir"),
    "ptbr_004": ("undetermined", None),
    "ptbr_005": ("undetermined", None),
    "ptbr_006": ("undetermined", None),
    "ptbr_007": ("undetermined", None),
    "ptbr_008": ("explicit_single", "comentar"),
    "ptbr_009": ("explicit_single", "link na bio"),
    "ptbr_010": ("undetermined", None),
    "ptbr_011": ("explicit_single", "DM"),
    "ptbr_012": ("negated_only", None),
    "ptbr_013": ("undetermined", None),
    "ptbr_014": ("undetermined", None),
    "e13_001": ("negated_only", None),
    "e13_002": ("negated_only", None),
    "e13_003": ("explicit_single", "comentar"),
    "e13_004": ("mixed_single", "comentar"),
    "e13_005": ("negated_only", None),
    "e13_006": ("explicit_multiple", None),
    "e13_007": ("explicit_single", "DM"),
    "e13_008": ("explicit_single", "link na bio"),
    "e13_009": ("explicit_single", "salvar"),
    "e13_010": ("explicit_single", "seguir"),
    "e13_011": ("mentioned_only", None),
    "e13_012": ("mentioned_only", None),
    "e13_013": ("explicit_single", "comentar"),
    "e13_014": ("mixed_single", "seguir"),
    "e13_015": ("negated_only", None),
    "e13_016": ("mentioned_only", None),
    "e13_017": ("mentioned_only", None),
    "e13_018": ("explicit_single", "salvar"),
    "e13_019": ("mixed_single", "salvar"),
    "e13_020": ("explicit_single", "link na bio"),
}


@dataclass(frozen=True)
class CTAChoice:
    """Accepted affirmative caption CTA or abstention; never video-wide False."""
    presence: bool | None = None
    kind: str | None = None

    def __post_init__(self) -> None:
        if self.presence not in (True, None):
            raise ValueError("E14_NEVER_ASSERT_CTA_ABSENCE")
        if self.kind is not None and (
            self.presence is not True or self.kind not in E1_LABELS["tipo_cta"]
        ):
            raise ValueError("E14_TYPED_CTA_REQUIRES_EVIDENCED_PRESENCE")


def _choice(bundle: DecisionBundle, evidence: EvidenceBundle) -> CTAChoice:
    if bundle.evidence_fingerprint != evidence.fingerprint():
        raise ValueError("E14_EVIDENCE_FINGERPRINT_MISMATCH")
    by_field = {decision.field_id: decision for decision in bundle.decisions}
    presence = by_field.get("tem_cta")
    kind = by_field.get("tipo_cta")
    affirmative = bool(
        presence is not None
        and not presence.abstained
        and presence.value is True
        and presence.modality == evidence.observation.modality
        and presence.locator == evidence.observation.locator
    )
    selected_type = (
        kind.value if (
            affirmative and kind is not None and not kind.abstained
            and kind.modality == evidence.observation.modality
            and kind.locator == evidence.observation.locator
        ) else None
    )
    return CTAChoice(True if affirmative else None, selected_type)


class _ReplayedDecider:
    """Returns previously captured decisions; does not run model inference."""
    model_id = "e14-replayed-local-e1"
    model_version = "e14-offline-replay-v1"

    def __init__(self, bundles: Mapping[str, DecisionBundle]):
        self._bundles = bundles

    def evaluate(self, evidence: EvidenceBundle, fields=None) -> DecisionBundle:
        bundle = self._bundles[evidence.fingerprint()]
        if bundle.evidence_fingerprint != evidence.fingerprint():
            raise ValueError("E14_CACHED_FINGERPRINT_MISMATCH")
        return bundle


def _text_agreement(evidence: EvidenceBundle, raw: dict,
                    *, require_presence_head: bool) -> CTAChoice:
    """Single, unnegated observed text CTA AND matching model type required.

    The permissive arm ignores a negative/unknown PRESENCE head only when the
    same visible caption itself explicitly supports the type. Neither arm
    asserts video-wide absence. These are candidates for analysis ONLY.
    """
    observed = evidence.observation
    if observed is None:
        return CTAChoice()
    options = explicit_nonnegated_cta_types(observed.text)
    if len(options) != 1:
        return CTAChoice()
    predicted_type = raw.get("tipo_cta")
    if predicted_type != options[0] or predicted_type not in E1_LABELS["tipo_cta"]:
        return CTAChoice()
    if require_presence_head and raw.get("tem_cta") != "sim":
        return CTAChoice()
    return CTAChoice(True, predicted_type)


def _guard_existing(evidence: EvidenceBundle, original: CTAChoice) -> CTAChoice:
    """Fail closed on any absence of precise model-and-caption corroboration."""
    observed = evidence.observation
    if observed is None:
        return CTAChoice()
    options = explicit_nonnegated_cta_types(observed.text)
    if len(options) != 1 or original.kind != options[0]:
        return CTAChoice()
    return CTAChoice(True, original.kind)


def _checked_cases(cases: list[E12Case]) -> None:
    if not cases or len(cases) > 34:
        raise ValueError("E14_EXPECTS_UP_TO_34_SYNTHETIC_CASES")
    validate_e12_dataset(cases)
    ids = [case.evidence.content_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("E14_DUPLICATE_CASE_ID")
    for case in cases:
        if (case.gold_kind != "synthetic_fixture"
                or case.split != "smoke"
                or case.evidence.source_kind != "synthetic"
                or case.evidence.observation is None
                or case.evidence.content_id not in CAPTION_REFERENCES):
            raise ValueError("E14_AUTHOR_REFERENCED_SYNTHETIC_ONLY")
        stratum, expected_type = CAPTION_REFERENCES[case.evidence.content_id]
        if stratum not in STRATA or (
            (stratum in KNOWN_SINGLE) != (expected_type is not None)
        ) or (expected_type is not None and expected_type not in E1_LABELS["tipo_cta"]):
            raise ValueError("E14_INVALID_CAPTION_REFERENCE")
        gold, _ = case.resolved()
        gold_type = gold["tipo_cta"]
        if gold_type.status == "observed" and (
            stratum not in KNOWN_SINGLE or gold_type.value != expected_type
        ):
            raise ValueError("E14_REFERENCE_CONFLICTS_WITH_E12")


def _score(rows: list[tuple[str, str | None, CTAChoice]]) -> dict:
    n = len(rows)
    known_negative = [r for r in rows if r[0] in KNOWN_NEGATIVE]
    positive_single = [r for r in rows if r[0] in KNOWN_SINGLE]
    possible_multi = [r for r in rows if r[0] == "explicit_multiple"]
    unresolved = [r for r in rows if r[0] == "undetermined"]
    presence_claims = sum(choice.presence is True for _, _, choice in rows)
    type_claims = sum(choice.kind is not None for _, _, choice in rows)
    known_negative_presence = sum(c.presence is True for _, _, c in known_negative)
    known_negative_type = sum(c.kind is not None for _, _, c in known_negative)
    correct = sum(c.kind == reference for _, reference, c in positive_single)
    wrong = sum(c.kind is not None and c.kind != reference
                for _, reference, c in positive_single)
    accepted_decidable = (
        sum(c.kind is not None for _, _, c in positive_single)
        + known_negative_type
    )
    def fraction(num: int, den: int) -> float | None:
        return round(num / den, 6) if den else None

    slices = {}
    for stratum in sorted(STRATA):
        entries = [c for cat, _, c in rows if cat == stratum]
        slices[stratum] = {
            "n": len(entries),
            "presence_claims": sum(c.presence is True for c in entries),
            "type_claims": sum(c.kind is not None for c in entries),
            "type_abstentions": sum(c.kind is None for c in entries),
        }
    return {
        "n_cases": n,
        "presence_claims": presence_claims,
        "presence_abstentions": n - presence_claims,
        "type_claims": type_claims,
        "type_abstentions": n - type_claims,
        "presence_coverage_all": fraction(presence_claims, n),
        "type_coverage_all": fraction(type_claims, n),
        "known_positive_single_support": len(positive_single),
        "known_positive_correct_type": correct,
        "known_positive_wrong_type": wrong,
        "known_positive_type_abstentions": (
            len(positive_single) - correct - wrong
        ),
        "positive_caption_type_recall": fraction(correct, len(positive_single)),
        "caption_negative_support": len(known_negative),
        "caption_negative_presence_claims": known_negative_presence,
        "caption_negative_type_claims": known_negative_type,
        "caption_negative_presence_fp_rate": fraction(
            known_negative_presence, len(known_negative)
        ),
        "caption_negative_type_fp_rate": fraction(
            known_negative_type, len(known_negative)
        ),
        "selective_type_precision_decidable_caption": fraction(
            correct, accepted_decidable
        ),
        "explicit_multiple_type_claims": sum(
            c.kind is not None for _, _, c in possible_multi
        ),
        "undetermined_type_claims": sum(
            c.kind is not None for _, _, c in unresolved
        ),
        "strata": slices,
    }


def evaluate_e14_synthetic(
    cases: list[E12Case],
    *,
    gliner_bundles: Mapping[str, DecisionBundle] | None = None,
    gliner_raw: Mapping[str, dict] | None = None,
) -> dict:
    """Paired caption-specific risk / coverage analysis on authored fixtures.

    gliner_bundles and gliner_raw must be captured from the same genuine,
    offline E1 checkpoint inference; E1.4 never downloads/loads a model.
    """
    _checked_cases(cases)
    if (gliner_bundles is None) != (gliner_raw is None):
        raise ValueError("E14_MODEL_AND_RAW_MUST_BE_PAIRED")
    expected_keys = {case.evidence.fingerprint() for case in cases}
    if gliner_bundles is not None and (
        set(gliner_bundles) != expected_keys or set(gliner_raw) != expected_keys
    ):
        raise ValueError("E14_GLINER_RECORDS_MUST_MATCH_CASES")
    baseline = DeterministicTextDecider()
    negation = NegationAwareTextDecider()
    replay = _ReplayedDecider(gliner_bundles) if gliner_bundles is not None else None
    hybrid = HybridTextCTADecider(replay) if replay is not None else None
    names = ["baseline_e1_original", "rule_negation_e13"]
    if replay is not None:
        names += [
            "gliner_e1_original", "gliner_e13_rule_assisted",
            "e14_gliner_original_text_guard",
            "e14_raw_type_text_agreement",
            "e14_raw_type_text_and_presence_agreement",
        ]
    scored: dict[str, list[tuple[str, str | None, CTAChoice]]] = {
        name: [] for name in names
    }
    stratum_support = Counter()
    for case in cases:
        evidence = case.evidence
        key = evidence.fingerprint()
        stratum, expected = CAPTION_REFERENCES[evidence.content_id]
        stratum_support[stratum] += 1
        responses = {
            "baseline_e1_original": _choice(baseline.evaluate(evidence), evidence),
            "rule_negation_e13": _choice(negation.evaluate(evidence), evidence),
        }
        if replay is not None:
            raw = gliner_raw[key]
            if not isinstance(raw, dict):
                raise ValueError("E14_INVALID_RAW_RECORD")
            # The raw input is ONLY a pre-sanitized, schema-bounded label map.
            # Unknown strings cannot be emitted in any report or accepted.
            allowed_type = E1_LABELS["tipo_cta"]
            raw = {
                "tem_cta": (
                    raw.get("tem_cta") if raw.get("tem_cta")
                    in ("sim", "nao", "indefinido") else "__out_of_schema__"
                ),
                "tipo_cta": (
                    raw.get("tipo_cta") if raw.get("tipo_cta")
                    in (*allowed_type, "indefinido") else "__out_of_schema__"
                ),
            }
            original = _choice(replay.evaluate(evidence), evidence)
            responses.update({
                "gliner_e1_original": original,
                "gliner_e13_rule_assisted": _choice(hybrid.evaluate(evidence), evidence),
                "e14_gliner_original_text_guard": _guard_existing(evidence, original),
                "e14_raw_type_text_agreement": _text_agreement(
                    evidence, raw, require_presence_head=False
                ),
                "e14_raw_type_text_and_presence_agreement": _text_agreement(
                    evidence, raw, require_presence_head=True
                ),
            })
        for name, choice in responses.items():
            scored[name].append((stratum, expected, choice))

    metrics = {name: _score(rows) for name, rows in scored.items()}
    baseline_metrics = metrics["baseline_e1_original"]
    paired_differences = {}
    for name, values in metrics.items():
        if name == "baseline_e1_original":
            continue
        paired_differences[name] = {
            "delta_caption_negative_presence_claims": (
                values["caption_negative_presence_claims"]
                - baseline_metrics["caption_negative_presence_claims"]
            ),
            "delta_correct_known_positive_types": (
                values["known_positive_correct_type"]
                - baseline_metrics["known_positive_correct_type"]
            ),
            "delta_type_abstentions_all": (
                values["type_abstentions"] - baseline_metrics["type_abstentions"]
            ),
        }
    sorted_cases = sorted(cases, key=lambda c: c.evidence.content_id)
    content_digest = sha256("".join(
        c.evidence.observation.sha256 for c in sorted_cases
    ).encode("ascii")).hexdigest()
    return {
        "schema_version": E14_VERSION,
        "study_design": "paired_synthetic_caption_only_not_scientific",
        "scientifically_validated": False,
        "production_enabled": False,
        "external_content_used": False,
        "n_cases": len(cases),
        "caption_source_digest_sha256": content_digest,
        "caption_reference_origin": "author_written_synthetic_not_human_gold",
        "reference_support": dict(sorted(stratum_support.items())),
        "policies": metrics,
        "paired_differences": paired_differences,
        "model_evaluated": replay is not None,
        "decision": "NO_PRODUCTION_POLICY_SELECTED",
        "limitations": [
            "Caption negative means no affirmative CTA in that synthetic text; never no CTA in the video.",
            "False positives are caption-only synthetic challenge counts, not population FPR.",
            "No scientifically valid holdout, human inter-annotator review or confidence calibration.",
            "Coverage versus abstention is descriptive on 34 authored examples.",
            "All GLiNER-assisted policies reuse the same model decisions and raw outputs.",
            "E1 and E1.3 baseline models remain untouched and production disabled.",
        ],
    }
