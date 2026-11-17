"""Local synthetic-only temporal benchmark; never accepts social media inputs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from tapi_gate0.multimodal_temporal import TemporalError, run_temporal_fixture_benchmark
from tapi_gate0.policy import Operation, decide

ROOT = Path(__file__).resolve().parents[1]


def readiness():
    binaries={name:bool(shutil.which(name)) for name in ("ffmpeg","ffprobe","tesseract","espeak-ng")}
    modules={name:importlib.util.find_spec(name) is not None for name in ("cv2","numpy","faster_whisper","transformers","onnxruntime")}
    return {"status":"MULTIMODAL_LOCAL_READINESS","binaries":binaries,"modules":modules,
            "synthetic_temporal_ready":binaries["ffmpeg"] and binaries["ffprobe"],
            "free_bytes":{"repository_volume":shutil.disk_usage(ROOT).free,
                          "temporary_volume":shutil.disk_usage(tempfile.gettempdir()).free},
            "asr_checkpoint_verified":False,"vlm_checkpoint_verified":False,
            "asr_evaluated":False,"vlm_evaluated":False,
            "real_media_processing_allowed":False,
            "instagram_media_policy":decide("instagram_media",Operation.PROCESS_MEDIA.value).code,
            "youtube_media_policy":decide("youtube_media",Operation.PROCESS_MEDIA.value).code,
            "external_data_accessed":False,"database_mutated":False,"scientific_admissions":0}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-ready",action="store_true")
    mode.add_argument("--synthetic-temporal",action="store_true")
    mode.add_argument("--synthetic-asr",action="store_true")
    mode.add_argument("--synthetic-ocr",action="store_true")
    mode.add_argument("--synthetic-ocr-consensus",action="store_true")
    mode.add_argument("--synthetic-vad",action="store_true")
    mode.add_argument("--synthetic-vad-asr",action="store_true")
    mode.add_argument("--synthetic-shared-multimodal",action="store_true")
    p.add_argument("--tessdata-dir",type=Path,help="Local OCR language files only")
    p.add_argument("--model-dir",type=Path,help="Pinned local ASR checkpoint directory only")
    p.add_argument("--asr-candidate",choices=("small","medium"),default="small")
    p.add_argument("--asr-suite",choices=("baseline","challenge","guarded"),default="baseline")
    p.add_argument("--report-name")
    a=p.parse_args(argv)
    stage="arguments"
    try:
        from tapi_gate0.multimodal_asr import ASRError,verify_checkpoint,run_asr_fixture_benchmark
        from tapi_gate0.multimodal_ocr import OCRError,verify_tessdata,run_ocr_fixture_benchmark
        from tapi_gate0.multimodal_ocr_consensus import run_ocr_consensus_benchmark
        from tapi_gate0.multimodal_vad import VADError,run_vad_fixture_benchmark
        from tapi_gate0.multimodal_vad_asr import run_vad_asr_benchmark
        from tapi_gate0.multimodal_fusion import FusionError
        from tapi_gate0.multimodal_shared_fixture import run_shared_fixture_benchmark
        if a.synthetic_shared_multimodal and (a.asr_candidate!="medium" or a.asr_suite!="baseline"):
            raise FusionError("FUSION_MEDIUM_REQUIRED")
        if a.synthetic_vad_asr and (a.asr_candidate!="medium" or a.asr_suite!="baseline"):
            raise ASRError("ASR_VAD_MEDIUM_REQUIRED")
        if a.tessdata_dir and not (a.check_ready or a.synthetic_ocr or a.synthetic_ocr_consensus or a.synthetic_shared_multimodal):
            raise OCRError("OCR_MODE_REQUIRED")
        if (a.asr_candidate!="small" or a.asr_suite!="baseline") and not (a.synthetic_asr or a.synthetic_vad_asr or a.synthetic_shared_multimodal or (a.check_ready and a.model_dir and a.asr_suite=="baseline")):
            raise ASRError("ASR_MODEL_MODE_REQUIRED")
        if a.model_dir and not (a.check_ready or a.synthetic_asr or a.synthetic_vad_asr or a.synthetic_shared_multimodal):
            raise ASRError("ASR_MODEL_MODE_REQUIRED")
        if a.check_ready:
            if a.report_name:
                raise TemporalError("TEMPORAL_REPORT_MODE_REQUIRED")
            stage="readiness"
            result=readiness()
            if a.model_dir:
                stage="checkpoint_preflight"
                result["asr_checkpoint"]=verify_checkpoint(a.model_dir,a.asr_candidate)
                result["free_bytes"]["model_volume"]=shutil.disk_usage(a.model_dir).free
                result["asr_checkpoint_verified"]=True  # published weight digest, not all companion hashes
            if a.tessdata_dir:
                result["ocr_language_data_sha256"]=verify_tessdata(a.tessdata_dir)
                result["ocr_language_data_independently_verified"]=False
            print(json.dumps(result))
            return 0
        if not decide("synthetic_local",Operation.EVALUATE_SYNTHETIC.value).permitted:
            raise TemporalError("TEMPORAL_SYNTHETIC_POLICY_DENIED")
        if not a.report_name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json",a.report_name):
            raise TemporalError("TEMPORAL_PRIVATE_REPORT_NAME_REQUIRED")
        stage="report_storage_preflight"
        private=ROOT/"artifacts"/"private"
        if private.resolve()!=private.absolute():
            raise TemporalError("TEMPORAL_PRIVATE_ROOT_REDIRECTED")
        private.mkdir(mode=0o700,parents=True,exist_ok=True)
        if shutil.disk_usage(private).free<64*1024*1024:
            raise TemporalError("TEMPORAL_REPORT_STORAGE_INSUFFICIENT")
        target=private/a.report_name
        if target.exists() or target.is_symlink():
            raise TemporalError("TEMPORAL_PRIVATE_REPORT_EXISTS")
        stage="benchmark"
        if a.synthetic_asr:
            if a.model_dir is None:
                raise ASRError("ASR_LOCAL_MODEL_DIRECTORY_REQUIRED")
            if a.asr_candidate=="small" and a.asr_suite=="baseline":
                report=run_asr_fixture_benchmark(a.model_dir)
            else:
                report=run_asr_fixture_benchmark(a.model_dir,candidate=a.asr_candidate,suite=a.asr_suite)
        elif a.synthetic_ocr:
            if a.tessdata_dir is None:
                raise OCRError("OCR_LOCAL_TESSDATA_REQUIRED")
            report=run_ocr_fixture_benchmark(a.tessdata_dir)
        elif a.synthetic_ocr_consensus:
            if a.tessdata_dir is None:
                raise OCRError("OCR_LOCAL_TESSDATA_REQUIRED")
            report=run_ocr_consensus_benchmark(a.tessdata_dir)
        elif a.synthetic_vad:
            report=run_vad_fixture_benchmark()
        elif a.synthetic_vad_asr:
            if a.model_dir is None:
                raise ASRError("ASR_LOCAL_MODEL_DIRECTORY_REQUIRED")
            report=run_vad_asr_benchmark(a.model_dir)
        elif a.synthetic_shared_multimodal:
            if a.model_dir is None or a.tessdata_dir is None:
                raise FusionError("FUSION_LOCAL_MODELS_REQUIRED")
            report=run_shared_fixture_benchmark(a.model_dir,a.tessdata_dir)
        else:
            report=run_temporal_fixture_benchmark()
        stage="report_write"
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(report,stream,ensure_ascii=False,indent=2)
        stage="summary"
        summary={k:v for k,v in report.items() if k!="cases"}
        if a.synthetic_asr:
            summary["case_summary"]=[{**{k:r[k] for k in ("case_id","reference_words","hypothesis_words","word_errors","wer","duration_s","inference_ms","real_time_factor")},
                                      **{k:r[k] for k in ("inference_attempted","abstention_reason") if k in r}} for r in report["cases"]]
        elif a.synthetic_ocr:
            summary["case_summary"]=[{k:r[k] for k in ("case_id","reference_words","hypothesis_words","word_errors","wer","cer","inference_ms")} for r in report["cases"]]
        elif a.synthetic_ocr_consensus:
            summary["case_summary"]=[{k:r[k] for k in ("suite","case_id","reference_words","hypothesis_words","word_errors","wer","cer","primary_word_count","supporting_word_count","accepted_word_count","discarded_primary_word_count","observation_status","abstention_reason","inference_ms")} for r in report["cases"]]
        elif a.synthetic_vad_asr:
            summary["case_summary"]=[{**{k:r[k] for k in ("case_id","reference_words","hypothesis_words","word_errors","wer","duration_s","asr_calls","inference_attempted","abstention_reason","asr_inference_ms","vad_inference_ms","real_time_factor")},
                                      "vad_passed":r["vad_score"]["passed"],"vad_iou":r["vad_score"]["iou"],"segments_count":len(r["segments"])} for r in report["cases"]]
        elif a.synthetic_shared_multimodal:
            summary["case_summary"]=[{"case_id":r["case_id"],"expected":r["expected"],
                                      "all_candidates":{k:r["arms"]["all"][k]["value"] for k in r["expected"]},
                                      "temporal_passed":r["temporal_passed"],"asr_calls":r["audio"]["asr_calls"],
                                      "ocr_frames":len(r["ocr_frames"]),"fragment_count":len(r["fragments"])}
                                     for r in report["cases"]]
        elif a.synthetic_vad:
            summary["case_summary"]=[{k:r[k] for k in ("case_id","passed","expected_speech_s","detected_speech_s","iou","max_boundary_error_s","false_positive_s","missed_speech_s","inference_ms")} for r in report["cases"]]
        else:
            summary["case_summary"]=[{"case_id":r["case_id"],"passed":r["passed"],
                                   "expected_transitions_s":r["expected_transitions_s"],
                                   "observed_transitions_s":[t["sample_time_s"] for t in r["observation"]["transition_candidates"]],
                                   "duration_s":r["observation"]["duration_s"],
                                   "samples":r["observation"]["samples"],
                                   "audio_stream_present":r["observation"]["audio_stream_present"],
                                   "audio_measurement_passed":r["audio_measurement_passed"],
                                   "audio_duration_s":r["observation"]["audio_measurements"]["duration_s"]
                                       if r["observation"]["audio_measurements"] else None}
                                  for r in report["cases"]]
        print(json.dumps({**summary,"report_name":a.report_name}))
        return 0 if report["engineering_gate_passed"] else 2
    except Exception as exc:
        code=exc.args[0] if isinstance(exc,(TemporalError,ASRError,OCRError,VADError,FusionError)) and exc.args and re.fullmatch(r"(?:TEMPORAL|ASR|OCR|VAD|FUSION)_[A-Z_]+",str(exc.args[0])) else ("FUSION_LOCAL_ERROR" if a.synthetic_shared_multimodal else "ASR_LOCAL_ERROR" if (a.synthetic_asr or a.synthetic_vad_asr) else "OCR_LOCAL_ERROR" if (a.synthetic_ocr or a.synthetic_ocr_consensus) else "VAD_LOCAL_ERROR" if a.synthetic_vad else "TEMPORAL_LOCAL_ERROR")
        diagnostic_stage=getattr(exc,"stage",stage)
        diagnostic_type=getattr(exc,"exception_type",type(exc).__name__)
        diagnostic_case=getattr(exc,"case_id",None)
        # Only code-owned identifiers; never emit exception text, paths or input data.
        safe=lambda value: value if isinstance(value,str) and re.fullmatch(r"[A-Za-z0-9_]{1,80}",value) else None
        print(json.dumps({"status":"BLOCKED","code":code,"stage":safe(diagnostic_stage),
                          "exception_type":safe(diagnostic_type),"case_id":safe(diagnostic_case),"synthetic_only":True,
                          "real_media_processed":0,"external_data_accessed":False,
                          "database_mutated":False,"scientific_admissions":0}))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
