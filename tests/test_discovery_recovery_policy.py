import pytest
from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_recovery_policy import recovery_action, require_recoverable


@pytest.mark.parametrize("reason", ["PROVIDER_RATE_LIMITED", "PROVIDER_UNAVAILABLE", "BD_ORPHANED_RUN_OPERATOR_RECOVERY"])
def test_retryable(reason):
    assert require_recoverable(reason, 0, False) == "retry"
    with pytest.raises(ConnectorError, match="BD_RECOVERY_FAILURE_NOT_ELIGIBLE"):
        require_recoverable(reason, 0, True)


@pytest.mark.parametrize("reason", ["BD_PAGINATION_STALLED", "BD_HISTORY_CURSOR_CYCLE"])
def test_explicit_history_restart_only(reason):
    assert require_recoverable(reason, 0, True) == "restart_history"
    with pytest.raises(ConnectorError, match="BD_RECOVERY_FAILURE_NOT_ELIGIBLE"):
        require_recoverable(reason, 0, False)


@pytest.mark.parametrize("reason", [None, "BD_TECHNICAL_INGEST_FAILED", "PROVIDER_PERMISSION_DENIED", "BD_HISTORY_AUDIT_FAILED", "BD_TARGET_ACCOUNT_MISMATCH", "BD_CROSS_SOURCE_MEDIA_ID_CONFLICT", "PROVIDER_REQUEST_FAILED"])
def test_unknown_or_security_failure_is_blocked(reason):
    assert recovery_action(reason, 0) == "blocked_unclassified_or_integrity"
    for restart in (False, True):
        with pytest.raises(ConnectorError, match="BD_RECOVERY_FAILURE_NOT_ELIGIBLE"):
            require_recoverable(reason, 0, restart)


@pytest.mark.parametrize("observations", [1, -1, True, None])
def test_partial_or_invalid_observations_block_recovery(observations):
    assert recovery_action("PROVIDER_RATE_LIMITED", observations) == "blocked_partial_or_invalid_observations"
    with pytest.raises(ConnectorError, match="BD_RECOVERY_FAILURE_NOT_ELIGIBLE"):
        require_recoverable("PROVIDER_RATE_LIMITED", observations, False)
