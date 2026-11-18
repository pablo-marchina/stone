"""A02.7.3 fixed authored ASR recovery experiment, not a production adapter.

Uses no vault/DB/provider and accepts no caller-provided audio or transcript.
All inference is through the existing Windows Job supervisor. The original
audio recipe and 0.50 WER / VAD criteria are unchanged. Both arms are evaluated
on every case; no automatic selection, fallback or persistence.
"""
import json
from pathlib import Path

from . import asset_asr_fixture as asr
from . import asset_windows_job as windows
from . import multimodal_cta_directed as directed
from .discovery_rubric_grounded import rule_evidence,UNKNOWN

VERSION="authored-asr-recovery.v1"
CASES=("inventory","agreement","conflict","cta","silence","tone")
EXPECTED={
    "inventory":("gestão",None),"agreement":("vendas",None),"conflict":("finanças",None),
    "cta":(None,"salvar"),"silence":(None,None),"tone":(None,None),
}


def _semantic(texts):
    # No concatenation between fragments. Use the same conservative
    # lexical and directed-request policy as protected candidate fusion.
    preds=[{"rule":rule_evidence("tipo_cta",t),"directed":directed.directed_evidence(t)} for t in texts]
    themes=[rule_evidence("tema_principal",t) for t in texts]
    labels={r["rule_value"] for r in themes}-{UNKNOWN}
    veto=any(r["reason"] in ("CONTEXT_GUARD","MULTIPLE_ANCHORS") for r in themes)
    return {"tema_principal":next(iter(labels)) if len(labels)==1 and not veto else None,
            "tipo_cta":directed.directed_decision(preds,hybrid=False)}


def _score(case,meta,output):
    # Structural/negative failures propagate and do not become observations.
    try:
        obs,quality=asr.result_from_output(meta,output)
        passed=True
        texts=[s.text for s in getattr(obs,"segments",())]
    except asr.ASRFixtureQualityError as exc:
        quality=exc.quality
        passed=False
        # Exact authored diagnostic only, after strict structural validation.
        # Never persist or use this rejected transcript for semantic fusion.
        texts=[r["text"] for r in json.loads(output)["segments"]]
    diagnostic_anchors=_semantic(texts)
    values=diagnostic_anchors if passed else None
    expected=dict(zip(("tema_principal","tipo_cta"),EXPECTED[case]))
    return {"quality_passed":passed,"quality":quality,"values":values,"expected":expected,
            "diagnostic_anchors_not_admitted":diagnostic_anchors,
            "semantic_exact_match":passed and values==expected,
            "hypothesis_sha256":asr._digest(" ".join(texts).encode("utf-8")),
            "hypothesis_word_count":len(asr._words(" ".join(texts))),
            "reference_word_count":len(asr._words(meta["reference"]))}


def run(model_dir):
    windows._native_api()
    model_dir=Path(model_dir)
    rows=[]
    runtime=asr._runtime(model_dir)
    for case,transport in [*((c,"argv") for c in CASES),("cta","utf8_stdin")]:
        data,meta=asr._authored_fixture(case,transport=transport)
        for profile in asr.RECOVERY_PROFILES:
            config,code=asr._plan(data,meta,model_dir,profile=profile)
            if config["runtime"]!=runtime:
                raise ValueError("ASR_RECOVERY_RUNTIME_CHANGED")
            def check():
                if asr._digest(data)!=config["input_sha256"]:
                    raise ValueError("ASR_RECOVERY_INPUT_CHANGED")
            # Fixed synthetic data; no DB lease or external asset. Explicit
            # runtime check before and after each protected child.
            row={"case":case,"transport":transport,"profile":profile,"pcm_sha256":meta["pcm_sha256"],
                "configuration_sha256":config["configuration_sha256"]}
            try:
                output,metrics=windows._run_model_fixture(code,data,check,limits=asr.LIMITS,max_output=asr.MAX_OUTPUT)
                row.update(resources=metrics,**_score(case,meta,output))
            except windows.JobError as exc:
                # A native failure remains a failure; allow the other fixed
                # arms to run. Do not expose exception text or promote it.
                row.update(quality_passed=False,semantic_exact_match=False,error_code="ASR_RECOVERY_NATIVE_FAILURE")
            if asr._runtime(model_dir)!=runtime:
                raise ValueError("ASR_RECOVERY_RUNTIME_CHANGED")
            rows.append(row)
    summaries={}
    for profile in asr.RECOVERY_PROFILES:
        group=[r for r in rows if r["profile"]==profile and r["transport"]=="argv"]
        summaries[profile]={"cases":len(group),
            "quality_passed":sum(r["quality_passed"] for r in group),
            "semantic_exact_matches":sum(r["semantic_exact_match"] for r in group),
            "engineering_gate_passed":all(r["quality_passed"] and r["semantic_exact_match"] for r in group)}
    return {"status":"ASR_RECOVERY_EXPERIMENT_COMPLETED","policy_version":VERSION,"rows":rows,
        "profiles":summaries,"tts_transport_exploratory":True,"synthetic_only":True,"independent_gold":False,
        "automatic_profile_selected":False,"canonical_rubric":False,"database_mutated":False}
