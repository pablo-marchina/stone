"""Synthetic-only cost/coverage diagnostics; no authorization or execution."""
from itertools import combinations
import math
import re

PROCESSORS=("asr_vad","ocr","temporal","vlm")
FIELDS=("tema_principal","tipo_cta","tem_cta","texto_na_tela")
FULL="+".join(PROCESSORS)
QUIET="asr_vad+ocr+temporal"
ARMS=tuple("+".join(a) for n in range(1,5) for a in combinations(PROCESSORS,n))
ORACLE={
    "inventory":(None,None,None,True),
    "silence":(None,None,None,None),
    "agreement":("vendas",None,None,True),
    "conflict":(None,None,None,True),
    "complementary":("vendas","salvar",True,True),
    "audio_only":(None,"salvar",True,None),
    "screen_only":("vendas",None,None,True),
    "tone_negative":(None,None,None,None),
}

def _values(decision):
    return {f.field_id:f.value for f in decision.fields if f.field_id in FIELDS}

def row_from_replay(case,replay,steps):
    if case not in ORACLE or set(steps)!=set(PROCESSORS) or set(replay["arms"])!=set(ARMS):
        raise ValueError("ROUTING_ROW_SHAPE")
    if any(replay[k] is not False for k in ("inference_reexecuted","routing_executed","policy_promoted")):
        raise ValueError("ROUTING_NOT_SHADOW")
    costs={}
    for p,s in steps.items():
        if s["processor"]!=p or s["status"]!="processed":
            raise ValueError("ROUTING_STEP")
        jobs=[s[k] for k in ("decode_resources","model_resources","ocr_resources") if s[k] is not None]
        costs[p]={"wall_ms":s["step_wall_ms"],"model_calls":s["model_calls"],
                  "peak_job_commit_bytes":max(j["peak_job_commit_bytes"] for j in jobs)}
    row={"case":case,"source_fingerprint":replay["source_fingerprint"],
         "expected":dict(zip(FIELDS,ORACLE[case])),
         "arms":{k:_values(v["guarded"]) for k,v in replay["arms"].items()},
         "diagnostic_full_baseline":_values(replay["arms"][FULL]["baseline"]),
         "coverage":replay["arms"][FULL]["coverage_details"],
         "asr_quality_rejected":bool(replay["full_quality_rejections"]),
         "shadow_route":replay["shadow_route"],"costs":costs}
    _validate(row)
    return row

def _validate(row):
    if type(row) is not dict or set(row)!={"case","source_fingerprint","expected","arms",
        "diagnostic_full_baseline","coverage","asr_quality_rejected","shadow_route","costs"}:
        raise ValueError("ROUTING_ROW_SHAPE")
    case=row["case"]
    if case not in ORACLE or row["expected"]!=dict(zip(FIELDS,ORACLE[case])):
        raise ValueError("ROUTING_ORACLE")
    if not isinstance(row["source_fingerprint"],str) or not re.fullmatch("[0-9a-f]{64}",row["source_fingerprint"]):
        raise ValueError("ROUTING_FINGERPRINT")
    if set(row["arms"])!=set(ARMS) or set(row["coverage"])!=set(PROCESSORS) or set(row["costs"])!=set(PROCESSORS):
        raise ValueError("ROUTING_PARTITION")
    for p,v in row["coverage"].items():
        if (type(v) is not dict or set(v)!={"state","reason"} or
                (v["state"],v["reason"]) not in (("observed",None),("abstained","no_observable_signal"),
                ("abstained","fixture_quality_rejected"))):
            raise ValueError("ROUTING_COVERAGE")
    rejected=row["coverage"]["asr_vad"]["reason"]=="fixture_quality_rejected"
    if row["asr_quality_rejected"] is not rejected:
        raise ValueError("ROUTING_REJECTION")
    if any(v["reason"]=="fixture_quality_rejected" for p,v in row["coverage"].items() if p!="asr_vad"):
        raise ValueError("ROUTING_REJECTION")
    quiet=all(row["coverage"][p]["reason"]=="no_observable_signal" for p in ("asr_vad","ocr"))
    if row["shadow_route"]!=(QUIET if quiet else FULL):
        raise ValueError("ROUTING_SHADOW_RULE")
    for values in [*row["arms"].values(),row["diagnostic_full_baseline"]]:
        if type(values) is not dict or set(values)!=set(FIELDS):
            raise ValueError("ROUTING_FIELDS")
        if (values["tema_principal"] is not None and type(values["tema_principal"]) is not str or
            values["tipo_cta"] is not None and type(values["tipo_cta"]) is not str or
            values["tem_cta"] is not (True if values["tipo_cta"] is not None else None) or
            values["texto_na_tela"] is not None and values["texto_na_tela"] is not True):
            raise ValueError("ROUTING_VALUES")
    for c in row["costs"].values():
        if (type(c) is not dict or set(c)!={"wall_ms","model_calls","peak_job_commit_bytes"} or
            type(c["wall_ms"]) not in (int,float) or not math.isfinite(c["wall_ms"]) or c["wall_ms"]<=0 or
            type(c["model_calls"]) is not int or not 0<=c["model_calls"]<=128 or
            type(c["peak_job_commit_bytes"]) is not int or c["peak_job_commit_bytes"]<=0):
            raise ValueError("ROUTING_COST")

def _score(rows,choose,*,baseline=False):
    cells=correct=wrong=missed=exact=expected_positive=predicted=0
    wall=0.0; calls=peak=0
    for r in rows:
        arm=choose(r)
        values=r["diagnostic_full_baseline"] if baseline else r["arms"][arm]
        expected=r["expected"]
        cells+=len(FIELDS)
        exact+=int(values==expected)
        for k in FIELDS:
            a,b=expected[k],values[k]
            expected_positive+=int(a is not None)
            predicted+=int(b is not None)
            correct+=int(a is not None and a==b)
            wrong+=int(b is not None and a!=b)
            missed+=int(a is not None and b is None)
        costs=[r["costs"][p] for p in arm.split("+")]
        wall+=sum(c["wall_ms"] for c in costs)
        calls+=sum(c["model_calls"] for c in costs)
        peak=max(peak,*(c["peak_job_commit_bytes"] for c in costs))
    return {"cells":cells,"expected_positive":expected_positive,"predicted_positive":predicted,
        "correct_nonabstained":correct,"wrong_nonabstained":wrong,"missed_candidates":missed,
        "exact_cases":exact,"coverage":predicted/cells,
        "selective_error_rate":wrong/predicted if predicted else None,
        "estimated_step_wall_ms":round(wall,3),"estimated_model_calls":calls,
        "max_observed_job_commit_bytes":peak}

def summarize(rows):
    if not isinstance(rows,list) or len(rows)!=len(ORACLE):
        raise ValueError("ROUTING_COMPLETE_COHORT_REQUIRED")
    for row in rows:
        _validate(row)
    if {r["case"] for r in rows}!=set(ORACLE) or len({r["source_fingerprint"] for r in rows})!=len(rows):
        raise ValueError("ROUTING_COMPLETE_COHORT_REQUIRED")
    arms={a:_score(rows,lambda r:a) for a in ARMS}
    shadow=_score(rows,lambda r:r["shadow_route"])
    full=arms[FULL]
    return {"schema_version":"shared-av-routing-summary.v1","cases":len(rows),
        "asr_rejected_cases":[r["case"] for r in rows if r["asr_quality_rejected"]],
        "arms":arms,"diagnostic_full_baseline":_score(rows,lambda r:FULL,baseline=True),
        "shadow":shadow,"shadow_routes":{r["case"]:r["shadow_route"] for r in rows},
        "shadow_same_guarded_values":all(r["arms"][r["shadow_route"]]==r["arms"][FULL] for r in rows),
        "shadow_estimated_wall_saved_ms":round(full["estimated_step_wall_ms"]-shadow["estimated_step_wall_ms"],3),
        "shadow_estimated_calls_saved":full["estimated_model_calls"]-shadow["estimated_model_calls"],
        "synthetic_only":True,"independent_gold":False,"canonical_rubric":False,
        "routing_executed":False,"realized_savings_measured":False,"policy_promoted":False,
        "cost_definition":"sum of observed processor step times; excludes final replay, not isolated counterfactual runtime"}
