"""DEC-017 E1.3: synthetic-only, read-only diagnosis of CTA decision cascade.

Never evaluate real posts, print input text, log credentials, adjust production
rules, claim scientific accuracy, or bypass existing adapter guardrails.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

from .classification import CTA
from .system_one_e1 import (
    DeterministicTextDecider, E1_FIELDS, E1_LABELS, LocalGLiNERDecider,
)
from .system_one_e12 import E12Case, evaluate_e12, validate_e12_dataset


BOOL_HEAD = ("sim", "nao", "indefinido")
TYPE_HEAD = (*E1_LABELS["tipo_cta"], "indefinido")
NEGATION = re.compile(r"\b(?:não|nunca|jamais)\s*$", flags=re.IGNORECASE)


def direct_negative_imperative(text: str) -> list[str]:
    """Flag direct 'não siga', 'nunca comente', etc., not infer video-wide absence.

    Not an NLP negation solver; 'não deixe de seguir' is deliberately not
    flagged. Reports need independent manual review before changing a baseline.
    """
    low = text.casefold()
    flagged = set()
    for kind, pattern in CTA.items():
        for match in re.finditer(pattern, low):
            before = low[max(0, match.start() - 36):match.start()]
            if NEGATION.search(before):
                flagged.add(kind)
    return sorted(flagged)


def label_bucket(value, field: str, schema: dict) -> str:
    """Do not echo unknown model output strings or user-provided material."""
    if not isinstance(schema, dict) or field not in schema:
        return "head_not_requested"
    if not isinstance(schema[field], (tuple, list)):
        raise ValueError("E13_INVALID_SCHEMA")
    if isinstance(value, bool):
        value = "sim" if value else "nao"
    if value is None:
        return "missing"
    if not isinstance(value, str):
        return "invalid_type"
    if value not in schema[field]:
        return "out_of_schema"
    return value


def _model_output(value, field: str, allowed: tuple) -> str:
    if not isinstance(value, dict):
        raise ValueError("E13_NON_DICT_MODEL_OUTPUT")
    return label_bucket(value.get(field), field, {field: allowed})


class _CaptureClassifier:
    """Pass through to the real extractor; preserve only label dictionaries."""
    def __init__(self, underlying):
        self.underlying = underlying
        self.last_raw = None
        self.last_schema = None
        self.calls = 0

    def classify_text(self, text, schema):
        self.calls += 1
        self.last_schema = schema
        self.last_raw = self.underlying.classify_text(text, schema)
        return self.last_raw


class _CachedDecider:
    """Use exactly the already-observed adapter decisions for paired scoring."""
    model_id = "gliner2.5-multi-decide-local"
    model_version = "gliner2.5-multi-decide-e1-v1"

    def __init__(self, decisions):
        self.decisions = decisions

    def evaluate(self, evidence, fields=E1_FIELDS):
        result = self.decisions[evidence.fingerprint()]
        if tuple(d.field_id for d in result.decisions) != tuple(fields):
            raise ValueError("E13_CACHED_FIELDS_MISMATCH")
        return result


def _confusion(cases: list[E12Case], predictions: dict) -> dict:
    """Observed-gold confusion; unknown gold counted outside F1."""
    per_field = {field: Counter() for field in E1_FIELDS}
    observed_support = Counter()
    unknown_gold = Counter()
    for case in cases:
        expected, _ = case.resolved()
        answers = {d.field_id: d for d in predictions[case.evidence.fingerprint()].decisions}
        for field in E1_FIELDS:
            ref = expected[field]
            value = answers[field].value if not answers[field].abstained else None
            if ref.status != "observed":
                unknown_gold[field] += 1
                continue
            observed_support[field] += 1
            target = str(ref.value).lower() if isinstance(ref.value, bool) else str(ref.value)
            predicted = ("ABSTAIN" if value is None else
                         str(value).lower() if isinstance(value, bool) else str(value))
            per_field[field][(target, predicted)] += 1
    return {
        f: {
            "n_observed_gold": observed_support[f],
            "n_unobservable_gold": unknown_gold[f],
            "cells": [
                {"gold": gold, "prediction": pred, "n": n}
                for (gold, pred), n in sorted(per_field[f].items())
            ],
        } for f in E1_FIELDS
    }


def diagnose_synthetic_cta(
    cases: list[E12Case], extractor, model_dir: str | Path,
) -> dict:
    """Inspect actual raw multi-head vs isolated heads, without changing E1.

    The caller must supply a previously loaded LOCAL extractor and explicitly
    enable TAPI_SYSTEM_ONE_ENABLED. A stub extractor can test this function,
    but such a test does not prove checkpoint inference.
    """
    if not 1 <= len(cases) <= 200:
        raise ValueError("E13_EXPECTS_1_TO_200_SYNTHETIC_CASES")
    if any(c.gold_kind != "synthetic_fixture" or c.split != "smoke"
           or c.evidence.source_kind != "synthetic" or c.evidence.observation is None
           for c in cases):
        raise ValueError("E13_SYNTHETIC_SMOKE_ONLY")
    validate_e12_dataset(cases)
    capturer = _CaptureClassifier(extractor)
    adapter = LocalGLiNERDecider(model_dir, _test_model=capturer)
    deterministic = DeterministicTextDecider()
    local_responses = {}
    baseline_responses = {}
    cases_report = []
    histograms = {
        "multi_presence": Counter(), "multi_type": Counter(),
        "single_presence": Counter(), "single_type": Counter(),
        "adapter_presence_reason": Counter(), "adapter_type_reason": Counter(),
    }
    conflict_counts = Counter()

    for index, case in enumerate(cases, 1):
        observation = case.evidence.observation
        ehash = case.evidence.fingerprint()
        adapter_result = adapter.evaluate(case.evidence)
        if capturer.last_raw is None or not isinstance(capturer.last_raw, dict):
            raise ValueError("E13_ADAPTER_RAW_RESPONSE_MISSING")
        raw = capturer.last_raw
        schema = capturer.last_schema
        multi_presence = _model_output(raw, "tem_cta", tuple(schema["tem_cta"]))
        multi_type = _model_output(raw, "tipo_cta", tuple(schema["tipo_cta"]))
        single_presence = _model_output(
            extractor.classify_text(observation.text, {"tem_cta": list(BOOL_HEAD)}),
            "tem_cta", BOOL_HEAD,
        )
        single_type = _model_output(
            extractor.classify_text(observation.text, {"tipo_cta": list(TYPE_HEAD)}),
            "tipo_cta", TYPE_HEAD,
        )

        responses = {d.field_id: d for d in adapter_result.decisions}
        presence = responses["tem_cta"]
        cta_kind = responses["tipo_cta"]
        baseline = deterministic.evaluate(case.evidence)
        local_responses[ehash] = adapter_result
        baseline_responses[ehash] = baseline
        negations = direct_negative_imperative(observation.text)

        for name, value in (
            ("multi_presence", multi_presence), ("multi_type", multi_type),
            ("single_presence", single_presence), ("single_type", single_type),
            ("adapter_presence_reason", presence.reason),
            ("adapter_type_reason", cta_kind.reason),
        ):
            histograms[name][value] += 1

        if multi_presence != single_presence:
            conflict_counts["presence_multi_vs_single_disagree"] += 1
        if multi_type != single_type:
            conflict_counts["type_multi_vs_single_disagree"] += 1
        if multi_type in E1_LABELS["tipo_cta"] and cta_kind.abstained:
            conflict_counts["valid_raw_type_suppressed_by_adapter"] += 1
            if cta_kind.reason == "cta_presence_not_corroborated":
                conflict_counts["suppressed_by_presence_dependency"] += 1
        if negations:
            conflict_counts["direct_negated_imperatives"] += 1
        base_decisions = {d.field_id:d for d in baseline.decisions}
        if negations and (not base_decisions["tem_cta"].abstained):
            conflict_counts["baseline_claims_cta_despite_direct_negation"] += 1

        gold, _ = case.resolved()
        cases_report.append({
            "synthetic_case_ordinal": index,
            "gold_presence_status": gold["tem_cta"].status,
            "gold_type_status": gold["tipo_cta"].status,
            "raw_multi_presence": multi_presence,
            "raw_multi_type": multi_type,
            "isolated_presence": single_presence,
            "isolated_type": single_type,
            "adapter_presence": "ABSTAIN" if presence.abstained else str(presence.value),
            "adapter_type": "ABSTAIN" if cta_kind.abstained else str(cta_kind.value),
            "adapter_presence_reason": presence.reason,
            "adapter_type_reason": cta_kind.reason,
            "has_direct_negated_imperative": bool(negations),
            "baseline_claims_cta": not base_decisions["tem_cta"].abstained,
        })

    metrics = evaluate_e12(cases, {
        "baseline": deterministic,
        "local_gliner": _CachedDecider(local_responses),
    }, split="smoke")
    return {
        "schema_version": "tapi-system-one-e13.v1",
        "scientifically_validated": False,
        "source_kind": "synthetic_only",
        "n_cases": len(cases),
        "notes": [
            "Raw multi-head and isolated-head candidates are NOT human evidence.",
            "No production classifier, thresholds, scientific corpus or grants are changed.",
            "Direct imperative negation flag is a limited regex diagnostic.",
            "Only synthetic case ordinals and schema-bounded labels are exported.",
        ],
        "cta_stage_histograms": {k: dict(sorted(v.items())) for k, v in histograms.items()},
        "cta_conflicts": dict(sorted(conflict_counts.items())),
        "case_diagnostics": cases_report,
        "observed_confusion": {
            "baseline": _confusion(cases, baseline_responses),
            "local_gliner": _confusion(cases, local_responses),
        },
        "paired_metrics": metrics,
    }
