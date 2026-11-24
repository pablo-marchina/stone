"""IMP-074: kill a real child process around the direct SQL ledger commit.

Synthetic local corpus only. Neither a LangGraph saver nor external tools are
exercised; no operational authority follows from this recovery evidence.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from sqlalchemy import select

from scripts import dec008_orchestrator_benchmark as bench
from tapi_gate0.agent_graph_checkpoints import agent_graph_events, agent_graph_runs
from tapi_gate0.agent_graph_readonly_runner import LocalGraphPlan, execute_bounded, execute_next
from tapi_gate0.sa_store import engine_for

ROOT = Path(__file__).resolve().parents[1]
_CHILD = r'''
import sys, time
from pathlib import Path
from scripts import dec008_orchestrator_benchmark as bench
from tapi_gate0 import agent_graph_readonly_runner as runner
from tapi_gate0.sa_store import engine_for
path, mode, boundary, marker = sys.argv[1:]
engine = engine_for("sqlite:///" + Path(path).as_posix())
plan = runner.LocalGraphPlan(mode=mode, content_id="fixture.post", as_of=bench.AS_OF)
def pause():
    Path(marker).write_text("READY", encoding="ascii")
    while True:
        time.sleep(0.1)
if boundary == "before_commit":
    original = runner.record_node
    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        pause()  # SQL writes issued but outer transaction has not committed.
    runner.record_node = interrupted
receipt = runner.execute_next(engine, tenant=bench.TENANT, actor=bench.ACTOR,
                              run_id=bench.RUN, plan=plan)
assert receipt["revision"] == 2 and boundary == "after_commit"
pause()  # execute_next has returned: the SQL commit is durable.
'''


def _engine(path):
    return engine_for("sqlite:///" + path.as_posix())


def _args(mode):
    return dict(tenant=bench.TENANT, actor=bench.ACTOR, run_id=bench.RUN,
                plan=LocalGraphPlan(mode=mode, content_id="fixture.post", as_of=bench.AS_OF))


def _kill_at_boundary(path, mode, boundary, marker):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONNOUSERSITE="1")
    child = subprocess.Popen([sys.executable, "-c", _CHILD, str(path), mode, boundary, str(marker)],
                             cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and child.poll() is None:
            if marker.exists() and marker.read_text(encoding="ascii") == "READY":
                break
            time.sleep(0.02)
        else:
            pytest.fail("DEC008_CHILD_BOUNDARY_NOT_REACHED")
        assert child.poll() is None
        child.kill()
        assert child.wait(timeout=10) != 0
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)


@pytest.mark.parametrize("mode,terminal,revision", [
    ("analisar", "TRACE_RECORDED", 5),
    ("recomendar", "TRACE_RECORDED", 6),
    ("gerar_criativo", "ABSTAINED", 5),
])
@pytest.mark.parametrize("boundary,expected_after_kill", [("before_commit", 1), ("after_commit", 2)])
def test_direct_ledger_real_process_kill_and_recovery(tmp_path, mode, terminal, revision,
                                                      boundary, expected_after_kill):
    path = tmp_path / "interrupted.sqlite"
    engine = _engine(path)
    try:
        bench._prepare(engine)
        assert execute_next(engine, **_args(mode))["revision"] == 1
    finally:
        engine.dispose()
    _kill_at_boundary(path, mode, boundary, tmp_path / "boundary.ready")
    recovered = _engine(path)
    reference = _engine(tmp_path / "reference.sqlite")
    try:
        with recovered.connect() as db:
            assert db.scalar(select(agent_graph_runs.c.revision)) == expected_after_kill
            assert len(db.execute(select(agent_graph_events)).all()) == expected_after_kill
        result = execute_bounded(recovered, **_args(mode))
        bench._prepare(reference)
        assert result == execute_bounded(reference, **_args(mode))
        assert (result["status"], result["revision"]) == (terminal, revision)
        assert execute_next(recovered, **_args(mode)) == result
        assert all(result[k] is False for k in bench.NEVER_TRUE)
        with recovered.connect() as db:
            events = db.execute(select(agent_graph_events).order_by(agent_graph_events.c.sequence)).mappings().all()
            assert [e["sequence"] for e in events] == list(range(1, revision + 1))
            assert "INJECTION" not in str(events)
    finally:
        recovered.dispose()
        reference.dispose()
