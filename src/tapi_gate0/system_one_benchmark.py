"""Paired E1 benchmark of structured text decisions; no I/O and no gold fabrication."""
from __future__ import annotations

from collections import Counter
from statistics import mean
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, model_validator

from .system_one_e1 import (EvidenceBundle, E1_LABELS, DecisionModel,
                            DeterministicTextDecider)


class BenchmarkCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: EvidenceBundle
    gold: dict[str, StrictStr | StrictBool] = Field(default_factory=dict)
    gold_kind: Literal["synthetic_fixture", "human_reviewed"] = "synthetic_fixture"
    gold_reference: str | None = Field(default=None, max_length=512)
    split: Literal["smoke", "dev", "test"] = "smoke"

    @model_validator(mode="after")
    def validate_gold(self):
        for field, value in self.gold.items():
            if field not in E1_LABELS or value not in E1_LABELS[field]:
                raise ValueError("INVALID_E1_GOLD_LABEL")
        if self.gold_kind == "human_reviewed":
            if (self.evidence.source_kind != "approved_local" or
                not self.gold_reference or len(self.gold_reference.strip()) < 12):
                raise ValueError("HUMAN_GOLD_PROVENANCE_REQUIRED")
        if self.gold_kind == "synthetic_fixture" and self.evidence.source_kind != "synthetic":
            raise ValueError("SYNTHETIC_GOLD_ONLY_FOR_SYNTHETIC_DATA")
        return self


def _macro_f1(actual: list, predicted: list, labels: tuple) -> float | None:
    if not actual:
        return None
    included = set(actual)
    per_class = []
    for label in labels:
        if label not in included:
            continue
        tp = sum(g == label and p == label for g, p in zip(actual, predicted))
        fp = sum(g != label and p == label for g, p in zip(actual, predicted))
        fn = sum(g == label and p != label for g, p in zip(actual, predicted))
        per_class.append(2 * tp / (2 * tp + fp + fn) if 2*tp+fp+fn else 0.0)
    return round(mean(per_class), 6) if per_class else None


def evaluate_paired(cases: list[BenchmarkCase], models: dict[str, DecisionModel] | None = None) -> dict:
    if not cases:
        raise ValueError("EMPTY_E1_BENCHMARK")
    if len(cases) > 2000:
        raise ValueError("E1_BENCHMARK_SIZE_EXCEEDED")
    unique = [(c.evidence.tenant_id, c.evidence.content_id) for c in cases]
    if len(set(unique)) != len(unique):
        raise ValueError("DUPLICATE_E1_CONTENT")
    models = models or {"baseline": DeterministicTextDecider()}
    if not models:
        raise ValueError("NO_E1_MODELS")
    output = {"schema_version": "tapi-system-one-e1-benchmark.v1",
              "n_cases": len(cases),
              "gold_kinds": dict(Counter(c.gold_kind for c in cases)),
              "splits": dict(Counter(c.split for c in cases)),
              "scientifically_validated": False,
              "note": "Synthetic tests prove contracts only; human labels need external review and creator-separated splits.",
              "models": {}}
    for name, model in models.items():
        measurements = {key: {"gold": [], "predicted": [], "answered": 0, "total": 0}
                        for key in E1_LABELS}
        durations = []
        invalid = 0
        for case in cases:
            started = perf_counter()
            bundle = model.evaluate(case.evidence)
            durations.append((perf_counter() - started)*1000)
            if bundle.evidence_fingerprint != case.evidence.fingerprint():
                raise ValueError("BENCHMARK_EVIDENCE_FINGERPRINT_MISMATCH")
            decisions = {d.field_id: d for d in bundle.decisions}
            for key, gold in case.gold.items():
                m = measurements[key]
                decision = decisions.get(key)
                m["total"] += 1
                m["gold"].append(gold)
                m["predicted"].append(None if decision is None or decision.abstained else decision.value)
                m["answered"] += int(decision is not None and not decision.abstained)
            invalid += sum(int(not d.abstained and (d.locator is None or d.modality is None))
                           for d in bundle.decisions)
        ordered_times = sorted(durations)
        def percentile(p):
            return round(ordered_times[max(0, int((len(ordered_times)-1)*p))], 3)
        metrics = {}
        for key, m in measurements.items():
            if not m["total"]:
                continue
            labels = E1_LABELS[key]
            answered = m["answered"]
            correct = sum(g == p for g, p in zip(m["gold"], m["predicted"]))
            metrics[key] = {
                "n_gold": m["total"], "n_answered": answered,
                "coverage": round(answered / m["total"], 6),
                "accuracy_over_all": round(correct / m["total"], 6),
                "accuracy_when_answered": round(correct / answered, 6) if answered else None,
                "macro_f1_including_abstentions": _macro_f1(m["gold"], m["predicted"], labels),
            }
        output["models"][name] = {
            "model_id": model.model_id,
            "model_version": model.model_version,
            "field_metrics": metrics,
            "unsupported_evidence_claims": invalid,
            "latency_p50_ms": percentile(.50),
            "latency_p95_ms": percentile(.95),
            "external_api_calls": 0,
            "model_downloads": 0,
        }
    return output
