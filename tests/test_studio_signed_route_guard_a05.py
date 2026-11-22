"""CAP-023 security-regression check: legacy guard is installed at route build.

FastAPI copies router dependencies when each route is registered; appending a
guard later does NOT secure previously registered routes. This test inspects
the REAL constructed application's route dependency graph, not a proxy.
"""
from pathlib import Path

from tapi_gate0 import secure_api, studio_api
from tapi_gate0.secure_api import create_secure_app


def test_all_legacy_studio_document_post_routes_have_signed_reference_guard():
    checkout_src = Path(__file__).resolve().parents[1] / "src" / "tapi_gate0"
    for module, filename in (
        (secure_api, "secure_api.py"), (studio_api, "studio_api.py"),
    ):
        assert Path(module.__file__).resolve() == (checkout_src / filename).resolve(), (
            "A05_WRONG_WORKTREE_IMPORT:" + filename
        )
    app = create_secure_app(
        "sqlite:///:memory:", initialize_schema=True,
        allow_http_local=True,
    )
    paths = []
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if (not isinstance(path, str)
                or not path.startswith("/v1/studio/documents/{document_id}")
                or "POST" not in methods):
            continue
        paths.append(path)
        # A POST route without a FastAPI dependency graph cannot silently
        # escape the reference guard: fail closed instead of filtering it out.
        dependant = getattr(route, "dependant", None)
        assert dependant is not None, path
        names = {getattr(dep.call, "__name__", "")
                 for dep in dependant.dependencies}
        assert "deny_unchecked_signed_document_mutation" in names, path
    observed = sorted(
        (route.path, sorted(getattr(route, "methods", None) or ()))
        for route in app.routes
        if isinstance(getattr(route, "path", None), str)
        and route.path.startswith("/v1/studio/")
    )
    assert paths, ("A05_STUDIO_DOCUMENT_POST_ROUTES_MISSING:"
                   + repr(observed[:45]))
    assert "/v1/studio/documents/{document_id}/text-patches" in paths
    assert "/v1/studio/documents/{document_id}/geometry" in paths
    assert "/v1/studio/documents/{document_id}/pages/duplicate" in paths
    assert "/v1/studio/documents/{document_id}/versions/restore" in paths
