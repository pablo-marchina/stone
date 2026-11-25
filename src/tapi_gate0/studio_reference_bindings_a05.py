"""A05→CAP-023 durable reference-grant bindings for each editable draft.

Only the trusted agent handoff may write bindings, in the SAME transaction
as signed rights verification and initial Studio document insertion. These
bindings are audit pointers, never licenses, publisher permits or credentials.
"""
from __future__ import annotations

from hashlib import sha256
import json
from datetime import datetime, timezone
from typing import Mapping, Sequence

from sqlalchemy import Table, Column, String, ForeignKeyConstraint, select, insert

from .sa_store import metadata, content_items
from .studio_e1 import studio_documents

studio_reference_bindings = Table(
    "studio_reference_bindings", metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("document_id", String(128), primary_key=True),
    Column("content_id", String(128), primary_key=True),
    Column("grant_id", String(128), nullable=False),
    Column("reference_set_sha256", String(64), nullable=False),
    Column("recorded_at", String(48), nullable=False),
    ForeignKeyConstraint(
        ["tenant_id", "document_id"],
        ["studio_documents.tenant_id", "studio_documents.document_id"],
        ondelete="RESTRICT",
    ),
    ForeignKeyConstraint(
        ["tenant_id", "content_id"],
        ["content_items.tenant_id", "content_items.id"],
        ondelete="RESTRICT",
    ),
)


class ReferenceBindingDenied(PermissionError):
    def __init__(self):
        super().__init__("STUDIO_REFERENCE_BINDING_INVALID")


def _digest(reference_content_ids: Sequence[str]) -> str:
    if (not isinstance(reference_content_ids, (list, tuple))
            or len(set(reference_content_ids)) != len(reference_content_ids)
            or any(not isinstance(value, str) or not value
                   for value in reference_content_ids)):
        raise ReferenceBindingDenied()
    return sha256(json.dumps(
        list(reference_content_ids), ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def persist_reference_bindings(
    db, *, tenant: str, document_id: str,
    reference_content_ids: Sequence[str], external_grant_ids: Mapping[str, str],
) -> None:
    """Insert immutable, exact external grant IDs after PEP approval.

    Transaction ownership is caller's; no independent commit or side channel.
    """
    digest = _digest(reference_content_ids)
    if (not tenant or not document_id or not isinstance(external_grant_ids, Mapping)
            or any(not isinstance(k, str) or not isinstance(v, str) or not k or not v
                   for k, v in external_grant_ids.items())
            or not set(external_grant_ids).issubset(set(reference_content_ids))):
        raise ReferenceBindingDenied()
    created = datetime.now(timezone.utc).isoformat()
    for content_id, grant_id in sorted(external_grant_ids.items()):
        db.execute(insert(studio_reference_bindings).values(
            tenant_id=tenant, document_id=document_id, content_id=content_id,
            grant_id=grant_id, reference_set_sha256=digest,
            recorded_at=created,
        ))


def load_reference_bindings(
    db, *, tenant: str, document_id: str,
    reference_content_ids: Sequence[str],
) -> dict[str, str]:
    """Return exact committed grants or deny if bindings drift from document.

    This does NOT decide whether a stored grant is still valid. A runtime PEP
    must revalidate current revocations and source rights before any reuse.
    """
    digest = _digest(reference_content_ids)
    rows = db.execute(select(
        studio_reference_bindings.c.content_id,
        studio_reference_bindings.c.grant_id,
        studio_reference_bindings.c.reference_set_sha256,
    ).where(
        studio_reference_bindings.c.tenant_id == tenant,
        studio_reference_bindings.c.document_id == document_id,
    )).all()
    if (any(row.reference_set_sha256 != digest
            or row.content_id not in reference_content_ids
            or not row.grant_id for row in rows)
            or len({row.content_id for row in rows}) != len(rows)):
        raise ReferenceBindingDenied()
    return {row.content_id: row.grant_id for row in rows}
