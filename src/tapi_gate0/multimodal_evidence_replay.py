"""IMP-063/064/136: synthetic report-only evidence composition v2.

No media input, model invocation, canonical assessment, external grant or
database write. VLM v2 failed its full gate; its votes remain exploratory.
"""
from hashlib import sha256
from itertools import combinations
import re
from collections import Counter

from . import multimodal_fusion as fusion
from . import multimodal_semantic_replay as replay
from . import multimodal_cta_directed as directed
from . import multimodal_vlm as vlm
from . import multimodal_vlm_single_scene as visual
from .discovery_rubric_grounded import rule_evidence,UNKNOWN
from .discovery_rubric_coverage import REQUIREMENTS
from .domain import RUBRIC_FIELD_NAMES

VERSION="bd-multimodal-evidence-replay.v2"
MODALITIES=(*fusion.MODALITIES,"vlm")
ARMS={"+".join(parts):parts for n in range(1,5) for parts in combinations(MODALITIES,n)}
ALL_ARM="+".join(MODALITIES)
FIELDS=("tema_principal","tipo_cta","texto_na_tela")


def fail(code):
    raise fusion.FusionError(code)


def validate_visual(shared_report,visual_report,source_digest):
    if (visual_report.get("policy_version")!=visual.VERSION
            or visual_report.get("source_report_sha256")!=source_digest
            or visual_report.get("model_id")!=vlm.MODEL_ID
            or visual_report.get("model_revision")!=vlm.MODEL_REVISION
            or visual_report.get("prompt_sha256")!=fusion.digest(visual.PROMPT)
            or visual_report.get("runtime",{}).get("build")!=vlm.RUNTIME_BUILD
            or visual_report.get("runtime",{}).get("commit_prefix")!=vlm.RUNTIME_COMMIT
            or visual_report.get("synthetic_only") is not True
            or visual_report.get("shared_pixels_hash_matched") is not True
            or any(visual_report.get(k) is not False for k in ("external_data_accessed","database_mutated","production_approved","real_media_processing_allowed"))
            or any(type(visual_report.get(k)) is not int or visual_report[k]!=0 for k in ("real_media_processed","scientific_admissions","rubric_assessments_written"))
            or {k:v["sha256"] for k,v in visual_report.get("checkpoint",{}).items()}!=vlm.FILES):
        fail("EVIDENCE_VISUAL_REPORT_INVALID")
    # Regenerate only the authored images; hash ties the report to pixels.
    frames=vlm.make_frames(shared_report)+visual.extra_frames()
    observations=visual_report["cases"]
    if len(observations)!=len(frames):
        fail("EVIDENCE_VISUAL_PARTITION_INVALID")
    cache={}
    bound={}
    for obs,frame in zip(observations,frames):
        image=frame.pop("image")
        digest=sha256(vlm.encode_image(image)).hexdigest()
        if any(obs.get(k)!=v for k,v in frame.items()) or obs.get("image_png_sha256")!=digest:
            fail("EVIDENCE_VISUAL_FRAME_MISMATCH")
        scene=obs["model_scene"]
        uniform=visual.exact_uniform(image)
        if uniform:
            expected=visual.derived("blank")
            if scene is not None or obs["inference_attempted"] is not False or obs["guard_reason"]!="EXACT_UNIFORM_PIXELS" or obs["response_sha256"] is not None:
                fail("EVIDENCE_VISUAL_GUARD_INVALID")
        else:
            if (scene not in ("blank","geometry","text_card","uncertain",None)
                    or obs["inference_attempted"] is not True
                    or not re.fullmatch(r"[a-f0-9]{64}",obs["response_sha256"] or "")
                    or obs["guard_reason"]!=("NONUNIFORM_BLANK_CONFLICT" if scene=="blank" else None)):
                fail("EVIDENCE_VISUAL_GUARD_INVALID")
            expected=visual.derived("uncertain" if scene=="blank" else scene)
        if obs["prediction"]!=expected:
            fail("EVIDENCE_VISUAL_PREDICTION_INVALID")
        signature={k:obs[k] for k in ("prediction","model_scene","response_sha256","guard_reason","inference_attempted")}
        if obs["reused_identical_image_result"]!=(digest in cache) or (digest in cache and cache[digest]!=signature):
            fail("EVIDENCE_VISUAL_CACHE_INVALID")
        cache[digest]=signature
        if obs["suite"]=="shared":
            bound[(obs["media_sha256"],obs["timestamp_s"])]=obs
    metrics=visual.metrics(observations)
    if (metrics["suites"]!=visual_report["suites"] or metrics["engineering_gate_passed"]!=visual_report["engineering_gate_passed"]
            or len(cache)!=visual_report["unique_images"]
            or sum(x["inference_attempted"] for x in cache.values())!=visual_report["unique_model_calls"]
            or sum(x["guard_reason"]=="EXACT_UNIFORM_PIXELS" for x in cache.values())!=visual_report["uniform_guard_unique_images"]):
        fail("EVIDENCE_VISUAL_METRIC_MISMATCH")
    return bound


def state(value=None,*,reason,state_name=None,supports=(),vetoes=(),measurement=None):
    return {"state":state_name or ("candidate" if value is not None else "abstained"),
            "value":value,"reason":reason,"supports":list(supports),"vetoes":list(vetoes),
            "measurement":measurement,"canonical":False}


def directed_cta(fragments,modalities):
    predictions=[]
    for f in fragments:
        if f["modality"] not in modalities or not f["semantic_eligible"]:
            continue
        predictions.append({"rule":rule_evidence("tipo_cta",f["text"]),"directed":directed.directed_evidence(f["text"]),
                            "modality":f["modality"],"text_sha256":f["text_sha256"],"locator":f["locator"]})
    value=directed.directed_decision(predictions,hybrid=False)
    if value is None:
        return state(reason="NO_UNAMBIGUOUS_DIRECTED_REQUEST",vetoes=predictions)
    return state(value,reason="DIRECTED_REQUEST_V2",supports=[p for p in predictions if p["directed"]["value"]==value])


def screen_candidate(ocr_frames,visual_frames,modalities):
    """VLM never promotes text alone in combined OCR+VLM arm.

    VLM-only is an explicit exploratory comparison, not selected policy.
    A negative VLM vote may veto same-frame OCR, never imply absence.
    """
    supports=[]
    vetoes=[]
    for frame in ocr_frames:
        t=frame["timestamp_s"]
        obs=visual_frames[t]
        pred=obs["prediction"]
        vote=pred["text_present"] if pred else "uncertain"
        if "ocr" in modalities and frame["words"]:
            evidence={"modality":"ocr","timestamp_s":t,"frame_sha256":frame["frame_sha256"],"words":frame["words"]}
            if "vlm" in modalities and vote=="no":
                vetoes.append({"ocr":evidence,"vlm":obs,"reason":"SAME_FRAME_MODALITY_CONFLICT"})
            else:
                supports.append(evidence)
                if "vlm" in modalities and vote=="yes":
                    supports.append({"modality":"vlm","timestamp_s":t,"image_png_sha256":obs["image_png_sha256"],"prediction":pred})
        elif "vlm" in modalities and "ocr" not in modalities and vote=="yes":
            supports.append({"modality":"vlm","timestamp_s":t,"image_png_sha256":obs["image_png_sha256"],"prediction":pred})
    # A conflict at one frame does not negate positive evidence at another.
    if supports:
        return state(True,reason="OCR_POSITIVE_WITH_OPTIONAL_VLM_SUPPORT" if "ocr" in modalities else "VLM_ONLY_EXPLORATORY",
                     supports=supports,vetoes=vetoes)
    return state(reason="NO_UNCONFLICTED_POSITIVE_SCREEN_EVIDENCE",vetoes=vetoes)


def compose(row,observations,modalities):
    if len(set(modalities))!=len(modalities) or not set(modalities)<=set(MODALITIES):
        fail("EVIDENCE_ARM_INVALID")
    fragments=row["fragments"]
    fields={f:state(reason=REQUIREMENTS[f],state_name="not_assessed") for f in RUBRIC_FIELD_NAMES}
    text_modalities=tuple(m for m in modalities if m in fusion.MODALITIES)
    fields["tema_principal"]={**fusion.field_candidate("tema_principal",fragments,text_modalities),"measurement":None,"canonical":False}
    fields["tipo_cta"]=directed_cta(fragments,text_modalities)
    cta=fields["tipo_cta"]
    fields["tem_cta"]={**cta,"value":True if cta["value"] is not None else None}
    fields["texto_na_tela"]=screen_candidate(row["ocr_frames"],observations,modalities)
    return fields


def measurements(row,fields):
    # Observed values are measurements, NOT rubric bins or scores.
    temporal=row["temporal"]
    opening=temporal["opening_samples"]
    fields["duracao_faixa"]=state(reason="DURATION_SECONDS_NOT_APPROVED_BIN",state_name="measurement_only",
        measurement={"duration_s":row["duration_s"],"media_sha256":row["media_sha256"]})
    fields["legenda_tamanho"]=state(reason="CHARACTER_COUNT_NOT_APPROVED_BIN",state_name="measurement_only",
        measurement={"characters":len(row["caption"]),"caption_sha256":row["caption_sha256"]})
    fields["hook_primeiros_3s"]=state(reason="OPENING_OBSERVATIONS_NOT_SEMANTIC_HOOK",state_name="measurement_only",
        measurement={"opening_samples":opening,"timestamp_kind":temporal["timestamp_kind"],
            "audio_segments":[s for s in row["audio"]["segments"] if s["start_s"]<3],
            "ocr_frames":[f for f in row["ocr_frames"] if f["timestamp_s"]<3]})
    fields["ritmo_cortes_0a10"]=state(reason="TRANSITION_COUNT_NOT_CALIBRATED_SCORE",state_name="measurement_only",
        measurement={"transition_candidates":temporal["transition_candidates"],"count":temporal["transition_candidate_count"],
                     "sample_fps":temporal["sample_fps"],"timestamp_kind":temporal["timestamp_kind"]})
    return fields


def run(shared_report,visual_report,source_digest):
    rows=replay.validate_report(shared_report)
    visual_bound=validate_visual(shared_report,visual_report,source_digest)
    result=[]
    for row in rows:
        observations={t:visual_bound[(row["media_sha256"],t)] for t in (0,3)}
        arms={name:compose(row,observations,mods) for name,mods in ARMS.items()}
        fields=measurements(row,dict(arms[ALL_ARM]))
        result.append({"case_id":row["case_id"],"media_sha256":row["media_sha256"],
            "expected":row["expected"],"arms":arms,"field_evidence":fields,
            "visual_observations":list(observations.values()),
            "source_rights":{"scope":"internally_authored_synthetic_fixture","external_grant_verified":False,
                             "real_media_processing_allowed":False}})
    scores={arm:{field:fusion.score_arm(result,arm,field) for field in FIELDS} for arm in ARMS}
    selected=scores[ALL_ARM]
    counts={field:dict(Counter(r["field_evidence"][field]["state"] for r in result)) for field in RUBRIC_FIELD_NAMES}
    return {"status":"MULTIMODAL_EVIDENCE_REPLAY_COMPLETED","policy_version":VERSION,
            "cases":result,"ablation":scores,"selected_experimental_arm":ALL_ARM,
            "field_coverage":counts,"field_count":len(RUBRIC_FIELD_NAMES),
            "total_field_cells":len(result)*len(RUBRIC_FIELD_NAMES),
            "engineering_gate_passed":all(m["wrong_nonabstained"]==0 and m["candidate_recall"]>=0.75 for m in selected.values()),
            "gate_criteria":{"min_candidate_recall":0.75,"wrong_nonabstained":0,"all_seven_shared_cases_required":True},
            "upstream_vlm_gate_passed":visual_report["engineering_gate_passed"],
            "vlm_only_exploratory":True,"visual_support_is_not_independent_validation":True,
            "models_invoked":0,"source_container_redecoded":False,"source_report_consistency_revalidated":True,
            "synthetic_only":True,"independent_gold":False,"real_media_processed":0,
            "real_media_processing_allowed":False,"external_data_accessed":False,
            "database_mutated":False,"scientific_admissions":0,"rubric_assessments_written":0,"production_approved":False}
