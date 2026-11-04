"""Read authorized-local or synthetic E1 evidence; output aggregate report only.

Does not download, log or print raw input text. No external API access.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from tapi_gate0.system_one_e1 import (DeterministicTextDecider, LocalGLiNERDecider)
from tapi_gate0.system_one_benchmark import BenchmarkCase, evaluate_paired


def main(argv=None):
    parser = argparse.ArgumentParser(description="DEC-017 E1 local offline benchmark")
    parser.add_argument("--input", required=True, help="JSONL E1 cases (never uploaded)")
    parser.add_argument("--output", required=True, help="Aggregated JSON output")
    parser.add_argument("--model", choices=("baseline", "local_gliner", "both"), default="baseline")
    parser.add_argument("--model-dir", help="Already-downloaded GLiNER weights directory")
    args = parser.parse_args(argv)
    input_file = Path(args.input).resolve()
    output_file = Path(args.output).resolve()
    if input_file == output_file:
        parser.error("input/output paths must differ")
    if not input_file.is_file() or input_file.stat().st_size > 5_000_000:
        parser.error("input must be an existing local JSONL file <= 5MB")
    if args.model in {"local_gliner", "both"} and not args.model_dir:
        parser.error("--model-dir is required for local_gliner")
    cases = []
    with input_file.open("r", encoding="utf-8") as handle:
        for i, line in enumerate(handle, 1):
            if line.strip():
                cases.append(BenchmarkCase.model_validate_json(line))
            if len(cases) > 2000:
                parser.error("Maximum 2000 cases per run")
    models = {}
    if args.model in {"baseline", "both"}:
        models["baseline"] = DeterministicTextDecider()
    if args.model in {"local_gliner", "both"}:
        models["local_gliner"] = LocalGLiNERDecider(args.model_dir)
    report = evaluate_paired(cases, models)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"E1 offline report: n={report['n_cases']} models={','.join(report['models'])}; no scientific accuracy claim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
