from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
import pytest
from tapi_gate0.discovery_corpus_readiness import classify_record, counts_for, source_gate, STAGES

NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)
CUT = NOW - timedelta(days=14)


def post(**changes):
    return NS(**dict(dict(is_synthetic=False, origin="instagram", media_type="reels",
        published_at=CUT, caption="Negócios locais"), **changes))


@pytest.mark.parametrize("item,metric,source_ok,trace_ok,expected", [
    (None, None, False, False, STAGES[0]),
    (None, None, True, True, STAGES[1]),
    (post(is_synthetic=True), NS(follower_count=100), True, True, STAGES[1]),
    (post(media_type="imagem"), NS(follower_count=100), True, True, STAGES[2]),
    (post(published_at=CUT+timedelta(seconds=1)), NS(follower_count=100), True, True, STAGES[3]),
    (post(), None, True, True, STAGES[4]),
    (post(), NS(follower_count=0), True, True, STAGES[4]),
    (post(), NS(follower_count=100), True, False, STAGES[5]),
    (post(caption=" \n"), NS(follower_count=100), True, True, STAGES[6]),
    (post(caption=None), NS(follower_count=100), True, True, STAGES[6]),
    (post(), NS(follower_count=100), True, True, STAGES[7]),
])
def test_first_blocking_stage(item, metric, source_ok, trace_ok, expected):
    assert classify_record(item, metric, source_ok=source_ok, trace_ok=trace_ok, cutoff=CUT) == expected


def test_counts_partition_and_unknown():
    assert sum(counts_for([STAGES[0], STAGES[7], STAGES[7]]).values()) == 3
    assert counts_for([])[STAGES[7]] == 0
    with pytest.raises(ValueError):
        counts_for(["unknown"])


def test_source_gate_requires_matching_verified_active_grant():
    source = NS(status="approved", expires_at=NOW+timedelta(days=1), approval_reference="ref")
    grant = dict(enabled=1, expires_at=(NOW+timedelta(days=1)).isoformat(),
                 approval_reference="ref", technical_verified_at=NOW.isoformat())
    assert source_gate(source, grant, NOW) == "TECHNICAL_SCOPE_MATCHED"
    assert source_gate(None, grant, NOW) == "MANIFEST_SOURCE_NOT_APPROVED"
    assert source_gate(source, dict(grant, enabled=0), NOW) == "ACTIVE_GRANT_REQUIRED"
    assert source_gate(source, dict(grant, approval_reference="other"), NOW) == "GRANT_REFERENCE_MISMATCH"
    assert source_gate(source, dict(grant, technical_verified_at=None), NOW) == "TECHNICAL_VERIFICATION_REQUIRED"
    assert source_gate(source, dict(grant, expires_at=NOW.isoformat()), NOW) == "ACTIVE_GRANT_REQUIRED"
