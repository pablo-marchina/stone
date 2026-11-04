"""DEC-017 E1.5: reproducible synthetic-only review workflow validation.

Never ingests real content, checks an operator-provided grant, or loads a model.
Logs and aggregate results are stored outside the repository. This validation
does NOT prove independent reviewers or any scientific CTA accuracy.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from validate_dec017_e13_integrated import _run

ROOT = Path(__file__).resolve().parents[1]


def _head_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT,
            text=True, capture_output=True, check=False,
        )
    except OSError:
        return None
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and len(sha) == 40 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="E1.5 simulated CTA review validation (no real data)",
    )
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    root = Path(args.output_dir).expanduser().resolve()
    if root == ROOT or ROOT in root.parents:
        parser.error("E15_PRIVATE_VALIDATION_OUTPUT_OUTSIDE_REPOSITORY_REQUIRED")
    root.mkdir(parents=True, exist_ok=True)
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    rehearsal = root / "synthetic_rehearsal.json"
    # Eliminate stale results from an earlier success.
    rehearsal.unlink(missing_ok=True)
    steps = {}
    steps["targeted_pytest"] = _run(
        "e15_targeted_pytest",
        ["-m", "pytest", "-q", "tests/test_system_one_e15.py"],
        logs,
    )
    steps["synthetic_rehearsal"] = _run(
        "e15_synthetic_rehearsal",
        ["scripts/rehearse_dec017_e15.py", "--output", str(rehearsal)],
        logs,
    )
    steps["full_pytest"] = _run(
        "e15_full_pytest", ["-m", "pytest", "-q"], logs,
    )
    steps["gate0"] = _run(
        "e15_gate0", ["scripts/check_gate0.py"], logs,
    )
    steps["zero_spend"] = _run(
        "e15_zero_spend", ["scripts/verify_zero_spend.py"], logs,
    )
    try:
        proof = (
            json.loads(rehearsal.read_text(encoding="utf-8"))
            if steps["synthetic_rehearsal"]["status"] == "PASS" else {}
        )
        if proof and (
            proof["mode"] != "SYNTHETIC_REHEARSAL_ONLY"
            or proof["scientifically_validated"] is not False
            or proof["production_enabled"] is not False
            or proof["holdout_claim_allowed"] is not False
        ):
            raise ValueError("E15_REHEARSAL_INVALID_SAFETY_LABELS")
        rehearsal_counts = {
            "n_total": proof.get("n_total"),
            "n_dev": (proof.get("dev") or {}).get("n_cases"),
            "n_test": (proof.get("test") or {}).get("n_cases"),
            "n_adjudicated_dev": (proof.get("dev") or {}).get(
                "reviewer_agreement", {}
            ).get("n_adjudicated"),
            "n_adjudicated_test": (proof.get("test") or {}).get(
                "reviewer_agreement", {}
            ).get("n_adjudicated"),
        } if proof else {}
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        steps["synthetic_rehearsal"] = {
            "status": "FAIL", "reason": "REHEARSAL_RESULT_NOT_SAFE",
        }
        rehearsal_counts = {}
    summary = {
        "schema_version": "tapi-dec017-e15-integrated-validation.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "head_sha": _head_sha(),
        "steps": steps,
        "rehearsal_counts": rehearsal_counts,
        "source_kind": "synthetic_only",
        "scientifically_validated": False,
        "production_enabled": False,
        "gate0b_authorized_by_this_runner": False,
        "external_data_accessed": False,
        "real_human_review_conducted": False,
        "decision": "NO_SCIENTIFIC_OR_PRODUCTION_APPROVAL",
    }
    summary["all_checks_pass"] = all(
        isinstance(v, dict) and v.get("status") == "PASS"
        for v in steps.values()
    )
    (root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for name, result in steps.items():
        print(f"{name}: {result['status']}")
    print(f"all_checks_pass={str(summary['all_checks_pass']).lower()}")
    print("E1.5 only fictional review rehearsal; real research authorization remains blocked.")
    return 0 if summary["all_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
