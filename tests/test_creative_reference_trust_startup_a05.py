"""Startup contract: opt-in trust file is host-only, never request supplied."""
import base64
from hashlib import sha256
import json

import pytest

from tapi_gate0.creative_reference_trust_a05 import (
    ENABLE, TRUST_FILE, TRUST_SHA256, SCHEMA,
)
from tapi_gate0 import secure_api


def _capture_runtime(monkeypatch):
    monkeypatch.setenv("TAPI_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.delenv("TAPI_ALLOW_HTTP_LOOPBACK", raising=False)
    monkeypatch.setattr(secure_api, "config_from_env", lambda _env: None)
    monkeypatch.setattr(secure_api, "replay_config_from_env", lambda _env: None)
    def capture(url, **kwargs):
        return dict(database_url=url, **kwargs)
    monkeypatch.setattr(secure_api, "create_secure_app", capture)


def test_normal_app_startup_does_not_enable_external_creative_references(monkeypatch):
    _capture_runtime(monkeypatch)
    for name in (ENABLE, TRUST_FILE, TRUST_SHA256):
        monkeypatch.delenv(name, raising=False)
    app = secure_api.from_environment()
    assert app["creative_reference_authorities"] is None


def test_explicit_external_trust_config_is_forwarded_without_grants(tmp_path, monkeypatch):
    _capture_runtime(monkeypatch)
    path = tmp_path / "host-trust.json"
    path.write_text(json.dumps({
        "schema_version": SCHEMA,
        "authorities": [{
            "tenant_id": "tenantA", "platform": "instagram",
            "issuer_id": "fixture-issuer",
            "public_key_b64": base64.b64encode(bytes(range(1, 33))).decode(),
            "min_revocation_revision": 2,
            "revocation_claims_sha256": "f" * 64,
        }],
    }))
    path.chmod(0o600)
    monkeypatch.setenv(ENABLE, "1")
    monkeypatch.setenv(TRUST_FILE, str(path))
    monkeypatch.setenv(TRUST_SHA256, sha256(path.read_bytes()).hexdigest())
    app = secure_api.from_environment()
    anchors = app["creative_reference_authorities"]
    assert list(anchors) == [("tenantA", "instagram")]
    assert anchors[("tenantA", "instagram")].min_revocation_revision == 2
    # A pinned public key alone does not create grants or release the PEP.
    assert app["initialize_schema"] is False
