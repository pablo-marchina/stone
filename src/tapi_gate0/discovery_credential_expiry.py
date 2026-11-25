"""Offline monitor for operator-declared Meta credential expiration times.

The timestamps are hints supplied from the provider's own tooling, not proof
of validity or a binding to a particular secret. Never log raw config values.
"""
from datetime import datetime, timedelta, timezone
import os
import re

from .connectors import ConnectorError
from .storage import now_utc

TOKEN_EXPIRY = "TAPI_META_TOKEN_EXPIRES_AT"
DATA_EXPIRY = "TAPI_META_DATA_ACCESS_EXPIRES_AT"
REQUIRE_EXPIRY = "TAPI_META_REQUIRE_TOKEN_EXPIRY"
WARNING_DAYS = 7
ISO = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z")


def _parse(value):
    if value is None or value == "":
        return None
    if not ISO.fullmatch(value):
        raise ValueError("INVALID_META_EXPIRY")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def expiry_status(*, now=None):
    """Read-only; never accesses a provider, a token, or the database."""
    now = now if now is not None else now_utc()
    result = {"status":"UNKNOWN", "blocked":False, "provider_verified":False,
              "external_data_accessed":False, "token_expires_at":None,
              "data_access_expires_at":None, "earliest_expires_at":None,
              "reason_code":None}
    try:
        required = os.getenv(REQUIRE_EXPIRY, "0")
        if required not in {"0", "1"}:
            raise ValueError("INVALID_META_EXPIRY")
        token = _parse(os.getenv(TOKEN_EXPIRY))
        data = _parse(os.getenv(DATA_EXPIRY))
    except (ValueError, OverflowError):
        return {**result,"status":"INVALID_CONFIGURATION","blocked":True,
                "reason_code":"BD_META_EXPIRY_CONFIGURATION_INVALID"}
    result.update(token_expires_at=token.isoformat() if token else None,
                  data_access_expires_at=data.isoformat() if data else None)
    earliest = min((v for v in (token,data) if v is not None), default=None)
    if earliest is not None:
        result["earliest_expires_at"] = earliest.isoformat()
        if earliest <= now:
            return {**result,"status":"EXPIRED","blocked":True,
                    "reason_code":"BD_META_DECLARED_CREDENTIAL_EXPIRED"}
    if required == "1" and token is None:
        return {**result,"status":"EXPIRY_REQUIRED","blocked":True,
                "reason_code":"BD_META_TOKEN_EXPIRY_REQUIRED"}
    if earliest is not None:
        result["status"] = "EXPIRING_SOON" if earliest-now <= timedelta(days=WARNING_DAYS) else "WITHIN_DECLARED_WINDOW"
    return result


def require_expiry_available():
    report = expiry_status()
    if report["blocked"]:
        raise ConnectorError(report["reason_code"], 409)
