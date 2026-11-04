"""DEC-017 E1.4: offline policy comparison on BUILT-IN PT-BR synthetic fixtures.

No external dataset argument, downloads, database writes, or provider APIs.
Scores are caption-text-only diagnostics, not proof about video CTA absence.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from time import perf_counter

from build_e13_cta_challenges import make_cases
from tapi_gate0.system_one_e14 import CAPTION_REFERENCES, evaluate_e14_synthetic


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E1.4 caption-only CTA policy lab")
    parser.add_argument("--output", required=True, help="JSON aggregate outside repository")
    parser.add_argument("--model", choices=("baseline", "both"), default="baseline")
    parser.add_argument("--model-dir", help="Verified E1.1 local SHA-pinned checkpoint")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    target = Path(args.output).expanduser().resolve()
    if target == root or root in target.parents:
        parser.error("E14_REPORT_MUST_BE_OUTSIDE_REPOSITORY")
    if args.model == "baseline" and args.model_dir:
        parser.error("E14_UNUSED_CHECKPOINT_IN_BASELINE_MODE")

    # Hard-coded, author-written fixtures ONLY: no caller-controlled JSONL.
    cases = make_cases()
    if (len(cases) != 34
            or {case.evidence.content_id for case in cases} != set(CAPTION_REFERENCES)):
        raise RuntimeError("E14_CANONICAL_SYNTHETIC_DATASET_MISMATCH")

    provenance = None
    timings = {"model_load_ms": None, "model_inference_ms": None}
    if args.model == "both":
        if os.getenv("TAPI_SYSTEM_ONE_ENABLED", "0") != "1":
            parser.error("E14_EXPERIMENT_DISABLED_BY_DEFAULT")
        if not args.model_dir:
            parser.error("E14_CHECKPOINT_REQUIRED")
        from prepare_gliner25_local_checkpoint import (
            _not_inside_project, validate_local_checkpoint,
        )
        model_dir = Path(args.model_dir).expanduser().resolve()
        _not_inside_project(model_dir)
        if not model_dir.is_dir():
            parser.error("E14_LOCAL_CHECKPOINT_NOT_FOUND")
        verified = validate_local_checkpoint(model_dir)
        if (not verified["manifest_present"]
                or not isinstance(verified["revision"], str)
                or len(verified["revision"]) != 40):
            raise RuntimeError("E14_SHA_PINNED_CHECKPOINT_REQUIRED")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        import torch
        from tapi_gate0.system_one_e1 import LocalGLiNERDecider
        from tapi_gate0.system_one_e13 import SyntheticRawRecorder

        load_start = perf_counter()
        base = LocalGLiNERDecider(model_dir)
        with torch.inference_mode():
            extractor = base._load()
        timings["model_load_ms"] = round(
            (perf_counter() - load_start) * 1000, 3
        )
        recorder = SyntheticRawRecorder(extractor)
        local = LocalGLiNERDecider(model_dir, _test_model=recorder)
        bundles = {}
        raw = {}
        infer_start = perf_counter()
        with torch.inference_mode():
            for case in cases:
                evidence = case.evidence
                observed = evidence.observation
                before = len(recorder.by_text_sha.get(observed.sha256, []))
                result = local.evaluate(evidence)
                captured = recorder.by_text_sha.get(observed.sha256, [])
                if len(captured) != before + 1:
                    raise RuntimeError("E14_RAW_MODEL_RESPONSE_NOT_CAPTURED_ONCE")
                bundles[evidence.fingerprint()] = result
                raw[evidence.fingerprint()] = captured[-1]
        timings["model_inference_ms"] = round(
            (perf_counter() - infer_start) * 1000, 3
        )
        report = evaluate_e14_synthetic(
            cases, gliner_bundles=bundles, gliner_raw=raw,
        )
        provenance = {
            "repository": verified["repository"],
            "revision": verified["revision"],
            "weights_sha256": verified["files"]["model.safetensors"]["sha256"],
        }
    else:
        report = evaluate_e14_synthetic(cases)

    report["checkpoint"] = provenance
    report["execution_timings"] = timings
    report["model_mode"] = args.model
    report["external_api_inference_enabled"] = False
    report["raw_caption_exported"] = False
    report["rubric_or_classifier_promoted"] = False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"E1.4 SYNTHETIC-ONLY COMPLETE: {report['n_cases']} cases, "
        f"{len(report['policies'])} policies, "
        "scientifically_validated=false; no production recommendation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
