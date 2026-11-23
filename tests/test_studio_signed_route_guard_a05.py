"""CAP-023 regression: signed reference guard on real nested FastAPI routes.

FastAPI >=0.137 keeps included routers nested. Top-level app.routes only
contains router wrappers; direct app.routes inspection gives false negatives.
We verify effective OpenAPI, the exact included router, and authenticated ASGI
requests with a synthetic signed-reference binding. No provider is contacted.
"""
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import insert

from tapi_gate0 import secure_api, studio_api
from tapi_gate0.sa_store import creators, content_items
from tapi_gate0.studio_e1 import studio_documents
from tapi_gate0.studio_reference_bindings_a05 import studio_reference_bindings
from tapi_gate0.secure_api import create_secure_app


def test_all_legacy_studio_document_post_routes_have_signed_reference_guard(
        monkeypatch):
    checkout_src = Path(__file__).resolve().parents[1] / "src" / "tapi_gate0"
    for module, filename in (
        (secure_api, "secure_api.py"), (studio_api, "studio_api.py"),
    ):
        assert Path(module.__file__).resolve() == (checkout_src / filename).resolve(), (
            "A05_WRONG_WORKTREE_IMPORT:" + filename
        )

    # Capture the EXACT APIRouter instance included in the secure app.
    # Factory-local routes remain inspectable on both old and modern FastAPI,
    # while app.routes is no longer a flat inventory on >=0.137.
    built = []
    original = secure_api.router_for_studio

    def capture_router(*args, **kwargs):
        router = original(*args, **kwargs)
        built.append(router)
        return router

    monkeypatch.setattr(secure_api, "router_for_studio", capture_router)
    app = create_secure_app(
        "sqlite:///:memory:", initialize_schema=True,
        allow_http_local=True,
    )
    try:
        assert len(built) == 1, "A05_STUDIO_ROUTER_NOT_INCLUDED"
        studio_router = built[0]
        document_posts = []
        for route in studio_router.routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None) or ()
            if (not isinstance(path, str)
                    or not path.startswith("/v1/studio/documents/")
                    or "POST" not in methods):
                continue
            document_posts.append(route)
            dependant = getattr(route, "dependant", None)
            assert dependant is not None, path
            # Router-level dependencies can be kept as an effective outer
            # context on newer FastAPI; check the exact included router too.
            local_names = {
                getattr(getattr(dep, "call", None), "__name__", "")
                for dep in dependant.dependencies
            }
            router_names = {
                getattr(getattr(dep, "dependency", None), "__name__", "")
                for dep in studio_router.dependencies
            }
            assert "deny_unchecked_signed_document_mutation" in (
                local_names | router_names
            ), "A05_SIGNED_GUARD_ABSENT:" + path

        assert len(document_posts) >= 8, "A05_STUDIO_POST_DISCOVERY_INCOMPLETE"
        required = {
            "/v1/studio/documents/diagnostic/text-patches":
                "/v1/studio/documents/{document_id}/text-patches",
            "/v1/studio/documents/diagnostic/geometry":
                "/v1/studio/documents/{document_id}/geometry",
            "/v1/studio/documents/diagnostic/pages/duplicate":
                "/v1/studio/documents/{document_id}/pages/duplicate",
            "/v1/studio/documents/diagnostic/versions/restore":
                "/v1/studio/documents/{document_id}/versions/restore",
        }
        effective = app.openapi()["paths"]
        assert not [
            actual for actual, route_path in required.items()
            if "post" not in effective.get(route_path, {})
        ], "A05_STUDIO_ROUTES_MISSING_FROM_EFFECTIVE_OPENAPI"

        # An actual signed binding must deny legacy POST methods, not just
        # appear in a dependency list. Fixture supplies only a SQL pointer,
        # NOT external rights or credentials.
        store = app.state.identity_store
        store.bootstrap("tenantA", "Synthetic Tenant",
                        "founder", "synthetic-test-password-123456")
        engine = store.engine
        with engine.begin() as db:
            db.execute(insert(creators).values(
                tenant_id="tenantA", id="creator",
                origin="instagram", payload="{}",
            ))
            db.execute(insert(content_items).values(
                tenant_id="tenantA", id="post",
                creator_id="creator", origin="instagram",
                published_at="2026-11-01T00:00:00+00:00",
                payload="{}",
            ))
            db.execute(insert(studio_documents).values(
                tenant_id="tenantA", document_id="signed.synthetic",
                spec_id="spec", current_version=1,
            ))
            db.execute(insert(studio_reference_bindings).values(
                tenant_id="tenantA", document_id="signed.synthetic",
                content_id="post", grant_id="fixture-pointer",
                reference_set_sha256="a" * 64,
                recorded_at="2026-11-21T00:00:00+00:00",
            ))

        with TestClient(app) as client:
            login = client.post("/v1/auth/sessions", json={
                "username": "founder", "tenant_id": "tenantA",
                "password": "synthetic-test-password-123456",
            })
            assert login.status_code == 200, "A05_TEST_LOGIN_FAILED"
            headers = {
                "Authorization": "Bearer " + login.json()["access_token"]
            }
            for template in required.values():
                target = template.replace("{document_id}", "signed.synthetic")
                response = client.post(target, headers=headers, json={})
                assert response.status_code == 403, (
                    "A05_STUDIO_SIGNED_GUARD_DISPATCH_FAILURE:"
                    + target + ":" + str(response.status_code)
                )
                assert response.json()["detail"] == (
                    "STUDIO_SIGNED_REFERENCE_ACTION_RECHECK_REQUIRED"
                )
    finally:
        app.state.identity_store.engine.dispose()
