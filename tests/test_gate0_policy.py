import pytest
from tapi_gate0.policy import decide, EXTERNAL_SOURCES, Operation

@pytest.mark.parametrize("source", sorted(EXTERNAL_SOURCES))
@pytest.mark.parametrize("operation", [o.value for o in Operation])
def test_all_external_requests_denied(source, operation):
    result = decide(source, operation)
    assert result.permitted is False
    assert result.code == "EXTERNAL_DENIED_PENDING_VERIFIED_GRANT"

@pytest.mark.parametrize("operation", ["publish", "manage_paid_campaign", "download_or_process_media", "read_crm"])
def test_synthetic_cannot_act_outside_eval(operation):
    assert not decide("synthetic_local", operation).permitted

def test_synthetic_local_fixture_allowed():
    assert decide("synthetic_local", "evaluate_local_fixture").permitted

def test_unknown_source_denied():
    assert not decide("mystery_source", "retrieve_metadata").permitted

def test_untrusted_approval_file_cannot_enable_external_action():
    # A engine jamais converte status/atributo enviado por cliente em permissão.
    assert not decide("instagram_metadata", "retrieve_metadata").permitted
