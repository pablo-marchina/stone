"""A02.7->S1 authenticated candidate transfer: no E1 promotion, media or rights reuse.

Pure report fixtures exercise the projection; an injectable evaluator is used
only in tests to prove the public entrypoint cannot accept forged input.
Real asset rights/lineage are tested by asset_candidate_fusion's own suite.
"""
from copy import deepcopy

import pytest

from tapi_gate0 import asset_candidate_fusion as fusion
from tapi_gate0.asset_system_one_guarded_handoff import (
    FIELDS, PROCESSORS, GuardedHandoffDenied, _project_guarded,
    bridge_guarded_av_to_system_one,
)
from tapi_gate0.domain import RUBRIC_FIELD_NAMES


def sample(partial=False):
    decisions = fusion.CandidateDecisions(
        evidence_fingerprint="a"*64, tenant_id="tenantA", content_id="post.one",
        object_id="b"*64, purpose="research_analysis",
        fields=tuple(fusion.FieldCandidate(
            field_id=field,
            state="abstained" if field in FIELDS else "not_assessed",
            reason="NO_EVIDENCE",
        ) for field in RUBRIC_FIELD_NAMES),
    )
    coverage = {p:"observed" for p in PROCESSORS}
    details = {p:{"state":"observed", "reason":None} for p in PROCESSORS}
    rejections = {}
    if partial:
        coverage["asr_vad"] = "abstained"
        details["asr_vad"] = {"state":"abstained","reason":"fixture_quality_rejected"}
        rejections["asr_vad"] = {"wer":0.5714285714285714}
    return {
        "schema_version":"shared-av-coverage-guard.v1",
        "source_fingerprint":"a"*64, "baseline":decisions, "guarded":decisions,
        "coverage":coverage, "coverage_details":details,
        "quality_rejections":rejections, "suppressed_fields":(),
        "inference_reexecuted":False, "canonical_rubric":False,
        "scientific_evidence":False, "policy_promoted":False,
    }


def test_handoff_is_readonly_and_never_calls_e1_or_grants_authority():
    report = _project_guarded(sample())
    assert report["status"] == "GUARDED_CANDIDATES_ONLY"
    assert report["source_fingerprint"] == "a"*64
    assert len(report["candidate_fields"]) == 4
    assert tuple(f["field_id"] for f in report["candidate_fields"]) == FIELDS
    assert all(f["value"] is None and len(f["provenance_sha256"]) == 64
               for f in report["candidate_fields"])
    assert report["system_one_e1_text_observations_created"] == 0
    assert report["scientific_admissions_created"] == 0
    assert report["rubric_assessments_written"] == 0
    assert report["database_mutated"] is False
    assert report["rights_reusable_outside_scope"] is False
    assert report["production_approved"] is False
    assert report["global_gates_released"] is False


def test_partial_asr_rejection_never_becomes_positive_candidate():
    report = _project_guarded(sample(partial=True))
    assert report["status"] == "PARTIAL_GUARDED_CANDIDATES_ONLY"
    assert report["rejected_processors"] == ("asr_vad",)
    assert report["coverage"]["asr_vad"] == "abstained"
    assert all(f["value"] is None for f in report["candidate_fields"])
    assert "0.571428" not in str(report)


def test_coverage_guard_cannot_silently_promote_a_new_decision():
    report = sample()
    before = report["baseline"]
    fields = list(before.fields)
    fields[0] = fields[0].model_copy(update={"reason": "FORGED_LABEL"})
    report["guarded"] = before.model_copy(update={"fields":tuple(fields)})
    with pytest.raises(GuardedHandoffDenied, match="GUARD_DECISION_CHANGED"):
        _project_guarded(report)


def test_entrypoint_invokes_protected_fusion_not_supplied_evidence(monkeypatch):
    report = sample()
    calls = []
    def authorized(*args, **kwargs):
        calls.append((args, kwargs))
        return report
    monkeypatch.setattr(fusion, "evaluate_shared_av_coverage_guard", authorized)
    ids = tuple("artifact." + str(i)*64 for i in range(4))
    store = object()
    result = bridge_guarded_av_to_system_one(
        store, "tenantA", "b"*64, ids, purpose="research_analysis")
    assert result["status"] == "GUARDED_CANDIDATES_ONLY"
    assert calls == [((store, "tenantA", "b"*64, ids),
                      {"purpose": "research_analysis"})]
    assert result["publication_allowed"] is False


def test_bad_artifact_selection_never_calls_fusion(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("must reject selection before protected call")
    monkeypatch.setattr(fusion, "evaluate_shared_av_coverage_guard", forbidden)
    with pytest.raises(GuardedHandoffDenied, match="FOUR_DISTINCT_ARTIFACTS_REQUIRED"):
        bridge_guarded_av_to_system_one(object(), "tenantA", "b"*64,
            ("artifact." + "a"*64,) * 4)


@pytest.mark.parametrize("mutation", [
    lambda g:g.update(policy_promoted=True),
    lambda g:g.update(source_fingerprint="0"*64),
    lambda g:g["coverage"].pop("vlm"),
    lambda g:g["coverage"].update(asr_vad="missing"),
    lambda g:g.update(quality_rejections={"vlm":{"wer":1}}),
    lambda g:g.update(suppressed_fields=("unknown_field",)),
    lambda g:g.update(inference_reexecuted=True),
    lambda g:g["coverage_details"].update(ocr={"state":"abstained","reason":None}),
])
def test_nonmatching_or_malicious_guard_is_denied(mutation):
    report = sample()
    mutation(report)
    with pytest.raises(GuardedHandoffDenied):
        _project_guarded(report)
