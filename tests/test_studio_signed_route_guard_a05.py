"""CAP-023 security-regression check: legacy guard is installed at route build.

FastAPI copies router dependencies when each route is registered; appending a
guard later does NOT secure previously registered routes. This test inspects
the REAL constructed application's route dependency graph, not a proxy.
"""
from tapi_gate0.secure_api import create_secure_app


def test_all_legacy_studio_document_post_routes_have_signed_reference_guard():
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
    assert "/v1/studio/documents/{document_id}/text-patches" in paths
    assert "/v1/studio/documents/{document_id}/geometry" in paths
    assert "/v1/studio/documents/{document_id}/pages/duplicate" in paths
    assert "/v1/studio/documents/{document_id}/versions/restore" in paths
