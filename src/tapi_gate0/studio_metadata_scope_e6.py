"""Pure authorization preflight for a source's already-acquired *metadata*.

A matching technical ingestion grant permits checking descriptive metadata only.
It does NOT permit using external media as CreativeSpec/Studio source material,
publishing, operating on a third-party account, or any API access.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Mapping

SOURCE_FIELDS = (
    "source_item_id", "platform", "source_account_id", "metadata_only",
    "denominator_quality", "processed_at", "enabled", "approval_reference",
    "approved_by", "approved_at", "technical_verified_at", "expires_at",
)


def metadata_source_scope_digest(
    row: Mapping[str, object], *, platform: str, source_profile_id: str | None,
    content_created_at: datetime, now: datetime,
) -> str | None:
    """Return a bound digest only for one current, exact metadata grant.

    An independently verified single joined row must be selected by the caller.
    This function has no authority over the source, its media, or creative reuse.
    Fail closed on missing, malformed, stale, or contradictory metadata.
    """
    if (not isinstance(row, Mapping)
            or not isinstance(platform, str) or platform not in ("instagram", "youtube")
            or not isinstance(source_profile_id, str) or not source_profile_id
            or not isinstance(content_created_at, datetime)
            or not isinstance(now, datetime)
            or any(t.tzinfo is None or t.utcoffset() is None
                   for t in (content_created_at, now))
            or content_created_at > now):
        return None
    try:
        pin = {name: row[name] for name in SOURCE_FIELDS}
        if (type(pin["enabled"]) is not int or pin["enabled"] != 1
                or type(pin["metadata_only"]) is not int
                or pin["metadata_only"] != 1
                or pin["platform"] != platform
                or pin["source_account_id"] != source_profile_id
                or any(not isinstance(pin[name], str) or not pin[name].strip()
                       for name in ("source_item_id", "denominator_quality",
                                    "approval_reference", "approved_by"))):
            return None
        approved, verified, processed, expires = (
            datetime.fromisoformat(pin[name]) for name in
            ("approved_at", "technical_verified_at", "processed_at", "expires_at")
        )
        if (any(t.tzinfo is None or t.utcoffset() is None
                for t in (approved, verified, processed, expires))
                or not approved <= verified <= processed <= now < expires):
            return None
        return sha256(json.dumps(pin, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False).encode("utf-8")).hexdigest()
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
