"""Asset-rights policy core (IMP-044/054), no operational authority configured.

Trusted host supplies anchors, a trusted clock and a durable revocation floor.
Untrusted callers supply signed documents and an exact requested scope, never
the trust anchor. No network, filesystem, database or media operation here.
An allow decision is not a reusable bearer credential or permission to bypass
the still-disabled production entrypoints.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from .policy import Decision

VERSION = "asset-rights.v1"
MAX_REVOCATION_AGE = timedelta(minutes=15)
Id = Annotated[str, StringConstraints(min_length=1,max_length=128,pattern=r"^[A-Za-z0-9_.:-]+$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Signature = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{128}$")]


class AssetOperation(str, Enum):
    DOWNLOAD = "download"
    RETAIN = "retain"
    PROCESS = "process"
    DERIVE = "derive"
    DISPLAY = "display"
    EXPORT = "export"
    PUBLISH = "publish"


class RightsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AssetIdentity(RightsModel):
    tenant_id: Id
    platform: Literal["instagram","youtube"]
    source_account_id: Id
    source_item_id: Id
    content_id: Id
    asset_id: Id
    media_kind: Literal["image","video","audio"]
    sha256: Digest


class Permission(RightsModel):
    operation: AssetOperation
    purpose: Literal["research_analysis","studio_creation","distribution"]
    field: Literal["image","video","audio","transcript","ocr","visual_features",
                   "rubric_evidence","creative_derivative"]
    # Exact triples, not a Cartesian product of independently allowed lists.


class GrantClaims(RightsModel):
    schema_version: Literal["asset-rights.v1"] = VERSION
    issuer_id: Id
    grant_id: Id
    target: AssetIdentity
    approval_evidence_sha256: Digest
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    retain_until: datetime
    permissions: tuple[Permission,...] = Field(min_length=1,max_length=64)

    @model_validator(mode="after")
    def valid_scope(self):
        times=(self.issued_at,self.not_before,self.expires_at,self.retain_until)
        if any(t.tzinfo is None or t.utcoffset() is None for t in times):
            raise ValueError("RIGHTS_AWARE_TIMESTAMPS_REQUIRED")
        if not self.issued_at <= self.not_before < self.expires_at or self.retain_until <= self.not_before:
            raise ValueError("RIGHTS_TIME_WINDOW_INVALID")
        if len(set(self.permissions))!=len(self.permissions):
            raise ValueError("RIGHTS_DUPLICATE_PERMISSION")
        return self


class SignedGrant(RightsModel):
    claims: GrantClaims
    signature: Signature


class RevokedSource(RightsModel):
    tenant_id: Id
    platform: Literal["instagram","youtube"]
    source_account_id: Id


class RevocationClaims(RightsModel):
    schema_version: Literal["asset-revocations.v1"] = "asset-revocations.v1"
    issuer_id: Id
    revision: int = Field(ge=0,strict=True)
    issued_at: datetime
    valid_until: datetime
    revoked_grant_ids: tuple[Id,...] = Field(max_length=10000)
    revoked_asset_ids: tuple[Id,...] = Field(max_length=10000)
    revoked_sources: tuple[RevokedSource,...] = Field(default=(),max_length=10000)

    @model_validator(mode="after")
    def valid_window(self):
        if any(t.tzinfo is None or t.utcoffset() is None for t in (self.issued_at,self.valid_until)):
            raise ValueError("RIGHTS_AWARE_TIMESTAMPS_REQUIRED")
        if not timedelta(0) < self.valid_until-self.issued_at <= MAX_REVOCATION_AGE:
            raise ValueError("RIGHTS_REVOCATION_WINDOW_INVALID")
        if len(set(self.revoked_grant_ids))!=len(self.revoked_grant_ids) or len(set(self.revoked_asset_ids))!=len(self.revoked_asset_ids) or len(set(self.revoked_sources))!=len(self.revoked_sources):
            raise ValueError("RIGHTS_DUPLICATE_REVOCATION")
        return self


class SignedRevocations(RightsModel):
    claims: RevocationClaims
    signature: Signature


@dataclass(frozen=True)
class TrustedAuthority:
    """Provisioned out of band by a trusted host, never by an API caller."""
    issuer_id: str
    public_key: bytes
    tenant_platform_scope: frozenset[tuple[str,str]]
    # A durable monotonic floor supplied by trusted registry. No default.
    min_revocation_revision: int
    # Hash of the exact accepted revocation snapshot at this floor. This
    # prevents same-revision equivocation; higher revisions need provisioning.
    revocation_claims_sha256: str


def signed_bytes(claims: RightsModel) -> bytes:
    """Versioned, deterministic JSON wire format, not RFC8785/JCS."""
    return json.dumps(claims.model_dump(mode="json"),sort_keys=True,
        separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")


def _signature_ok(public_key, claims, signature):
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
    except ImportError:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(bytes.fromhex(signature),signed_bytes(claims))
        return True
    except (InvalidSignature, UnsupportedAlgorithm, ValueError, TypeError):
        return False


def decide_asset(*, authority: TrustedAuthority | None, grant: SignedGrant | None,
                 revocations: SignedRevocations | None, target: AssetIdentity,
                 permission: Permission, now: datetime) -> Decision:
    """Evaluate exact signed scope, expiry and current revocation evidence.

    Call only from trusted application code. A positive policy decision does
    not execute anything; the production PEP and registry remain separate.
    """
    def deny(code):
        return Decision(False,code,"Direito de ativo não demonstrado para esta operação.")
    if authority is None or grant is None or revocations is None:
        return deny("ASSET_RIGHTS_EVIDENCE_REQUIRED")
    if now.tzinfo is None or now.utcoffset() is None:
        return deny("ASSET_RIGHTS_TRUSTED_CLOCK_REQUIRED")
    g,rv=grant.claims,revocations.claims
    if (g.issuer_id!=authority.issuer_id or rv.issuer_id!=authority.issuer_id
            or (target.tenant_id,target.platform) not in authority.tenant_platform_scope):
        return deny("ASSET_RIGHTS_UNTRUSTED_ISSUER")
    if not _signature_ok(authority.public_key,g,grant.signature) or not _signature_ok(authority.public_key,rv,revocations.signature):
        return deny("ASSET_RIGHTS_SIGNATURE_INVALID")
    from hashlib import sha256
    if (type(authority.min_revocation_revision) is not int or authority.min_revocation_revision<0
            or rv.revision!=authority.min_revocation_revision
            or sha256(signed_bytes(rv)).hexdigest()!=authority.revocation_claims_sha256):
        return deny("ASSET_RIGHTS_REVOCATION_STATE_MISMATCH")
    if not rv.issued_at<=now<rv.valid_until:
        return deny("ASSET_RIGHTS_REVOCATION_STALE")
    if not g.not_before<=now<min(g.expires_at,g.retain_until):
        return deny("ASSET_RIGHTS_GRANT_INACTIVE")
    source = RevokedSource(tenant_id=target.tenant_id,platform=target.platform,
        source_account_id=target.source_account_id)
    if (g.grant_id in rv.revoked_grant_ids or target.asset_id in rv.revoked_asset_ids
            or source in rv.revoked_sources):
        return deny("ASSET_RIGHTS_REVOKED")
    if g.target!=target:
        return deny("ASSET_RIGHTS_TARGET_MISMATCH")
    if permission not in g.permissions:
        return deny("ASSET_RIGHTS_SCOPE_MISMATCH")
    return Decision(True,"ASSET_RIGHTS_EXACT_SCOPE","Escopo assinado e estado de revogação correspondentes; execução depende do PEP.")


class AssetRightsDenied(PermissionError):
    pass


def require_asset_rights(**scope) -> Decision:
    """Fail-closed preflight for future PEPs; invoke again at every use.

    No media adapter is enabled by this helper. Future PEPs must additionally
    bind actual bytes to target.sha256, authenticate the actor, check source
    grant, enforce retention and recheck on output/commit.
    """
    decision = decide_asset(**scope)
    if not decision.permitted:
        raise AssetRightsDenied(decision.code)
    return decision
