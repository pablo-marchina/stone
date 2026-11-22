"""A05.4 local reference-rights registry / authenticated NON-ACTIONABLE inspection.

An experimental, explicitly created SQL schema holds signed grants/revocations.
Independent host trust pins are passed by trusted local code, never API callers.
This module has NO HTTP/MCP registration, no workflow permission, no publisher,
no Studio write, no external I/O and no credential/anchor provisioning.

Even an authenticated positive inspection is evidence of a checked contract,
not an authorization to generate a CreativeSpec or use a source operationally.
The normal B2 and Studio paths are deliberately NOT wired to this diagnostic.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256

from pydantic import ValidationError
from sqlalchemy import (
    BigInteger, Column, MetaData, String, Table, Text, and_, insert,
    select, update,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .asset_rights import _signature_ok, signed_bytes
from .creative_reference_rights_a05 import (
    ReferenceIdentity, ReferenceOperation, SignedReferenceGrant,
    SignedReferenceRevocations, TrustedReferenceAuthority,
    decide_reference_contract,
)
from .domain import ContentItem, Creator
from .identity import IdentityFailure, IdentityStore
from .ingestion import ingestion_records, source_grants
from .sa_store import content_items, creators
from .storage import now_utc

VERSION = "tapi-a054-local-reference-registry.v1"

# Deliberately NOT attached to domain metadata or migrations. Tests explicitly
# instantiate these tables in disposable SQLite only. Production migration,
# authority provisioning and authentication at a real PEP remain BLOCKED.
experimental_metadata = MetaData()
authorities = Table(
    "a054_reference_authorities", experimental_metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("platform", String(32), primary_key=True),
    Column("issuer_id", String(128), primary_key=True),
    Column("public_key_sha256", String(64), nullable=False),
    Column("revision", BigInteger, nullable=False),
    Column("state_sha256", String(64), nullable=False),
)
revocations = Table(
    "a054_reference_revocations", experimental_metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("platform", String(32), primary_key=True),
    Column("issuer_id", String(128), primary_key=True),
    Column("revision", BigInteger, primary_key=True),
    Column("state_sha256", String(64), nullable=False),
    Column("payload", Text, nullable=False),
)
grants = Table(
    "a054_reference_grants", experimental_metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("platform", String(32), primary_key=True),
    Column("issuer_id", String(128), primary_key=True),
    Column("grant_id", String(128), primary_key=True),
    Column("content_id", String(128), nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("claims_sha256", String(64), nullable=False),
    Column("payload", Text, nullable=False),
)


class ReferenceRegistryDenied(PermissionError):
    """Typed denial; no source text, IDs, tokens or submitted claims."""


def _deny(reason):
    raise ReferenceRegistryDenied("A054_" + reason)


def _digest(claims):
    return sha256(signed_bytes(claims)).hexdigest()


def _key(anchor, tenant, platform):
    if (not isinstance(anchor, TrustedReferenceAuthority)
            or not isinstance(anchor.public_key, bytes)
            or len(anchor.public_key) != 32
            or (tenant, platform) not in anchor.tenant_platform_scope
            or not isinstance(anchor.issuer_id, str) or not anchor.issuer_id):
        _deny("TRUSTED_HOST_REQUIRED")
    return {"tenant_id": tenant, "platform": platform, "issuer_id": anchor.issuer_id}


def _where(table, key):
    return [table.c[name] == value for name, value in key.items()]


def _state_valid(anchor, state, now):
    if (not isinstance(state, SignedReferenceRevocations)
            or state.claims.issuer_id != anchor.issuer_id
            or not _signature_ok(anchor.public_key, state.claims, state.signature)):
        _deny("SIGNED_REVOCATION_REQUIRED")
    if not state.claims.issued_at <= now < state.claims.valid_until:
        _deny("REVOCATION_STALE")


def _load(db, key, anchor):
    row = db.execute(select(authorities).where(*_where(authorities, key))).mappings().one_or_none()
    if row is None:
        _deny("AUTHORITY_UNREGISTERED")
    if row["public_key_sha256"] != sha256(anchor.public_key).hexdigest():
        _deny("HOST_KEY_MISMATCH")
    if (type(anchor.min_revocation_revision) is not int
            or anchor.min_revocation_revision != row["revision"]
            or anchor.revocation_claims_sha256 != row["state_sha256"]):
        _deny("INDEPENDENT_HOST_PIN_MISMATCH")
    record = db.execute(select(revocations).where(
        *_where(revocations, key), revocations.c.revision == row["revision"],
    )).mappings().one_or_none()
    if record is None:
        _deny("REVOCATION_RECORD_MISSING")
    try:
        state = SignedReferenceRevocations.model_validate_json(record["payload"])
    except (ValidationError, ValueError, TypeError):
        _deny("REVOCATION_RECORD_INVALID")
    if (state.claims.revision != row["revision"]
            or state.claims.issuer_id != key["issuer_id"]
            or _digest(state.claims) != row["state_sha256"]
            or record["state_sha256"] != row["state_sha256"]):
        _deny("REVOCATION_RECORD_CORRUPT")
    _state_valid(anchor, state, now_utc())
    return row, state


def _source_bound(db, target, now):
    """Require precise live ingestion provenance AND independent creative grant.

    Technical source grants alone are never interpreted as creative rights.
    """
    if target.platform not in ("instagram", "youtube"):
        return False
    ir, sg, ci, cr = ingestion_records, source_grants, content_items, creators
    joined = (
        ir.join(sg, and_(
            ir.c.tenant_id == sg.c.tenant_id,
            ir.c.platform == sg.c.platform,
            ir.c.source_account_id == sg.c.source_account_id,
        ))
        .join(ci, and_(ir.c.tenant_id == ci.c.tenant_id,
                       ir.c.content_id == ci.c.id))
        .join(cr, and_(ci.c.tenant_id == cr.c.tenant_id,
                       ci.c.creator_id == cr.c.id))
    )
    matches = db.execute(
        select(sg.c.enabled, sg.c.approved_at, sg.c.expires_at,
               sg.c.technical_verified_at, ci.c.origin,
               ci.c.creator_id.label("indexed_creator_id"),
               ci.c.published_at.label("indexed_published_at"),
               ci.c.payload.label("content_payload"),
               cr.c.id.label("indexed_creator_row_id"),
               cr.c.origin.label("creator_origin"),
               cr.c.payload.label("creator_payload"))
        .select_from(joined)
        .where(
            ir.c.tenant_id == target.tenant_id,
            ir.c.platform == target.platform,
            ir.c.source_account_id == target.source_account_id,
            ir.c.content_id == target.content_id,
            ir.c.metadata_only == 1,
        )
    ).mappings().all()
    if len(matches) != 1:
        return False
    row = matches[0]
    if (row["enabled"] != 1 or row["origin"] != target.platform
            or row["creator_origin"] != target.platform):
        return False
    try:
        a, v, e = (
            datetime.fromisoformat(row[key]) for key in
            ("approved_at", "technical_verified_at", "expires_at")
        )
        content = ContentItem.model_validate_json(row["content_payload"])
        creator = Creator.model_validate_json(row["creator_payload"])
        indexed_published = datetime.fromisoformat(row["indexed_published_at"])
        return bool(
            a.tzinfo and v.tzinfo and e.tzinfo and indexed_published.tzinfo
            and a <= v <= now < e
            and content.published_at == indexed_published
            and content.published_at <= now
            and content.creator_id == row["indexed_creator_id"]
            and creator.creator_id == row["indexed_creator_row_id"]
            and creator.created_at <= now
            and content.tenant_id == target.tenant_id
            and content.content_id == target.content_id
            and content.origin.value == target.platform
            and not content.is_synthetic
            and content.created_at <= now
            and creator.tenant_id == target.tenant_id
            and creator.creator_id == content.creator_id
            and creator.origin.value == target.platform
            and creator.source_profile_id == target.source_account_id
            and sha256(row["content_payload"].encode("utf-8")).hexdigest()
                == target.content_sha256
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def _output(*, reason, matched=False):
    return {
        "schema_version": VERSION,
        "status": "CONTRACT_VERIFIED_DIAGNOSTIC_ONLY" if matched else "BLOCKED",
        "reason_code": reason,
        "contract_verified": bool(matched),
        "permitted_use": "private_contract_diagnostic_only" if matched else "none",
        "authenticated_tenant_verified": bool(matched),
        "operational_action_allowed": False,
        "creative_spec_allowed": False,
        "studio_write_allowed": False,
        "publication_allowed": False,
        "current_external_legal_rights_independently_audited": False,
        "scientifically_validated": False,
        "gates_released": False,
        "production_approved": False,
    }


class ExperimentalReferenceRegistry:
    """Local-only, write-explicit registry; DO NOT wire to an API or MCP.

    Caller must create experimental_metadata on disposable SQLite separately.
    The registry never creates tables or provisions anchors by itself.
    """

    def __init__(self, engine):
        self.engine = engine

    def provision(self, anchor, tenant, platform, state):
        key = _key(anchor, tenant, platform)
        now = now_utc()
        _state_valid(anchor, state, now)
        if (state.claims.revision != anchor.min_revocation_revision
                or _digest(state.claims) != anchor.revocation_claims_sha256):
            _deny("INITIAL_HOST_PIN_INVALID")
        try:
            with self.engine.begin() as db:
                db.execute(insert(authorities).values(
                    **key,
                    public_key_sha256=sha256(anchor.public_key).hexdigest(),
                    revision=state.claims.revision, state_sha256=_digest(state.claims),
                ))
                db.execute(insert(revocations).values(
                    **key, revision=state.claims.revision,
                    state_sha256=_digest(state.claims),
                    payload=state.model_dump_json(),
                ))
        except IntegrityError as exc:
            raise ReferenceRegistryDenied("A054_PROVISION_CONFLICT") from exc

    def advance(self, anchor, tenant, platform, state):
        key = _key(anchor, tenant, platform)
        _state_valid(anchor, state, now_utc())
        try:
            with self.engine.begin() as db:
                old, previous = _load(db, key, anchor)
                if (state.claims.revision == old["revision"]
                        and _digest(state.claims) == old["state_sha256"]):
                    return False
                if state.claims.revision <= old["revision"]:
                    _deny("REVISION_NOT_INCREASING")
                if state.claims.issued_at < previous.claims.issued_at:
                    _deny("REVOCATION_TIME_ROLLBACK")
                for field in ("revoked_grant_ids", "revoked_content_ids", "revoked_sources"):
                    if not set(getattr(previous.claims, field)) <= set(
                            getattr(state.claims, field)):
                        _deny("REVOCATION_REMOVAL")
                updated = db.execute(update(authorities).where(
                    *_where(authorities, key),
                    authorities.c.revision == old["revision"],
                    authorities.c.state_sha256 == old["state_sha256"],
                ).values(
                    revision=state.claims.revision,
                    state_sha256=_digest(state.claims),
                ))
                if updated.rowcount != 1:
                    _deny("CONCURRENT_REVOCATION_UPDATE")
                db.execute(insert(revocations).values(
                    **key, revision=state.claims.revision,
                    state_sha256=_digest(state.claims),
                    payload=state.model_dump_json(),
                ))
                return True
        except IntegrityError as exc:
            raise ReferenceRegistryDenied("A054_REVOCATION_CONFLICT") from exc

    def register(self, anchor, grant, *, verified_approval_digest):
        if not isinstance(grant, SignedReferenceGrant):
            _deny("SIGNED_GRANT_REQUIRED")
        target = grant.claims.target
        key = _key(anchor, target.tenant_id, target.platform)
        if (type(verified_approval_digest) is not str
                or verified_approval_digest != grant.claims.approval_evidence_sha256):
            _deny("TRUSTED_APPROVAL_REQUIRED")
        try:
            with self.engine.begin() as db:
                _, state = _load(db, key, anchor)
                now = now_utc()
                if not _source_bound(db, target, now):
                    _deny("LIVE_SOURCE_BINDING_REQUIRED")
                decision = decide_reference_contract(
                    authority=anchor, grant=grant, revocations=state,
                    target=target, operation=grant.claims.operations[0], now=now,
                )
                if not decision.permitted:
                    _deny("SIGNED_GRANT_SCOPE_INVALID")
                prior = db.execute(select(grants).where(
                    *_where(grants, key),
                    grants.c.grant_id == grant.claims.grant_id,
                )).mappings().one_or_none()
                serialized = grant.model_dump_json()
                if prior is not None:
                    if prior["payload"] != serialized:
                        _deny("GRANT_ID_CONFLICT")
                    return False
                db.execute(insert(grants).values(
                    **key, grant_id=grant.claims.grant_id,
                    content_id=target.content_id,
                    content_sha256=target.content_sha256,
                    claims_sha256=_digest(grant.claims),
                    payload=serialized,
                ))
                return True
        except IntegrityError as exc:
            raise ReferenceRegistryDenied("A054_GRANT_INSERT_CONFLICT") from exc

    def inspect_authenticated(self, identity_store, token, anchor, grant_id,
                              target, operation):
        """Resolve a revocable session on each inspection; never grant a PEP.

        There is NO callable HTTP route. A positive result is diagnostic and
        MUST NOT be reused as an authorization for a separate operation.
        """
        if not isinstance(target, ReferenceIdentity) or not isinstance(
                operation, ReferenceOperation):
            return _output(reason="A054_REQUEST_INVALID")
        # A local caller cannot assert an arbitrary principal provider or
        # resolve a token against a different tenant/session database.
        # The host must inject its actual IdentityStore using this engine.
        # This is a non-actionable diagnostic, NOT an HTTP/MCP permission.
        if (type(identity_store) is not IdentityStore
                or identity_store.engine is not self.engine):
            return _output(reason="A054_TRUSTED_IDENTITY_STORE_REQUIRED")
        if not isinstance(token, str) or not token or len(token) > 256:
            return _output(reason="A054_AUTHENTICATED_SESSION_REQUIRED")
        try:
            principal = identity_store.resolve(token)
            accepted = (
                {"admin", "researcher", "editor"}
                if operation is ReferenceOperation.CREATIVE_SPEC_REFERENCE
                else {"admin", "editor"}
            )
            if principal.tenant_id != target.tenant_id or principal.role not in accepted:
                return _output(reason="A054_AUTHORIZED_ROLE_AND_TENANT_REQUIRED")
        except (IdentityFailure, AttributeError, TypeError, ValueError):
            return _output(reason="A054_AUTHENTICATED_SESSION_REQUIRED")
        try:
            key = _key(anchor, target.tenant_id, target.platform)
            with self.engine.connect() as db:
                _, state = _load(db, key, anchor)
                now = now_utc()
                if not _source_bound(db, target, now):
                    _deny("LIVE_SOURCE_BINDING_REQUIRED")
                row = db.execute(select(grants).where(
                    *_where(grants, key), grants.c.grant_id == grant_id,
                )).mappings().one_or_none()
                if row is None:
                    _deny("GRANT_NOT_REGISTERED")
                try:
                    grant = SignedReferenceGrant.model_validate_json(row["payload"])
                except (ValidationError, ValueError, TypeError):
                    _deny("GRANT_RECORD_INVALID")
                if (grant.claims.grant_id != grant_id
                        or grant.claims.target.content_id != row["content_id"]
                        or grant.claims.target.content_sha256 != row["content_sha256"]
                        or _digest(grant.claims) != row["claims_sha256"]):
                    _deny("GRANT_RECORD_CORRUPT")
                decision = decide_reference_contract(
                    authority=anchor, grant=grant, revocations=state,
                    target=target, operation=operation, now=now,
                )
                if not decision.permitted:
                    _deny("SIGNED_POLICY_DENIED")
            return _output(reason="A054_PRIVATE_CONTRACT_MATCH", matched=True)
        except ReferenceRegistryDenied as exc:
            return _output(reason=str(exc))
        except (SQLAlchemyError, ValidationError, ValueError, TypeError):
            return _output(reason="A054_REGISTRY_INVALID_STATE")
