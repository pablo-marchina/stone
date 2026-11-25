"""Contract-only A02.7 -> Stone-S1 guarded label handoff tests.

No ASR/VLM, external rights, model, DB, E1 admission or publication.
"""
from types import SimpleNamespace as S
from copy import deepcopy

import pytest

from tapi_gate0.asset_system_one_guarded_handoff import (
    FIELDS, PROCESSORS, GuardedHandoffDenied, _project_guarded,
    bridge_guarded_av_to_system_one,
)


def report(*, partial=False):
    names=list(FIELDS)+["unused_%02d"%i for i in range(16)]
    fields=tuple(S(field_id=k, state=("abstained" if k in FIELDS else "not_assessed"),
                   value=None, supports=(), vetoes=()) for k in names)
    decision=S(evidence_fingerprint="a"*64, scientific_evidence=False,
               canonical_rubric=False, fields=fields,
               tenant_id="fixture", content_id="post", object_id="b"*64,
               purpose="research_analysis")
    coverage={p:"observed" for p in PROCESSORS}
    details={p:{"state":"observed","reason":None} for p in PROCESSORS}
    rejects={}
    if partial:
        coverage["asr_vad"]="abstained"
        details["asr_vad"]={"state":"abstained","reason":"fixture_quality_rejected"}
        rejects={"asr_vad":{"wer":4/7}}
    return {
        "schema_version":"shared-av-coverage-guard.v1",
        "source_fingerprint":"a"*64, "baseline":decision, "guarded":deepcopy(decision),
        "coverage":coverage, "coverage_details":details,
        "quality_rejections":rejects, "suppressed_fields":(),
        "inference_reexecuted":False, "canonical_rubric":False,
        "scientific_evidence":False, "policy_promoted":False,
    }


def test_complete_guarded_handoff_never_promotes_e1_or_studio():
    result=_project_guarded(report())
    assert result["status"]=="GUARDED_CANDIDATES_ONLY"
    assert result["source_fingerprint"]=="a"*64
    assert len(result["candidate_fields"])==4
    assert all(row["value"] is None for row in result["candidate_fields"])
    assert all(len(row["provenance_sha256"])==64 for row in result["candidate_fields"])
    for key in ("system_one_e1_text_observations_created",
                "scientific_admissions_created","rubric_assessments_written"):
        assert result[key]==0
    for key in ("database_mutated","independent_gold_available",
                "rights_reusable_outside_scope","studio_write_allowed",
                "publication_allowed","production_approved",
                "global_gates_released"):
        assert result[key] is False


def test_partial_quality_rejection_is_explicit_and_never_synthetic_gold():
    result=_project_guarded(report(partial=True))
    assert result["status"]=="PARTIAL_GUARDED_CANDIDATES_ONLY"
    assert result["rejected_processors"]==("asr_vad",)
    assert result["coverage"]["asr_vad"]=="abstained"
    assert result["scientific_admissions_created"]==0


@pytest.mark.parametrize("tamper",[
    lambda g: g.update(policy_promoted=True),
    lambda g: g.update(source_fingerprint="0"*64),
    lambda g: g["coverage"].pop("vlm"),
    lambda g: g["coverage"].update(asr_vad="missing"),
    lambda g: g.update(quality_rejections={"vlm":{"wer":1}}),
    lambda g: g.update(suppressed_fields=("unknown_field",)),
    lambda g: g.update(inference_reexecuted=True),
    lambda g: g["coverage_details"].update(ocr={"state":"abstained","reason":None}),
    lambda g: g["guarded"].__dict__.update(tenant_id="other"),
    lambda g: g["guarded"].__dict__.update(evidence_fingerprint="0"*64),
])
def test_guard_tampering_denied_without_leaking_values(tamper):
    case=report()
    tamper(case)
    with pytest.raises(GuardedHandoffDenied,match="A027_S1_HANDOFF_"):
        _project_guarded(case)


@pytest.mark.parametrize("ids",[
    (), ("artifact."+"a"*64,)*4,
    ("artifact."+"a"*64,"artifact."+"b"*64,"artifact."+"c"*64,"bad"),
    tuple("artifact."+(str(n)*64) for n in range(5)),
    ([], {}, None, "bad"),
])
def test_invalid_selection_denied_before_protected_evaluation(ids,monkeypatch):
    from tapi_gate0 import asset_candidate_fusion as protected
    monkeypatch.setattr(protected,"evaluate_shared_av_coverage_guard",
        lambda *a,**kw: pytest.fail("must not evaluate invalid artifact selection"))
    with pytest.raises(GuardedHandoffDenied,match="FOUR_DISTINCT_ARTIFACTS_REQUIRED"):
        bridge_guarded_av_to_system_one(None,"fixture","b"*64,ids)


def test_entrypoint_requires_actual_typed_fusion_results(monkeypatch):
    from tapi_gate0 import asset_candidate_fusion as protected
    ids=tuple("artifact."+(str(n)*64) for n in range(4))
    called=[]
    def evaluator(store,tenant,object_id,artifact_ids,*,purpose):
        called.append((tenant,object_id,tuple(artifact_ids),purpose))
        return report()
    monkeypatch.setattr(protected,"evaluate_shared_av_coverage_guard",evaluator)
    with pytest.raises(GuardedHandoffDenied,match="GUARD_RESULT_INVALID"):
        bridge_guarded_av_to_system_one(object(),"fixture","b"*64,ids)
    assert called==[("fixture","b"*64,ids,"research_analysis")]


def test_guard_suppression_removes_value_but_retains_provenance():
    case=report()
    before=case["baseline"].fields[0]
    after=case["guarded"].fields[0]
    before.state="candidate"
    before.value="vendas"
    before.supports=(S(artifact_id="artifact."+"c"*64,
                       payload_sha256="d"*64,processor="ocr"),)
    after.supports=deepcopy(before.supports)
    case["suppressed_fields"]=("tema_principal",)
    result=_project_guarded(case)
    field=result["candidate_fields"][0]
    assert field["state"]=="abstained"
    assert field["value"] is None
    assert field["suppressed_by_guard"] is True
    assert field["support_count"]==1
    assert "supports" not in field
    assert "artifact." not in str(field)


def test_insufficient_coverage_is_partial_even_without_wer_rejection():
    case=report()
    case["coverage"]["asr_vad"]="abstained"
    case["coverage_details"]["asr_vad"]={"state":"abstained","reason":"insufficient_evidence"}
    result=_project_guarded(case)
    assert result["status"]=="PARTIAL_GUARDED_CANDIDATES_ONLY"
    assert result["rejected_processors"]==()


def test_missing_quality_rejection_receipt_fails_closed():
    case=report(partial=True)
    case["quality_rejections"]={}
    with pytest.raises(GuardedHandoffDenied,match="QUALITY_REJECTION_INVALID"):
        _project_guarded(case)


def test_studio_purpose_cannot_use_research_handoff(monkeypatch):
    from tapi_gate0 import asset_candidate_fusion as protected
    monkeypatch.setattr(protected,"evaluate_shared_av_coverage_guard",
        lambda *a,**kw: pytest.fail("must not evaluate studio creation"))
    ids=tuple("artifact."+(str(n)*64) for n in range(4))
    with pytest.raises(GuardedHandoffDenied,match="RESEARCH_SCOPE_REQUIRED"):
        bridge_guarded_av_to_system_one(None,"fixture","b"*64,ids,purpose="studio_creation")
