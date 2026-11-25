"""IMP-063/064/136: synthetic, co-referenced evidence composition.

Lexical candidates only. No canonical rubric, no inference from absence,
no modality concatenation, no semantic hook or calibrated rating.
"""
from hashlib import sha256
import re
from .domain import RUBRIC_FIELD_NAMES
from .discovery_rubric_grounded import rule_evidence,UNKNOWN

VERSION="bd-multimodal-fusion.v1"
FIELDS=("tema_principal","tipo_cta")
MODALITIES=("caption","audio","ocr")
ARMS={"caption_only":("caption",),"audio_only":("audio",),"ocr_only":("ocr",),
      "caption_audio":("caption","audio"),"caption_ocr":("caption","ocr"),
      "audio_ocr":("audio","ocr"),"all":MODALITIES}


class FusionError(ValueError):
    pass


def digest(text):
    return sha256(text.encode("utf-8")).hexdigest()


def fragment(asset_sha,modality,text,locator,*,semantic_eligible=True):
    if (not re.fullmatch(r"[a-f0-9]{64}",asset_sha) or modality not in MODALITIES
            or not isinstance(text,str) or not text.strip() or len(text)>10000
            or not isinstance(locator,dict) or type(semantic_eligible) is not bool):
        raise FusionError("FUSION_FRAGMENT_INVALID")
    return {"asset_sha256":asset_sha,"modality":modality,"text":text,
            "text_sha256":digest(text),"locator":locator,"semantic_eligible":semantic_eligible}


def validate_fragments(asset_sha,fragments):
    if not re.fullmatch(r"[a-f0-9]{64}",asset_sha) or len(fragments)>128:
        raise FusionError("FUSION_FRAGMENT_INVALID")
    for f in fragments:
        if f.get("asset_sha256")!=asset_sha:
            raise FusionError("FUSION_ASSET_MISMATCH")
        expected=fragment(asset_sha,f["modality"],f["text"],f["locator"],
                          semantic_eligible=f["semantic_eligible"])
        if expected!=f:
            raise FusionError("FUSION_FRAGMENT_INVALID")


def field_candidate(field,fragments,modalities):
    anchors=[]
    vetoes=[]
    for f in fragments:
        if f["modality"] not in modalities or not f["semantic_eligible"]:
            continue
        r=rule_evidence(field,f["text"])
        if r["reason"] in ("CONTEXT_GUARD","MULTIPLE_ANCHORS"):
            vetoes.append({"modality":f["modality"],"reason":r["reason"],
                           "text_sha256":f["text_sha256"],"locator":f["locator"]})
        if r["rule_value"]!=UNKNOWN:
            anchors.append({"value":r["rule_value"],"modality":f["modality"],
                            "text_sha256":f["text_sha256"],"locator":f["locator"],
                            "spans":r["evidence_spans"]})
    labels={a["value"] for a in anchors}
    if vetoes or len(labels)!=1:
        return {"state":"abstained","value":None,"supports":anchors,"vetoes":vetoes,
                "reason":"CONTEXT_VETO" if vetoes else "CONFLICTING_ANCHORS" if labels else "NO_ANCHOR"}
    return {"state":"candidate","value":next(iter(labels)),"supports":anchors,
            "vetoes":[],"reason":"UNIQUE_LEXICAL_ANCHOR_ACROSS_AVAILABLE_MODALITIES"}


def fuse(asset_sha,fragments,modalities=MODALITIES):
    validate_fragments(asset_sha,fragments)
    if len(set(modalities))!=len(modalities) or not set(modalities)<=set(MODALITIES):
        raise FusionError("FUSION_ARM_INVALID")
    result={f:{"state":"not_assessed","value":None,"reason":"REQUIRES_ADDITIONAL_EVIDENCE_OR_CALIBRATION",
               "supports":[],"vetoes":[]} for f in RUBRIC_FIELD_NAMES}
    for field in FIELDS:
        result[field]=field_candidate(field,fragments,modalities)
    cta=result["tipo_cta"]
    result["tem_cta"]={**cta,"value":True if cta["state"]=="candidate" else None}
    screen=[{"modality":"ocr","text_sha256":f["text_sha256"],"locator":f["locator"]}
            for f in fragments if f["modality"]=="ocr" and "ocr" in modalities]
    result["texto_na_tela"]={"state":"candidate" if screen else "abstained",
                            "value":True if screen else None,"supports":screen,"vetoes":[],
                            "reason":"PARTIAL_OCR_WORDS" if screen else "NO_POSITIVE_OCR_EVIDENCE"}
    return result


def score_arm(rows,arm,field):
    pairs=[(r["expected"][field],r["arms"][arm][field]["value"]) for r in rows]
    expected=sum(a is not None for a,b in pairs)
    correct=sum(a is not None and a==b for a,b in pairs)
    wrong=sum(b is not None and a!=b for a,b in pairs)
    return {"cases":len(pairs),"expected_candidates":expected,"correct_candidates":correct,
            "wrong_nonabstained":wrong,"abstentions":sum(b is None for a,b in pairs),
            "exact_matches":sum(a==b for a,b in pairs),
            "candidate_recall":correct/expected if expected else None,
            "candidate_precision":correct/(correct+wrong) if correct+wrong else None}


def evaluate(rows):
    metrics={arm:{field:score_arm(rows,arm,field) for field in (*FIELDS,"texto_na_tela")}
             for arm in ARMS}
    gate=bool(rows) and all(m["expected_candidates"]>0 and m["wrong_nonabstained"]==0
        and m["candidate_recall"]>=0.75 for m in metrics["all"].values())
    return {"ablation":metrics,"engineering_gate_passed":gate,
            "gate_criteria":{"all_modalities_min_candidate_recall":0.75,
                             "all_modalities_wrong_nonabstained":0,
                             "temporal_and_asset_integrity_required":True},
            "independent_gold":False,"scientific_admissions":0,"rubric_assessments_written":0}
