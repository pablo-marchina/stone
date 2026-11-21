"""A04.6: real synthetic evaluation + real FTS preview, mocked live rights only.

No real tenant, network, operational database, media, gold, model, or agent.
The mock deliberately cannot certify current rights or source authorization.
"""
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from tapi_gate0.discovery_eval_engine import evaluate_versioned_synthetic
from tapi_gate0.discovery_eval_handoff import link_private_reports
from tapi_gate0 import discovery_retrieval_scoped as scoped
from tapi_gate0.discovery_retrieval_fts import RetrievalBaselineError

FIXTURE = Path(__file__).parent / "fixtures" / "CT-04_fts_synthetic.json"
MANIFEST_PIN = "c" * 64


def _encode(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return raw, sha256(raw).hexdigest()


def _evaluation():
    fixture = FIXTURE.read_bytes()
    fixture_sha = sha256(fixture).hexdigest()
    report = evaluate_versioned_synthetic(
        fixture, expected_sha256=fixture_sha, evaluation_version="a046-integration",
        split="validation", k=2,
    )
    assert report["status"] == "PASS"
    assert report["local_gate_scope"] == "synthetic_regression_only"
    assert report["scientifically_validated"] is False
    assert report["gold_relevance_judgments_available"] is False
    return report


def _mock_scoped_data(monkeypatch, *, deny_scope_call=None, drift=False):
    """Exercise the actual FTS5 implementation; mock only external scope/data."""
    calls = {"scopes": 0, "readiness": 0}

    def gate(_engine, tenant, frame, viewer):
        calls["scopes"] += 1
        if tenant != "synthetic-tenant" or viewer != "synthetic-viewer":
            raise RetrievalBaselineError("RETRIEVAL_SCOPE_DENIED")
        if deny_scope_call == calls["scopes"]:
            raise RetrievalBaselineError("RETRIEVAL_SCOPE_REVOKED")
        return "synthetic-test-scope"

    def readiness(_engine, tenant, frame, viewer, *, _record_observer,
                  _timing_observer=None, _trace_auditor=None):
        calls["readiness"] += 1
        rows = [
            ("synthetic-post-1", "synthetic-snapshot-1", "Vendas e atendimento"),
            ("synthetic-post-2", "synthetic-snapshot-2", "Estoque e controle"),
        ]
        if drift and calls["readiness"] == 2:
            rows[0] = ("synthetic-post-1", "synthetic-snapshot-changed", "Vendas e atendimento")
        for cid, snapshot, caption in rows:
            _record_observer(
                NS(username="synthetic-source"),
                NS(content_id=cid, caption=caption),
                NS(snapshot_id=snapshot),
            )
        return {
            "status": "CORPUS_READINESS_PLANNED",
            "manifest_sha256": frame.fingerprint(),
            "first_blocking_stage": {"CAPTION_AVAILABLE_FOR_ASSESSMENT": 2},
            "completed_runs_without_valid_bd_trace": 0,
            "new_scientific_admissions": 0,
            "database_mutated": False,
            "external_data_accessed": False,
            "sources": [{"source_gate": "TECHNICAL_SCOPE_MATCHED"}],
        }

    monkeypatch.setattr(scoped, "require_scoped_research", gate)
    monkeypatch.setattr(scoped, "readiness_report", readiness)
    return calls


def _preview():
    frame = NS(sources=[NS(username="synthetic-source")],
               fingerprint=lambda: MANIFEST_PIN)
    report = scoped.preview_scoped_fts(
        object(), "synthetic-tenant", frame, "synthetic-viewer",
        queries=["vendas"], expected_posts=2, expected_sources=1, limit=2,
    )
    assert report["status"] == "SCOPED_FTS_LOCAL_PREVIEW_COMPLETED"
    assert report["gold_relevance_judgments_available"] is False
    assert report["queries"][0]["gold_metrics"] is None
    return report


def _link(ev, rt, *, eval_pin=None, preview_pin=None, manifest_pin=MANIFEST_PIN):
    ev_raw, ev_digest = _encode(ev)
    rt_raw, rt_digest = _encode(rt)
    return link_private_reports(
        ev_raw, rt_raw,
        evaluation_report_sha256=ev_digest if eval_pin is None else eval_pin,
        retrieval_report_sha256=rt_digest if preview_pin is None else preview_pin,
        evaluation_spec_sha256=ev["evaluation_spec_sha256"],
        fixture_sha256=ev["fixture_sha256"],
        manifest_sha256=manifest_pin,
        partition_sha256=rt["partition_sha256"],
    )


def test_actual_producers_link_only_for_private_diagnostics(monkeypatch):
    counts = _mock_scoped_data(monkeypatch)
    result = _link(_evaluation(), _preview())
    assert counts == {"scopes": 3, "readiness": 2}
    assert result["status"] == "TECHNICAL_REPORTS_LINKED"
    assert result["permitted_use"] == "private_diagnostic_only"
    assert result["technical_reports_linked"] is True
    for key in ("tenant_scope_currently_verified", "source_rights_currently_verified",
                "independent_gold_available", "scientifically_validated",
                "a05_agent_handoff_allowed", "creative_handoff_allowed",
                "gates_released", "production_approved"):
        assert result[key] is False
    assert "synthetic-post-1" not in str(result)


def test_actual_eval_is_blocked_when_replaced_after_hash_pinning(monkeypatch):
    _mock_scoped_data(monkeypatch)
    ev, rt = _evaluation(), _preview()
    _, pinned = _encode(ev)
    ev["status"] = "FAIL"
    result = _link(ev, rt, eval_pin=pinned)
    assert result["reason_code"] == "A046_REPORT_SHA_MISMATCH"
    assert result["a05_agent_handoff_allowed"] is False


def test_actual_preview_partition_cannot_be_swapped(monkeypatch):
    _mock_scoped_data(monkeypatch)
    ev, rt = _evaluation(), _preview()
    result = _link(ev, rt, manifest_pin="a" * 64)
    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "A046_RETRIEVAL_PROVENANCE_INVALID"
    assert result["creative_handoff_allowed"] is False


def test_actual_preview_revocation_prevents_any_report(monkeypatch):
    counts = _mock_scoped_data(monkeypatch, deny_scope_call=2)
    with pytest.raises(RetrievalBaselineError, match="RETRIEVAL_SCOPE_REVOKED"):
        _preview()
    assert counts == {"scopes": 2, "readiness": 1}


def test_actual_preview_drift_prevents_any_report(monkeypatch):
    counts = _mock_scoped_data(monkeypatch, drift=True)
    with pytest.raises(RetrievalBaselineError, match="RETRIEVAL_PARTITION_DRIFT"):
        _preview()
    assert counts == {"scopes": 3, "readiness": 2}


def test_actual_producers_do_not_allow_fabricated_gold(monkeypatch):
    _mock_scoped_data(monkeypatch)
    ev, rt = _evaluation(), _preview()
    ev["scientifically_validated"] = True
    assert _link(ev, rt)["reason_code"] == "A046_EVALUATION_UNSAFE_CLAIM"
    ev = _evaluation()
    rt["queries"][0]["gold_metrics"] = {"recall_at_k": 1.0}
    assert _link(ev, rt)["reason_code"] == "A046_RETRIEVAL_QUERY_CONTRACT_INVALID"
