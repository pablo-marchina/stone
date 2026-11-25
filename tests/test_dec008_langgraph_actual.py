"""IMP-027 conditional REAL LangGraph parity; never substitute a test double.

This file is intentionally outside the focal A11 required set while optional
LangGraph is unavailable. When installed, it runs actual StateGraph adapters
against separate equal SQL fixture databases; no fake measurements.
"""
from __future__ import annotations

import pytest

from scripts import dec008_orchestrator_benchmark as bench
from tapi_gate0.agent_graph_orchestrator_dec008 import available_backends


@pytest.mark.parametrize("mode", ["analisar", "recomendar", "gerar_criativo"])
def test_genuine_langgraph_and_direct_ledger_parity_on_synthetic_sql(tmp_path, mode):
    if available_backends()["langgraph"] is None:
        pytest.skip("DEC008_REAL_LANGGRAPH_DEPENDENCY_NOT_INSTALLED")
    direct, _, _ = bench._run_case(tmp_path, mode=mode, backend="direct", number=0)
    actual_graph, _, _ = bench._run_case(tmp_path, mode=mode, backend="langgraph", number=0)
    assert actual_graph["status"] == direct["status"]
    assert actual_graph["revision"] == direct["revision"]
    assert actual_graph["chain_sha256"] == direct["chain_sha256"]
    assert actual_graph["production_approved"] is False
