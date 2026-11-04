"""DEC-017 E1.3: local-only CTA cascade/root-cause diagnostic (synthetic only).

This command refuses any non-synthetic dataset, verifies local checkpoint SHA
before inference, never accesses providers, and exports *no raw captions*.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
from time import perf_counter

from tapi_gate0.system_one_e1 import (
    DeterministicTextDecider, E1_LABELS, LocalGLiNERDecider,
)
from tapi_gate0.system_one_e13 import (
    HybridTextCTADecider, NegationAwareTextDecider, SyntheticRawRecorder,
    evaluate_e13_synthetic,
)
from benchmark_system_one_e12 import load_cases


def _safe_raw(raw, field: str, candidates: list[str]) -> str:
    if not isinstance(raw, dict):
        return "__not_dictionary__"
    value = raw.get(field)
    if isinstance(value, bool):
        value = "sim" if value else "nao"
    return value if isinstance(value, str) and value in candidates else "__out_of_schema__"


def _ablate_individual_cta_heads(extractor, cases: list, joint_trace: list) -> dict:
    """Compare E1 joint-schema response against separate identical field heads."""
    joined = {x["synthetic_case_id"]: x for x in joint_trace}
    differences = {"tem_cta": 0, "tipo_cta": 0}
    cases_out = []
    options = {
        "tem_cta": ["sim", "nao", "indefinido"],
        "tipo_cta": [*E1_LABELS["tipo_cta"], "indefinido"],
    }
    for case in cases:
        item = case.evidence.observation
        prior = joined[case.evidence.content_id]
        row = {"synthetic_case_id": case.evidence.content_id}
        for field in ("tem_cta", "tipo_cta"):
            raw = extractor.classify_text(item.text, {field: options[field]})
            result = _safe_raw(raw, field, options[field])
            original = prior["joint_raw_" + field]
            row["solo_" + field] = result
            row["joint_" + field] = original
            changed = result != original
            row["changed_" + field] = changed
            differences[field] += int(changed)
        cases_out.append(row)
    return {
        "n_cases": len(cases),
        "joint_vs_solo_changed": differences,
        "per_synthetic_case": cases_out,
        "note": "Head isolation uses extra inference calls with the same public checkpoint; synthetic only.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="DEC-017 E1.3 PT-BR CTA diagnostics")
    parser.add_argument("--input", required=True, help="Synthetic-only JSONL (never real posts)")
    parser.add_argument("--output", required=True, help="Aggregates + synthetic IDs only")
    parser.add_argument("--model", choices=("baseline", "both"), default="baseline")
    parser.add_argument("--model-dir", help="Original SHA-pinned local GLiNER2.5 weights")
    parser.add_argument("--ablate-cta-heads", action="store_true",
                        help="Run standalone tem_cta/tipo_cta heads and compare with joint outputs")
    args = parser.parse_args(argv)
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    if input_path == output_path:
        parser.error("E13_INPUT_OUTPUT_MUST_DIFFER")
    cases = load_cases(input_path)
    if any(
        case.gold_kind != "synthetic_fixture"
        or case.split != "smoke"
        or case.evidence.source_kind != "synthetic"
        or case.evidence.observation is None
        for case in cases
    ):
        parser.error("E13_SYNTHETIC_INPUT_ONLY")
    if args.ablate_cta_heads and args.model != "both":
        parser.error("E13_ABLATION_REQUIRES_GLINER")
    models = {
        "baseline_original": DeterministicTextDecider(),
        "baseline_negation_aware": NegationAwareTextDecider(),
    }
    provenance = None
    recorder = None
    extractor = None
    model_load_ms = None
    if args.model == "both":
        if os.getenv("TAPI_SYSTEM_ONE_ENABLED", "0") != "1":
            parser.error("E13_SYSTEM_ONE_EXPERIMENT_DISABLED")
        if not args.model_dir:
            parser.error("E13_LOCAL_CHECKPOINT_DIRECTORY_REQUIRED")
        from prepare_gliner25_local_checkpoint import (
            _not_inside_project, validate_local_checkpoint,
        )
        model_dir = Path(args.model_dir).expanduser().resolve()
        _not_inside_project(model_dir)
        verified = validate_local_checkpoint(model_dir)
        if not verified["manifest_present"] or not verified["revision"]:
            raise RuntimeError("E13_PINNED_CHECKPOINT_MANIFEST_REQUIRED")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        import torch
        started = perf_counter()
        direct = LocalGLiNERDecider(model_dir)
        with torch.inference_mode():
            extractor = direct._load()
            # A single synthetic preflight is excluded from the model-to-model
            # latency comparison and doesn't create or upload any evidence.
            extractor.classify_text(
                "Comente sobre sua loja de bairro.",
                {"tem_cta": ["sim", "nao", "indefinido"]},
            )
        model_load_ms = round((perf_counter() - started) * 1000, 3)
        recorder = SyntheticRawRecorder(extractor)
        gliner = LocalGLiNERDecider(model_dir, _test_model=recorder)
        models["gliner"] = gliner
        models["gliner_rule_assisted_experimental"] = HybridTextCTADecider(gliner)
        provenance = {
            "repository": verified["repository"],
            "revision": verified["revision"],
            "weights_sha256": verified["files"]["model.safetensors"]["sha256"],
        }
    guard = torch.inference_mode() if args.model == "both" else nullcontext()
    with guard:
        report = evaluate_e13_synthetic(cases, models, raw_recorder=recorder)
        if args.ablate_cta_heads:
            report["cta_head_isolation"] = _ablate_individual_cta_heads(
                extractor, cases, report["synthetic_cta_trace"],
            )
    report["model_checkpoint"] = provenance
    report["model_load_and_preflight_ms"] = model_load_ms
    report["external_api_inference_enabled"] = False
    report["raw_input_exported"] = False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8",
    )
    print(
        f"E1.3 SYNTHETIC ONLY PASS: {len(cases)} cases;"
        f" {', '.join(models)}; scientifically_validated=false"
    )
    if recorder is not None:
        print("CTA cascade-blocked synthetic cases:", report["n_cta_cascade_blocked"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
