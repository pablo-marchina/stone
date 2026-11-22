"""Offline route-inventory regression: no Windows SQLite file-lock cleanup."""
from __future__ import annotations

import json
from types import SimpleNamespace

from scripts import a05_route_inventory_diagnostic as diagnostic
from tapi_gate0 import secure_api


def test_route_inventory_uses_memory_and_disposes_engine(monkeypatch):
    seen = {"calls": 0, "disposed": 0}

    class Engine:
        def dispose(self):
            seen["disposed"] += 1

    def deny_unchecked_signed_document_mutation():
        pass

    def route(path):
        return SimpleNamespace(
            path=path, methods={"POST"},
            dependant=SimpleNamespace(
                dependencies=[SimpleNamespace(
                    call=deny_unchecked_signed_document_mutation)]
            ),
        )

    paths = [
        route("/v1/agent/creative-drafts"),
        route("/v1/studio/documents/{document_id}/text-patches"),
    ]

    def create_app(database_url, *, initialize_schema, allow_http_local):
        seen["calls"] += 1
        assert database_url == "sqlite:///:memory:"
        assert initialize_schema is True
        assert allow_http_local is True
        return SimpleNamespace(
            routes=paths,
            router=SimpleNamespace(routes=paths),
            state=SimpleNamespace(
                identity_store=SimpleNamespace(engine=Engine())
            ),
        )

    monkeypatch.setattr(secure_api, "create_secure_app", create_app)
    result = diagnostic.inventory()

    assert result["status"] == "DIAGNOSTIC_ONLY"
    assert result["production_approved"] is False
    assert all(result["module_from_this_checkout"].values())
    assert seen == {"calls": 1, "disposed": 1}
    assert result["app_routes_count"] == 2
    assert result["app_router_routes_count"] == 2
    assert result["agent_routes"][0]["path"] == "/v1/agent/creative-drafts"
    assert result["studio_routes"][0]["signed_guard_present"] is True


def test_route_inventory_redacts_app_construction_exception(monkeypatch, capsys):
    def reject(*_args, **_kwargs):
        raise PermissionError("sensitive example message must not leak")

    monkeypatch.setattr(secure_api, "create_secure_app", reject)
    assert diagnostic.main() == 2
    output = capsys.readouterr().out
    assert "sensitive example message must not leak" not in output
    result = json.loads(output)
    assert result["status"] == "BLOCKED_DIAGNOSTIC_EXCEPTION"
    assert result["exception_type"] == "PermissionError"
    assert result["production_approved"] is False
