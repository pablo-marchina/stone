"""DEC-017 E1.3: offline, zero-spend validation orchestrator for the operator.

Run on a checkout of the PR #29 branch. Never fetch checkpoints or provider
data. Logs stay local; summary.json contains only counts/status, not captions.
This does NOT confer scientific validity or turn on production features.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "tapi-dec017-e13-integrated-validation.v1"


def _run(name: str, arguments: list[str], logs: Path, *, model_enabled: bool = False) -> dict:
    """Capture complete diagnostics locally without publishing private output."""
    env = os.environ.copy()
    env.update({
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "TAPI_SYSTEM_ONE_ENABLED": "1" if model_enabled else "0",
        "TAPI_MPE_PERSISTENCE_ENABLED": "0",
    })
    start = perf_counter()
    try:
        result = subprocess.run(
            [sys.executable, *arguments], cwd=ROOT, env=env,
            text=True, capture_output=True, check=False,
        )
        status, exit_code = ("PASS" if result.returncode == 0 else "FAIL"), result.returncode
        output = result.stdout + ("\n" if result.stdout and result.stderr else "") + result.stderr
    except OSError as exc:
        status, exit_code = "ERROR", None
        output = f"{type(exc).__name__}: command could not execute\n"
    duration = round(perf_counter() - start, 3)
    (logs / f"{name}.log").write_text(output, encoding="utf-8")
    return {"status": status, "exit_code": exit_code, "duration_s": duration}


def _read_aggregate(path: Path) -> dict:
    """Return a strict aggregate subset, without case-level traces or raw labels."""
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = {
        "n_cases": payload.get("n_cases"),
        "scientifically_validated": False,
        "n_cta_cascade_blocked": payload.get("n_cta_cascade_blocked"),
    }
    head = payload.get("cta_head_isolation")
    if isinstance(head, dict):
        result["joint_vs_solo_changed"] = head.get("joint_vs_solo_changed")
    crosscheck = payload.get("cta_evidence_crosscheck")
    if isinstance(crosscheck, dict):
        result["cta_conflicts"] = crosscheck.get("cta_conflicts")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run offline DEC-017 E1.3 validation")
    parser.add_argument("--model-dir", help="Previously verified GLiNER E1.1 checkpoint on a real local volume")
    parser.add_argument("--output-dir", required=True, help="Private local folder, preferably OUTSIDE checkout")
    args = parser.parse_args(argv)
    target = Path(args.output_dir).expanduser().resolve()
    if target == ROOT or ROOT in target.parents:
        parser.error("E13_VALIDATION_OUTPUT_MUST_BE_OUTSIDE_CHECKOUT")
    target.mkdir(parents=True, exist_ok=True)
    logs = target / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    synthetic = target / "e13_synthetic.jsonl"
    baseline = target / "baseline.json"
    both = target / "gliner_and_baselines.json"
    results = {}
    results["targeted_pytest"] = _run(
        "targeted_pytest", ["-m", "pytest", "-q", "tests/test_system_one_e13.py"], logs
    )
    results["synthetic_generation"] = _run(
        "synthetic_generation", [
            "scripts/build_e13_cta_challenges.py", "--output", str(synthetic),
        ], logs,
    )
    if results["synthetic_generation"]["status"] == "PASS":
        results["baseline_benchmark"] = _run(
            "baseline_benchmark", [
                "scripts/diagnose_e13_cta.py", "--input", str(synthetic),
                "--output", str(baseline), "--model", "baseline",
            ], logs,
        )
    else:
        results["baseline_benchmark"] = {"status": "BLOCKED", "reason": "fixture_generation_failed"}
    if args.model_dir is None:
        results["gliner_ablation"] = {"status": "BLOCKED", "reason": "model_dir_required"}
    elif results["synthetic_generation"]["status"] != "PASS":
        results["gliner_ablation"] = {"status": "BLOCKED", "reason": "fixture_generation_failed"}
    else:
        weights = Path(args.model_dir).expanduser().resolve()
        if not weights.is_dir():
            results["gliner_ablation"] = {"status": "BLOCKED", "reason": "checkpoint_directory_missing"}
        else:
            results["gliner_ablation"] = _run(
                "gliner_ablation", [
                    "scripts/diagnose_e13_cta.py", "--input", str(synthetic),
                    "--output", str(both), "--model", "both",
                    "--model-dir", str(weights), "--ablate-cta-heads",
                ], logs, model_enabled=True,
            )
    results["full_pytest"] = _run(
        "full_pytest", ["-m", "pytest", "-q"], logs
    )
    results["gate0"] = _run(
        "gate0", ["scripts/check_gate0.py"], logs
    )
    results["zero_spend"] = _run(
        "zero_spend", ["scripts/verify_zero_spend.py"], logs
    )
    summary = {
        "schema_version": SCHEMA,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scientifically_validated": False,
        "production_enabled": False,
        "external_data_accessed_by_runner": False,
        "steps": results,
        "aggregate_baseline": _read_aggregate(baseline),
        "aggregate_gliner": _read_aggregate(both),
    }
    summary["all_checks_pass"] = all(
        isinstance(step, dict) and step.get("status") == "PASS"
        for step in results.values()
    )
    (target / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for name, result in results.items():
        print(f"{name}: {result['status']}")
    print(f"all_checks_pass={str(summary['all_checks_pass']).lower()}")
    print("Summary (aggregates only) and PRIVATE logs saved to the requested directory.")
    return 0 if summary["all_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
