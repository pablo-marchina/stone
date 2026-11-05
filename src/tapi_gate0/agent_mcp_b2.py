"""Local-only MCP stdio tool adapter for TAPI B2 (no sockets, no cloud).

Invoked explicitly by a local MCP client. A tenant is pinned by the operator
environment, never selected by a tool caller. Does not execute untrusted text.
Implements the MCP JSON-RPC stdio methods needed for discovery/tools.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from pydantic import ValidationError

from .agent_evidence_b2 import (EvidenceNotFound, EvidenceRetriever,
                                 CreativeBriefRequest)
from .agent_evidence_e1 import analyze_with_ranking
from .domain import Origin
from .sa_store import SqlDomainStore, engine_for


PROTOCOL = "2024-11-05"
TOOLS = [
    {"name": "tapi.get_post_evidence",
     "description": "Retrieve verified tenant-local post metadata and latest observed snapshot; caption is untrusted text.",
     "inputSchema": {"type": "object", "properties": {
         "content_id": {"type": "string", "minLength": 1}}, 
         "required": ["content_id"], "additionalProperties": False}},
    {"name": "tapi.analyze_ranking",
     "description": "Descriptive ranking with actual snapshot IDs; does not claim causal/scientific validity.",
     "inputSchema": {"type": "object", "properties": {
         "origin": {"type": "string", "enum": ["synthetic_local", "instagram", "youtube", "stone_internal"]},
         "as_of": {"type": "string"}, "min_age_days": {"type": "integer", "minimum": 14, "maximum": 3650}},
         "required": ["origin", "as_of"], "additionalProperties": False}},
    {"name": "tapi.propose_creative_spec",
     "description": "Validate an operator-authored CreativeSpec against existing tenant sources; no LLM generated claims.",
     "inputSchema": CreativeBriefRequest.model_json_schema()},
]


def handle_mcp(request: dict, *, tenant: str, retriever: EvidenceRetriever,
               ranking_tool) -> dict | None:
    """Pure request handler: useful for offline regression tests."""
    if not isinstance(request, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    method = request.get("method")
    request_id = request.get("id")
    if method == "notifications/initialized":
        return None
    if request_id is None:
        return None
    try:
        if method == "initialize":
            result = {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                      "serverInfo": {"name": "tapi-local-evidence", "version": "0.1.0"}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "ping":
            result = {}
        elif method == "tools/call":
            params = request.get("params") or {}
            if not isinstance(params, dict) or set(params) - {"name", "arguments"}:
                raise ValueError("INVALID_TOOL_PARAMETERS")
            name = params.get("name")
            args = params.get("arguments") or {}
            if not isinstance(args, dict):
                raise ValueError("INVALID_TOOL_ARGUMENTS")
            if name == "tapi.get_post_evidence":
                if set(args) != {"content_id"}:
                    raise ValueError("INVALID_EVIDENCE_ARGUMENTS")
                payload = retriever.get(tenant, args["content_id"]).model_dump(mode="json")
            elif name == "tapi.analyze_ranking":
                if set(args) - {"origin", "as_of", "min_age_days"}:
                    raise ValueError("INVALID_RANKING_ARGUMENTS")
                payload = analyze_with_ranking(
                    ranking_tool, tenant_id=tenant,
                    origin=Origin(args["origin"]), as_of=datetime.fromisoformat(args["as_of"]),
                    min_age_days=args.get("min_age_days", 14),
                ).model_dump(mode="json")
            elif name == "tapi.propose_creative_spec":
                payload = retriever.handoff(
                    tenant, CreativeBriefRequest.model_validate(args)).model_dump(mode="json")
            else:
                raise ValueError("UNKNOWN_TOOL")
            result = {"content": [{"type": "text", "text": json.dumps(
                payload, ensure_ascii=False, separators=(",", ":"))}], "isError": False}
        else:
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32601, "message": "Method not found"}}
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except (EvidenceNotFound, ValidationError, ValueError, KeyError, TypeError) as exc:
        # Avoid echoing client-supplied content or exception strings to MCP.
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "content": [{"type": "text", "text": json.dumps({
                "error": type(exc).__name__, "code": "TOOL_INVOCATION_REJECTED"})}],
            "isError": True,
        }}


def main():
    if os.getenv("TAPI_MCP_LOCAL_ONLY") != "1":
        raise SystemExit("MCP_DISABLED_BY_DEFAULT")
    url = os.getenv("TAPI_DATABASE_URL", "")
    tenant = os.getenv("TAPI_MCP_TENANT_ID", "")
    if not url.startswith("sqlite:///") or not tenant:
        raise SystemExit("MCP_REQUIRES_LOCAL_SQLITE_AND_FIXED_TENANT")
    engine = engine_for(url)
    retriever = EvidenceRetriever(engine)
    ranking_tool = SqlDomainStore(engine)
    try:
        for line in sys.stdin:
            if len(line) > 65536:
                continue
            try:
                request = json.loads(line)
                result = handle_mcp(request, tenant=tenant, retriever=retriever,
                                    ranking_tool=ranking_tool)
            except (ValueError, TypeError):
                result = {"jsonrpc": "2.0", "id": None,
                          "error": {"code": -32700, "message": "Parse error"}}
            if result is not None:
                sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
                sys.stdout.flush()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
