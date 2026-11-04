"""Gate 0B: observable, zero-network readiness for an individual official read.

The result is a preflight *diagnostic*, not a grant, OAuth verification, or
permission to operate. Its caller must obtain the grant from the authenticated
tenant's database rather than accept caller-supplied grant assertions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

State = Literal["BLOCKED", "READY_FOR_BOUNDED_PREFLIGHT", "PREVIOUSLY_VERIFIED_RECHECK_REQUIRED"]


class TechnicalReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["tapi-gate0b-technical.v1"] = "tapi-gate0b-technical.v1"
    status: State
    grant_recorded: bool
    grant_active: bool
    credential_present: bool
    read_switch_enabled: bool
    zero_billing_operator_confirmed: bool
    technical_verified_previously: bool
    can_attempt_validation: bool
    blockers: list[str]
    policy_scope: Literal["single-account-official-metadata-read"] = "single-account-official-metadata-read"
    production_approved: Literal[False] = False
    institutional_rights_audited_by_software: Literal[False] = False


def assess_metadata_readiness(
    grant: dict | None,
    *,
    credential_present: bool,
    read_switch_enabled: bool,
    zero_billing_operator_confirmed: bool,
    now: datetime | None = None,
) -> TechnicalReadiness:
    """Never read secrets, call APIs or enable a capability based on this result.

    Grant data must be loaded using the authenticated tenant/account key.
    A stale or expired grant blocks the *attempt* even if its token is present.
    Previous technical verification never implies present OAuth validity.
    """
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("GATE0B_TIMEZONE_REQUIRED")
    active = False
    previous = False
    blockers: list[str] = []
    if grant is None:
        blockers.append("SOURCE_GRANT_REQUIRED")
    else:
        try:
            expires = datetime.fromisoformat(str(grant["expires_at"]))
            active = bool(grant["enabled"]) and expires.utcoffset() is not None and expires > now
            previous = bool(grant.get("technical_verified_at"))
        except (KeyError, ValueError, TypeError):
            active = False
        if not active:
            blockers.append("SOURCE_GRANT_EXPIRED_OR_DISABLED")
        if not str(grant.get("approval_reference", "")).strip():
            blockers.append("SOURCE_GRANT_REFERENCE_REQUIRED")
            active = False
    if not credential_present:
        blockers.append("LOCAL_CREDENTIAL_MISSING")
    if not read_switch_enabled:
        blockers.append("OFFICIAL_READ_SWITCH_DISABLED")
    if not zero_billing_operator_confirmed:
        blockers.append("ZERO_BILLING_NOT_CONFIRMED")
    ready = not blockers
    return TechnicalReadiness(
        status=("PREVIOUSLY_VERIFIED_RECHECK_REQUIRED" if previous else "READY_FOR_BOUNDED_PREFLIGHT")
        if ready else "BLOCKED",
        grant_recorded=grant is not None,
        grant_active=active,
        credential_present=credential_present,
        read_switch_enabled=read_switch_enabled,
        zero_billing_operator_confirmed=zero_billing_operator_confirmed,
        technical_verified_previously=previous,
        can_attempt_validation=ready,
        blockers=blockers,
    )
