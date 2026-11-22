"""CAP-023 security-regression check: legacy guard is installed at route build.

FastAPI copies router dependencies when each route is registered; appending a
guard later does NOT secure previously registered routes. This test inspects
the REAL constructed application's route dependency graph, not a proxy.
"""
from fastapi.routing import APIRoute

from tapi_gate0.secure_api import create_secure_app


def test_all_legacy_studio_document_post_routes_have_signed_reference_guard():
    app = create_secure_app(
        "sqlite:///:memory:", initialize_schema=True,
        allow_http_local=True,
    )
    paths = []
    for route in app.routes:
        if (not isinstance(route, APIRoute)
                or not route.path.startswith("/v1/studio/documents/{document_id}")
                or "POST" not in (route.methods or set())):
            continue
        paths.append(route.path)
        names = {getattr(dep.call, "__name__", "") for dep in route.dependant.dependencies}
        assert "deny_unchecked_signed_document_mutation" in names, route.path
    assert "/v1/studio/documents/{document_id}/text-patches" in paths
    assert "/v1/studio/documents/{document_id}/geometry" in paths
    assert "/v1/studio/documents/{document_id}/pages/duplicate" in paths
    assert "/v1/studio/documents/{document_id}/versions/restore" in paths
