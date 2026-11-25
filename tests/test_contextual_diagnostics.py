import json
import pytest
from tapi_gate0.contextual_diagnostics import safe_failure


@pytest.mark.parametrize("error,kind,reason", [
    (ValueError("CHECKPOINT_REQUIRED_FILE_MISSING: private/path"), "ValueError", "CHECKPOINT_REQUIRED_FILE_MISSING"),
    (RuntimeError("INSTALL_OPTIONAL_GLINER2_LOCAL_EXTRA"), "RuntimeError", "INSTALL_OPTIONAL_GLINER2_LOCAL_EXTRA"),
    (ValueError("private caption or token"), "ValueError", None),
    (OSError("private/path"), "OSError", None),
    (KeyError("private_key"), "KeyError", None),
    (Exception("private data"), "OtherError", None),
])
def test_safe_failure(error, kind, reason):
    report = safe_failure(error, "checkpoint_validation")
    assert report["failure_stage"] == "checkpoint_validation"
    assert report["error_type"] == kind
    assert report.get("reason_code") == reason
    assert "private" not in json.dumps(report)


def test_import_module_is_bounded():
    assert safe_failure(ModuleNotFoundError("secret", name="gliner2.foo"), "runtime_import")["missing_module"] == "gliner2"
    assert "missing_module" not in safe_failure(ModuleNotFoundError("secret", name="private.module"), "runtime_import")
