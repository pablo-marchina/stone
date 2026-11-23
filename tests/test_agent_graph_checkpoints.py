"""IMP-074 provisional checkpoint baseline: synthetic metadata, no tools or rights."""
from __future__ import annotations

from hashlib import sha256

import pytest
from sqlalchemy import insert, select, update, text

from tapi_gate0.agent_graph_checkpoints import (
    AgentCheckpointDenied, MODES, VERSION,
    agent_graph_events, agent_graph_runs,
    begin_run, record_node, resume_run,
)
from tapi_gate0.sa_store import engine_for, metadata, tenants

TENANT = "fixture-tenant"
ACTOR = "fixture-operator"
RUN = "run.abc"
PLAN = "a" * 64
RESULT = "b" * 64


@pytest.fixture
def engine(tmp_path):
    result = engine_for("sqlite:///" + (tmp_path / "checkpoint.sqlite").as_posix())
    metadata.create_all(result)
    with result.begin() as db:
        db.execute(insert(tenants), [
            {"tenant_id": TENANT, "name": "A"},
            {"tenant_id": "other-tenant", "name": "B"},
        ])
    try:
        yield result
    finally:
        result.dispose()


def start(engine, **kwargs):
    return begin_run(engine, tenant=TENANT, actor=ACTOR, run_id=RUN,
                     mode="analisar", plan_sha256=PLAN, **kwargs)


def record(engine, expected_revision=0, node="plan", outcome="PASS", receipt_sha256=RESULT, **kwargs):
    return record_node(engine, tenant=TENANT, actor=ACTOR, run_id=RUN,
                       expected_revision=expected_revision, node=node,
                       outcome=outcome, receipt_sha256=receipt_sha256, **kwargs)


def test_begin_idempotent_and_explicitly_non_authorizing(engine):
    first = start(engine)
    assert first == start(engine)
    assert first["status"] == "OPEN" and first["next_node"] == "plan"
    assert first["revision"] == 0
    assert len(first["chain_sha256"]) == 64
    assert first["schema_version"] == VERSION
    for flag in ("node_execution_proved", "independent_gold_available",
                 "rights_verified", "scientifically_validated", "studio_write_allowed",
                 "publication_allowed", "production_approved", "global_gates_released"):
        assert first[flag] is False
    assert "fixture-operator" not in str(first)
    assert "fixture-tenant" not in str(first)


@pytest.mark.parametrize("mode", sorted(MODES))
def test_all_three_modes_have_bounded_replayable_graphs(engine, mode):
    first = begin_run(engine, tenant=TENANT, actor=ACTOR, run_id=RUN,
                      mode=mode, plan_sha256=PLAN)
    assert first["next_node"] == "plan"
    for i, node in enumerate(MODES[mode]):
        next_result = record(engine, expected_revision=i, node=node,
                             receipt_sha256=sha256(node.encode()).hexdigest())
        assert next_result["revision"] == i + 1
        assert next_result["next_node"] == (MODES[mode][i + 1]
                                               if i + 1 < len(MODES[mode]) else None)
        assert next_result["studio_write_allowed"] is False
        assert next_result["production_approved"] is False
        assert resume_run(engine, tenant=TENANT, actor=ACTOR, run_id=RUN) == next_result
    assert next_result["status"] == "TRACE_RECORDED"
    assert begin_run(engine, tenant=TENANT, actor=ACTOR, run_id=RUN,
                     mode=mode, plan_sha256=PLAN) == next_result
    with engine.connect() as db:
        rows = db.execute(select(agent_graph_events.c.sequence,
                                 agent_graph_events.c.node)).all()
    assert rows == [(i + 1, node) for i, node in enumerate(MODES[mode])]


@pytest.mark.parametrize("outcome,terminal", [
    ("ABSTAIN", "ABSTAINED"), ("BLOCKED", "BLOCKED"),
])
def test_early_stop_never_retries_or_auto_advances(engine, outcome, terminal):
    start(engine)
    stopped = record(engine, outcome=outcome)
    assert stopped["status"] == terminal and stopped["next_node"] is None
    assert record(engine, outcome=outcome) == stopped  # idempotent duplicate
    with pytest.raises(AgentCheckpointDenied, match="REVISION_CONFLICT"):
        record(engine, expected_revision=1, node="retrieve")
    assert resume_run(engine, tenant=TENANT, actor=ACTOR, run_id=RUN) == stopped


def test_exact_replay_after_later_steps_and_conflicting_receipt(engine):
    start(engine)
    first = record(engine)
    second = record(engine, expected_revision=1, node="retrieve",
                    receipt_sha256="c" * 64)
    assert first["chain_sha256"] != second["chain_sha256"]
    assert record(engine) == second  # Old exact retry cannot roll the state back
    with pytest.raises(AgentCheckpointDenied, match="REPLAY_CONFLICT"):
        record(engine, receipt_sha256="d" * 64)
    with pytest.raises(AgentCheckpointDenied, match="REPLAY_CONFLICT"):
        record(engine, outcome="ABSTAIN")
    assert resume_run(engine, tenant=TENANT, actor=ACTOR, run_id=RUN) == second


def test_cross_tenant_and_wrong_actor_never_read_or_update(engine):
    start(engine)
    for tenant, actor in (("other-tenant", ACTOR), (TENANT, "other-operator")):
        with pytest.raises(AgentCheckpointDenied, match="RUN_NOT_IN_TRUSTED_SCOPE"):
            resume_run(engine, tenant=tenant, actor=actor, run_id=RUN)
        with pytest.raises(AgentCheckpointDenied, match="RUN_NOT_IN_TRUSTED_SCOPE"):
            record_node(engine, tenant=tenant, actor=actor, run_id=RUN,
                        expected_revision=0, node="plan", outcome="PASS",
                        receipt_sha256=RESULT)
    assert resume_run(engine, tenant=TENANT, actor=ACTOR, run_id=RUN)["revision"] == 0


def test_plan_or_actor_conflict_cannot_overwrite_run(engine):
    start(engine)
    for change in ({"plan_sha256": "c" * 64}, {"mode": "recomendar"},
                   {"actor": "different-actor"}):
        args = {"tenant": TENANT, "actor": ACTOR, "run_id": RUN,
                "mode": "analisar", "plan_sha256": PLAN} | change
        with pytest.raises(AgentCheckpointDenied, match="RUN_ID_CONFLICT"):
            begin_run(engine, **args)
    assert resume_run(engine, tenant=TENANT, actor=ACTOR, run_id=RUN)["revision"] == 0


@pytest.mark.parametrize("kwargs", [
    {"tenant": ""}, {"actor": ""}, {"run_id": "../escape"},
    {"mode": "publish"}, {"mode": "gerar_criativo;publish"},
    {"plan_sha256": "invalid"}, {"plan_sha256": "A" * 64},
])
def test_invalid_start_denied_without_rows(engine, kwargs):
    params = {"tenant": TENANT, "actor": ACTOR, "run_id": RUN,
              "mode": "analisar", "plan_sha256": PLAN} | kwargs
    with pytest.raises(AgentCheckpointDenied, match="INPUT_INVALID"):
        begin_run(engine, **params)
    with engine.connect() as db:
        assert db.scalar(select(agent_graph_runs.c.run_id)) is None


@pytest.mark.parametrize("kwargs,code", [
    ({"expected_revision": True}, "INPUT_INVALID"),
    ({"receipt_sha256": "0" * 63}, "INPUT_INVALID"),
    ({"node": "studio_handoff"}, "NODE_OUT_OF_ORDER"),
    ({"outcome": "EXECUTE_PAID"}, "INPUT_INVALID"),
    ({"expected_revision": 2}, "REVISION_CONFLICT"),
])
def test_unauthorized_transition_or_invalid_receipt_denied(engine, kwargs, code):
    start(engine)
    params = {"tenant": TENANT, "actor": ACTOR, "run_id": RUN,
              "expected_revision": 0, "node": "plan", "outcome": "PASS",
              "receipt_sha256": RESULT} | kwargs
    with pytest.raises(AgentCheckpointDenied, match=code):
        record_node(engine, **params)
    assert resume_run(engine, tenant=TENANT, actor=ACTOR, run_id=RUN)["revision"] == 0


@pytest.mark.parametrize("table,values,code", [
    (agent_graph_events, {"receipt_sha256": "f" * 64}, "LEDGER_INTEGRITY_INVALID"),
    (agent_graph_events, {"outcome": "ABSTAIN"}, "LEDGER_INTEGRITY_INVALID"),
    (agent_graph_runs, {"cursor": "creative_spec_draft"}, "STORED_STATE_DRIFT"),
    (agent_graph_runs, {"chain_sha256": "f" * 64}, "STORED_STATE_DRIFT"),
    (agent_graph_runs, {"revision": 0}, "LEDGER_GAP_OR_EXTRA_ENTRY"),
])
def test_stored_state_and_event_tampering_fails_closed(engine, table, values, code):
    start(engine)
    record(engine)
    with engine.begin() as db:
        db.execute(update(table).where(table.c.tenant_id == TENANT,
                                       table.c.run_id == RUN).values(**values))
    with pytest.raises(AgentCheckpointDenied, match=code):
        resume_run(engine, tenant=TENANT, actor=ACTOR, run_id=RUN)


def test_restart_of_engine_recovers_state_with_provenance(engine, tmp_path):
    start(engine)
    record(engine)
    new_engine = engine_for(str(engine.url))
    try:
        restored = resume_run(new_engine, tenant=TENANT, actor=ACTOR, run_id=RUN)
        assert restored["revision"] == 1 and restored["next_node"] == "retrieve"
        next_result = record(new_engine, expected_revision=1, node="retrieve",
                             receipt_sha256="c" * 64)
        assert next_result["revision"] == 2
        assert resume_run(engine, tenant=TENANT, actor=ACTOR, run_id=RUN) == next_result
    finally:
        new_engine.dispose()


def test_nonexistent_tenant_cannot_start(engine):
    with pytest.raises(AgentCheckpointDenied, match="TENANT_UNAVAILABLE"):
        begin_run(engine, tenant="missing-tenant", actor=ACTOR, run_id=RUN,
                  mode="analisar", plan_sha256=PLAN)


def test_no_raw_tool_payload_or_promoted_rights_in_database(engine):
    start(engine)
    record(engine)
    with engine.connect() as db:
        stored = db.execute(select(agent_graph_events)).mappings().one()
        run = db.execute(select(agent_graph_runs)).mappings().one()
    assert "caption" not in str(stored)
    assert "prompt" not in str(stored)
    assert "creator" not in str(stored)
    assert ACTOR not in str(run)
    assert run["actor_sha256"] != sha256(ACTOR.encode()).hexdigest()
    assert stored["receipt_sha256"] == RESULT
