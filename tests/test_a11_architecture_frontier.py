"""Offline DAG analysis must never be mistaken for task or gate acceptance."""
import csv

import pytest

from scripts.a11_architecture_frontier import FrontierInvalid, analyze, main


def _write(path, name, columns, rows):
    with (path / name).open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def plan(tmp_path):
    _write(tmp_path, "BACKLOG_UNICO_IMPORTAVEL.csv",
           ("id", "dependencies", "hours_estimate", "workstream", "capability_ids"), [
               {"id": "IMP-001", "dependencies": "", "hours_estimate": "2", "workstream": "source", "capability_ids": "CAP-001"},
               {"id": "IMP-002", "dependencies": "IMP-001", "hours_estimate": "5", "workstream": "agent", "capability_ids": "CAP-001"},
               {"id": "IMP-003", "dependencies": "IMP-001", "hours_estimate": "3", "workstream": "studio", "capability_ids": "CAP-001"},
               {"id": "IMP-131", "dependencies": "IMP-002;IMP-003", "hours_estimate": "1", "workstream": "release", "capability_ids": "CAP-001"},
           ])
    _write(tmp_path, "DEPENDENCIAS.csv", ("predecessor", "successor", "type"), [
        {"predecessor": "IMP-001", "successor": "IMP-002", "type": "bloqueante"},
        {"predecessor": "IMP-001", "successor": "IMP-003", "type": "bloqueante"},
        {"predecessor": "IMP-002", "successor": "IMP-131", "type": "bloqueante"},
        {"predecessor": "IMP-003", "successor": "IMP-131", "type": "bloqueante"},
    ])
    _write(tmp_path, "MATRIZ_CAPACIDADES.csv", ("feature_id",), [{"feature_id": "CAP-001"}])
    return tmp_path


def test_longest_dependency_chain_and_parallel_lanes(plan):
    result = analyze(plan)
    assert result["status"] == "PLANNING_FRONTIER_ONLY"
    assert result["task_count"] == 4
    assert result["dependency_count"] == 4
    assert result["longest_dependency_chain"] == ["IMP-001", "IMP-002", "IMP-131"]
    assert result["longest_dependency_chain_estimated_hours"] == 8
    assert result["dag_layers"] == 3
    assert result["initial_graph_roots"] == ["IMP-001"]
    assert len(result["parallel_lanes"]) == 4
    assert result["completion_claimed"] is False
    assert result["production_approved"] is False
    assert result["gates_released"] is False


def test_dependency_drift_fails_closed(plan):
    f = plan / "BACKLOG_UNICO_IMPORTAVEL.csv"
    f.write_text(f.read_text().replace("IMP-002;IMP-003", "IMP-002"))
    with pytest.raises(FrontierInvalid, match="FRONTIER_DEPENDENCY_DRIFT"):
        analyze(plan)


def test_cycle_denied(plan):
    f = plan / "DEPENDENCIAS.csv"
    f.write_text(f.read_text().replace("IMP-003,IMP-131", "IMP-131,IMP-003"))
    with pytest.raises(FrontierInvalid):
        analyze(plan)


def test_invalid_estimate_and_capability_denied(plan):
    f = plan / "BACKLOG_UNICO_IMPORTAVEL.csv"
    s = f.read_text()
    f.write_text(s.replace("IMP-003,IMP-001,3", "IMP-003,IMP-001,-3"))
    with pytest.raises(FrontierInvalid, match="ESTIMATE_OR_CAPABILITY_INVALID"):
        analyze(plan)
    f.write_text(s.replace("CAP-001", "CAP-999"))
    with pytest.raises(FrontierInvalid, match="ESTIMATE_OR_CAPABILITY_INVALID"):
        analyze(plan)


def test_duplicate_task_and_duplicate_edge_denied(plan):
    f = plan / "BACKLOG_UNICO_IMPORTAVEL.csv"
    with f.open("a") as stream:
        stream.write("IMP-002,IMP-001,5,agent,CAP-001\n")
    with pytest.raises(FrontierInvalid, match="IDENTITIES_INVALID"):
        analyze(plan)


def test_cli_is_explicitly_non_release(plan, capsys):
    assert main(["--plan-dir", str(plan)]) == 0
    payload = capsys.readouterr().out
    assert '"production_approved": false' in payload
    assert '"status": "PLANNING_FRONTIER_ONLY"' in payload
