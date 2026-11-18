"""Only synthetic local report fixtures; no operational DB, no model or network."""
import json

import pytest

from scripts import a02_payloads_preflight as pf

HEAD = "a" * 40


@pytest.fixture
def report(tmp_path):
    folder = tmp_path / "artifacts/private/test-report"
    folder.mkdir(parents=True)
    backup = folder.parent / "test-backup.sqlite3"
    backup.write_bytes(b"synthetic-not-an-operational-database")
    steps = []
    for name in pf.STEPS:
        log = folder / (name + ".log")
        log.write_text("synthetic", encoding="utf-8")
        steps.append({"step": name, "exit_code": 0, "log_sha256": pf.digest(log)})
    xml = folder / "pytest.xml"
    xml.write_text('<testsuite>' + '<testcase name="fixture"/>' * pf.MIN_FOCAL + '</testsuite>', encoding="utf-8")
    pin = pf.digest(backup)
    data = {"schema": pf.SCHEMA, "commit": HEAD, "status": "A02_PAYLOADS_PREFLIGHT_VERIFIED",
        "checkout_unchanged": True, "operational_database_mutated": False,
        "all_writers_stopped_attested": True, "focal_files": list(pf.FOCAL), "steps": steps,
        "pytest": {"tests": pf.MIN_FOCAL, "passed": pf.MIN_FOCAL, "failed": 0, "errors": 0, "skipped": 0},
        "pytest_xml_sha256": pf.digest(xml),
        "backup": {"status": "BACKUP_RESTORE_VERIFIED", "backup_name": backup.name,
                   "backup_sha256": pin, "revision": pf.OLD, "restore_target_disposable": True,
                   "live_restore_performed": False},
        "rehearsal": {"status": "A02_MIGRATION_REHEARSAL_VERIFIED", "backup_name": backup.name,
            "backup_sha256": pin, "from_revision": pf.OLD, "to_revision": pf.NEW,
            "new_empty_tables": ["asset_derived_payloads"], "legacy_schema_unchanged": True,
            "upgrade_integrity_verified": True, "empty_downgrade_verified": True, "backup_unchanged": True,
            "operational_database_accessed": False, "operational_database_mutated": False,
            "media_enabled": False, "real_grants_created": 0}}
    path = folder / "summary.json"
    return tmp_path, path, data, backup


def verify(report):
    root, path, data, _ = report
    path.write_text(json.dumps(data), encoding="utf-8")
    return pf.verify_report(root, path.parent.name, HEAD, pf.digest(path))


def test_report_requires_exact_head_and_hash(report):
    assert verify(report)["status"] == "A02_PAYLOADS_PREFLIGHT_VERIFIED"
    root, path, _, _ = report
    with pytest.raises(ValueError, match="REPORT_PIN_MISMATCH"):
        pf.verify_report(root, path.parent.name, HEAD, "0" * 64)
    with pytest.raises(ValueError, match="REPORT_CONTEXT_INVALID"):
        pf.verify_report(root, path.parent.name, "b" * 40, pf.digest(path))


@pytest.mark.parametrize("key", ["failed", "errors", "skipped"])
def test_focal_denies_nonpass_even_with_positive_count(key):
    counts = {"tests": pf.MIN_FOCAL, "passed": pf.MIN_FOCAL, "failed": 0, "errors": 0, "skipped": 0}
    counts[key] = 1
    assert not pf.focal_passed(counts)
    counts[key] = 0
    counts["tests"] = counts["passed"] = pf.MIN_FOCAL - 1
    assert not pf.focal_passed(counts)


def test_modified_logs_and_backup_are_rejected(report):
    verify(report)
    root, path, data, backup = report
    log = path.parent / "focal.log"
    old = log.read_bytes()
    log.write_bytes(b"modified")
    with pytest.raises(ValueError, match="LOG_MISMATCH"):
        verify(report)
    log.write_bytes(old)
    backup.write_bytes(b"changed")
    with pytest.raises(ValueError, match="BACKUP_PIN_MISMATCH"):
        verify(report)


def test_junit_skips_rejected_even_with_recomputed_pin(report):
    _, path, data, _ = report
    xml = path.parent / "pytest.xml"
    xml.write_text('<testsuite>' + '<testcase/>' * (pf.MIN_FOCAL - 1)
                   + '<testcase><skipped/></testcase></testsuite>', encoding="utf-8")
    data["pytest_xml_sha256"] = pf.digest(xml)
    with pytest.raises(ValueError, match="FOCAL_NOT_PASS"):
        verify(report)


def test_rehearsal_wrong_transition_or_live_access_rejected(report):
    _, _, data, _ = report
    data["rehearsal"]["from_revision"] = "0014_asset_lineage"
    with pytest.raises(ValueError, match="REHEARSAL_NOT_PASS"):
        verify(report)
    data["rehearsal"]["from_revision"] = pf.OLD
    data["rehearsal"]["operational_database_accessed"] = True
    with pytest.raises(ValueError, match="REHEARSAL_NOT_PASS"):
        verify(report)


def test_report_missing_step_and_unsafe_basename_rejected(report):
    _, _, data, _ = report
    data["steps"].pop()
    with pytest.raises(ValueError, match="STEPS_NOT_PASS"):
        verify(report)
    with pytest.raises(ValueError, match="PRIVATE_NAME_INVALID"):
        pf.private_file(report[0], "../outside")
