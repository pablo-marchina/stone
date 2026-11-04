"""DEC-017 E1.2: defensible, text-only Portuguese benchmark.

This module never reads provider APIs, downloads a model, or writes scientific
eligibility. Human gold is an independently reviewed *experimental* reference.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from statistics import mean
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, model_validator

from .domain import Id
from .system_one_e1 import (
    DecisionModel, DeterministicTextDecider, EvidenceBundle, E1_FIELDS, E1_LABELS,
)

E12_SCHEMA = "tapi-system-one-e12.v1"
Status = Literal["observed", "not_observable", "not_applicable"]
Split = Literal["smoke", "dev", "test"]
Value = StrictStr | StrictBool


class ReferenceLabel(BaseModel):
    """Label about the same caption/transcript that the models receive."""
    model_config = ConfigDict(extra="forbid")
    field_id: str
    status: Status
    value: Value | None = None
    evidence_locator: str | None = Field(default=None, max_length=4096)
    rationale: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def enforce_text_observability(self):
        if self.field_id not in E1_LABELS:
            raise ValueError("UNKNOWN_E12_FIELD")
        if self.status == "observed":
            if self.value not in E1_LABELS[self.field_id] or not self.evidence_locator:
                raise ValueError("OBSERVED_GOLD_REQUIRES_ALLOWED_VALUE_AND_LOCATOR")
            if self.field_id == "tipo_hook":
                raise ValueError("E12_CANNOT_GOLD_LABEL_FIRST_3_SECONDS_FROM_TEXT")
            if self.field_id in {"tem_cta", "oferta_ou_beneficio_explicito"} and self.value is False:
                raise ValueError("E12_TEXT_CANNOT_PROVE_VIDEO_WIDE_ABSENCE")
        elif self.value is not None or self.evidence_locator is not None:
            raise ValueError("UNOBSERVABLE_GOLD_CANNOT_CLAIM_LABEL")
        return self


def _by_field(labels: list[ReferenceLabel]) -> dict[str, ReferenceLabel]:
    mapped = {label.field_id: label for label in labels}
    if len(labels) != len(mapped) or set(mapped) != set(E1_FIELDS):
        raise ValueError("E12_REQUIRES_SEVEN_UNIQUE_FIELD_ASSESSMENTS")
    cta = mapped["tem_cta"]
    cta_kind = mapped["tipo_cta"]
    if cta_kind.status == "observed" and not (
        cta.status == "observed" and cta.value is True
    ):
        raise ValueError("E12_CTA_TYPE_REQUIRES_OBSERVED_CTA")
    return mapped


def _verify_locator(evidence: EvidenceBundle, labels: list[ReferenceLabel]) -> None:
    observed = evidence.observation
    for value in labels:
        if value.status == "observed" and (
            observed is None or value.evidence_locator != observed.locator
        ):
            raise ValueError("E12_GOLD_LOCATOR_MUST_MATCH_INPUT_TEXT")


class HumanReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer_id: Id
    reviewed_at: datetime
    evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    labels: list[ReferenceLabel] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def check_review(self):
        if self.reviewed_at.utcoffset() is None:
            raise ValueError("HUMAN_REVIEW_TIMEZONE_REQUIRED")
        _by_field(self.labels)
        return self


class E12Case(BaseModel):
    """Synthetic smoke OR human reviewed; never silently conflate their gold."""
    model_config = ConfigDict(extra="forbid")
    evidence: EvidenceBundle
    split: Split
    gold_kind: Literal["synthetic_fixture", "human_consensus"]
    synthetic_labels: list[ReferenceLabel] = Field(default_factory=list)
    human_reviews: list[HumanReview] = Field(default_factory=list)
    gold_reference: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def secure_gold(self):
        if self.gold_kind == "synthetic_fixture":
            if (self.evidence.source_kind != "synthetic" or self.split != "smoke"
                or self.human_reviews or self.gold_reference is not None):
                raise ValueError("SYNTHETIC_E12_ONLY_IN_SMOKE")
            labels = _by_field(self.synthetic_labels)
            _verify_locator(self.evidence, list(labels.values()))
        else:
            if (self.evidence.source_kind != "approved_local" or self.split not in ("dev", "test")
                or self.synthetic_labels or not self.gold_reference
                or len(self.gold_reference.strip()) < 12):
                raise ValueError("HUMAN_GOLD_REQUIRES_APPROVED_LOCAL_AND_REFERENCE")
            if len(self.human_reviews) not in (2, 3):
                raise ValueError("HUMAN_GOLD_REQUIRES_TWO_OR_THREE_REVIEWS")
            reviewers = [review.reviewer_id for review in self.human_reviews]
            if len(set(reviewers)) != len(reviewers):
                raise ValueError("HUMAN_GOLD_REQUIRES_DISTINCT_REVIEWERS")
            for review in self.human_reviews:
                if review.evidence_fingerprint != self.evidence.fingerprint():
                    raise ValueError("HUMAN_REVIEW_EVIDENCE_FINGERPRINT_MISMATCH")
                _verify_locator(self.evidence, review.labels)
            self.resolved()
        return self

    def resolved(self) -> tuple[dict[str, ReferenceLabel], set[str]]:
        if self.gold_kind == "synthetic_fixture":
            return _by_field(self.synthetic_labels), set()
        first = _by_field(self.human_reviews[0].labels)
        second = _by_field(self.human_reviews[1].labels)
        third = _by_field(self.human_reviews[2].labels) if len(self.human_reviews) == 3 else {}
        chosen: dict[str, ReferenceLabel] = {}
        disagreements: set[str] = set()
        for field in E1_FIELDS:
            a, b = first[field], second[field]
            # Compare the scientific observation and label; human rationale
            # can differ while the adjudicated reference is the same.
            agreed = (a.status, a.value, a.evidence_locator) == (
                b.status, b.value, b.evidence_locator
            )
            if agreed:
                chosen[field] = a
            else:
                disagreements.add(field)
                if field not in third:
                    raise ValueError("E12_UNRESOLVED_REVIEWER_DISAGREEMENT")
                chosen[field] = third[field]
        _by_field(list(chosen.values()))
        return chosen, disagreements


def _macro_f1(gold: list, predicted: list, allowed: tuple) -> float | None:
    if not gold:
        return None
    scores = []
    for label in allowed:
        if label not in gold:
            continue
        tp = sum(g == label and p == label for g, p in zip(gold, predicted))
        fp = sum(g != label and p == label for g, p in zip(gold, predicted))
        fn = sum(g == label and p != label for g, p in zip(gold, predicted))
        scores.append(2*tp/(2*tp + fp + fn) if 2*tp + fp + fn else 0.0)
    return round(mean(scores), 6) if scores else None


def _percentile(samples: list[float], pct: float) -> float:
    samples = sorted(samples)
    i = (len(samples) - 1) * pct
    lo = int(i)
    hi = min(lo + 1, len(samples)-1)
    return round(samples[lo] + (samples[hi]-samples[lo])*(i-lo), 3)


def _metrics_for_field(field: str, observed: list[tuple[object, object]], not_observable: int,
                       claims_without_gold: int) -> dict:
    gold = [g for g, _ in observed]
    predicted = [p for _, p in observed]
    answered = sum(p is not None for p in predicted)
    correct = sum(g == p for g, p in observed)
    per_class = {}
    for label in E1_LABELS[field]:
        support = sum(g == label for g in gold)
        if not support:
            continue
        tp = sum(g == label and p == label for g, p in observed)
        fp = sum(g != label and p == label for g, p in observed)
        fn = sum(g == label and p != label for g, p in observed)
        per_class[str(label).lower() if isinstance(label, bool) else str(label)] = {
            "support": support,
            "precision": round(tp/(tp+fp), 6) if tp+fp else None,
            "recall": round(tp/(tp+fn), 6) if tp+fn else 0.0,
            "f1": round(2*tp/(2*tp+fp+fn), 6) if 2*tp+fp+fn else 0.0,
        }
    return {
        "n_observed_gold": len(observed),
        "n_not_observable_gold": not_observable,
        "n_answered_observable": answered,
        "coverage_observable": round(answered/len(gold),6) if gold else None,
        "accuracy_all_observable": round(correct/len(gold),6) if gold else None,
        "accuracy_when_answered": round(correct/answered,6) if answered else None,
        "macro_f1_penalizing_abstention": _macro_f1(
            gold, predicted, E1_LABELS[field]
        ),
        "claims_when_gold_unobservable": claims_without_gold,
        "per_class": per_class,
    }


def validate_e12_dataset(cases: list[E12Case]) -> None:
    """Check identities and disjoint dev/test creator/text evidence before scoring."""
    if not 1 <= len(cases) <= 2000:
        raise ValueError("E12_EXPECTS_1_TO_2000_CASES")
    identities = [(c.evidence.tenant_id, c.evidence.content_id) for c in cases]
    if len(identities) != len(set(identities)):
        raise ValueError("E12_DUPLICATE_CONTENT")
    split_by_creator: dict[tuple[str, str], set[str]] = {}
    split_by_text: dict[str, set[str]] = {}
    for c in cases:
        if c.split in {"dev", "test"}:
            split_by_creator.setdefault(
                (c.evidence.tenant_id, c.evidence.creator_id), set()
            ).add(c.split)
            if c.evidence.observation is not None:
                split_by_text.setdefault(c.evidence.observation.sha256, set()).add(c.split)
    if any(len(v) > 1 for v in split_by_creator.values()):
        raise ValueError("E12_CREATOR_SPLIT_LEAKAGE")
    if any(len(v) > 1 for v in split_by_text.values()):
        raise ValueError("E12_DUPLICATE_TEXT_SPLIT_LEAKAGE")


def evaluate_e12(cases: list[E12Case], models: dict[str, DecisionModel] | None = None,
                 *, split: Split | None = None) -> dict:
    """Aggregate paired metrics for exactly ONE split, after verifying all splits.

    Never mix dev (tuning) and test (held out) metrics into a global headline.
    """
    validate_e12_dataset(cases)
    all_splits = dict(Counter(c.split for c in cases))
    if split is None:
        if len(all_splits) != 1:
            raise ValueError("E12_SPLIT_SELECTION_REQUIRED")
        split = next(iter(all_splits))
    if split not in all_splits:
        raise ValueError("E12_SELECTED_SPLIT_EMPTY")
    scored_cases = [case for case in cases if case.split == split]
    gold_resolved = [c.resolved() for c in scored_cases]
    gold_mix = dict(Counter(c.gold_kind for c in scored_cases))
    models = {"baseline": DeterministicTextDecider()} if models is None else models
    if not models:
        raise ValueError("E12_MODELS_REQUIRED")
    results: dict = {
        "schema_version": E12_SCHEMA,
        "n_cases": len(scored_cases),
        "n_total_input_cases": len(cases),
        "scored_split": split,
        "n_unique_creators": len(set((c.evidence.tenant_id,c.evidence.creator_id) for c in scored_cases)),
        "splits": all_splits,
        "gold_kinds": gold_mix,
        "scientifically_validated": False,
        "note": "Exploratory evidence; synthetic smoke is not a scientific benchmark. Human gold requires independent audit.",
        "inter_annotator": {},
        "models": {},
    }
    for field in E1_FIELDS:
        reviews = [
            (c.human_reviews[0], c.human_reviews[1])
            for c in scored_cases if c.gold_kind == "human_consensus"
        ]
        matches = sum(
            (_by_field(a.labels)[field].status,
             _by_field(a.labels)[field].value) ==
            (_by_field(b.labels)[field].status,
             _by_field(b.labels)[field].value)
            for a,b in reviews
        )
        results["inter_annotator"][field] = {
            "n_double_reviewed": len(reviews),
            "raw_agreement": round(matches/len(reviews),6) if reviews else None,
            "n_adjudicated": sum(field in conflicts for _, conflicts in gold_resolved),
        }

    for model_name, model in models.items():
        measures = {field: {"pairs": [], "unknown": 0, "claims_without_gold": 0}
                    for field in E1_FIELDS}
        duration = []
        for case, (reference, _) in zip(scored_cases, gold_resolved):
            start = perf_counter()
            response = model.evaluate(case.evidence)
            duration.append((perf_counter()-start)*1000)
            if response.evidence_fingerprint != case.evidence.fingerprint():
                raise ValueError("E12_MODEL_EVIDENCE_MISMATCH")
            by_field = {d.field_id: d for d in response.decisions}
            if len(by_field) != len(response.decisions):
                raise ValueError("E12_MODEL_DUPLICATE_DECISION")
            for field in E1_FIELDS:
                truth = reference[field]
                prediction = by_field.get(field)
                value = None if prediction is None or prediction.abstained else prediction.value
                if prediction is not None and not prediction.abstained:
                    observation = case.evidence.observation
                    if observation is None or (
                        prediction.modality != observation.modality
                        or prediction.locator != observation.locator
                    ):
                        raise ValueError("E12_MODEL_UNSUPPORTED_EVIDENCE_LOCATOR")
                    if value not in E1_LABELS[field]:
                        raise ValueError("E12_MODEL_OUT_OF_SCHEMA_LABEL")
                if truth.status == "observed":
                    measures[field]["pairs"].append((truth.value, value))
                else:
                    measures[field]["unknown"] += 1
                    if value is not None:
                        measures[field]["claims_without_gold"] += 1
        report_fields = {}
        for field in E1_FIELDS:
            row = measures[field]
            report_fields[field] = _metrics_for_field(
                field, row["pairs"], row["unknown"], row["claims_without_gold"]
            )
        results["models"][model_name] = {
            "model_id": model.model_id,
            "model_version": model.model_version,
            "fields": report_fields,
            "latency_p50_ms": _percentile(duration, .50),
            "latency_p95_ms": _percentile(duration, .95),
            "n_evaluated_cases": len(duration),
        }
    return results
