"""DEC-017 E1.4: one-command offline validation with local-only aggregate output.

This orchestrator does not connect to providers or store captions. It reuses
the E1.3 validation subprocess harness and keeps all logs off-repository.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from validate_dec017_e13_integrated import _run

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "tapi-dec017-e14-integrated-validation.v1"
SUMMARY_FIELDS = (
    "n_cases", "presence_claims", "presence_abstentions",
    "type_claims", "type_abstentions", "presence_coverage_all",
    "type_coverage_all", "known_positive_single_support",
    "known_positive_correct_type", "known_positive_wrong_type",
    "known_positive_type_abstentions", "positive_caption_type_recall",
    "caption_negative_support", "caption_negative_presence_claims",
    "caption_negative_type_claims", "caption_negative_presence_fp_rate",
    "caption_negative_type_fp_rate", "selective_type_precision_decidable_caption",
    "explicit_multiple_type_claims", "undetermined_type_claims",
)


def aggregate_report(path: Path) -> dict:
    """Only pre-approved scalar metrics; exclude case IDs, raw text and model trace."""
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    policies = payload.get("policies", {})
    if not isinstance(policies, dict):
        raise ValueError("E14_MALFORMED_POLICY_REPORT")
    chosen = {}
    for policy, fields in policies.items():
        if not isinstance(policy, str) or not isinstance(fields, dict):
            raise ValueError("E14_INVALID_POLICY_DATA")
        chosen[policy] = {key: fields.get(key) for key in SUMMARY_FIELDS}
    return {
        "schema_version": payload.get("schema_version"),
        "n_cases": payload.get("n_cases"),
        "scientifically_validated": False,
        "production_enabled": False,
        "model_mode": payload.get("model_mode"),
        "policies": chosen,
        "decision": "NO_PRODUCTION_POLICY_SELECTED",
    }


def _head_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and len(value) == 40 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DEC-017 E1.4 integrated offline validation")
    parser.add_argument("--output-dir", required=True, help="Private directory OUTSIDE checkout")
    parser.add_argument("--model-dir", help="Existing E1.1 verified checkpoint")
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()
    if output_dir == ROOT or ROOT in output_dir.parents:
        parser.error("E14_VALIDATION_OUTPUT_OUTSIDE_REPOSITORY_REQUIRED")
    output_dir.mkdir(parents=True, exist_ok=True)
    logs = output_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    baseline_path = output_dir / "e14_baseline.json"
    model_path = output_dir / "e14_gliner.json"
    # Never reuse metrics from a previous run if this invocation fails.
    baseline_path.unlink(missing_ok=True)
    model_path.unlink(missing_ok=True)
    results = {}
    results["targeted_pytest"] = _run(
        "e14_targeted_pytest", ["-m", "pytest", "-q", "tests/test_system_one_e14.py"],
        logs,
    )
    results["baseline_comparison"] = _run(
        "e14_baseline_comparison", [
            "scripts/benchmark_system_one_e14.py", "--model", "baseline",
            "--output", str(baseline_path),
        ], logs,
    )
    if args.model_dir is None:
        results["gliner_comparison"] = {
            "status": "BLOCKED", "reason": "checkpoint_directory_required",
        }
    elif not Path(args.model_dir).expanduser().resolve().is_dir():
        results["gliner_comparison"] = {
            "status": "BLOCKED", "reason": "checkpoint_directory_missing",
        }
    else:
        results["gliner_comparison"] = _run(
            "e14_gliner_comparison", [
                "scripts/benchmark_system_one_e14.py", "--model", "both",
                "--model-dir", str(Path(args.model_dir).expanduser().resolve()),
                "--output", str(model_path),
            ], logs, model_enabled=True,
        )
    results["full_pytest"] = _run(
        "e14_full_pytest", ["-m", "pytest", "-q"], logs,
    )
    results["gate0"] = _run(
        "e14_gate0", ["scripts/check_gate0.py"], logs,
    )
    results["zero_spend"] = _run(
        "e14_zero_spend", ["scripts/verify_zero_spend.py"], logs,
    )
    summary = {
        "schema_version": SCHEMA,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "head_sha": _head_sha(),
        "scientifically_validated": False,
        "production_enabled": False,
        "external_data_accessed_by_runner": False,
        "steps": results,
        "baseline": (
            aggregate_report(baseline_path)
            if results["baseline_comparison"]["status"] == "PASS" else {}
        ),
        "gliner": (
            aggregate_report(model_path)
            if results["gliner_comparison"]["status"] == "PASS" else {}
        ),
    }
    summary["all_checks_pass"] = all(
        isinstance(item, dict) and item.get("status") == "PASS"
        for item in results.values()
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for name, outcome in results.items():
        print(f"{name}: {outcome['status']}")
    print(f"all_checks_pass={str(summary['all_checks_pass']).lower()}")
    print("PRIVATE logs and aggregate-only summary saved outside checkout.")
    return 0 if summary["all_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
