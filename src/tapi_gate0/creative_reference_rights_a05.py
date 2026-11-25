"""A05.3: offline signed *reference* rights contract, not an operational PEP.

The caller must supply an independently provisioned authority, current signed
revocations, trusted clock and a content digest bound to verified source rows.
This module never provisions rights, reads an operational DB, creates an HTTP
endpoint, calls providers, or authorizes an agent, Studio write or publication.

A positive policy decision verifies a narrow signed contract only; separate
authenticated PEP, source/record binding, durable revocation state and approval
are mandatory at every actual use. Ingestion/caption-research grants and
media asset rights are intentionally NOT accepted here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from hashlib import sha256
from typing import Literal

from pydantic import Field, model_validator

from .asset_rights import (
    Digest, Id, RightsModel, Signature, _signature_ok, signed_bytes,
)
from .policy import Decision

VERSION = "creative-reference-rights.v1"
REVOCATION_VERSION = "creative-reference-revocations.v1"
MAX_REVOCATION_AGE = timedelta(minutes=15)


class ReferenceOperation(str, Enum):
    CREATIVE_SPEC_REFERENCE = "creative_spec_reference"
    STUDIO_DRAFT_REFERENCE = "studio_draft_reference"


class ReferenceIdentity(RightsModel):
    tenant_id: Id
    platform: Literal["instagram", "youtube", "stone_internal"]
    source_account_id: Id
    content_id: Id
    # Digest of the exact canonical source content representation chosen by
    # the trusted host. Never a hash of untrusted client-supplied free text.
    content_sha256: Digest


class ReferenceGrantClaims(RightsModel):
    schema_version: Literal["creative-reference-rights.v1"] = VERSION
    issuer_id: Id
    grant_id: Id
    target: ReferenceIdentity
    approval_evidence_sha256: Digest
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    operations: tuple[ReferenceOperation, ...] = Field(min_length=1, max_length=2)
    purpose: Literal["studio_creation"] = "studio_creation"

    @model_validator(mode="after")
    def validate_grant(self):
        times = (self.issued_at, self.not_before, self.expires_at)
        if any(t.tzinfo is None or t.utcoffset() is None for t in times):
            raise ValueError("CREATIVE_REFERENCE_AWARE_TIMESTAMPS_REQUIRED")
        if not self.issued_at <= self.not_before < self.expires_at:
            raise ValueError("CREATIVE_REFERENCE_TIME_WINDOW_INVALID")
        if len(set(self.operations)) != len(self.operations):
            raise ValueError("CREATIVE_REFERENCE_DUPLICATE_OPERATION")
        return self


class SignedReferenceGrant(RightsModel):
    claims: ReferenceGrantClaims
    signature: Signature


class ReferenceSource(RightsModel):
    tenant_id: Id
    platform: Literal["instagram", "youtube", "stone_internal"]
    source_account_id: Id


class ReferenceRevocationClaims(RightsModel):
    schema_version: Literal["creative-reference-revocations.v1"] = REVOCATION_VERSION
    issuer_id: Id
    revision: int = Field(ge=0, strict=True)
    issued_at: datetime
    valid_until: datetime
    revoked_grant_ids: tuple[Id, ...] = Field(default=(), max_length=10000)
    revoked_content_ids: tuple[Id, ...] = Field(default=(), max_length=10000)
    revoked_sources: tuple[ReferenceSource, ...] = Field(default=(), max_length=10000)

    @model_validator(mode="after")
    def validate_revocation_window(self):
        if any(t.tzinfo is None or t.utcoffset() is None
               for t in (self.issued_at, self.valid_until)):
            raise ValueError("CREATIVE_REFERENCE_AWARE_TIMESTAMPS_REQUIRED")
        if not timedelta(0) < self.valid_until - self.issued_at <= MAX_REVOCATION_AGE:
            raise ValueError("CREATIVE_REFERENCE_REVOCATION_WINDOW_INVALID")
        if (len(set(self.revoked_grant_ids)) != len(self.revoked_grant_ids)
                or len(set(self.revoked_content_ids)) != len(self.revoked_content_ids)
                or len(set(self.revoked_sources)) != len(self.revoked_sources)):
            raise ValueError("CREATIVE_REFERENCE_DUPLICATE_REVOCATION")
        return self


class SignedReferenceRevocations(RightsModel):
    claims: ReferenceRevocationClaims
    signature: Signature


@dataclass(frozen=True)
class TrustedReferenceAuthority:
    """Trusted host state, never accepted from a client or grant document."""
    issuer_id: str
    public_key: bytes
    tenant_platform_scope: frozenset[tuple[str, str]]
    min_revocation_revision: int
    revocation_claims_sha256: str


def decide_reference_contract(*, authority: TrustedReferenceAuthority | None,
                              grant: SignedReferenceGrant | None,
                              revocations: SignedReferenceRevocations | None,
                              target: ReferenceIdentity,
                              operation: ReferenceOperation,
                              now: datetime) -> Decision:
    """Check signatures and exact reference scope; NEVER authorize a PEP by itself."""
    def deny(code):
        return Decision(False, code, "Autorizacao criativa de referencia nao demonstrada.")

    if (not isinstance(authority, TrustedReferenceAuthority)
            or not isinstance(grant, SignedReferenceGrant)
            or not isinstance(revocations, SignedReferenceRevocations)):
        return deny("CREATIVE_REF_SIGNED_EVIDENCE_REQUIRED")
    if not isinstance(target, ReferenceIdentity) or not isinstance(operation, ReferenceOperation):
        return deny("CREATIVE_REF_REQUEST_INVALID")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return deny("CREATIVE_REF_TRUSTED_CLOCK_REQUIRED")

    claims, state = grant.claims, revocations.claims
    if (not isinstance(authority.issuer_id, str)
            or claims.issuer_id != authority.issuer_id
            or state.issuer_id != authority.issuer_id
            or (target.tenant_id, target.platform) not in authority.tenant_platform_scope
            or type(authority.public_key) is not bytes
            or len(authority.public_key) != 32):
        return deny("CREATIVE_REF_UNTRUSTED_AUTHORITY")
    if (not _signature_ok(authority.public_key, claims, grant.signature)
            or not _signature_ok(authority.public_key, state, revocations.signature)):
        return deny("CREATIVE_REF_SIGNATURE_INVALID")
    if (type(authority.min_revocation_revision) is not int
            or authority.min_revocation_revision < 0
            or type(authority.revocation_claims_sha256) is not str
            or state.revision != authority.min_revocation_revision
            or sha256(signed_bytes(state)).hexdigest() != authority.revocation_claims_sha256):
        return deny("CREATIVE_REF_REVOCATION_STATE_MISMATCH")
    if not state.issued_at <= now < state.valid_until:
        return deny("CREATIVE_REF_REVOCATION_STALE")
    if not claims.not_before <= now < claims.expires_at:
        return deny("CREATIVE_REF_GRANT_INACTIVE")
    source = ReferenceSource(
        tenant_id=target.tenant_id,
        platform=target.platform,
        source_account_id=target.source_account_id,
    )
    if (claims.grant_id in state.revoked_grant_ids
            or target.content_id in state.revoked_content_ids
            or source in state.revoked_sources):
        return deny("CREATIVE_REF_REVOKED")
    if claims.target != target:
        return deny("CREATIVE_REF_TARGET_MISMATCH")
    if operation not in claims.operations or claims.purpose != "studio_creation":
        return deny("CREATIVE_REF_OPERATION_MISMATCH")
    return Decision(
        True, "CREATIVE_REF_SIGNED_SCOPE_ONLY",
        "Contrato assinado corresponde; uso real depende de PEP autenticado e direitos vigentes.",
    )
