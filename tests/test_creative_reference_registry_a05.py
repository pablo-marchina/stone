"""A05.4 isolated persistence + signed source binding + authenticated inspection.

Local SQLite only. The source, owner, grants, trust anchor, approval digest and
Ed25519 keys are self-contained synthetic test fixtures, not operational proof.
"""
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256

import pytest
from sqlalchemy import select, update

from tapi_gate0.asset_rights import signed_bytes
from tapi_gate0.connectors import NormalizedItem, Platform
from tapi_gate0.creative_reference_rights_a05 import (
    ReferenceIdentity, ReferenceOperation, ReferenceGrantClaims,
    SignedReferenceGrant, ReferenceRevocationClaims, SignedReferenceRevocations,
    TrustedReferenceAuthority,
)
from tapi_gate0.creative_reference_registry_a05 import (
    ExperimentalReferenceRegistry, ReferenceRegistryDenied,
    authorities, revocations, grants, experimental_metadata,
)
from tapi_gate0.domain import MediaType
from tapi_gate0.identity import IdentityStore, memberships
from tapi_gate0.ingestion import (
    GrantCreate, IngestionStore, ingestion_records, source_grants,
)
from tapi_gate0.sa_store import SqlDomainStore, content_items, engine_for
from tapi_gate0.storage import now_utc

TENANT = "a054-local"
ACCOUNT = "17841400011122233"
ITEM = "17900000000011111"
PASSWORD = "test-local-authenticated-reference-123456"


@pytest.fixture
def registry(tmp_path):
    crypto = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    key = crypto.Ed25519PrivateKey.generate()
    engine = engine_for("sqlite:///" + str(tmp_path / "ref-a054.sqlite"))
    SqlDomainStore(engine).initialize()
    identity = IdentityStore(engine)
    identity.bootstrap(TENANT, "Fixture only", "localadmin", PASSWORD)
    signed_in = identity.login("localadmin", PASSWORD, TENANT).access_token
    experimental_metadata.create_all(engine)  # Explicit disposable-only opt-in.
    ingest = IngestionStore(engine)
    now = now_utc()
    ingest.grant(TENANT, "fixture", GrantCreate(
        platform=Platform.INSTAGRAM, source_account_id=ACCOUNT,
        approval_reference="fixture-only-metadata-grant",
        expires_at=now + timedelta(days=1),
    ))
    with engine.begin() as db:
        db.execute(update(source_grants).where(
            source_grants.c.tenant_id == TENANT,
        ).values(technical_verified_at=now_utc().isoformat()))
    ingest._persist_item(TENANT, NormalizedItem(
        platform=Platform.INSTAGRAM,
        source_account_id=ACCOUNT, source_item_id=ITEM,
        creator_handle="fictional_source", media_type=MediaType.REELS,
        source_url="https://www.instagram.com/p/SyntheticFixture123/",
        published_at=now - timedelta(days=30),
        caption="Fictional local metadata, not licensed content.",
        likes=1, comments=0, follower_count=100,
        denominator_quality="observed_current_only", metadata_only=True,
    ))
    with engine.connect() as db:
        cid = db.scalar(select(ingestion_records.c.content_id).where(
            ingestion_records.c.tenant_id == TENANT))
        payload = db.scalar(select(content_items.c.payload).where(
            content_items.c.tenant_id == TENANT, content_items.c.id == cid))
    target = ReferenceIdentity(
        tenant_id=TENANT, platform="instagram",
        source_account_id=ACCOUNT, content_id=cid,
        content_sha256=sha256(payload.encode("utf-8")).hexdigest(),
    )
    def sign(claims):
        return key.sign(signed_bytes(claims)).hex()
    def state(revision=1, **changes):
        claims = ReferenceRevocationClaims(**(
            dict(issuer_id="a054-test-authority", revision=revision,
                 issued_at=now_utc() - timedelta(seconds=5),
                 valid_until=now_utc() + timedelta(minutes=9)) | changes
        ))
        return SignedReferenceRevocations(
            claims=claims, signature=sign(claims),
        )
    def anchor(signed):
        return TrustedReferenceAuthority(
            issuer_id="a054-test-authority",
            public_key=key.public_key().public_bytes_raw(),
            tenant_platform_scope=frozenset({(TENANT, "instagram")}),
            min_revocation_revision=signed.claims.revision,
            revocation_claims_sha256=sha256(signed_bytes(signed.claims)).hexdigest(),
        )
    def grant(**changes):
        claims = ReferenceGrantClaims(**(
            dict(issuer_id="a054-test-authority", grant_id="a054-fixture-grant",
                 target=target, approval_evidence_sha256="a" * 64,
                 issued_at=now_utc() - timedelta(minutes=10),
                 not_before=now_utc() - timedelta(minutes=5),
                 expires_at=now_utc() + timedelta(hours=1),
                 operations=(ReferenceOperation.CREATIVE_SPEC_REFERENCE,)) | changes
        ))
        return SignedReferenceGrant(claims=claims, signature=sign(claims))
    first = state()
    svc = ExperimentalReferenceRegistry(engine)
    try:
        yield dict(engine=engine, identity=identity, token=signed_in,
                   svc=svc, target=target, first=first, anchor=anchor(first),
                   state=state, pin=anchor, grant=grant, key=key,
                   content_id=cid)
    finally:
        engine.dispose()


def provision(r):
    r["svc"].provision(r["anchor"], TENANT, "instagram", r["first"])


def register(r):
    provision(r)
    assert r["svc"].register(r["anchor"], r["grant"](),
                             verified_approval_digest="a" * 64)


def inspect(r, **changes):
    args = dict(identity_store=r["identity"], token=r["token"],
                anchor=r["anchor"], grant_id="a054-fixture-grant",
                target=r["target"],
                operation=ReferenceOperation.CREATIVE_SPEC_REFERENCE)
    return r["svc"].inspect_authenticated(**(args | changes))


def test_auth_requires_persisted_authority_and_grant(registry):
    r = registry
    assert inspect(r)["reason_code"] == "A054_AUTHORITY_UNREGISTERED"
    provision(r)
    assert inspect(r)["reason_code"] == "A054_GRANT_NOT_REGISTERED"
    assert r["svc"].register(r["anchor"], r["grant"](),
                             verified_approval_digest="a" * 64)
    result = inspect(r)
    assert result["status"] == "CONTRACT_VERIFIED_DIAGNOSTIC_ONLY"
    assert result["contract_verified"] is True
    assert result["authenticated_tenant_verified"] is True
    assert result["permitted_use"] == "private_contract_diagnostic_only"
    for key in ("operational_action_allowed", "creative_spec_allowed",
                "studio_write_allowed", "publication_allowed",
                "current_external_legal_rights_independently_audited",
                "scientifically_validated", "gates_released",
                "production_approved"):
        assert result[key] is False
    assert r["content_id"] not in str(result)
    assert r["token"] not in str(result)


def test_registration_is_idempotent_with_out_of_band_approval(registry):
    r = registry
    provision(r)
    # Idempotency means replaying the identical signed document, not issuing
    # another grant with the same ID and slightly different now_utc() fields.
    original = r["grant"]()
    with pytest.raises(ReferenceRegistryDenied, match="A054_TRUSTED_APPROVAL_REQUIRED"):
        r["svc"].register(r["anchor"], original,
                          verified_approval_digest="b" * 64)
    assert r["svc"].register(r["anchor"], original,
                             verified_approval_digest="a" * 64) is True
    assert r["svc"].register(r["anchor"], original,
                             verified_approval_digest="a" * 64) is False
    # A different, correctly signed payload with the SAME grant ID must not
    # silently replace the first grant, even with the trusted approval digest.
    changed = r["grant"](expires_at=original.claims.expires_at + timedelta(minutes=1))
    assert changed.claims.grant_id == original.claims.grant_id
    assert changed.model_dump_json() != original.model_dump_json()
    with pytest.raises(ReferenceRegistryDenied, match="A054_GRANT_ID_CONFLICT"):
        r["svc"].register(r["anchor"], changed,
                          verified_approval_digest="a" * 64)
    with r["engine"].connect() as db:
        persisted = db.execute(select(grants.c.payload)).scalars().all()
        assert persisted == [original.model_dump_json()]


def test_source_grant_revocation_and_content_drift_are_rechecked(registry):
    r = registry
    register(r)
    assert inspect(r)["contract_verified"] is True
    with r["engine"].begin() as db:
        db.execute(update(source_grants).where(
            source_grants.c.tenant_id == TENANT,
        ).values(enabled=0))
    assert inspect(r)["reason_code"] == "A054_LIVE_SOURCE_BINDING_REQUIRED"
    with r["engine"].begin() as db:
        db.execute(update(source_grants).where(
            source_grants.c.tenant_id == TENANT,
        ).values(enabled=1))
        db.execute(update(content_items).where(
            content_items.c.tenant_id == TENANT,
            content_items.c.id == r["content_id"],
        ).values(payload='{"forged":"data"}'))
    assert inspect(r)["reason_code"] == "A054_LIVE_SOURCE_BINDING_REQUIRED"


def test_wrong_tenant_wrong_token_and_revoked_session_denied(registry):
    r = registry
    register(r)
    assert inspect(r, token="forged-token")["reason_code"] == \
        "A054_AUTHENTICATED_SESSION_REQUIRED"
    wrong = r["target"].model_copy(update={"tenant_id": "otherTenant"})
    assert inspect(r, target=wrong)["reason_code"] == \
        "A054_AUTHORIZED_ROLE_AND_TENANT_REQUIRED"
    principal = r["identity"].resolve(r["token"])
    r["identity"].revoke(r["token"], principal)
    assert inspect(r)["reason_code"] == "A054_AUTHENTICATED_SESSION_REQUIRED"


def test_current_membership_role_is_rechecked_on_each_inspection(registry):
    r = registry
    register(r)
    with r["engine"].begin() as db:
        db.execute(update(memberships).where(
            memberships.c.tenant_id == TENANT,
        ).values(role="viewer"))
    assert inspect(r)["reason_code"] == \
        "A054_AUTHORIZED_ROLE_AND_TENANT_REQUIRED"


def test_operation_is_not_transferrable_between_creative_and_studio(registry):
    r = registry
    register(r)
    result = inspect(r, operation=ReferenceOperation.STUDIO_DRAFT_REFERENCE)
    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "A054_SIGNED_POLICY_DENIED"


def test_revocation_requires_persistent_update_and_new_independent_pin(registry):
    r = registry
    register(r)
    revoked = r["state"](revision=2, revoked_grant_ids=("a054-fixture-grant",))
    assert r["svc"].advance(r["anchor"], TENANT, "instagram", revoked) is True
    assert inspect(r)["reason_code"] == "A054_INDEPENDENT_HOST_PIN_MISMATCH"
    new_anchor = r["pin"](revoked)
    assert inspect(r, anchor=new_anchor)["reason_code"] == "A054_SIGNED_POLICY_DENIED"
    assert r["svc"].advance(new_anchor, TENANT, "instagram", revoked) is False
    with r["engine"].connect() as db:
        assert len(db.execute(select(revocations)).all()) == 2


def test_revocation_is_monotonic_no_unrevoking_or_equivocation(registry):
    r = registry
    register(r)
    revoked = r["state"](revision=2, revoked_content_ids=(r["content_id"],))
    r["svc"].advance(r["anchor"], TENANT, "instagram", revoked)
    new_anchor = r["pin"](revoked)
    with pytest.raises(ReferenceRegistryDenied, match="A054_REVOCATION_REMOVAL"):
        r["svc"].advance(new_anchor, TENANT, "instagram", r["state"](revision=3))
    with pytest.raises(ReferenceRegistryDenied, match="A054_REVISION_NOT_INCREASING"):
        r["svc"].advance(new_anchor, TENANT, "instagram",
                         r["state"](revision=2, revoked_content_ids=("forged",)))


def test_host_key_hash_and_state_corruption_fail_closed(registry):
    r = registry
    register(r)
    corrupted = replace(r["anchor"], public_key=b"\x00" * 32)
    assert inspect(r, anchor=corrupted)["reason_code"] == "A054_HOST_KEY_MISMATCH"
    with r["engine"].begin() as db:
        db.execute(update(revocations).values(payload='{"broken":true}'))
    assert inspect(r)["reason_code"] == "A054_REVOCATION_RECORD_INVALID"


def test_source_binding_is_not_established_by_signed_grant_alone(registry):
    r = registry
    provision(r)
    wrong = r["target"].model_copy(update={"content_sha256": "f" * 64})
    with pytest.raises(ReferenceRegistryDenied, match="A054_LIVE_SOURCE_BINDING_REQUIRED"):
        r["svc"].register(
            r["anchor"], r["grant"](target=wrong),
            verified_approval_digest="a" * 64,
        )


def test_no_schema_auto_provisioning_without_explicit_experimental_setup(tmp_path):
    engine = engine_for("sqlite:///" + str(tmp_path / "no-auto.sqlite"))
    SqlDomainStore(engine).initialize()
    try:
        with engine.connect() as db:
            # The experimental schema is separate from the domain metadata.
            from sqlalchemy import text
            names = db.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'a054_reference_%'"
            )).scalars().all()
        assert names == []
    finally:
        engine.dispose()
