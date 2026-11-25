from datetime import datetime, timedelta, timezone
import re

import pytest
from tapi_gate0.studio_metadata_scope_e6 import metadata_source_scope_digest

NOW = datetime(2026, 11, 21, 15, tzinfo=timezone.utc)

def sample(**delta):
    row = {
        "source_item_id": "fixture-post", "platform": "instagram",
        "source_account_id": "fixture-account", "metadata_only": 1,
        "denominator_quality": "observed_current_only",
        "processed_at": (NOW-timedelta(minutes=3)).isoformat(),
        "enabled": 1, "approval_reference": "fictional-test-reference",
        "approved_by": "test-fixture", "approved_at": (NOW-timedelta(hours=2)).isoformat(),
        "technical_verified_at": (NOW-timedelta(hours=1)).isoformat(),
        "expires_at": (NOW+timedelta(days=1)).isoformat(),
    }
    row.update(delta)
    return row

def evaluate(row, **kwargs):
    return metadata_source_scope_digest(
        row, platform=kwargs.get("platform", "instagram"),
        source_profile_id=kwargs.get("source_profile_id", "fixture-account"),
        content_created_at=kwargs.get("content_created_at", NOW-timedelta(days=1)),
        now=kwargs.get("now", NOW),
    )

def test_local_metadata_grant_is_only_a_digest_not_a_creative_license():
    digest = evaluate(sample())
    assert re.fullmatch(r"[a-f0-9]{64}", digest or "")
    assert evaluate(sample(approval_reference="changed")) != digest
    assert evaluate(sample(source_item_id="other-post")) != digest

@pytest.mark.parametrize("changes", [
    {"enabled": 0}, {"enabled": True}, {"metadata_only": 0},
    {"metadata_only": True}, {"technical_verified_at": None},
    {"technical_verified_at": "not-a-date"},
    {"technical_verified_at": (NOW-timedelta(hours=3)).isoformat()},
    {"processed_at": (NOW-timedelta(hours=4)).isoformat()},
    {"processed_at": (NOW+timedelta(minutes=1)).isoformat()},
    {"expires_at": (NOW-timedelta(seconds=1)).isoformat()},
    {"approved_at": "2026-11-20T00:00:00"},
    {"approval_reference": ""}, {"source_account_id": "other-account"},
    {"platform": "youtube"}, {"source_item_id": ""},
])
def test_invalid_or_expired_source_grant_denies(changes):
    assert evaluate(sample(**changes)) is None

@pytest.mark.parametrize("kwargs", [
    {"source_profile_id": None}, {"source_profile_id": "other-account"},
    {"platform": "stone_internal"},
    {"now": NOW+timedelta(days=2)},
    {"content_created_at": NOW+timedelta(seconds=1)},
    {"now": NOW.replace(tzinfo=None)},
])
def test_untrusted_subject_or_clock_denies(kwargs):
    assert evaluate(sample(), **kwargs) is None

def test_missing_field_and_string_payload_denies():
    assert evaluate({}) is None
    assert evaluate("not-a-row") is None
