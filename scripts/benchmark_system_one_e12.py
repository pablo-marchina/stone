"""DEC-017 E1.2: compare a deterministic baseline and optional real local GLiNER.

Input is local JSONL. Output contains aggregates only, never post text, URLs,
human reviewer IDs or per-content predictions. No provider/API calls.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys
from time import perf_counter

from tapi_gate0.system_one_e1 import DeterministicTextDecider, LocalGLiNERDecider
from tapi_gate0.system_one_e12 import E12Case, evaluate_e12


def load_cases(path: Path) -> list[E12Case]:
    if not path.is_file() or path.stat().st_size > 10_000_000:
        raise ValueError("E12_LOCAL_JSONL_REQUIRED_MAX_10MB")
    cases = []
    with path.open(encoding="utf-8") as reader:
        for line in reader:
            if line.strip():
                cases.append(E12Case.model_validate_json(line))
            if len(cases) > 2000:
                raise ValueError("E12_MAX_2000_CASES")
    if not cases:
        raise ValueError("E12_EMPTY_JSONL")
    return cases


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TAPI E1.2 paired Portuguese classification research")
    parser.add_argument("--input", required=True, help="Local synthetic or authorized double-reviewed JSONL")
    parser.add_argument("--output", required=True, help="Only aggregate metrics; no raw examples")
    parser.add_argument("--model", choices=("baseline", "both"), default="baseline")
    parser.add_argument("--split", choices=("smoke", "dev", "test"),
                        help="Required when input contains both dev and test")
    parser.add_argument("--model-dir", help="SHA-pinned local GLiNER2.5 weights; required for --model both")
    args = parser.parse_args(argv)
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    if input_path == output_path:
        parser.error("Output cannot overwrite input")
    cases = load_cases(input_path)
    # The entire dataset is checked for creator/duplicate-text leakage before
    # any inference is allowed on a selected split.
    from tapi_gate0.system_one_e12 import validate_e12_dataset
    validate_e12_dataset(cases)
    available_splits = {case.split for case in cases}
    if args.split is None and len(available_splits) != 1:
        parser.error("E12_SPLIT_SELECTION_REQUIRED: choose --split dev or --split test")
    selected = args.split if args.split is not None else next(iter(available_splits))
    if selected not in available_splits:
        parser.error("E12_SELECTED_SPLIT_EMPTY")
    first_case = next(case for case in cases if case.split == selected)
    models = {"baseline": DeterministicTextDecider()}
    provenance = None
    load_ms = None
    if args.model == "both":
        if os.getenv("TAPI_SYSTEM_ONE_ENABLED") != "1":
            parser.error("SYSTEM_ONE_EXPERIMENT_DISABLED: set TAPI_SYSTEM_ONE_ENABLED=1 explicitly")
        if not args.model_dir:
            parser.error("--model-dir is required for the local model")
        model_dir = Path(args.model_dir).expanduser().resolve()
        if not model_dir.is_dir():
            parser.error("LOCAL_CHECKPOINT_NOT_FOUND")
        # Import only when optional real-weight experiment was explicitly requested.
        from prepare_gliner25_local_checkpoint import (
            validate_local_checkpoint, _not_inside_project,
        )
        _not_inside_project(model_dir)
        verified = validate_local_checkpoint(model_dir)
        if (not verified["manifest_present"] or
            not verified["revision"] or len(verified["revision"]) != 40):
            raise RuntimeError("E12_PINNED_CHECKPOINT_REQUIRED")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        import torch
        local = LocalGLiNERDecider(model_dir)
        start = perf_counter()
        with torch.inference_mode():
            local._load()
            # Warm up model once. This is excluded from per-case latency.
            local.evaluate(first_case.evidence)
        load_ms = round((perf_counter()-start)*1000, 3)
        models["local_gliner"] = local
        provenance = {
            "repository": verified["repository"],
            "revision": verified["revision"],
            "weights_sha256": verified["files"]["model.safetensors"]["sha256"],
        }

    if args.model == "both":
        import torch
        guard = torch.inference_mode()
    else:
        guard = nullcontext()
    with guard:
        report = evaluate_e12(cases, models, split=selected)
    report["checkpoint"] = provenance
    report["model_load_and_warmup_ms"] = load_ms
    # The same JSON schema is used for synthetics and authorized human data;
    # scientific eligibility is never written, regardless of score.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(
        "E1.2 local aggregate PASS:",
        report["n_cases"], "cases on", selected + ";", ", ".join(models),
        "; scientifically_validated=false (exploratory)",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
