"""A05.3 signed reference-contract tests. All keys/scopes are temporary fixtures.

This exercises Ed25519 cryptography and a pure policy, not grants from Stone,
providers, a trusted host, or any A05/MCP/Studio operational path.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest
from pydantic import ValidationError

from tapi_gate0.asset_rights import (
    AssetIdentity, GrantClaims as MediaGrantClaims, SignedGrant as SignedMediaGrant,
    signed_bytes,
)
from tapi_gate0.creative_reference_rights_a05 import (
    ReferenceIdentity, ReferenceOperation, ReferenceGrantClaims,
    SignedReferenceGrant, ReferenceSource, ReferenceRevocationClaims,
    SignedReferenceRevocations, TrustedReferenceAuthority,
    decide_reference_contract,
)

NOW = datetime(2026, 11, 21, 16, tzinfo=timezone.utc)
TARGET = ReferenceIdentity(
    tenant_id="tenantA", platform="instagram",
    source_account_id="sourceA", content_id="postA",
    content_sha256="a" * 64,
)


@pytest.fixture
def signed_reference():
    crypto = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    private = crypto.Ed25519PrivateKey.generate()
    pub = private.public_key().public_bytes_raw()

    def grant(**overrides):
        data = {
            "issuer_id": "trusted-reference-test", "grant_id": "grantA",
            "target": TARGET, "approval_evidence_sha256": "b" * 64,
            "issued_at": NOW - timedelta(hours=1),
            "not_before": NOW - timedelta(minutes=30),
            "expires_at": NOW + timedelta(hours=1),
            "operations": (ReferenceOperation.CREATIVE_SPEC_REFERENCE,),
        }
        data.update(overrides)
        claims = ReferenceGrantClaims(**data)
        return SignedReferenceGrant(
            claims=claims, signature=private.sign(signed_bytes(claims)).hex(),
        )

    def revocations(**overrides):
        data = {
            "issuer_id": "trusted-reference-test", "revision": 7,
            "issued_at": NOW - timedelta(minutes=2),
            "valid_until": NOW + timedelta(minutes=8),
        }
        data.update(overrides)
        claims = ReferenceRevocationClaims(**data)
        return SignedReferenceRevocations(
            claims=claims, signature=private.sign(signed_bytes(claims)).hex(),
        )

    def authority(state):
        return TrustedReferenceAuthority(
            issuer_id="trusted-reference-test", public_key=pub,
            tenant_platform_scope=frozenset({("tenantA", "instagram")}),
            min_revocation_revision=state.claims.revision,
            revocation_claims_sha256=sha256(signed_bytes(state.claims)).hexdigest(),
        )

    return grant, revocations, authority


def evaluate(fixture, *, grant=None, state=None, authority=None, target=TARGET,
             operation=ReferenceOperation.CREATIVE_SPEC_REFERENCE, now=NOW):
    create_grant, create_revocations, create_authority = fixture
    grant = create_grant() if grant is None else grant
    state = create_revocations() if state is None else state
    authority = create_authority(state) if authority is None else authority
    return decide_reference_contract(
        authority=authority, grant=grant, revocations=state,
        target=target, operation=operation, now=now,
    )


def test_signed_reference_contract_is_only_local_policy_preflight(signed_reference):
    result = evaluate(signed_reference)
    assert result.permitted is True
    assert result.code == "CREATIVE_REF_SIGNED_SCOPE_ONLY"
    assert "PEP" in result.reason
    # This is not an HTTP route, Studio write, publishing token or a rights grant.


def test_no_grant_no_revocations_and_no_trusted_host_deny(signed_reference):
    grant, state, anchor = signed_reference
    actual = state()
    g = grant()
    a = anchor(actual)
    for kwargs in (
        {"authority": None, "grant": g, "revocations": actual},
        {"authority": a, "grant": None, "revocations": actual},
        {"authority": a, "grant": g, "revocations": None},
        {"authority": a, "grant": "self-asserted", "revocations": actual},
    ):
        decision = decide_reference_contract(
            target=TARGET, operation=ReferenceOperation.CREATIVE_SPEC_REFERENCE,
            now=NOW, **kwargs,
        )
        assert not decision.permitted
        assert decision.code == "CREATIVE_REF_SIGNED_EVIDENCE_REQUIRED"


@pytest.mark.parametrize("changes", [
    {"tenant_id": "tenantB"},
    {"platform": "youtube"},
    {"source_account_id": "sourceB"},
    {"content_id": "postB"},
    {"content_sha256": "e" * 64},
])
def test_exact_target_binding_does_not_widen_source_or_tenant(signed_reference, changes):
    changed = ReferenceIdentity(**(TARGET.model_dump() | changes))
    result = evaluate(signed_reference, target=changed)
    assert not result.permitted
    assert result.code in ("CREATIVE_REF_TARGET_MISMATCH", "CREATIVE_REF_UNTRUSTED_AUTHORITY")


def test_other_operation_is_denied_without_signed_permission(signed_reference):
    decision = evaluate(
        signed_reference, operation=ReferenceOperation.STUDIO_DRAFT_REFERENCE,
    )
    assert decision.code == "CREATIVE_REF_OPERATION_MISMATCH"
    assert not decision.permitted


@pytest.mark.parametrize("revoked", [
    {"revoked_grant_ids": ("grantA",)},
    {"revoked_content_ids": ("postA",)},
    {"revoked_sources": (ReferenceSource(tenant_id="tenantA", platform="instagram",
                                         source_account_id="sourceA"),)},
])
def test_revocation_by_grant_content_or_source(signed_reference, revoked):
    _, state, _ = signed_reference
    decision = evaluate(signed_reference, state=state(**revoked))
    assert decision.code == "CREATIVE_REF_REVOKED"
    assert not decision.permitted


def test_expired_or_future_grant_denied(signed_reference):
    grant, _, _ = signed_reference
    expired = grant(
        not_before=NOW - timedelta(hours=4),
        issued_at=NOW - timedelta(hours=5),
        expires_at=NOW - timedelta(minutes=1),
    )
    assert evaluate(signed_reference, grant=expired).code == "CREATIVE_REF_GRANT_INACTIVE"
    not_yet = grant(
        issued_at=NOW,
        not_before=NOW + timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )
    assert evaluate(signed_reference, grant=not_yet).code == "CREATIVE_REF_GRANT_INACTIVE"


def test_stale_revocation_snapshot_denied(signed_reference):
    _, state, _ = signed_reference
    stale = state(
        issued_at=NOW - timedelta(minutes=20),
        valid_until=NOW - timedelta(minutes=10),
    )
    assert evaluate(signed_reference, state=stale).code == "CREATIVE_REF_REVOCATION_STALE"


def test_rollback_or_same_revision_equivocation_denied(signed_reference):
    grant, state, anchor = signed_reference
    current = state()
    trusted = anchor(current)
    rollback = state(revision=6)
    assert evaluate(signed_reference, state=rollback, authority=trusted).code == \
        "CREATIVE_REF_REVOCATION_STATE_MISMATCH"
    equivocal = state(revoked_grant_ids=("anotherGrant",))
    assert evaluate(signed_reference, state=equivocal, authority=trusted).code == \
        "CREATIVE_REF_REVOCATION_STATE_MISMATCH"


def test_signature_mutation_and_wrong_trust_key_denied(signed_reference):
    grant, state, anchor = signed_reference
    g, s = grant(), state()
    mutated = g.model_copy(update={"signature": "0" * 128})
    assert evaluate(signed_reference, grant=mutated).code == "CREATIVE_REF_SIGNATURE_INVALID"
    invalid_authority = replace(anchor(s), public_key=b"\x00" * 32)
    assert evaluate(signed_reference, authority=invalid_authority).code == \
        "CREATIVE_REF_SIGNATURE_INVALID"


def test_time_requires_trusted_aware_clock(signed_reference):
    assert evaluate(signed_reference, now=datetime(2026, 11, 21, 16)).code == \
        "CREATIVE_REF_TRUSTED_CLOCK_REQUIRED"


def test_unsigned_media_rights_are_not_reference_rights(signed_reference):
    grant, state, anchor = signed_reference
    current = state()
    fake = SignedMediaGrant.model_construct(
        claims=MediaGrantClaims.model_construct(schema_version="asset-rights.v1"),
        signature="0" * 128,
    )
    decision = decide_reference_contract(
        authority=anchor(current), grant=fake, revocations=current,
        target=TARGET, operation=ReferenceOperation.CREATIVE_SPEC_REFERENCE,
        now=NOW,
    )
    assert decision.code == "CREATIVE_REF_SIGNED_EVIDENCE_REQUIRED"


def test_reject_tampered_schema_duplicate_permissions_and_invalid_times():
    data = {
        "issuer_id": "test", "grant_id": "g", "target": TARGET,
        "approval_evidence_sha256": "a" * 64,
        "issued_at": NOW - timedelta(hours=1),
        "not_before": NOW - timedelta(minutes=30),
        "expires_at": NOW + timedelta(hours=1),
        "operations": (ReferenceOperation.CREATIVE_SPEC_REFERENCE,),
    }
    for delta in (
        {"schema_version": "asset-rights.v1"},
        {"operations": (ReferenceOperation.CREATIVE_SPEC_REFERENCE,) * 2},
        {"expires_at": NOW - timedelta(minutes=1)},
        {"issued_at": datetime(2026, 11, 21, 16)},
    ):
        with pytest.raises(ValidationError):
            ReferenceGrantClaims(**(data | delta))


def test_signed_revocation_window_is_bounded_and_duplicate_free():
    base = {
        "issuer_id": "test", "revision": 1,
        "issued_at": NOW, "valid_until": NOW + timedelta(minutes=5),
    }
    for delta in (
        {"valid_until": NOW + timedelta(minutes=16)},
        {"valid_until": NOW},
        {"revoked_content_ids": ("postA", "postA")},
        {"revision": True},
    ):
        with pytest.raises(ValidationError):
            ReferenceRevocationClaims(**(base | delta))
