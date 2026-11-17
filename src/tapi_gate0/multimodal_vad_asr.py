"""IMP-063: staged VAD + ASR synthetic integration, no external input.

VAD evaluated first, cache released before Whisper load. Preserve the
original decoded PCM timeline; never concatenate away unknown gaps.
"""
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
import gc
import math
import os
import shutil
import tempfile

from . import multimodal_asr as asr
from . import multimodal_vad as vad
from .multimodal_temporal import _run

VERSION="bd-vad-asr-fixture.v1"


def transcribe_regions(model,raw,intervals):
    n=vad._validate_pcm(raw)
    intervals=vad.validate_intervals(intervals,n)
    full_hash=sha256(raw).hexdigest()
    segments=[]
    chunks=[]
    for region in intervals:
        a,b=region["start"],region["end"]
        pcm=raw[a*2:b*2]
        result=asr._transcribe(model,pcm)
        duration=(b-a)/asr.SAMPLE_RATE
        offset=a/asr.SAMPLE_RATE
        chunk_hash=sha256(pcm).hexdigest()
        if result["pcm_sha256"]!=chunk_hash:
            raise asr.ASRError("ASR_CHUNK_HASH_MISMATCH")
        chunks.append({"start_sample":a,"end_sample":b,"pcm_sha256":chunk_hash,
                       "transcript":result["transcript"]})
        for segment in result["segments"]:
            start,end=segment["start_s"],segment["end_s"]
            # The recognizer may round its last timestamp beyond the chunk.
            # Clip only within the existing 250ms ASR tolerance and retain raw
            # coordinates; never attribute speech to an unprocessed interval.
            if not (0<=start<duration and start<end<=duration+0.25):
                raise asr.ASRError("ASR_CHUNK_TIMESTAMP_INVALID")
            end_clipped=min(end,duration)
            if len(segments)>=128:
                raise asr.ASRError("ASR_CHUNK_SEGMENT_LIMIT")
            segments.append({**segment,"start_s":offset+start,"end_s":offset+end_clipped,
                             "chunk_start_s":start,"chunk_end_s":end,
                             "chunk_pcm_sha256":chunk_hash,"source_pcm_sha256":full_hash,
                             "region_start_sample":a,"region_end_sample":b,
                             "end_clipped":end_clipped!=end})
    return {"pcm_sha256":full_hash,"duration_s":n/asr.SAMPLE_RATE,
            "segments":segments,"chunks":chunks,
            "transcript":" ".join(c["transcript"] for c in chunks if c["transcript"]),
            "inference_attempted":bool(intervals),"asr_calls":len(intervals),
            "abstention_reason":None if intervals else "NO_VAD_SPEECH_REGION",
            "timestamp_kind":"model_estimate_mapped_to_decoded_pcm_not_original_pts"}


def reference_for(cid):
    refs={key:text for key,text,_ in asr.CHALLENGE_SPEECH}
    mapping={"inventory_padded":refs["inventory"],"quiet_speech":refs["inventory"],
             "speech_with_noise":refs["inventory"],"costs_padded":refs["costs"],
             "two_speech_regions":refs["costs"]+" "+refs["costs"],
             "planning_padded":refs["planning"],"silence":"","tone":"","noise":""}
    if cid not in mapping:
        raise asr.ASRError("ASR_UNKNOWN_VAD_FIXTURE")
    return mapping[cid]


def evaluate(cases):
    positives=[c for c in cases if c["reference_words"]]
    negatives=[c for c in cases if not c["reference_words"]]
    total=sum(c["reference_words"] for c in positives)
    errors=sum(c["word_errors"] for c in positives)
    wer=errors/total if total else None
    expected={"inventory_padded","quiet_speech","speech_with_noise","costs_padded",
              "two_speech_regions","planning_padded","silence","tone","noise"}
    complete=len(cases)==9 and {c["case_id"] for c in cases}==expected
    gate=(complete and len(positives)==6 and len(negatives)==3 and wer is not None
          and wer<=asr.MAX_POOLED_WER and all(c["wer"]<=asr.MAX_CASE_WER and c["inference_attempted"] for c in positives)
          and all(c["hypothesis_words"]==0 and c["asr_calls"]==0 and not c["inference_attempted"] for c in negatives)
          and all(c["vad_score"]["passed"] for c in cases))
    return {"speech_reference_words":total,"speech_word_errors":errors,"pooled_wer":wer,
            "negative_inserted_words":sum(c["hypothesis_words"] for c in negatives),
            "negative_asr_calls":sum(c["asr_calls"] for c in negatives),
            "total_asr_calls":sum(c["asr_calls"] for c in cases),
            "vad_cases_passed":sum(c["vad_score"]["passed"] for c in cases),
            "engineering_gate_passed":bool(gate),
            "gate_criteria":{"max_pooled_wer":asr.MAX_POOLED_WER,"max_case_wer":asr.MAX_CASE_WER,
                "negative_inserted_words":0,"negative_asr_calls":0,"vad_all_passed":True,
                "all_nine_cases_required":True}}


def run_vad_asr_benchmark(model_dir):
    os.environ.update(HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",HF_HUB_DISABLE_TELEMETRY="1")
    with asr.asr_stage("checkpoint_preflight"):
        checkpoint=asr.verify_checkpoint(model_dir,"medium")
        asr.require_temp_capacity()
        if version("faster-whisper")!=asr.ASR_VERSION:
            raise asr.ASRError("ASR_RUNTIME_VERSION_MISMATCH")
    espeak,ffmpeg=shutil.which("espeak-ng"),shutil.which("ffmpeg")
    if not espeak or not ffmpeg:
        raise asr.ASRError("ASR_LOCAL_BINARY_UNAVAILABLE")
    from faster_whisper.utils import get_assets_path
    from faster_whisper.vad import VadOptions,get_speech_timestamps,get_vad_model
    asset=Path(get_assets_path())/"silero_vad_v6.onnx"
    if not asset.is_file() or asset.is_symlink() or not 0<asset.stat().st_size<=30_000_000:
        raise asr.ASRError("ASR_VAD_LOCAL_ASSET_REQUIRED")
    digest=asr._file_hash(asset)
    with tempfile.TemporaryDirectory(prefix="tapi-vad-asr-") as temp:
        fixtures=vad.fixture_rows(espeak,ffmpeg,temp)
    prepared=[]
    with asr.asr_stage("vad"):
        get_vad_model.cache_clear()
        try:
            options=VadOptions(**vad.OPTIONS)
            get_vad_model()
            for cid,raw,expected in fixtures:
                observation=vad.inspect_pcm(raw,lambda pcm:get_speech_timestamps(pcm,options,sampling_rate=asr.SAMPLE_RATE))
                score=vad.score_intervals(observation["intervals"],expected,len(raw)//2)
                prepared.append((cid,raw,expected,observation,score))
            if asr._file_hash(asset)!=digest:
                raise asr.ASRError("ASR_VAD_ASSET_CHANGED")
        finally:
            get_vad_model.cache_clear()
            gc.collect()
    with asr.asr_stage("model_load"):
        from faster_whisper import WhisperModel
        t=perf_counter()
        model=WhisperModel(str(model_dir),device="cpu",compute_type="int8",cpu_threads=4,num_workers=1,local_files_only=True)
        if not model.model.is_multilingual or model.feature_extractor.sampling_rate!=asr.SAMPLE_RATE:
            raise asr.ASRError("ASR_MULTILINGUAL_MODEL_REQUIRED")
        load_ms=round((perf_counter()-t)*1000,3)
    cases=[]
    for cid,raw,expected,observation,score in prepared:
        with asr.asr_stage("inference",cid):
            t=perf_counter()
            result=transcribe_regions(model,raw,observation["intervals"])
            latency=round((perf_counter()-t)*1000,3)
            reference=reference_for(cid)
            cases.append({"case_id":cid,"reference":reference,"expected_regions":expected,
                          "vad":observation,"vad_score":score,**result,
                          **asr.word_errors(reference,result["transcript"]),
                          "asr_inference_ms":latency,"vad_inference_ms":observation["inference_ms"],
                          "real_time_factor":round((latency+observation["inference_ms"])/(1000*result["duration_s"]),6)})
    del model
    gc.collect()
    with asr.asr_stage("checkpoint_postflight"):
        if asr.verify_checkpoint(model_dir,"medium")!=checkpoint:
            raise asr.ASRError("ASR_CHECKPOINT_CHANGED")
    return {"status":"VAD_ASR_FIXTURE_BENCHMARK_COMPLETED","policy_version":VERSION,
            "checkpoint":checkpoint,"vad_asset_sha256":digest,"vad_asset_independently_verified":False,
            "vad_options":vad.OPTIONS,"runtime_versions":{name:version(name) for name in ("faster-whisper","ctranslate2","onnxruntime","numpy","tokenizers","huggingface-hub")},
            "model_load_ms":load_ms,"device":"cpu","compute_type":"int8",
            "execution_order":"vad_all_then_cache_clear_then_whisper","cases":cases,**evaluate(cases),
            "synthetic_only":True,"asr_integration_evaluated":True,"independent_gold":False,
            "real_media_processed":0,"real_media_processing_allowed":False,"external_data_accessed":False,
            "database_mutated":False,"rubric_assessments_written":0,"scientific_admissions":0,"production_approved":False}
