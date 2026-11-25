from pathlib import Path
import importlib.util
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("documentation_catalog", ROOT / "scripts/documentation_catalog.py")
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)


def test_graph_explicit_ids_and_provenance():
    graph = catalog.graph(ROOT)
    ids = {node["id"] for node in graph["nodes"]}
    assert {"IMP-131", "IMP-062", "DEC-018", "CAP-023", "U01"} <= ids
    assert len(ids) == len(graph["nodes"])
    assert all(edge["source"] in ids and edge["target"] in ids and edge["origin"]
               for edge in graph["edges"])
    assert any(edge["source"] == "IMP-062" and edge["target"] == "DEC-018"
               and edge["relation"] == "governed_by" for edge in graph["edges"])


def test_graph_rejects_missing_target(monkeypatch):
    real = catalog.rows
    def modified(root, filename):
        result = real(root, filename)
        if filename == "DEPENDENCIAS.csv":
            result[0]["successor"] = "IMP-NOT-EXIST"
        return result
    monkeypatch.setattr(catalog, "rows", modified)
    with pytest.raises(ValueError, match="unresolved explicit link"):
        catalog.graph(ROOT)


def test_index_distinguishes_historical_and_mirror():
    result = {entry["path"]: entry for entry in catalog.index(ROOT)["documents"]}
    assert result["docs/governance/STATE_2026-11-24.md"]["class_hint"] == "historical"
    assert result["docs/base_atemporal/00_Indice_e_Protocolo.md"]["class_hint"] == "baseline_mirror_or_adoption"
    assert len(result["docs/README.md"]["git_blob_sha1"]) == 40


def test_check_reports_structure_only():
    result = catalog.check(ROOT)
    assert result["status"] == "PASS_DOCUMENTATION_STRUCTURE"
    assert result["mirror_blobs"] == 32
    assert result["gates"] == "NOT_ASSESSED"
    assert result["semantic_audit"] == "NOT_PERFORMED"


def test_all_matrix_families_and_candidate_gap():
    result = catalog.graph(ROOT)
    kinds = {node["kind"] for node in result["nodes"]}
    assert {"ISO", "CONFLICT", "DOMAIN", "CONTRACT", "SCHEMA"} <= kinds
    assert len([node for node in result["nodes"] if node["kind"] == "ISO"]) == 207
    assert len([node for node in result["nodes"] if node["kind"] == "CONTRACT"]) == 28
    assert any(edge["relation"] == "candidate_schema" for edge in result["edges"])
    assert result["candidate_names_not_in_inventory"]
