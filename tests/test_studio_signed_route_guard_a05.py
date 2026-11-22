"""CAP-023 security-regression check: legacy guard is installed at route build.

FastAPI copies router dependencies when each route is registered; appending a
guard later does NOT secure previously registered routes. This test inspects
the REAL constructed application's route dependency graph, not a proxy.
"""
from pathlib import Path
from starlette.routing import Match

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
    # Inspect ALL POST routes under this base path, even if a framework
    # spells a dynamic parameter as "{document_id:str}" instead of
    # "{document_id}". A route without a security dependency tree is denied.
    document_posts = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or ()
        if (not isinstance(path, str)
                or not path.startswith("/v1/studio/documents/")
                or "POST" not in methods):
            continue
        document_posts.append(route)
        dependant = getattr(route, "dependant", None)
        assert dependant is not None, path
        names = {getattr(dep.call, "__name__", "")
                 for dep in dependant.dependencies}
        assert "deny_unchecked_signed_document_mutation" in names, path

    required = (
        "/v1/studio/documents/diagnostic/text-patches",
        "/v1/studio/documents/diagnostic/geometry",
        "/v1/studio/documents/diagnostic/pages/duplicate",
        "/v1/studio/documents/diagnostic/versions/restore",
    )
    def serves(concrete):
        scope = {"type": "http", "path": concrete,
                 "method": "POST", "root_path": ""}
        return any(route.matches(scope)[0] == Match.FULL
                   for route in document_posts)

    missing = [target for target in required if not serves(target)]
    assert not missing, (
        "A05_STUDIO_DOCUMENT_POST_ROUTES_MISSING:" + repr(missing)
        + "; observed_studio_posts="
        + repr(sorted(route.path for route in document_posts)[:45])
    )
