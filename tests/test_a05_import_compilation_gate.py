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

    # A global editable install of the parent Stone checkout can be cached
    # before pytest applies its pythonpath config. Reject mixed-source
    # validation rather than silently checking a different revision.
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
        "sqlite:///" + str(tmp_path / "import-smoke.sqlite"),
        initialize_schema=True, allow_http_local=True,
    )
    # Check the mounted ASGI routes, not the identity of one FastAPI
    # APIRoute class. Reloads/compatible wrappers may provide different
    # route subclasses while the application still exposes the endpoints.
    # The exact required method/path pairs must remain present.
    paths = {
        (method, route.path)
        for route in app.routes
        if isinstance(getattr(route, "path", None), str)
        for method in (getattr(route, "methods", None) or ())
    }
    required = {
        ("POST", "/v1/agent/creative-drafts"),
        ("POST", "/v1/agent/creative-drafts/{document_id}/text-patches"),
        ("POST", "/v1/agent/creative-drafts/{document_id}/geometry"),
        ("POST", "/v1/agent/creative-drafts/{document_id}/reference-recheck"),
    }
    missing = sorted(required - paths)
    assert not missing, (
        "A05_CREATIVE_ROUTES_MISSING:"
        + repr(missing)
        + "; observed_agent_posts="
        + repr(sorted(path for method, path in paths
                      if method == "POST" and path.startswith("/v1/agent/")))
    )
