import pytest
from tapi_gate0.asset_shared_av_routing import ARMS,FULL,QUIET,ORACLE,FIELDS,PROCESSORS,summarize

def rows():
    result=[]
    for i,(case,values) in enumerate(ORACLE.items()):
        expected=dict(zip(FIELDS,values))
        quiet=case in ("silence","tone_negative")
        rejected=case in ("complementary","audio_only")
        coverage={p:{"state":"observed","reason":None} for p in PROCESSORS}
        if quiet:
            for p in ("asr_vad","ocr"):
                coverage[p]={"state":"abstained","reason":"no_observable_signal"}
        if rejected:
            coverage["asr_vad"]={"state":"abstained","reason":"fixture_quality_rejected"}
        blank=dict.fromkeys(FIELDS)
        full=blank if quiet or rejected else expected
        result.append({"case":case,"source_fingerprint":format(i+1,"064x"),"expected":expected,
            "arms":{a:dict(full if a==FULL else blank) for a in ARMS},
            "diagnostic_full_baseline":dict(full),"coverage":coverage,"asr_quality_rejected":rejected,
            "shadow_route":QUIET if quiet else FULL,
            "costs":{p:{"wall_ms":10,"model_calls":int(p!="temporal"),"peak_job_commit_bytes":100}
                     for p in PROCESSORS}})
    return result

def test_routing_summary_exact_cohort_and_counterfactual_cost():
    report=summarize(rows())
    assert len(report["arms"])==15 and report["cases"]==8
    assert report["shadow_same_guarded_values"]
    assert report["shadow_estimated_wall_saved_ms"]==20
    assert report["shadow_estimated_calls_saved"]==2
    assert report["arms"][FULL]["cells"]==32
    assert report["asr_rejected_cases"]==["complementary","audio_only"]
    assert not report["routing_executed"] and not report["realized_savings_measured"]

def test_routing_rejects_missing_duplicate_oracle():
    data=rows()
    with pytest.raises(ValueError,match="COMPLETE_COHORT"):
        summarize(data[:-1])
    with pytest.raises(ValueError,match="COMPLETE_COHORT"):
        summarize(data[:-1]+[data[0]])
    data[0]["expected"]["tema_principal"]="vendas"
    with pytest.raises(ValueError,match="ORACLE"):
        summarize(data)

def test_routing_rejects_false_negative_and_unavailable_cost():
    data=rows()
    data[0]["arms"][FULL]["texto_na_tela"]=False
    with pytest.raises(ValueError,match="VALUES"):
        summarize(data)
    data=rows()
    data[0]["costs"]["vlm"]["wall_ms"]=float("nan")
    with pytest.raises(ValueError,match="COST"):
        summarize(data)

def test_routing_rejection_cannot_be_hidden_or_used_to_skip_vlm():
    data=rows()
    data[4]["asr_quality_rejected"]=False
    with pytest.raises(ValueError,match="REJECTION"):
        summarize(data)
    data=rows()
    data[4]["shadow_route"]=QUIET
    with pytest.raises(ValueError,match="SHADOW_RULE"):
        summarize(data)
