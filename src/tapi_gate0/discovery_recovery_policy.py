"""Fail-closed classification of technical acquisition recovery; no network."""
from .connectors import ConnectorError

RETRYABLE = frozenset({"PROVIDER_RATE_LIMITED", "PROVIDER_UNAVAILABLE", "BD_ORPHANED_RUN_OPERATOR_RECOVERY"})
RESTARTABLE = frozenset({"BD_PAGINATION_STALLED", "BD_HISTORY_CURSOR_CYCLE"})


def recovery_action(reason, observations):
    """Only known safe, observation-free failures can enter the retry queue."""
    if type(observations) is not int or observations != 0:
        return "blocked_partial_or_invalid_observations"
    if reason in RETRYABLE:
        return "retry"
    if reason in RESTARTABLE:
        return "restart_history"
    return "blocked_unclassified_or_integrity"


def require_recoverable(reason, observations, restart_history):
    action = recovery_action(reason, observations)
    if action != ("restart_history" if restart_history else "retry"):
        raise ConnectorError("BD_RECOVERY_FAILURE_NOT_ELIGIBLE", 409)
    return action
