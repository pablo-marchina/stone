"""DEC-017 E1.3: authenticated, offline GLiNER CTA diagnosis on SYNTHETIC text.

Do not use for real content. No provider APIs, downloads, writes to corpus,
raw captions or usernames in the aggregate report.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from tapi_gate0.system_one_e13 import diagnose_synthetic_cta
from tapi_gate0.system_one_e12 import E12Case, validate_e12_dataset


def load_synthetic(path: Path) -> list[E12Case]:
    if not path.is_file() or path.stat().st_size > 5_000_000:
        raise ValueError("E13_SYNTHETIC_LOCAL_JSONL_REQUIRED_MAX_5MB")
    cases = []
    with path.open(encoding="utf-8") as reader:
        for row in reader:
            if row.strip():
                case = E12Case.model_validate_json(row)
                if (case.gold_kind != "synthetic_fixture" or case.split != "smoke"
                    or case.evidence.source_kind != "synthetic"):
                    raise ValueError("E13_REJECT_NON_SYNTHETIC_INPUT")
                cases.append(case)
            if len(cases) > 200:
                raise ValueError("E13_SYNTHETIC_MAX_200")
    validate_e12_dataset(cases)
    return cases


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Experiment E1.3: GLiNER CTA multi-head / isolated-head diagnostics"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-dir", required=True, help="E1.1 local, SHA-verified weights")
    args = parser.parse_args(argv)
    if os.getenv("TAPI_SYSTEM_ONE_ENABLED", "0") != "1":
        parser.error("SYSTEM_ONE_EXPERIMENT_DISABLED")
    path = Path(args.input).expanduser().resolve()
    target = Path(args.output).expanduser().resolve()
    if path == target:
        parser.error("E13_OUTPUT_MUST_NOT_OVERWRITE_INPUT")
    cases = load_synthetic(path)

    from prepare_gliner25_local_checkpoint import (
        _not_inside_project, validate_local_checkpoint,
    )
    directory = Path(args.model_dir).expanduser().resolve()
    _not_inside_project(directory)
    checked = validate_local_checkpoint(directory)
    if not checked["manifest_present"] or not checked["revision"] or len(checked["revision"]) != 40:
        raise RuntimeError("E13_PINNED_CHECKPOINT_REQUIRED")

    # Hard-bound the local, no-download run BEFORE importing model dependencies.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    import torch
    from tapi_gate0.system_one_e1 import LocalGLiNERDecider

    local = LocalGLiNERDecider(directory)
    with torch.inference_mode():
        extractor = local._load()
        report = diagnose_synthetic_cta(cases, extractor, directory)
    report["checkpoint"] = {
        "repository": checked["repository"],
        "revision": checked["revision"],
        "weights_sha256": checked["files"]["model.safetensors"]["sha256"],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("E1.3 synthetic CTA diagnostic PASS:", report["n_cases"], "cases",
          "; no model-selection or scientific claim.")
    print("Detected multi-head CTA type suppressions:",
          report["cta_conflicts"].get("suppressed_by_presence_dependency", 0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
