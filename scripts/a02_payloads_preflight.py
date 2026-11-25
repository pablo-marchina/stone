"""Validate A02 0016 locally; never apply a migration to the operational DB.

Focal tests run with the existing reduced child environment, without operational
credentials. Only after PASS, an explicitly requested read-only source backup and
rehearsal on its disposable copy are allowed. Local evidence, not an authorization
or scientific/production gate. Reports stay in artifacts/private.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "tapi-a02-payloads-preflight.v1"
OLD = "0015_asset_jobs"
NEW = "0016_asset_derived_payloads"
FOCAL = (
    "tests/test_a02_operational_upgrade.py", "tests/test_asset_lineage.py",
    "tests/test_asset_vault.py", "tests/test_asset_rights.py",
    "tests/test_asset_rights_registry.py", "tests/test_discovery_backup.py",
    "tests/test_a02_payloads_preflight.py",
)
# 124 previous cases + four new upgrade parametrizations; the new report tests
# add further cases. A minimum prevents silently validating a truncated suite.
MIN_FOCAL = 128
STEPS = ("documentary", "legacy_gate0", "zero_spend", "focal")


def require(ok, code):
    if not ok:
        raise ValueError("A02_PREFLIGHT_" + code)


def digest(path):
    h = sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def focal_passed(counts):
    return (isinstance(counts, dict)
            and type(counts.get("tests")) is int and counts["tests"] >= MIN_FOCAL
            and counts.get("passed") == counts["tests"]
            and all(type(counts.get(k)) is int and counts[k] == 0
                    for k in ("failed", "errors", "skipped")))


def rehearsal_passed(report, name, pin):
    return (isinstance(report, dict)
            and report.get("status") == "A02_MIGRATION_REHEARSAL_VERIFIED"
            and report.get("backup_name") == name and report.get("backup_sha256") == pin
            and report.get("from_revision") == OLD and report.get("to_revision") == NEW
            and report.get("new_empty_tables") == ["asset_derived_payloads"]
            and all(report.get(k) is True for k in ("legacy_schema_unchanged",
                "upgrade_integrity_verified", "empty_downgrade_verified", "backup_unchanged"))
            and all(report.get(k) is False for k in ("operational_database_accessed",
                "operational_database_mutated", "media_enabled"))
            and report.get("real_grants_created") == 0)


def private_file(root, name, suffix=""):
    require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", name))
            and name.endswith(suffix), "PRIVATE_NAME_INVALID")
    private = root / "artifacts" / "private"
    p = private / name
    require(p.resolve() == p.absolute(), "PRIVATE_PATH_REDIRECTED")
    return p


def verify_report(root, report_name, expected_head, expected_sha256):
    """Check local evidence at the exact HEAD; not a signature or trust boundary."""
    require(bool(re.fullmatch(r"[a-f0-9]{40}", expected_head)), "HEAD_INVALID")
    require(bool(re.fullmatch(r"[a-f0-9]{64}", expected_sha256)), "REPORT_PIN_INVALID")
    folder = private_file(root, report_name)
    summary = folder / "summary.json"
    require(summary.resolve() == summary.absolute() and summary.is_file(), "REPORT_MISSING")
    require(summary.stat().st_size <= 1024 * 1024, "REPORT_TOO_LARGE")
    raw = summary.read_bytes()
    require(sha256(raw).hexdigest() == expected_sha256, "REPORT_PIN_MISMATCH")
    report = json.loads(raw)
    require(report.get("schema") == SCHEMA and report.get("commit") == expected_head
            and report.get("status") == "A02_PAYLOADS_PREFLIGHT_VERIFIED"
            and report.get("checkout_unchanged") is True
            and report.get("operational_database_mutated") is False
            and report.get("all_writers_stopped_attested") is True
            and report.get("focal_files") == list(FOCAL), "REPORT_CONTEXT_INVALID")
    steps = report.get("steps", [])
    require([s.get("step") for s in steps] == list(STEPS)
            and all(s.get("exit_code") == 0 for s in steps), "STEPS_NOT_PASS")
    for s in steps:
        log = folder / (s["step"] + ".log")
        require(log.resolve() == log.absolute() and log.is_file()
                and digest(log) == s.get("log_sha256"), "LOG_MISMATCH")
    xml = folder / "pytest.xml"
    require(xml.resolve() == xml.absolute() and xml.is_file()
            and digest(xml) == report.get("pytest_xml_sha256"), "JUNIT_MISMATCH")
    # Re-derive counts from JUnit; do not trust the JSON counts alone.
    cases = list(ET.parse(xml).getroot().iter("testcase"))
    counts = {"tests": len(cases), "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for case in cases:
        key = next((k for k, tag in (("errors", "error"), ("failed", "failure"),
                    ("skipped", "skipped")) if case.find(tag) is not None), "passed")
        counts[key] += 1
    require(focal_passed(counts) and all(report.get("pytest", {}).get(k) == v
            for k, v in counts.items()), "FOCAL_NOT_PASS")
    backup = report.get("backup", {})
    name, pin = backup.get("backup_name", ""), backup.get("backup_sha256", "")
    require(backup.get("status") == "BACKUP_RESTORE_VERIFIED"
            and backup.get("revision") == OLD and backup.get("restore_target_disposable") is True
            and backup.get("live_restore_performed") is False
            and bool(re.fullmatch(r"[a-f0-9]{64}", pin)), "BACKUP_NOT_VERIFIED")
    path = private_file(root, name, ".sqlite3")
    require(path.is_file() and digest(path) == pin, "BACKUP_PIN_MISMATCH")
    require(rehearsal_passed(report.get("rehearsal"), name, pin), "REHEARSAL_NOT_PASS")
    return report


def execute(root, expected, report_name, backup_name, *, stopped):
    from sqlalchemy.engine import make_url
    from scripts.a00_baseline import check_checkout, child_environment, private_run_dir, run_step, junit_counts
    from scripts.a02_migration_rehearsal import rehearsal
    from tapi_gate0.discovery_backup import backup_and_restore_drill, _readonly, _inventory
    from tapi_gate0.discovery_local_db import validate_existing_database_url

    require(stopped, "ALL_WRITERS_MUST_STOP")
    check_checkout(root, expected)
    backup_path = private_file(root, backup_name, ".sqlite3")
    require(not backup_path.exists(), "BACKUP_EXISTS")
    target = private_run_dir(root, report_name)
    env = child_environment(root, os.environ)
    xml = target / "pytest.xml"
    report = {"schema": SCHEMA, "commit": expected, "status": "BLOCKED",
              "focal_files": list(FOCAL), "steps": [], "operational_database_mutated": False,
              "all_writers_stopped_attested": True, "external_credentials_forwarded": False,
              "network_sandbox": False, "global_gates_released": False}
    try:
        commands = (
            ("documentary", [sys.executable, "docs/base_atemporal/ferramentas/validar_espelho.py"]),
            ("legacy_gate0", [sys.executable, "scripts/check_gate0.py"]),
            ("zero_spend", [sys.executable, "scripts/verify_zero_spend.py"]),
            ("focal", [sys.executable, "-m", "pytest", "-q", *FOCAL, "--junitxml", str(xml)]),
        )
        for name, command in commands:
            step = run_step(root, target, name, command, env)
            report["steps"].append(step)
            require(step["exit_code"] == 0, "STEP_FAILED_" + name.upper())
        report["pytest"] = junit_counts(xml)
        require(focal_passed(report["pytest"]), "FOCAL_NOT_PASS")
        report["pytest_xml_sha256"] = digest(xml)
        check_checkout(root, expected)
        url = make_url(validate_existing_database_url(os.environ.get("TAPI_DATABASE_URL", "")))
        require(url.drivername == "sqlite", "SQLITE_ONLY")
        source = Path(url.database).absolute()
        require(source.resolve() == source, "SOURCE_REDIRECTED")
        tenant = os.environ.get("TAPI_TENANT_ID", "")
        require(bool(tenant), "TENANT_REQUIRED")
        with closing(_readonly(source)) as db:
            require(_inventory(db, tenant)["migration_versions"] == [OLD], "BASE_REVISION_REQUIRED")
        saved = backup_and_restore_drill(source, backup_path, tenant, stopped=True)
        require(saved["inventory"]["migration_versions"] == [OLD], "BASE_REVISION_REQUIRED")
        report["backup"] = {k: saved[k] for k in ("status", "backup_name", "backup_sha256",
                             "backup_bytes", "restore_target_disposable", "live_restore_performed")}
        report["backup"]["revision"] = OLD
        report["rehearsal"] = rehearsal(root, backup_name, saved["backup_sha256"], tenant, payloads=True)
        require(rehearsal_passed(report["rehearsal"], backup_name, saved["backup_sha256"]), "REHEARSAL_NOT_PASS")
        check_checkout(root, expected)
        report["checkout_unchanged"] = True
        report["status"] = "A02_PAYLOADS_PREFLIGHT_VERIFIED"
    except Exception as exc:
        report["code"] = str(exc) if str(exc).startswith("A02_PREFLIGHT_") else "A02_PREFLIGHT_LOCAL_ERROR"
        report["exception_type"] = type(exc).__name__
        report["keep_writers_stopped"] = True
    path = target / "summary.json"
    with path.open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    if report["status"] == "A02_PAYLOADS_PREFLIGHT_VERIFIED":
        verify_report(root, report_name, expected, digest(path))
    return report | {"report_name": report_name, "report_sha256": digest(path)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-head", required=True)
    p.add_argument("--report-name", required=True)
    p.add_argument("--backup-name", required=True)
    p.add_argument("--confirm-all-writers-stopped", action="store_true")
    a = p.parse_args(argv)
    try:
        report = execute(ROOT, a.expected_head, a.report_name, a.backup_name,
                         stopped=a.confirm_all_writers_stopped)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["status"] == "A02_PAYLOADS_PREFLIGHT_VERIFIED" else 2
    except (ValueError, OSError, subprocess.SubprocessError, ET.ParseError) as exc:
        code = str(exc) if str(exc).startswith("A02_PREFLIGHT_") else "A02_PREFLIGHT_LOCAL_ERROR"
        print(json.dumps({"status": "BLOCKED", "code": code, "keep_writers_stopped": True,
                          "operational_database_mutated": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
