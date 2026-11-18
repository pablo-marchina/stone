"""A02.7.3 fixed authored ASR recovery experiment, not a production adapter.

Uses no vault/DB/provider and accepts no caller-provided audio or transcript.
All inference is through the existing Windows Job supervisor. The original
audio recipe and 0.50 WER / VAD criteria are unchanged. Both arms of the selected round are evaluated
on every case; no automatic selection, fallback or persistence.
"""
import json
from pathlib import Path

from . import asset_asr_fixture as asr
from . import asset_windows_job as windows
from . import multimodal_cta_directed as directed
from .discovery_rubric_grounded import rule_evidence,UNKNOWN

VERSION="authored-asr-recovery.v2"
ROUNDS={"v1":("baseline","context_500ms"),"v2":("beam10","word_context_500ms")}
CASES=("inventory","agreement","conflict","cta","silence","tone")
# Operator round v1 PCM pins (18 Nov); v2 must compare exactly these inputs.
V1_PCM={
    ("inventory","argv"):"a466b1a2a12073c94175aa7202fc55d874b614a4b72ae03612323fd6c79f9a9b",
    ("agreement","argv"):"c202e822ab54b8537b3d874006a9bb184459ad97f421753bacd12f9b10042666",
    ("conflict","argv"):"7dd41857625aad130c0aa8fdfae107eb12aa4cd94d108769b002f24c9560d973",
    ("cta","argv"):"aba15de4d51a3c6f699b31be456dea7caab466369bbc89fbe8cd1ee4535b08b6",
    ("silence","argv"):"55873fecc61a79e87ca550c7072e38ccdd7ecb600ace286fe4717952a97c42b0",
    ("tone","argv"):"37442e2a99755bfa13c7d1e04b9845d570dc151371e0e2f755fd70e991fab3b6",
    ("cta","utf8_stdin"):"7ea19e0442aeb03a7a5020a0a79f8e9fde097fce9c63c94717c9af3fbb0793cf",
}
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


def _score(case,meta,output,*,profile="baseline"):
    parsed=json.loads(output)
    if (profile in ("context_500ms","word_context_500ms") and type(parsed) is dict and set(parsed)=={"pcm_sha256","diagnostic_error"}
            and parsed["pcm_sha256"]==meta["pcm_sha256"] and parsed["diagnostic_error"] in
            ("ASR_RECOVERY_CONTEXT_TIMESTAMP","ASR_RECOVERY_CONTEXT_NO_OVERLAP",
             "ASR_RECOVERY_WORD_TEXT_MISMATCH","ASR_RECOVERY_WORD_TIMESTAMP")):
        return {"quality_passed":False,"semantic_exact_match":False,"values":None,
                "error_code":parsed["diagnostic_error"]}
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
    hypothesis_words=set(asr._words(" ".join(texts)))
    anchor_words={"inventory":("estoque",),"agreement":("vendas",),"conflict":("custos","fixos"),
                  "cta":("salve","este","conteúdo")}.get(case,())
    values=diagnostic_anchors if passed else None
    expected=dict(zip(("tema_principal","tipo_cta"),EXPECTED[case]))
    return {"quality_passed":passed,"quality":quality,"values":values,"expected":expected,
            "diagnostic_anchors_not_admitted":diagnostic_anchors,
            "expected_anchor_word_presence":{w:w in hypothesis_words for w in anchor_words},
            "semantic_exact_match":passed and values==expected,
            "hypothesis_sha256":asr._digest(" ".join(texts).encode("utf-8")),
            "hypothesis_word_count":len(asr._words(" ".join(texts))),
            "reference_word_count":len(asr._words(meta["reference"]))}


def run(model_dir,*,round_id="v2",progress=None):
    if round_id not in ROUNDS:
        raise ValueError("ASR_RECOVERY_ROUND")
    profiles=ROUNDS[round_id]
    windows._native_api()
    model_dir=Path(model_dir)
    rows=[]
    total=2*(len(CASES)+1)
    def notify(event,row):
        if progress is not None:
            progress({"event":event,"round_id":round_id,"case":row["case"],
                "transport":row["transport"],"profile":row["profile"],
                "pcm_sha256":row["pcm_sha256"],"completed":len(rows),"total":total})
    runtime=asr._runtime(model_dir)
    for case,transport in [*((c,"argv") for c in CASES),("cta","utf8_stdin")]:
        data,meta=asr._authored_fixture(case,transport=transport)
        matches_v1=meta["pcm_sha256"]==V1_PCM[(case,transport)]
        if round_id=="v2" and not matches_v1:
            raise ValueError("ASR_RECOVERY_V1_PCM_MISMATCH")
        for profile in profiles:
            config,code=asr._plan(data,meta,model_dir,profile=profile)
            if config["runtime"]!=runtime:
                raise ValueError("ASR_RECOVERY_RUNTIME_CHANGED")
            def check():
                if asr._digest(data)!=config["input_sha256"]:
                    raise ValueError("ASR_RECOVERY_INPUT_CHANGED")
            # Fixed synthetic data; no DB lease or external asset. Explicit
            # runtime check before and after each protected child.
            row={"case":case,"transport":transport,"profile":profile,"pcm_sha256":meta["pcm_sha256"],
                "configuration_sha256":config["configuration_sha256"],"matches_v1_pcm":matches_v1}
            # Native errors (including failure to verify cleanup) must abort;
            # no next child may start until the operator reconciles them.
            notify("started",row)
            output,metrics=windows._run_model_fixture(code,data,check,limits=asr.LIMITS,max_output=asr.MAX_OUTPUT)
            row.update(resources=metrics,**_score(case,meta,output,profile=profile))
            if asr._runtime(model_dir)!=runtime:
                raise ValueError("ASR_RECOVERY_RUNTIME_CHANGED")
            rows.append(row)
            notify("completed",row)
    summaries=_summaries(rows,profiles)
    return {"status":"ASR_RECOVERY_EXPERIMENT_COMPLETED","policy_version":VERSION,"round_id":round_id,"rows":rows,
        "profiles":summaries,"tts_transport_exploratory":True,"synthetic_only":True,"independent_gold":False,
        "automatic_profile_selected":False,"canonical_rubric":False,"database_mutated":False}


def _summaries(rows,profiles):
    summaries={}
    for profile in profiles:
        group=[r for r in rows if r["profile"]==profile and r["transport"]=="argv"]
        complete=len(group)==len(CASES) and {r["case"] for r in group}==set(CASES)
        summaries[profile]={"cases":len(group),"complete":complete,
            "quality_passed":sum(r["quality_passed"] for r in group),
            "semantic_exact_matches":sum(r["semantic_exact_match"] for r in group),
            "engineering_gate_passed":complete and all(r["quality_passed"] and
                r["semantic_exact_match"] and r["matches_v1_pcm"] for r in group)}
    return summaries
