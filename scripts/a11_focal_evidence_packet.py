"""A11: offline focal-validation evidence packet, NEVER release/gate approval.

Runs only fixed local Python, Node and headless-browser checks. Does not
download or install anything, access APIs, seed databases, activate connectors,
run ASR, run media workers, or publish. A green packet means ONLY these focal
diagnostics passed at one exact clean Git SHA. It is not A00 full regression,
G0-G6 validation, IMP-131 acceptance or proof of third-party creative rights.

Receipts contain aggregate counts, SHA-256 digests of local source/results,
fixed reason codes and no raw logs, credentials, captions or visual assets.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "tapi-a11-focal-evidence-packet.v1"
PY_A05_A07 = (
    "tests/test_studio_synthetic_provenance_a067.py",
    "tests/test_creative_reference_registry_a05.py",
    "tests/test_creative_reference_pep_a05.py",
    "tests/test_creative_reference_pep_migration_a05.py",
    "tests/test_creative_reference_rights_a05.py",
    "tests/test_agent_creative_preview_a05.py",
    "tests/test_agent_creative_studio_synthetic_a05.py",
    "tests/test_agent_b2.py",
    "tests/test_agent_atomic_draft_a05.py",
    "tests/test_agent_evidence_e1.py",
    "tests/test_agent_studio_handoff_integration.py",
    "tests/test_discovery_retrieval_scoped.py",
    "tests/test_discovery_editorial_agent.py",
    "tests/test_discovery_studio_handoff.py",
    "tests/test_studio_e1.py",
    "tests/test_studio_e4.py",
    "tests/test_studio_evidence_integrity_e6.py",
    "tests/test_studio_metadata_scope_e6.py",
)
PY_A073 = (
    "tests/test_a07_browser_visual_parity_runner.py",
    "tests/test_a07_browser_cdp_driver.py",
)
NODE_A073 = (
    "tests/frontend/test_studio_export_browser_fixture_a07.mjs",
    "tests/frontend/test_studio_export_a07.mjs",
    "tests/frontend/test_studio_timeline_e8.mjs",
)
# These are expected collection counts after the A05 B2 hardening tests, NOT
# required gate acceptance counts or a promise about all future code changes.
EXPECTED = {"python_a05_a07": 207, "python_a073_cdp": 13, "node_a073": 19}
SOURCE_FILES = (
    "scripts/a11_focal_evidence_packet.py",
    "scripts/a07_browser_visual_parity.py",
    "scripts/a07_browser_cdp.py",
    "scripts/verify_zero_spend.py",
    "src/tapi_gate0/web/studio_export_e4.js",
    "src/tapi_gate0/studio_synthetic_provenance_a067.py",
    "src/tapi_gate0/creative_reference_rights_a05.py",
    "src/tapi_gate0/creative_reference_registry_a05.py",
    "src/tapi_gate0/creative_reference_pep_a05.py",
    "src/tapi_gate0/agent_draft_a05.py",
    "src/tapi_gate0/agent_evidence_b2.py",
    "migrations/versions/0017_creative_reference_pep.py",
    "tests/frontend/studio_export_browser_a07.html",
) + PY_A05_A07 + PY_A073 + NODE_A073

GATES = {f"G{i}": "BLOCKED" for i in range(7)}
GATES["IMP-131"] = "BLOCKED"
RE_PY = re.compile(r"\b(\d+)\s+passed\b")
RE_PY_SKIP = re.compile(r"\b(\d+)\s+skipped\b")
RE_PY_FAIL = re.compile(r"\b(\d+)\s+failed\b")


def _digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def _redacted_result(argv: list[str], result, *, kind: str,
                     expected_count: int | None = None, seconds: float = 0.0):
    stdout = getattr(result, "stdout", "") or ""
    stderr = getattr(result, "stderr", "") or ""
    combined = stdout + "\n" + stderr
    rc = int(result.returncode)
    count = 0
    skips = 0
    fails = 0
    code = "A11_LOCAL_CHECK_FAILED"
    verified = False

    if kind == "pytest":
        matched = RE_PY.findall(stdout)
        skip_values = RE_PY_SKIP.findall(stdout)
        fail_values = RE_PY_FAIL.findall(stdout)
        count = int(matched[-1]) if len(matched) == 1 else 0
        skips = int(skip_values[-1]) if skip_values else 0
        fails = int(fail_values[-1]) if fail_values else 0
        verified = (rc == 0 and len(matched) == 1
                    and count == expected_count and skips == 0 and fails == 0)
        code = "A11_PYTEST_COUNTS_MATCH" if verified else "A11_PYTEST_INCOMPLETE"

    elif kind == "node":
        # Node's TAP output may prefix with Unicode informational marker.
        def metric(name: str):
            # In Python Unicode, the TAP info symbol "ℹ" is a \w character.
            # Accept only the actual Node summary prefixes, never arbitrary
            # preceding characters, to avoid a false positive on TAP failure.
            matches = re.findall(
                rf"(?m)^[ \t]*(?:ℹ(?:\ufe0f)?[ \t]+|#[ \t]+)"
                rf"{re.escape(name)}[ \t]+([0-9]+)[ \t]*$", stdout,
            )
            return int(matches[-1]) if len(matches) == 1 else None
        total, passed, failed, skipped, canceled, todo = (
            metric(name) for name in
            ("tests", "pass", "fail", "skipped", "cancelled", "todo")
        )
        count = passed or 0
        skips = skipped or 0
        fails = failed or 0
        verified = (
            rc == 0 and total == expected_count and passed == expected_count
            and failed == 0 and skipped == 0 and canceled == 0 and todo == 0
        )
        code = "A11_NODE_COUNTS_MATCH" if verified else "A11_NODE_INCOMPLETE"

    elif kind == "chrome":
        verified = rc == 0 and stdout.strip() == "A073_BROWSER_PARITY_PASS 7/7"
        count = 7 if verified else 0
        code = "A11_CHROME_VISUAL_7_OF_7" if verified else "A11_CHROME_NOT_VALIDATED"

    elif kind == "zero_spend":
        verified = (
            rc == 0 and stdout.strip()
            == "PASS — invariantes locais de gasto zero e bloqueio externo"
        )
        count = 1 if verified else 0
        code = "A11_ZERO_SPEND_CONFIRMED" if verified else "A11_ZERO_SPEND_UNVERIFIED"

    return {
        "argv": argv, "process_exit_code": rc,
        "reason_code": code, "passed": verified,
        "observed_pass_count": count,
        "observed_skip_count": skips,
        "observed_fail_count": fails,
        "expected_pass_count": expected_count if expected_count is not None
                               else (7 if kind == "chrome" else 1),
        "output_sha256": _digest(combined.encode("utf-8")),
        "elapsed_seconds": round(seconds, 3),
        "raw_output_stored": False,
    }


def _execute(argv: list[str], *, timeout: int, cwd: Path):
    return subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
        check=False, shell=False,
    )


def _command_result(run, argv: list[str], *, kind: str,
                    expected_count: int | None, timeout: int, root: Path):
    started = time.monotonic()
    try:
        result = run(argv, timeout=timeout, cwd=root)
    except subprocess.TimeoutExpired:
        return {
            "argv": argv, "reason_code": "A11_LOCAL_CHECK_TIMEOUT",
            "passed": False, "process_exit_code": None,
            "observed_pass_count": 0, "observed_skip_count": 0,
            "observed_fail_count": 0,
            "expected_pass_count": expected_count or (7 if kind == "chrome" else 1),
            "output_sha256": None, "elapsed_seconds": round(time.monotonic()-started,3),
            "raw_output_stored": False,
        }
    except OSError:
        return {
            "argv": argv, "reason_code": "A11_LOCAL_EXECUTABLE_UNAVAILABLE",
            "passed": False, "process_exit_code": None,
            "observed_pass_count": 0, "observed_skip_count": 0,
            "observed_fail_count": 0,
            "expected_pass_count": expected_count or (7 if kind == "chrome" else 1),
            "output_sha256": None, "elapsed_seconds": round(time.monotonic()-started,3),
            "raw_output_stored": False,
        }
    return _redacted_result(
        argv, result, kind=kind, expected_count=expected_count,
        seconds=time.monotonic()-started,
    )


def _git_state(run, root: Path, expected_head: str | None):
    try:
        rev = run(["git", "rev-parse", "HEAD"], timeout=10, cwd=root)
        status = run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            timeout=10, cwd=root,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, "A11_GIT_UNAVAILABLE"
    sha = rev.stdout.strip()
    if rev.returncode or status.returncode or not re.fullmatch(r"[a-f0-9]{40}", sha):
        return None, "A11_GIT_UNAVAILABLE"
    if status.stdout.strip():
        return sha, "A11_TRACKED_WORKTREE_DIRTY"
    if expected_head and sha != expected_head:
        return sha, "A11_EXPECTED_HEAD_MISMATCH"
    return sha, "A11_CLEAN_HEAD_VERIFIED"


def build_packet(*, root: Path = ROOT, expected_head: str | None = None,
                 run=_execute) -> dict:
    root = Path(root)
    head, reason = _git_state(run, root, expected_head)
    packet = {
        "schema_version": SCHEMA,
        "produced_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": "pablo-marchina/stone",
        "git_head": head,
        "git_status_reason": reason,
        "scope": "offline_focal_A05_A06_A07_A11_receipt_only",
        "validation_status": "BLOCKED_NOT_VALIDATED",
        "gate_status": dict(GATES),
        "imp131_accepted": False,
        "full_a00_validated_on_this_head": False,
        "independent_gold_available": False,
        "external_reference_rights_verified": False,
        "science_approved": False,
        "production_approved": False,
        "studio_publication_approved": False,
        "zero_spend_check_observed": False,
        "source_sha256": {},
        "checks": [],
        "limits": [
            "Focal local diagnostics only; NOT complete A00 or CT-STUDIO acceptance",
            "Synthetic references and browser-local pixels; no licensed external creatives",
            "No independent gold, real-world source rights, publication or deployment",
            "G0-G6 remain BLOCKED and IMP-131 not accepted",
        ],
    }
    if reason != "A11_CLEAN_HEAD_VERIFIED":
        return packet
    for path in SOURCE_FILES:
        file = root / path
        if not file.is_file():
            packet["validation_status"] = "BLOCKED_SOURCE_MISSING"
            return packet
        packet["source_sha256"][path] = _digest(file.read_bytes())

    py = sys.executable
    steps = [
        # Windows redirected Python stdout may default to cp1252. UTF-8
        # mode makes the em dash in the exact verification receipt stable.
        # The exact PASS text and exit=0 remain mandatory; never normalize
        # undecodable output or reinterpret a failed process as approved.
        ("zero_spend", [py, "-X", "utf8", "scripts/verify_zero_spend.py"],
         "zero_spend", None, 30),
        ("python_a05_a07", [py, "-m", "pytest", "-q", "-rs", *PY_A05_A07],
         "pytest", EXPECTED["python_a05_a07"], 300),
        ("python_a073_cdp", [py, "-m", "pytest", "-q", "-rs", *PY_A073],
         "pytest", EXPECTED["python_a073_cdp"], 90),
        ("node_a073", ["node", "--test", *NODE_A073],
         "node", EXPECTED["node_a073"], 90),
        ("chrome_a073", [py, "scripts/a07_browser_visual_parity.py"],
         "chrome", 7, 70),
    ]
    for name, argv, kind, expected, timeout in steps:
        result = _command_result(
            run, argv, kind=kind, expected_count=expected,
            timeout=timeout, root=root,
        )
        packet["checks"].append({"check_id": name, **result})
        if name == "zero_spend":
            packet["zero_spend_check_observed"] = result["passed"]
            if not result["passed"]:
                packet["validation_status"] = "BLOCKED_ZERO_SPEND_PREFLIGHT"
                return packet  # Fail before ANY further execution.

    if len(packet["checks"]) == 5 and all(c["passed"] for c in packet["checks"]):
        packet["validation_status"] = "FOCAL_DIAGNOSTICS_VERIFIED_NO_GATE_RELEASE"
    return packet


def write_packet(packet: dict, location: Path) -> str:
    """Create only, never overwrite an old receipt even after a failed run."""
    serialized = (json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2)
                  + "\n").encode("utf-8")
    location.parent.mkdir(parents=True, exist_ok=True)
    with location.open("xb") as out:
        out.write(serialized)
    return _digest(serialized)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="New local .json receipt; an existing file is never overwritten")
    parser.add_argument("--expected-head",
                        help="Optional exact 40-character commit to require")
    options = parser.parse_args(argv)
    if options.expected_head and not re.fullmatch(r"[0-9a-f]{40}", options.expected_head):
        parser.error("--expected-head requires a full 40-character lowercase Git SHA")
    receipt = build_packet(expected_head=options.expected_head)
    try:
        digest = write_packet(receipt, options.output)
    except (OSError, ValueError):
        print("A11_REPORT_WRITE_FAILED_OR_ALREADY_EXISTS")
        return 2
    print("A11_PACKET_STATUS=" + receipt["validation_status"])
    print("A11_GIT_HEAD=" + str(receipt["git_head"]))
    print("A11_REPORT_SHA256=" + digest)
    print("A11_GATE_STATUS=G0-G6_BLOCKED_IMP131_BLOCKED")
    return 0 if receipt["validation_status"] == (
        "FOCAL_DIAGNOSTICS_VERIFIED_NO_GATE_RELEASE"
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
