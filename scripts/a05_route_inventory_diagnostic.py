"""Offline A05/Studio route inventory for a pinned local Git checkout.

This is diagnostic only, NOT acceptance evidence or a gate release. It creates
one temporary synthetic SQLite schema, never reads operational databases,
starts a server, makes an HTTP request, installs dependencies or contacts
external providers. Emits only module filenames and public route names.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "stone-a05-route-inventory-diagnostic.v1"


def inventory() -> dict:
    import fastapi
    import starlette
    import tapi_gate0
    from tapi_gate0 import secure_api, agent_api_e1, studio_api

    root = (ROOT / "src" / "tapi_gate0").resolve()
    modules = {
        "tapi_gate0": (tapi_gate0, "__init__.py"),
        "secure_api": (secure_api, "secure_api.py"),
        "agent_api_e1": (agent_api_e1, "agent_api_e1.py"),
        "studio_api": (studio_api, "studio_api.py"),
    }
    module_origin = {
        key: Path(module.__file__).resolve() == root / name
        for key, (module, name) in modules.items()
    }
    # Never build app with untrusted imported source. In particular, avoid
    # silently evaluating tests against the parent editable Stone checkout.
    if not all(module_origin.values()):
        return {
            "schema_version": SCHEMA,
            "status": "BLOCKED_WRONG_WORKTREE_IMPORT",
            "module_from_this_checkout": module_origin,
            "production_approved": False,
        }

    with TemporaryDirectory(prefix="stone-a05-route-inventory-") as folder:
        database = Path(folder) / "fixture.sqlite"
        app = secure_api.create_secure_app(
            "sqlite:///" + database.as_posix(),
            initialize_schema=True,
            allow_http_local=True,
        )

        def entries(routes):
            rows = []
            for route in routes:
                path = getattr(route, "path", None)
                methods = getattr(route, "methods", None) or ()
                if not isinstance(path, str):
                    continue
                rows.append({
                    "path": path,
                    "methods": sorted(str(method) for method in methods),
                    "kind": type(route).__name__,
                    "dependency_graph_present": getattr(route, "dependant", None) is not None,
                    "signed_guard_present": any(
                        getattr(getattr(dep, "call", None), "__name__", "")
                        == "deny_unchecked_signed_document_mutation"
                        for dep in getattr(getattr(route, "dependant", None),
                                           "dependencies", ())
                    ),
                })
            return rows

        routes = entries(app.routes)
        agent = [r for r in routes if r["path"].startswith("/v1/agent")]
        studio = [r for r in routes if r["path"].startswith("/v1/studio")]
        # If a different version exposes route paths under a different
        # prefix, this bounded names-only sample helps locate the mismatch.
        sample = routes[:30] if not agent or not studio else []
        return {
            "schema_version": SCHEMA,
            "status": "DIAGNOSTIC_ONLY",
            "fastapi_version": fastapi.__version__,
            "starlette_version": starlette.__version__,
            "module_from_this_checkout": module_origin,
            "app_type": type(app).__name__,
            "app_routes_count": len(routes),
            "app_router_routes_count": len(app.router.routes),
            "agent_routes": agent,
            "studio_routes": studio,
            "other_route_sample": sample,
            "production_approved": False,
        }


def main() -> int:
    try:
        result = inventory()
    except Exception as exc:
        # Exception types are safe metadata; exception messages might include
        # SQL paths or arbitrary private payloads and must not be printed.
        result = {
            "schema_version": SCHEMA,
            "status": "BLOCKED_DIAGNOSTIC_EXCEPTION",
            "exception_type": type(exc).__name__,
            "production_approved": False,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "DIAGNOSTIC_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
