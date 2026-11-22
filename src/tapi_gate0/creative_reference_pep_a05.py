"""A05: transactional, session-bound creative-reference PEP.

This is an opt-in runtime boundary, NOT authority provisioning or evidence that
any third-party license exists. The host must pin independently verified
TrustedReferenceAuthority objects and provision the reviewed registry schema
and source/creative grants out of band. No default trusted authority exists.

A metadata ingestion grant by itself NEVER authorizes creative reuse. Both
creative_spec_reference and studio_draft_reference must be signed and active.
No network calls, credential issuance, media access or publication are here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Mapping
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import insert, select
from sqlalchemy.exc import SQLAlchemyError

from .asset_rights import signed_bytes
from .creative_reference_registry_a05 import (
    ReferenceRegistryDenied, _digest, _key, _load, _source_bound,
    authorities as registry_authorities, grants as registered_grants,
)
from .creative_reference_rights_a05 import (
    ReferenceOperation, SignedReferenceGrant, TrustedReferenceAuthority,
    decide_reference_contract,
)
from .identity import digest as session_digest, memberships, sessions, users
from .ingestion import source_grants
from .sa_store import content_items, domain_events, outbox
from .storage import now_utc


class CreativeReferencePermissionDenied(PermissionError):
    """Fixed reason, never echo a grant, source, caption or credential."""


def _deny():
    raise CreativeReferencePermissionDenied("CREATIVE_REFERENCE_RIGHTS_PEP_REQUIRED")


class CreativeReferencePEP:
    """Externally pinned trust; one DB connection and action-specific grants.

    The normal application must use `None` unless an independently managed
    runtime supplies trusted authorities. This object has no grant-issuance API.
    """

    def __init__(self, engine, authorities: Mapping[tuple[str, str], TrustedReferenceAuthority]):
        if not isinstance(authorities, Mapping):
            raise ValueError("CREATIVE_REFERENCE_TRUST_HOST_REQUIRED")
        checked = {}
        for scope, anchor in authorities.items():
            if (not isinstance(scope, tuple) or len(scope) != 2
                    or any(not isinstance(v, str) or not v for v in scope)
                    or not isinstance(anchor, TrustedReferenceAuthority)
                    or scope not in anchor.tenant_platform_scope):
                raise ValueError("CREATIVE_REFERENCE_TRUST_HOST_INVALID")
            checked[scope] = anchor
        self.engine = engine
        self._anchors = MappingProxyType(checked)

    @staticmethod
    def _session_active(db, token, tenant, actor):
        if not isinstance(token, str) or not token or len(token) > 256:
            _deny()
        # Lock the exact revocable session and membership in this transaction.
        row = db.execute(select(
            sessions.c.user_id, sessions.c.tenant_id, sessions.c.expires_at,
            sessions.c.revoked_at, users.c.disabled, memberships.c.role,
        ).select_from(sessions.join(
            users, users.c.user_id == sessions.c.user_id,
        ).join(
            memberships,
            (memberships.c.user_id == sessions.c.user_id)
            & (memberships.c.tenant_id == sessions.c.tenant_id),
        )).where(
            sessions.c.token_hash == session_digest(token),
        ).with_for_update()).one_or_none()
        if (row is None or row.user_id != actor or row.tenant_id != tenant
                or row.role not in {"admin", "editor"}
                or row.revoked_at is not None or row.disabled
                or datetime.fromisoformat(row.expires_at) <= now_utc()):
            _deny()

    def require_for_atomic_draft(self, db, *, token: str, tenant: str,
                                 actor: str, document_id: str,
                                 grant_ids: Mapping[str, str]):
        """Verify and audit ALL external references before the draft is inserted.

        The caller supplies a trusted, active SQL transaction. A failed check
        raises, rolling back the draft and any partial audit/outbox writes.
        Revocation authority, source grant and content rows are locked to
        serialize approval against concurrent changes on PostgreSQL.
        """
        if (db.engine is not self.engine or not isinstance(grant_ids, Mapping)
                or not 1 <= len(grant_ids) <= 10):
            _deny()
        try:
            self._session_active(db, token, tenant, actor)
            for content_id, grant_id in sorted(grant_ids.items()):
                if (not isinstance(content_id, str) or not content_id
                        or not isinstance(grant_id, str) or not grant_id
                        or len(content_id) > 128 or len(grant_id) > 128):
                    _deny()
                # Lock the signed grant row as well as the authority head:
                # concurrent replacement must not race an approved draft.
                rows = db.execute(select(registered_grants).where(
                    registered_grants.c.tenant_id == tenant,
                    registered_grants.c.content_id == content_id,
                    registered_grants.c.grant_id == grant_id,
                ).with_for_update()).mappings().all()
                if len(rows) != 1:
                    _deny()
                row = rows[0]
                platform = row["platform"]
                anchor = self._anchors.get((tenant, platform))
                if anchor is None:
                    _deny()
                key = _key(anchor, tenant, platform)
                db.execute(select(registry_authorities.c.revision).where(
                    registry_authorities.c.tenant_id == tenant,
                    registry_authorities.c.platform == platform,
                    registry_authorities.c.issuer_id == anchor.issuer_id,
                ).with_for_update()).first()
                _, revocations = _load(db, key, anchor)
                grant = SignedReferenceGrant.model_validate_json(row["payload"])
                target = grant.claims.target
                if (grant.claims.grant_id != grant_id
                        or target.tenant_id != tenant
                        or target.platform != platform
                        or target.content_id != content_id
                        or row["issuer_id"] != anchor.issuer_id
                        or row["content_sha256"] != target.content_sha256
                        or row["claims_sha256"] != _digest(grant.claims)):
                    _deny()
                # Locks prevent source revocation and source-content mutation
                # from racing the creative document write within this DB txn.
                db.execute(select(source_grants.c.enabled).where(
                    source_grants.c.tenant_id == tenant,
                    source_grants.c.platform == platform,
                    source_grants.c.source_account_id == target.source_account_id,
                ).with_for_update()).first()
                db.execute(select(content_items.c.id).where(
                    content_items.c.tenant_id == tenant,
                    content_items.c.id == content_id,
                ).with_for_update()).first()
                now = now_utc()
                if not _source_bound(db, target, now):
                    _deny()
                for operation in (
                    ReferenceOperation.CREATIVE_SPEC_REFERENCE,
                    ReferenceOperation.STUDIO_DRAFT_REFERENCE,
                ):
                    decision = decide_reference_contract(
                        authority=anchor, grant=grant, revocations=revocations,
                        target=target, operation=operation, now=now,
                    )
                    if not decision.permitted:
                        _deny()
                # Every successful authorization is an auditable transaction
                # fact, not a grant of editorial or publishing approval.
                event = db.execute(insert(domain_events).values(
                    event_id=str(uuid4()), tenant_id=tenant,
                    aggregate_type="creative_reference_use",
                    aggregate_id=str(uuid4()),
                    aggregate_version=1,
                    event_type="creative_reference.checked_for_draft",
                    occurred_at=now.isoformat(),
                    payload=json.dumps({
                        "document_sha256": sha256(document_id.encode()).hexdigest(),
                        "content_sha256": sha256(content_id.encode()).hexdigest(),
                        "grant_sha256": sha256(signed_bytes(grant.claims)).hexdigest(),
                        "operations": [
                            ReferenceOperation.CREATIVE_SPEC_REFERENCE.value,
                            ReferenceOperation.STUDIO_DRAFT_REFERENCE.value,
                        ],
                    }, sort_keys=True, separators=(",", ":")),
                ))
                db.execute(insert(outbox).values(
                    seq=event.inserted_primary_key[0],
                    attempts=0, dead_letter=0,
                ))
        except CreativeReferencePermissionDenied:
            raise
        except (SQLAlchemyError, ReferenceRegistryDenied, ValidationError,
                ValueError, TypeError, AttributeError, KeyError, IndexError):
            # All untrusted state/corruption failures are a typed denial.
            _deny()
