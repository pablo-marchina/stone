"""DEC-017 E1.3: conservative CTA ablation, not production classification.

Do not change the institutional baseline or the existing GLiNER E1 adapter.
E1.3 policy variants are separate experimental arms. No provider I/O.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import re
from typing import Protocol

from .classification import CTA
from .system_one_e1 import (
    Decision, DecisionBundle, DecisionModel, DeterministicTextDecider,
    E1_FIELDS, E1_LABELS, EvidenceBundle, LocalGLiNERDecider,
)
from .system_one_e12 import E12Case, evaluate_e12

ABSTAIN = "__abstain__"
NEGATORS = frozenset({"não", "nao", "nunca", "jamais", "nem"})
CTA_FIELDS = ("tem_cta", "tipo_cta")
# Lab-only extension. The institutional classification.CTA patterns are untouched.
E13_CTA_PATTERNS = {**CTA, "salvar": r"\bsalv[ea]\b|\bsalvar\b"}


def _is_directly_negated(prefix: str) -> bool:
    """Narrow PT-BR clause-local negation check for diagnostic use only.

    Double-negated imperatives ("não deixe de seguir") are not prohibitions.
    This is deliberately not a linguistic entailment model.
    """
    lowered = prefix.casefold()
    if re.search(r"\b(?:não|nao)\s+(?:deixe|esqueça|esqueca)\s+de\s*$", lowered):
        return False
    words = re.findall(r"\b[\wÀ-ÿ]+\b", lowered)
    return bool(NEGATORS.intersection(words[-3:]))


def _cta_is_mentioned_not_requested(text: str, start: int, end: int) -> bool:
    """Conservative syntactic evidence of citation/metalinguistic CTA use.

    It does not assert full semantic disambiguation; it only abstains from
    known misleading surface forms used in synthetic diagnostic cases.
    """
    prefix = re.split(r"[.!?;:,\n]", text[:start])[-1].casefold()
    suffix = re.split(r"[.!?;:,\n]", text[end:])[0].casefold()
    if any(prefix.count(q) % 2 for q in ("'", '"', "“")):
        return True
    if re.search(r"\b(?:a palavra|o verbo|o termo)\s+$", prefix):
        return True
    if re.search(
        r"\b(?:não|nao)\s+(?:é|e)\s+(?:uma\s+)?instrução\s+para\s+$",
        prefix,
    ):
        return True
    if re.match(
        r"\s+(?:(?:a|o|os|as|essas|esses|esta|este|seus|suas)\s+)?"
        r"(?:lista|passos|orientações|orientacoes|instruções|instrucoes|"
        r"procedimentos|regras)\b",
        suffix,
    ):
        return True
    return False


def directly_negated_cta_types(text: str) -> tuple[str, ...]:
    """PR #27 diagnostic retained: report direct negative CTA matches, not claims of CTA absence."""
    negatives = set()
    for field, pattern in E13_CTA_PATTERNS.items():
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            prefix = re.split(r"[.!?;:,\n]", text[:match.start()])[-1]
            if _is_directly_negated(prefix) and not _cta_is_mentioned_not_requested(
                text, match.start(), match.end()
            ):
                negatives.add(field)
    return tuple(sorted(negatives))


def explicit_nonnegated_cta_types(text: str) -> tuple[str, ...]:
    """Small, deliberately high-precision Portuguese CTA positive detector.

    A negator up to three preceding tokens *in the same clause* blocks the
    candidate. This is NOT a general-purpose negation or intent model.
    """
    positives: list[str] = []
    for field, pattern in E13_CTA_PATTERNS.items():
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            prefix = re.split(r"[.!?;:,\n]", text[:match.start()])[-1]
            if _is_directly_negated(prefix):
                continue
            if _cta_is_mentioned_not_requested(text, match.start(), match.end()):
                continue
            positives.append(field)
            break
    return tuple(sorted(set(positives)))


def _decision(field: str, value, evidence: EvidenceBundle, reason: str) -> Decision:
    item = evidence.observation
    if item is None:
        raise ValueError("E13_OBSERVED_TEXT_REQUIRED")
    return Decision(
        field_id=field, value=value, abstained=False, reason=reason,
        modality=item.modality, locator=item.locator,
    )


def _abstain(field: str, reason: str) -> Decision:
    return Decision(field_id=field, abstained=True, reason=reason)


def _rebuild(original: DecisionBundle, decisions: list[Decision],
             *, model_id: str, version: str) -> DecisionBundle:
    return DecisionBundle(
        evidence_fingerprint=original.evidence_fingerprint,
        model_id=model_id, model_version=version,
        duration_ms=original.duration_ms, decisions=decisions,
    )


def _patch_cta(original: DecisionBundle, evidence: EvidenceBundle,
               *, only_when_abstained: bool, model_id: str,
               version: str) -> DecisionBundle:
    item = evidence.observation
    if item is None:
        return _rebuild(original, original.decisions, model_id=model_id, version=version)
    positives = explicit_nonnegated_cta_types(item.text)
    decisions = []
    current = {d.field_id: d for d in original.decisions}
    for old in original.decisions:
        if old.field_id not in CTA_FIELDS:
            decisions.append(old)
            continue
        if only_when_abstained and not old.abstained:
            decisions.append(old)
            continue
        if old.field_id == "tem_cta":
            decisions.append(
                _decision("tem_cta", True, evidence, "e13_explicit_text_cta_rule")
                if positives else _abstain("tem_cta", "e13_no_confirmed_text_cta")
            )
        else:
            # If a typed CTA is accepted, its presence must also be asserted
            # using the SAME observed text, never by inferring absent video.
            if len(positives) == 1 and (
                current.get("tem_cta") is not None
            ):
                decisions.append(
                    _decision("tipo_cta", positives[0], evidence, "e13_explicit_text_cta_rule")
                )
            else:
                decisions.append(_abstain("tipo_cta", "e13_ambiguous_or_negated_cta"))
    # Preserve consistency: do not retain a type without positive presence.
    has_presence = any(
        d.field_id == "tem_cta" and not d.abstained and d.value is True
        for d in decisions
    )
    if not has_presence:
        decisions = [
            _abstain("tipo_cta", "e13_cta_presence_not_confirmed")
            if d.field_id == "tipo_cta" and not d.abstained else d
            for d in decisions
        ]
    return _rebuild(original, decisions, model_id=model_id, version=version)


class NegationAwareTextDecider:
    """Experimental stricter rule baseline; old baseline remains unchanged."""
    model_id = "tapi-deterministic-e13-negation-experimental"
    model_version = "e13-ptbr-negation-v1"

    def __init__(self):
        self._original = DeterministicTextDecider()

    def evaluate(self, evidence: EvidenceBundle,
                 fields: tuple[str, ...] = E1_FIELDS) -> DecisionBundle:
        response = self._original.evaluate(evidence, fields)
        return _patch_cta(
            response, evidence, only_when_abstained=False,
            model_id=self.model_id, version=self.model_version,
        )


class HybridTextCTADecider:
    """GLiNER plus rule-confirmed observed CTA; NOT GLiNER-only performance."""
    model_id = "gliner2.5-e13-explicit-cta-fallback-experimental"
    model_version = "e13-gliner-with-cta-rule-v1"

    def __init__(self, local_model: DecisionModel):
        self._local_model = local_model

    def evaluate(self, evidence: EvidenceBundle,
                 fields: tuple[str, ...] = E1_FIELDS) -> DecisionBundle:
        result = self._local_model.evaluate(evidence, fields)
        return _patch_cta(
            result, evidence, only_when_abstained=True,
            model_id=self.model_id, version=self.model_version,
        )


class ObservedRawClassifier(Protocol):
    def classify_text(self, text: str, schema: dict) -> dict: ...


class SyntheticRawRecorder:
    """Capture only schema labels, never text or arbitrary model output.

    Only usable in the E1.3 synthetic runner. Trace indices are SHA-256 of
    the synthetic example text, not creator identities or private URLs.
    """
    def __init__(self, extractor: ObservedRawClassifier):
        self.extractor = extractor
        self.by_text_sha: dict[str, list[dict]] = defaultdict(list)

    def classify_text(self, text: str, schema: dict) -> dict:
        result = self.extractor.classify_text(text, schema)
        if not isinstance(result, dict):
            raise ValueError("E13_LOCAL_CLASSIFIER_OUTPUT_NOT_DICTIONARY")
        normalized = {}
        for field, allowed in schema.items():
            value = result.get(field)
            if isinstance(value, bool):
                value = "sim" if value else "nao"
            normalized[field] = value if (
                isinstance(value, str) and value in allowed
            ) else "__out_of_schema__"
        self.by_text_sha[sha256(text.encode("utf-8")).hexdigest()].append(normalized)
        return result


class RecordingDecider:
    """One trace per model/case: evidence fingerprints, not raw text."""
    def __init__(self, model: DecisionModel):
        self.model = model
        self.model_id = model.model_id
        self.model_version = model.model_version
        self.by_fingerprint: dict[str, DecisionBundle] = {}

    def evaluate(self, evidence: EvidenceBundle,
                 fields: tuple[str, ...] = E1_FIELDS) -> DecisionBundle:
        result = self.model.evaluate(evidence, fields)
        if result.evidence_fingerprint != evidence.fingerprint():
            raise ValueError("E13_MODEL_EVIDENCE_MISMATCH")
        self.by_fingerprint[evidence.fingerprint()] = result
        return result


def _label(value) -> str:
    if value is None:
        return ABSTAIN
    return str(value).lower() if isinstance(value, bool) else str(value)


def _matrix_for(model: RecordingDecider, cases: list[E12Case]) -> dict:
    by_field = {field: Counter() for field in E1_FIELDS}
    reasons = {field: Counter() for field in E1_FIELDS}
    not_observable = {field: Counter() for field in E1_FIELDS}
    for case in cases:
        response = model.by_fingerprint[case.evidence.fingerprint()]
        choices = {d.field_id: d for d in response.decisions}
        reference, _ = case.resolved()
        for field in E1_FIELDS:
            decision = choices.get(field)
            predicted = _label(
                None if decision is None or decision.abstained else decision.value
            )
            truth = reference[field]
            if truth.status == "observed":
                by_field[field][(_label(truth.value), predicted)] += 1
            else:
                not_observable[field][predicted] += 1
            reasons[field][
                decision.reason if decision is not None else "missing_decision"
            ] += 1
    return {
        "confusion_observed": {
            field: [
                {"gold": g, "predicted": p, "n": n}
                for (g, p), n in sorted(counter.items())
            ]
            for field, counter in by_field.items()
        },
        "predictions_when_reference_unobservable": {
            field: dict(sorted(counter.items()))
            for field, counter in not_observable.items()
        },
        "decision_reasons": {
            field: dict(sorted(counter.items()))
            for field, counter in reasons.items()
        },
    }


def evaluate_e13_synthetic(
    cases: list[E12Case], models: dict[str, DecisionModel],
    *, raw_recorder: SyntheticRawRecorder | None = None,
) -> dict:
    """Experimental paired diagnostics: only synthetic; no private cases allowed."""
    if not cases:
        raise ValueError("E13_EMPTY_SYNTHETIC_CASES")
    if any(
        case.gold_kind != "synthetic_fixture"
        or case.split != "smoke"
        or case.evidence.source_kind != "synthetic"
        or case.evidence.observation is None
        for case in cases
    ):
        raise ValueError("E13_SYNTHETIC_INPUT_ONLY")
    if not models:
        raise ValueError("E13_MODELS_REQUIRED")
    wrappers = {name: RecordingDecider(model) for name, model in models.items()}
    report = evaluate_e12(cases, wrappers, split="smoke")
    report["schema_version"] = "tapi-system-one-e13-diagnostic.v1"
    report["study_design"] = "synthetic_ablation_not_scientific_validation"
    report["scientifically_validated"] = False
    report["diagnostics"] = {
        name: _matrix_for(recorder, cases)
        for name, recorder in wrappers.items()
    }
    if raw_recorder is not None:
        traces = []
        cascade = 0
        for case in cases:
            item = case.evidence.observation
            raw_runs = raw_recorder.by_text_sha.get(item.sha256, [])
            # With two model arms sharing one underlying checkpoint, keep
            # only the first joint-head response for this diagnostic.
            joint = next(
                (r for r in raw_runs if "tem_cta" in r and "tipo_cta" in r),
                {},
            )
            local = wrappers.get("gliner")
            if local is not None:
                dec = {
                    d.field_id: d for d in
                    local.by_fingerprint[case.evidence.fingerprint()].decisions
                }
                gate = dec["tipo_cta"].reason
                was_blocked = (
                    gate == "cta_presence_not_corroborated"
                    and joint.get("tipo_cta") not in (
                        None, "indefinido", "__out_of_schema__",
                    )
                )
                cascade += int(was_blocked)
            else:
                gate = "not_run"
                was_blocked = False
            traces.append({
                "synthetic_case_id": case.evidence.content_id,
                "joint_raw_tem_cta": joint.get("tem_cta"),
                "joint_raw_tipo_cta": joint.get("tipo_cta"),
                "post_adapter_tipo_cta_reason": gate,
                "cta_cascade_blocked": was_blocked,
                "negation_aware_cta_types": list(
                    explicit_nonnegated_cta_types(item.text)
                ),
            })
        report["synthetic_cta_trace"] = traces
        report["n_cta_cascade_blocked"] = cascade
    report["limitations"] = [
        "Synthetic labels are not independently annotated or representative.",
        "Disagreement with not_observable synthetic gold is not proof of hallucination.",
        "Negation detection is a deliberately narrow regex, not a semantic model.",
        "Hybrid CTA uses deterministic rule fallback and is not pure GLiNER accuracy.",
        "No raw text, reviewer data or real content can be exported by this runner.",
    ]
    return report


def summarize_e13_cta_evidence(cases: list[E12Case], report: dict) -> dict:
    """Consolidated #27/#28 cross-check; raw schema labels and synthetic ordinals only.

    This reuses E1.3 recorded joint heads and re-evaluates only the existing
    deterministic baseline. It must never judge CTA absence in unobserved video.
    """
    trace = report.get("synthetic_cta_trace")
    if not isinstance(trace, list) or len(trace) != len(cases):
        raise ValueError("E13_CTA_TRACE_REQUIRED")
    joint_presence = Counter()
    joint_type = Counter()
    adapter_reasons = Counter()
    conflicts = Counter()
    rows = []
    baseline = DeterministicTextDecider()
    for index, (case, row) in enumerate(zip(cases, trace), start=1):
        if case.gold_kind != "synthetic_fixture" or case.evidence.source_kind != "synthetic":
            raise ValueError("E13_SYNTHETIC_INPUT_ONLY")
        if row["synthetic_case_id"] != case.evidence.content_id:
            raise ValueError("E13_CTA_TRACE_CASE_MISMATCH")
        observation = case.evidence.observation
        if observation is None:
            raise ValueError("E13_OBSERVED_TEXT_REQUIRED")
        negated = directly_negated_cta_types(observation.text)
        positive = explicit_nonnegated_cta_types(observation.text)
        raw_presence = row.get("joint_raw_tem_cta") or ABSTAIN
        raw_type = row.get("joint_raw_tipo_cta") or ABSTAIN
        gate = row.get("post_adapter_tipo_cta_reason") or ABSTAIN
        joint_presence[raw_presence] += 1
        joint_type[raw_type] += 1
        adapter_reasons[gate] += 1
        blocked = bool(row.get("cta_cascade_blocked"))
        conflicts["suppressed_by_presence_dependency"] += int(blocked)
        conflicts["direct_negated_imperatives"] += int(bool(negated))
        conflicts["mixed_negated_and_other_cta_candidates"] += int(bool(negated and positive))
        original = {d.field_id: d for d in baseline.evaluate(case.evidence).decisions}
        baseline_claims_presence = (
            "tem_cta" in original
            and not original["tem_cta"].abstained
            and original["tem_cta"].value is True
        )
        bad_negative_claim = bool(
            negated and not positive and baseline_claims_presence
        )
        conflicts["baseline_cta_with_only_directly_negated_candidates"] += int(
            bad_negative_claim
        )
        rows.append({
            "synthetic_case_ordinal": index,
            "has_direct_negated_imperative": bool(negated),
            "has_nonnegated_cta_candidate": bool(positive),
            "adapter_type_suppressed_by_presence": blocked,
            "baseline_claims_presence_with_only_direct_negation": bad_negative_claim,
        })
    return {
        "source_kind": "synthetic_only",
        "scientifically_validated": False,
        "joint_head_histograms": {
            "tem_cta": dict(sorted(joint_presence.items())),
            "tipo_cta": dict(sorted(joint_type.items())),
            "adapter_tipo_cta_reason": dict(sorted(adapter_reasons.items())),
        },
        "cta_conflicts": dict(sorted(conflicts.items())),
        "case_flags": rows,
        "limitations": [
            "Direct negation is a clause-local heuristic and may miss nested contexts.",
            "The synthetic fixture's negative evidence never means the video lacks CTA.",
            "No raw captions, creators or non-schema model text are exported.",
        ],
    }
