"""IMP-064: replay the authored shared-fixture report with GLiNER.

Reuses extracted fragments; does not rerun ASR/OCR or attest source bytes.
Only the seven authored fixtures are supported. No canonical assessments.
"""
import json
from hashlib import sha256
from pathlib import Path
from . import multimodal_fusion as fusion
from . import multimodal_shared_fixture as shared
from . import multimodal_asr as asr
from .discovery_rubric_grounded import rule_evidence,UNKNOWN
from .discovery_rubric_benchmark import candidate

VERSION="bd-multimodal-semantic-replay.v1"
VARIANTS=("lexical","model_consensus","grounded_hybrid")
MODEL_REVISION="e173bca1f0c4217d7a55b3b0c705d5ece8a0218d"
MODEL_WEIGHTS="9efe0f88c99f2aa794452e9559dc60e98d60d9fa2bf1b60cf2710411b6da5b4e"
MAX_REPORT_BYTES=2_000_000


def validate_report(report):
    if (report.get("policy_version")!=shared.VERSION or report.get("fusion_policy")!=fusion.VERSION
            or report.get("synthetic_only") is not True or report.get("engineering_gate_passed") is not True
            or report.get("temporal_integrity_passed") is not True
            or report.get("ocr_language_data_sha256")!=shared.BEST_HASHES
            or report.get("vad_asset_sha256")!=shared.VAD_HASH
            or report.get("checkpoint",{}).get("weights_sha256")!=asr.MEDIUM_SHA256
            or any(report.get(k) is not False for k in ("external_data_accessed","database_mutated","production_approved","real_media_processing_allowed"))
            or any(type(report.get(k)) is not int or report[k]!=0 for k in ("real_media_processed","scientific_admissions","rubric_assessments_written","negative_asr_calls"))):
        raise fusion.FusionError("FUSION_REPLAY_REPORT_INVALID")
    rows=report["cases"]
    if not isinstance(rows,list) or len(rows)!=len(shared.CASES):
        raise fusion.FusionError("FUSION_REPLAY_PARTITION_INVALID")
    if len({r["media_sha256"] for r in rows})!=len(rows):
        raise fusion.FusionError("FUSION_REPLAY_DUPLICATE_ASSET")
    for row,case in zip(rows,shared.CASES):
        cid,caption,speech,screen,late,geometry,topic,cta,has_text=case
        expected={"tema_principal":topic,"tipo_cta":cta,"texto_na_tela":has_text}
        if (row["case_id"]!=cid or row["caption"]!=caption or row["expected"]!=expected
                or row["duration_s"]!=shared.DURATION or row["temporal_passed"] is not True
                or row["source_pixels_and_pcm_verified"] is not True
                or row["asset_binding_verified"] is not True
                or (not speech and row["audio"]["asr_calls"]!=0)):
            raise fusion.FusionError("FUSION_REPLAY_CASE_INVALID")
        shared.validate_asset_binding(row)
        # Recompute the exact expected fragment partition. Missing conflicting
        # fragments must not silently improve a replay result.
        expected_fragments=[]
        for frame in row["ocr_frames"]:
            words=shared.consensus.consensus_words(frame["primary_words"],frame["supporting_words"])
            if words!=frame["words"]:
                raise fusion.FusionError("FUSION_REPLAY_OCR_MISMATCH")
            complete=bool(words) and len(words)==len(frame["primary_words"])==len(frame["supporting_words"]) and [w["supporting_index"] for w in words]==list(range(len(words)))
            if complete!=frame["complete_primary_and_supporting_sequence_retained"]:
                raise fusion.FusionError("FUSION_REPLAY_OCR_MISMATCH")
            if words:
                locator={k:frame[k] for k in ("timestamp_s","timestamp_kind","frame_sha256","frame_png_sha256","view_sha256","words","complete_text_verified")}
                expected_fragments.append(fusion.fragment(row["media_sha256"],"ocr"," ".join(w["text"] for w in words),locator,semantic_eligible=complete))
        if caption:
            expected_fragments.append(fusion.fragment(row["media_sha256"],"caption",caption,
                {"caption_sha256":row["caption_sha256"],"source":"authored_fixture_caption"}))
        for seg in row["audio"]["segments"]:
            if not 0<=seg["start_s"]<seg["end_s"]<=shared.DURATION:
                raise fusion.FusionError("FUSION_REPLAY_TIMESTAMP_INVALID")
            expected_fragments.append(fusion.fragment(row["media_sha256"],"audio",seg["text"],
                {"start_s":seg["start_s"],"end_s":seg["end_s"],"source_pcm_sha256":seg["source_pcm_sha256"],
                 "chunk_pcm_sha256":seg["chunk_pcm_sha256"],"timestamp_kind":row["audio"]["timestamp_kind"]}))
        if expected_fragments!=row["fragments"]:
            raise fusion.FusionError("FUSION_REPLAY_FRAGMENT_PARTITION_INVALID")
        recomputed={name:fusion.fuse(row["media_sha256"],row["fragments"],mods) for name,mods in fusion.ARMS.items()}
        if row["arms"]!=recomputed:
            raise fusion.FusionError("FUSION_REPLAY_LEXICAL_MISMATCH")
    if fusion.evaluate(rows)["ablation"]!=report["ablation"] or not fusion.evaluate(rows)["engineering_gate_passed"]:
        raise fusion.FusionError("FUSION_REPLAY_METRIC_MISMATCH")
    return rows


def fragment_predictions(extractor,f,field):
    rule=rule_evidence(field,f["text"])
    pt=candidate(extractor,field,f["text"],"pt")
    en=candidate(extractor,field,f["text"],"en")
    con=pt if pt==en else UNKNOWN
    return {"modality":f["modality"],"text_sha256":f["text_sha256"],"locator":f["locator"],
            "rule":rule,"pt":pt,"en":en,"model_consensus":con,
            "grounded_hybrid":con if con==rule["rule_value"] else UNKNOWN}


def select_field(predictions,modalities,variant):
    chosen=[p for p in predictions if p["modality"] in modalities]
    if any(p["rule"]["reason"] in ("CONTEXT_GUARD","MULTIPLE_ANCHORS") for p in chosen):
        return {"state":"abstained","value":None,"reason":"CONTEXT_VETO","supports":[]}
    # A lexical conflict must survive even when one model abstains.
    lexical={p["rule"]["rule_value"] for p in chosen}-{UNKNOWN}
    model={p["model_consensus"] for p in chosen}-{UNKNOWN}
    if len(lexical)>1 or (variant!="lexical" and (len(model)>1 or (lexical and model and lexical!=model))):
        return {"state":"abstained","value":None,"reason":"CONFLICTING_ANCHORS","supports":[]}
    def value(p):
        return p["rule"]["rule_value"] if variant=="lexical" else p[variant]
    supports=[p for p in chosen if value(p)!=UNKNOWN]
    labels={value(p) for p in supports}
    return {"state":"candidate" if len(labels)==1 else "abstained",
            "value":next(iter(labels)) if len(labels)==1 else None,
            "reason":"EXPERIMENTAL_"+variant.upper() if len(labels)==1 else "NO_ANCHOR",
            "supports":supports if len(labels)==1 else []}


def replay(report,extractor):
    rows=validate_report(report)
    result=[]
    for row,case in zip(rows,shared.CASES):
        preds={field:[fragment_predictions(extractor,f,field) for f in row["fragments"] if f["semantic_eligible"]]
               for field in fusion.FIELDS}
        variants={}
        for variant in VARIANTS:
            arms={}
            for arm,mods in fusion.ARMS.items():
                values=fusion.fuse(row["media_sha256"],row["fragments"],mods)
                for field in fusion.FIELDS:
                    values[field]=select_field(preds[field],mods,variant)
                cta=values["tipo_cta"]
                values["tem_cta"]={**cta,"value":True if cta["state"]=="candidate" else None}
                arms[arm]=values
            variants[variant]=arms
        result.append({"case_id":row["case_id"],"media_sha256":row["media_sha256"],
            "expected":row["expected"],"fragment_predictions":preds,"variants":variants,
            "audio_diagnostic":asr.word_errors(case[2],row["audio"]["transcript"])})
    metrics={variant:fusion.evaluate([{"expected":r["expected"],"arms":r["variants"][variant]} for r in result])
             for variant in VARIANTS}
    if metrics["lexical"]["ablation"]!=report["ablation"]:
        raise fusion.FusionError("FUSION_REPLAY_LEXICAL_MISMATCH")
    return {"status":"MULTIMODAL_SEMANTIC_REPLAY_COMPLETED","policy_version":VERSION,
            "cases":result,"variants":metrics,"engineering_gate_passed":metrics["grounded_hybrid"]["engineering_gate_passed"],
            "model_only_is_exploratory":True,"automatic_variant_selected":False,
            "source_bytes_redecoded":False,"source_report_consistency_revalidated":True,
            "synthetic_only":True,"independent_gold":False,"real_media_processed":0,
            "real_media_processing_allowed":False,"external_data_accessed":False,
            "database_mutated":False,"scientific_admissions":0,"rubric_assessments_written":0,
            "production_approved":False}
