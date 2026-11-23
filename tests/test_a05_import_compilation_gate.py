"""Fast local gate: detect syntax breaks before A05/Studio integration runs.

Compilation is entirely offline: it never imports source modules or executes
application code, initializes a database, provisions authority, spends money,
or touches outside providers. Avoid repeating a broken signed-rights module
in the long draft PR stack.
"""
from __future__ import annotations

import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_python_sources_compile_without_import_side_effects():
    sources = sorted((ROOT / "src" / "tapi_gate0").glob("*.py"))
    assert len(sources) >= 100, "RUNTIME_SOURCE_DISCOVERY_INCOMPLETE"
    for source in sources:
        compile(source.read_bytes(), str(source), "exec")


def test_pinned_a05_migrations_compile_without_running_ddl():
    for name in (
        "0017_creative_reference_pep.py",
        "0018_studio_reference_bindings.py",
    ):
        source = ROOT / "migrations" / "versions" / name
        assert source.is_file()
        compile(source.read_bytes(), str(source), "exec")


def test_signed_pep_import_and_public_action_contract():
    # This regression exposed a second '*' in the keyword-only signature.
    # Import after syntax checks so a failure reports the actual module.
    from tapi_gate0.creative_reference_pep_a05 import CreativeReferencePEP

    fn = CreativeReferencePEP.require_for_atomic_draft
    params = inspect.signature(fn).parameters
    assert list(params) == [
        "self", "db", "token", "tenant", "actor", "document_id",
        "grant_ids", "audit_event_type",
    ]
    for name in (
        "token", "tenant", "actor", "document_id", "grant_ids",
        "audit_event_type",
    ):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["audit_event_type"].default == (
        "creative_reference.checked_for_draft"
    )


def test_secure_api_imports_and_mounts_creative_routes(tmp_path):
    import tapi_gate0
    from tapi_gate0 import secure_api, agent_api_e1, studio_api
    from tapi_gate0.secure_api import create_secure_app
    from fastapi.testclient import TestClient

    # Never silently test the editable parent checkout.
    source = (ROOT / "src" / "tapi_gate0").resolve()
    for module, filename in (
        (tapi_gate0, "__init__.py"),
        (secure_api, "secure_api.py"),
        (agent_api_e1, "agent_api_e1.py"),
        (studio_api, "studio_api.py"),
    ):
        assert Path(module.__file__).resolve() == source / filename, (
            "A05_WRONG_WORKTREE_IMPORT:" + filename
        )

    app = create_secure_app(
        "sqlite:///:memory:",
        initialize_schema=True, allow_http_local=True,
    )
    try:
        # FastAPI >=0.137 preserves included routers as nested candidates;
        # app.routes and app.router.routes are NOT flat APIRoute inventories.
        # The framework's own OpenAPI traversal resolves the effective paths.
        paths = app.openapi()["paths"]
        required = {
            "/v1/agent/creative-drafts":
                "/v1/agent/creative-drafts",
            "/v1/agent/creative-drafts/diagnostic/text-patches":
                "/v1/agent/creative-drafts/{document_id}/text-patches",
            "/v1/agent/creative-drafts/diagnostic/geometry":
                "/v1/agent/creative-drafts/{document_id}/geometry",
            "/v1/agent/creative-drafts/diagnostic/reference-recheck":
                "/v1/agent/creative-drafts/{document_id}/reference-recheck",
        }
        missing = [
            sample for sample, template in required.items()
            if "post" not in paths.get(template, {})
        ]
        assert not missing, (
            "A05_CREATIVE_ROUTES_MISSING:" + repr(missing)
            + "; openapi_agent_posts="
            + repr(sorted(path for path, ops in paths.items()
                          if path.startswith("/v1/agent/creative-drafts")
                          and "post" in ops))
        )

        # OpenAPI metadata alone cannot establish that routes actually
        # dispatch. Exercise each POST without credentials: every mounted
        # route must deny authentication (401), not fall through to 404.
        with TestClient(app) as client:
            for sample in required:
                response = client.post(sample, json={})
                assert response.status_code == 401, (
                    "A05_CREATIVE_ROUTE_NOT_AUTHENTICATED:"
                    + sample + ":" + str(response.status_code)
                )
    finally:
        app.state.identity_store.engine.dispose()
