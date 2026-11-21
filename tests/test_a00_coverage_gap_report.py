"""A00 coverage report contract: validated saved artefacts only, no rerun."""
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from scripts import a00_coverage_gap_report as gaps
from scripts.a00_baseline import BaselineError, junit_counts, multimodal_coverage


def _fixture(tmp_path, *, skipped=True, tampered_coverage=False):
    directory = tmp_path / "artifacts" / "private" / "fixture"
    directory.mkdir(parents=True)
    root = ET.Element("testsuite")
    ET.SubElement(root, "testcase", classname="tests.test_studio_e1",
                  name="test_local_draft")
    if skipped:
        c = ET.SubElement(root, "testcase",
                          classname="tests.test_asset_rights_registry",
                          name="test_real_asr_fixture_encrypted_result[fictional]")
        ET.SubElement(c, "skipped", message="explicit local ASR model opt-in required")
        c = ET.SubElement(root, "testcase",
                          classname="tests.test_discovery_eval_engine",
                          name="test_cli_refuses_symlink_private_and_path_traversal")
        ET.SubElement(c, "skipped", message="creating directory symlinks requires privileges")
    xml = directory / "pytest.xml"
    ET.ElementTree(root).write(xml, encoding="utf-8")
    counts = junit_counts(xml)
    report = {
        "policy_version": "a00-local-baseline.v2",
        "profile": "full",
        "inventory": {"commit": "a" * 40, "tree": "b" * 40},
        "checks_passed": True,
        "full_regression_without_skips": not skipped,
        "pytest": counts,
        "multimodal_coverage": multimodal_coverage(xml),
        "pytest_xml_sha256": sha256(xml.read_bytes()).hexdigest(),
        "steps": [],
    }
    if tampered_coverage:
        report["multimodal_coverage"]["all_required_passed"] = True
    for step in ("legacy_gate0", "zero_spend", "documentary_mirror",
                 "pytest", "node"):
        name = step + ".log"
        content = (step + " synthetic log").encode("utf-8")
        (directory / name).write_bytes(content)
        report["steps"].append({
            "step": step,
            "log": name,
            "log_sha256": sha256(content).hexdigest(),
        })
    (directory / "summary.json").write_text(
        json.dumps(report), encoding="utf-8",
    )
    return directory


def test_saved_report_exact_hashes_and_skips_are_grouped_without_reruns(tmp_path):
    _fixture(tmp_path)
    result = gaps.analyze_gap(tmp_path, "fixture")
    assert result["status"] == "A00_FULL_WITH_COVERAGE_GAPS"
    assert result["counts"] == {
        "tests": 3, "passed": 1, "failed": 0, "errors": 0, "skipped": 2,
    }
    assert result["skipped_by_test_family"] == {
        "NATIVE_MULTIMODAL_OPT_IN_TESTS": 1,
        "WINDOWS_SYMLINK_PRIVILEGE_TEST": 1,
    }
    assert result["skip_family_is_causal_proof"] is False
    assert result["multimodal_all_required_passed"] is False
    assert result["multimodal_coverage_deficits"]
    assert result["tests_rerun"] is False
    assert result["model_inference_invoked"] is False
    assert result["operational_database_mutated"] is False
    assert result["external_rights_verified"] is False
    assert all(value == "BLOCKED" for value in result["gate_status"].values())
    assert len(result["summary_sha256"]) == len(result["junit_sha256"]) == 64
    assert "explicit local" not in json.dumps(result)


def test_saved_junit_deficits_still_block_full_coverage_even_with_no_skips(tmp_path):
    _fixture(tmp_path, skipped=False)
    result = gaps.analyze_gap(tmp_path, "fixture")
    assert result["counts"]["skipped"] == 0
    assert result["status"] == "A00_FULL_WITH_COVERAGE_GAPS"
    assert result["full_regression_without_skips"] is True
    assert result["multimodal_all_required_passed"] is False


def test_manually_forged_multimodal_coverage_is_denied(tmp_path):
    _fixture(tmp_path, tampered_coverage=True)
    with pytest.raises(BaselineError, match="A00_MULTIMODAL_COVERAGE_MISMATCH"):
        gaps.analyze_gap(tmp_path, "fixture")


def test_modified_junit_after_report_is_denied(tmp_path):
    directory = _fixture(tmp_path)
    with (directory / "pytest.xml").open("ab") as out:
        out.write(b"altered")
    with pytest.raises(BaselineError, match="A00_REPORT_XML_HASH_MISMATCH"):
        gaps.analyze_gap(tmp_path, "fixture")


def test_no_other_profile_or_traversal(tmp_path):
    directory = _fixture(tmp_path)
    data = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    data["profile"] = "semantic"
    (directory / "summary.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BaselineError, match="A00_REPORT_STEPS_INVALID"):
        gaps.analyze_gap(tmp_path, "fixture")
    with pytest.raises(BaselineError, match="A00_REPORT_NAME_INVALID"):
        gaps.analyze_gap(tmp_path, "../fixture")


def test_unexpected_skip_identity_remains_unclassified():
    assert gaps._skip_category({
        "class": "tests.unfamiliar", "name": "test_unexpected_skip",
    }) == "UNCLASSIFIED_SKIP_INVESTIGATE"
