"""A11: offline, read-only release-evidence preflight. Never deploys or releases a gate.

Gate receipts are signed by externally pinned authorities and bound to an exact
Git commit plus local evidence bytes. Neither this check nor a synthetically
signed test receipt establishes legal rights, scientific quality, or approval.
The trust bundle MUST be provisioned independently of this repository.
"""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

GATES = ("G0-PERMISSIONS", "G1-CONTRACT", "G2-REPRODUCIBILITY",
         "G3-EVAL", "G4-SECURITY", "G5-OPS", "G6-ISO")
SCHEMA = "tapi-a11-release-gate-preflight.v1"
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
RECEIPT_FIELDS = frozenset({"schema_version", "subject", "status", "git_head",
                            "evidence_path", "evidence_sha256", "evaluated_at",
                            "expires_at", "signer_id", "signature_b64"})


def _json_file(path: Path) -> dict:
    if path.stat().st_size > 65536:
        raise ValueError("TOO_LARGE")
    with path.open("rb") as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise ValueError("TOO_LARGE")
    obj = json.loads(data)
    if not isinstance(obj, dict):
        raise ValueError("NOT_OBJECT")
    return obj


def _timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("TIME_INVALID")
    t = datetime.fromisoformat(value)
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return t.astimezone(timezone.utc)


def _inside_evidence(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.startswith("evidence/gates/proofs/"):
        raise ValueError("PROOF_LOCATION_INVALID")
    # Resolve symlinks and traversal; receipts cannot read arbitrary host files.
    base = (root / "evidence/gates/proofs").resolve()
    target = (root / relative).resolve()
    if (not base.is_relative_to(root.resolve())
            or not target.is_relative_to(base) or not target.is_file()):
        raise ValueError("PROOF_LOCATION_INVALID")
    return target


def _check_receipt(root, subject, raw, head, anchors, now):
    if set(raw) != RECEIPT_FIELDS:
        return "RECEIPT_SCHEMA_INVALID", None
    if (raw["schema_version"] != "tapi-release-attestation.v1"
            or raw["subject"] != subject or raw["status"] != "PASS"
            or raw["git_head"] != head
            or not isinstance(raw["evidence_sha256"], str)
            or not DIGEST.fullmatch(raw["evidence_sha256"])):
        return "RECEIPT_SCOPE_INVALID", None
    try:
        evaluated, expires = _timestamp(raw["evaluated_at"]), _timestamp(raw["expires_at"])
        if not (now - timedelta(days=7) <= evaluated <= now < expires
                and expires <= evaluated + timedelta(days=7)):
            return "RECEIPT_EXPIRED_OR_FUTURE", None
        file = _inside_evidence(root, raw["evidence_path"])
        if file.stat().st_size > 8_000_000:
            return "PROOF_DIGEST_INVALID", None
        data = file.read_bytes()
        if sha256(data).hexdigest() != raw["evidence_sha256"]:
            return "PROOF_DIGEST_INVALID", None
        signer = raw["signer_id"]
        if (not isinstance(signer, str) or not isinstance(anchors.get("signers"), dict)
                or signer not in anchors["signers"]
                or anchors.get("assignments", {}).get(subject) != signer):
            return "TRUSTED_SIGNER_MISSING", None
        key_bytes = base64.b64decode(anchors["signers"][signer], validate=True)
        sig = base64.b64decode(raw["signature_b64"], validate=True)
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        payload = {k: raw[k] for k in raw if k != "signature_b64"}
        signed = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False).encode("utf-8")
        Ed25519PublicKey.from_public_bytes(key_bytes).verify(sig, signed)
        return "SIGNED_EVIDENCE_VERIFIED", sha256(signed).hexdigest()
    except Exception:
        # Do not include exception text, paths, keys or evidence in the report.
        return "SIGNED_EVIDENCE_INVALID", None


def _git_state(root: Path, head: str) -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                             text=True, capture_output=True, timeout=10, check=False)
        # Private receipts may be untracked; only tracked source modifications
        # invalidate the SHA-pinned checkout.
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root,
                               text=True, capture_output=True, timeout=10, check=False)
        if rev.returncode or dirty.returncode or rev.stdout.strip() != head:
            return "GIT_HEAD_MISMATCH"
        if dirty.stdout.strip():
            return "GIT_WORKTREE_DIRTY"
        return "GIT_CLEAN_HEAD_VERIFIED"
    except (OSError, subprocess.TimeoutExpired):
        return "GIT_UNAVAILABLE"


def evaluate(root: Path, *, expected_head: str, trust_bundle: Path,
             now: datetime | None = None) -> dict:
    root = root.resolve()
    result = {"schema_version": SCHEMA, "git_head": expected_head,
              "status": "NO_GO", "deploy_authorized": False,
              "gates": {g: "BLOCKED" for g in GATES}, "IMP-131": "BLOCKED",
              "reason_codes": [], "verified_receipt_digests": {}}
    if not isinstance(expected_head, str) or not SHA.fullmatch(expected_head):
        result["reason_codes"].append("INVALID_EXPECTED_SHA")
        return result
    git_status = _git_state(root, expected_head)
    if git_status != "GIT_CLEAN_HEAD_VERIFIED":
        result["reason_codes"].append(git_status)
        return result
    try:
        # The Git checkout cannot provide its own trust authority.
        if trust_bundle.resolve().is_relative_to(root):
            raise ValueError("UNTRUSTED_LOCAL_KEY")
        anchors = _json_file(trust_bundle)
        if anchors.get("schema_version") != "tapi-external-trust-bundle.v1":
            raise ValueError("TRUST_SCHEMA_INVALID")
        assignments = anchors.get("assignments", {})
        if (set(assignments) != set(GATES) | {"IMP-131"}
                or len(set(assignments.values())) < 3
                or assignments["G0-PERMISSIONS"] == assignments["IMP-131"]
                or assignments["IMP-131"] in {assignments[x] for x in GATES}
                or len({anchors["signers"][assignments[x]]
                        for x in (*GATES, "IMP-131")}) < 3
                or anchors["signers"][assignments["IMP-131"]] in {
                    anchors["signers"][assignments[x]] for x in GATES
                }):
            raise ValueError("TRUST_ROLE_SEPARATION_INVALID")
        with (root / "planning/base_atemporal/MATRIZ_GATE_GLOBAL.csv").open(
                encoding="utf-8-sig", newline="") as f:
            listed = [r["gate_id"] for r in csv.DictReader(f)]
        if len(listed) != len(GATES) or set(listed) != set(GATES):
            raise ValueError("NORMATIVE_GATES_INVALID")
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        result["reason_codes"].append("TRUST_OR_NORMATIVE_BASE_INVALID")
        return result
    moment = now or datetime.now(timezone.utc)
    digests = {}
    for subject in (*GATES, "IMP-131"):
        path = root / "evidence/gates" / (subject + ".json")
        try:
            receipt = _json_file(path)
            reason, digest = _check_receipt(root, subject, receipt, expected_head,
                                            anchors, moment)
        except (OSError, ValueError, UnicodeError):
            reason, digest = "RECEIPT_MISSING_OR_INVALID", None
        if digest is not None:
            digests[subject] = digest
            if subject in result["gates"]:
                result["gates"][subject] = "SIGNED_EVIDENCE_VERIFIED"
            else:
                result["IMP-131"] = "SIGNED_EVIDENCE_VERIFIED"
        else:
            result["reason_codes"].append(subject + ":" + reason)
    # This verifies signed evidence existence and integrity, not acceptance
    # of the actual proof by scientific/legal operators. Never auto-deploy.
    result["verified_receipt_digests"] = digests
    if len(digests) == len(GATES) + 1:
        # The final acceptance must bind the exact seven gate receipts.
        try:
            accepted = _json_file(_inside_evidence(root,
                _json_file(root / "evidence/gates/IMP-131.json")["evidence_path"]))
            if (accepted.get("schema_version") != "tapi-imp131-release-acceptance.v1"
                    or accepted.get("git_head") != expected_head
                    or accepted.get("gate_receipt_sha256") != {
                        gate: digests[gate] for gate in GATES
                    }
                    or accepted.get("acceptance") != "ACCEPTED_FOR_RELEASE_REVIEW"):
                raise ValueError("FINAL_ACCEPTANCE_BINDING_INVALID")
            result["status"] = "SIGNED_RECEIPTS_COMPLETE_HUMAN_REVIEW_REQUIRED"
        except (OSError, KeyError, ValueError, TypeError):
            result["reason_codes"].append("IMP-131:ACCEPTANCE_BINDING_INVALID")
            result["IMP-131"] = "BLOCKED"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--trust-bundle", required=True, type=Path)
    args = parser.parse_args()
    report = evaluate(args.root, expected_head=args.expected_head,
                      trust_bundle=args.trust_bundle)
    print(json.dumps(report, sort_keys=True, ensure_ascii=False))
    # Never use a zero exit code as deploy authorization. Human gate review
    # and a separate release operation remain mandatory even if signatures pass.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
