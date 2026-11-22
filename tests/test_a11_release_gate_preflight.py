"""Synthetic, local-only gate-signature tests; never claim live release approval."""
import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from scripts import a11_release_gate_preflight as pre

HEAD = "a" * 40


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(obj))


@pytest.fixture
def signed_case(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    gate_csv = root / "planning/base_atemporal/MATRIZ_GATE_GLOBAL.csv"
    gate_csv.parent.mkdir(parents=True)
    gate_csv.write_text("gate_id\n" + "\n".join(pre.GATES) + "\n", encoding="utf-8")
    keys = {name: Ed25519PrivateKey.generate() for name in ("rights", "quality", "release")}
    assignments = {g: ("rights" if g == "G0-PERMISSIONS" else "quality") for g in pre.GATES}
    assignments["IMP-131"] = "release"
    trust = tmp_path / "independently-provisioned-trust.json"
    dump(trust, {"schema_version": "tapi-external-trust-bundle.v1",
                 "assignments": assignments,
                 "signers": {name: base64.b64encode(key.public_key().public_bytes(
                     encoding=serialization.Encoding.Raw,
                     format=serialization.PublicFormat.Raw,
                 )).decode() for name, key in keys.items()}})
    now = datetime.now(timezone.utc)
    digest_by_gate = {}

    def sign(subject, evidence, *, key=None, head=HEAD):
        proof = root / "evidence/gates/proofs" / (subject + ".json")
        dump(proof, evidence)
        payload = {
            "schema_version": "tapi-release-attestation.v1",
            "subject": subject, "status": "PASS", "git_head": head,
            "evidence_path": f"evidence/gates/proofs/{subject}.json",
            "evidence_sha256": sha256(proof.read_bytes()).hexdigest(),
            "evaluated_at": (now - timedelta(minutes=1)).isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat(),
            "signer_id": assignments[subject],
        }
        signed = canonical(payload)
        signer = key or keys[assignments[subject]]
        payload["signature_b64"] = base64.b64encode(signer.sign(signed)).decode()
        dump(root / "evidence/gates" / (subject + ".json"), payload)
        return sha256(signed).hexdigest()

    for g in pre.GATES:
        digest_by_gate[g] = sign(g, {"fixture": "not_real_evidence", "gate": g})
    sign("IMP-131", {"schema_version": "tapi-imp131-release-acceptance.v1",
                     "git_head": HEAD,
                     "gate_receipt_sha256": digest_by_gate,
                     "acceptance": "ACCEPTED_FOR_RELEASE_REVIEW"})
    monkeypatch.setattr(pre, "_git_state", lambda r, h: "GIT_CLEAN_HEAD_VERIFIED")
    return root, trust, keys, sign, digest_by_gate


def check(case):
    root, trust, *_ = case
    return pre.evaluate(root, expected_head=HEAD, trust_bundle=trust)


def test_signed_receipts_verify_without_authorizing_a_deployment(signed_case):
    report = check(signed_case)
    assert report["status"] == "SIGNED_RECEIPTS_COMPLETE_HUMAN_REVIEW_REQUIRED"
    assert report["deploy_authorized"] is False
    assert report["reason_codes"] == []
    assert len(report["verified_receipt_digests"]) == 8
    assert all(s == "SIGNED_EVIDENCE_VERIFIED" for s in report["gates"].values())


def test_gate_receipt_absent_blocks(signed_case):
    (signed_case[0] / "evidence/gates/G4-SECURITY.json").unlink()
    report = check(signed_case)
    assert report["status"] == "NO_GO"
    assert report["gates"]["G4-SECURITY"] == "BLOCKED"


def test_proof_modification_blocks(signed_case):
    (signed_case[0] / "evidence/gates/proofs/G0-PERMISSIONS.json").write_text('tampered')
    report = check(signed_case)
    assert report["status"] == "NO_GO"
    assert "G0-PERMISSIONS:PROOF_DIGEST_INVALID" in report["reason_codes"]


def test_wrong_key_blocks_even_with_valid_looking_signature(signed_case):
    root, _trust, keys, sign, _digest = signed_case
    sign("G1-CONTRACT", {"fixture": "not_real_evidence"}, key=keys["rights"])
    report = check(signed_case)
    assert report["status"] == "NO_GO"
    assert report["gates"]["G1-CONTRACT"] == "BLOCKED"


def test_other_git_head_does_not_authorize(signed_case):
    root, _trust, _keys, sign, _digest = signed_case
    sign("G6-ISO", {"fixture": "not_real_evidence"}, head="b" * 40)
    assert check(signed_case)["status"] == "NO_GO"


def test_imp131_cannot_accept_unrelated_gate_receipt_hashes(signed_case):
    _root, _trust, _keys, sign, _digest = signed_case
    sign("IMP-131", {"schema_version": "tapi-imp131-release-acceptance.v1",
                     "git_head": HEAD, "gate_receipt_sha256": {},
                     "acceptance": "ACCEPTED_FOR_RELEASE_REVIEW"})
    report = check(signed_case)
    assert report["status"] == "NO_GO"
    assert report["IMP-131"] == "BLOCKED"
    assert "IMP-131:ACCEPTANCE_BINDING_INVALID" in report["reason_codes"]


def test_trust_bundle_cannot_be_owned_by_repository(signed_case):
    root, trust, *_ = signed_case
    location = root / "trust.json"
    location.write_bytes(trust.read_bytes())
    report = pre.evaluate(root, expected_head=HEAD, trust_bundle=location)
    assert report["status"] == "NO_GO"
    assert "TRUST_OR_NORMATIVE_BASE_INVALID" in report["reason_codes"]


def test_trust_reusing_release_signer_for_gate_blocks(signed_case):
    _root, trust, *_ = signed_case
    obj = json.loads(trust.read_text())
    obj["assignments"]["G2-REPRODUCIBILITY"] = obj["assignments"]["IMP-131"]
    dump(trust, obj)
    assert check(signed_case)["status"] == "NO_GO"


def test_malformed_traversal_proof_path_denied(signed_case):
    root, _trust, _keys, _sign, _digest = signed_case
    p = root / "evidence/gates/G4-SECURITY.json"
    data = json.loads(p.read_text())
    data["evidence_path"] = "evidence/gates/proofs/../../../passwords"
    dump(p, data)
    report = check(signed_case)
    assert report["status"] == "NO_GO"
    assert report["gates"]["G4-SECURITY"] == "BLOCKED"


def test_expired_gate_denied(signed_case):
    root, *_ = signed_case
    p = root / "evidence/gates/G1-CONTRACT.json"
    data = json.loads(p.read_text())
    data["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    dump(p, data)
    assert check(signed_case)["status"] == "NO_GO"


def test_dirty_checkout_never_validates_gate_receipts(signed_case, monkeypatch):
    monkeypatch.setattr(pre, "_git_state", lambda r, h: "GIT_WORKTREE_DIRTY")
    report = check(signed_case)
    assert report["status"] == "NO_GO"
    assert report["verified_receipt_digests"] == {}


def test_invalid_normative_gate_count_blocks(signed_case):
    root, *_ = signed_case
    (root / "planning/base_atemporal/MATRIZ_GATE_GLOBAL.csv").write_text(
        "gate_id\nG0-PERMISSIONS\n", encoding="utf-8")
    assert check(signed_case)["status"] == "NO_GO"
