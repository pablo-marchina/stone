"""Read-only A00 full-coverage gap audit from an already-persisted private report.

Never reruns tests, invokes models, upgrades DBs, connects to providers or
alters gates. Validates original A00 log/JUnit hashes through the inspector,
recalculates required multimodal groups from the same saved JUnit, and reports
only aggregated source-identity categories (not raw skip messages or logs).
A completed regression with skips is NOT a complete multimodal acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from scripts.a00_baseline import ROOT, BaselineError, multimodal_coverage
from scripts.a00_inspect_report import inspect_report, checked_file


def _skip_category(identity: dict) -> str:
    suite = identity["class"]
    if suite == "tests.test_asset_rights_registry":
        return "NATIVE_MULTIMODAL_OPT_IN_TESTS"
    if suite in (
        "tests.test_asset_ocr_fixture", "tests.test_multimodal_ocr",
        "tests.test_multimodal_ocr_consensus",
    ):
        return "OCR_LOCAL_OPT_IN_TESTS"
    if suite == "tests.test_evidence_lab":
        return "EVIDENCE_LAB_LOCAL_TRIPLET_OPT_IN"
    if suite == "tests.test_discovery_eval_engine":
        return "WINDOWS_SYMLINK_PRIVILEGE_TEST"
    return "UNCLASSIFIED_SKIP_INVESTIGATE"


def analyze_gap(root: Path, report_name: str) -> dict:
    root = Path(root)
    inspected = inspect_report(root, report_name)
    if inspected["profile"] != "full":
        raise BaselineError("A00_GAP_FULL_PROFILE_REQUIRED")
    directory = root / "artifacts" / "private" / report_name
    # inspect_report already verified original summary/log/JUnit hashes and
    # exact step lists. Don't trust the summary's coverage assertion blindly.
    record = json.loads(checked_file(directory, "summary.json").read_bytes())
    current = multimodal_coverage(checked_file(directory, "pytest.xml"))
    stored = record.get("multimodal_coverage")
    if stored != current:
        raise BaselineError("A00_MULTIMODAL_COVERAGE_MISMATCH")
    counts = inspected["counts"]
    if counts["passed"] + counts["failed"] + counts["errors"] + counts["skipped"] != counts["tests"]:
        raise BaselineError("A00_GAP_JUNIT_COUNTS_INVALID")
    # The report's skip-free assertion must never contradict the verified JUnit.
    # Treat malformed positive claims as tampering, not partial success.
    if record.get("full_regression_without_skips") is True and (
        counts["skipped"] != 0 or not inspected["checks_passed"]
    ):
        raise BaselineError("A00_GAP_SKIP_FREE_CLAIM_CONFLICT")

    categories = dict(sorted(Counter(
        _skip_category(skip) for skip in inspected["skipped_tests"]
    ).items()))
    if sum(categories.values()) != counts["skipped"]:
        raise BaselineError("A00_GAP_SKIP_COUNT_INVALID")
    deficits = [
        {
            "group": group, "minimum": data["minimum"],
            "collected": data["collected"], "passed": data["passed"],
            "passed_required": False,
        }
        for group, data in current["groups"].items()
        if not data["passed_required"]
    ]
    status = (
        "A00_FULL_COVERAGE_VERIFIED" if inspected["checks_passed"]
        and counts["skipped"] == 0 and not deficits
        else "A00_FULL_WITH_COVERAGE_GAPS" if inspected["checks_passed"]
        else "A00_REPORT_CONTAINS_BLOCKERS"
    )
    return {
        "schema_version": "tapi-a00-readonly-coverage-gap.v1",
        "status": status,
        "source_report_name": report_name,
        "source_git_head": inspected["commit"],
        "source_policy_version": inspected["policy_version"],
        "summary_sha256": inspected["summary_sha256"],
        "junit_sha256": inspected["pytest_xml_sha256"],
        "reports_authenticity_independent": False,
        "report_logs_hash_verified": inspected["logs_match_recorded_digests"],
        "checks_passed": inspected["checks_passed"],
        "full_regression_without_skips": bool(record.get("full_regression_without_skips")),
        "counts": counts,
        "skipped_by_test_family": categories,
        "skip_family_is_causal_proof": False,
        "multimodal_all_required_passed": current["all_required_passed"],
        "multimodal_coverage_deficits": deficits,
        "tests_rerun": False,
        "model_inference_invoked": False,
        "operational_database_mutated": False,
        "external_rights_verified": False,
        "independent_gold_available": False,
        "gate_status": {**{f"G{i}": "BLOCKED" for i in range(7)},
                        "IMP-131": "BLOCKED"},
        "interpretation": (
            "Skip family is inferred from test module identity, NOT an "
            "attestation of the precise skip cause; consult saved JUnit "
            "skip reason locally before enabling any explicit model opt-in."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-name", required=True)
    opts = parser.parse_args(argv)
    try:
        result = analyze_gap(ROOT, opts.report_name)
    except (BaselineError, OSError, ValueError, KeyError, TypeError,
            ET.ParseError) as exc:
        reason = str(exc) if isinstance(exc, BaselineError) else "A00_GAP_REPORT_INVALID"
        print(json.dumps({"status": "BLOCKED", "reason_code": reason}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] != "A00_REPORT_CONTAINS_BLOCKERS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
