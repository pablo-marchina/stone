"""Local synthetic-only temporal benchmark; never accepts social media inputs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil

from tapi_gate0.multimodal_temporal import TemporalError, run_temporal_fixture_benchmark
from tapi_gate0.policy import Operation, decide

ROOT = Path(__file__).resolve().parents[1]


def readiness():
    binaries={name:bool(shutil.which(name)) for name in ("ffmpeg","ffprobe","tesseract","espeak-ng")}
    modules={name:importlib.util.find_spec(name) is not None for name in ("cv2","numpy","faster_whisper","transformers")}
    return {"status":"MULTIMODAL_LOCAL_READINESS","binaries":binaries,"modules":modules,
            "synthetic_temporal_ready":binaries["ffmpeg"] and binaries["ffprobe"],
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
    p.add_argument("--model-dir",type=Path,help="Pinned local ASR checkpoint directory only")
    p.add_argument("--report-name")
    a=p.parse_args(argv)
    try:
        from tapi_gate0.multimodal_asr import ASRError,verify_checkpoint,run_asr_fixture_benchmark
        if a.model_dir and not (a.check_ready or a.synthetic_asr):
            raise ASRError("ASR_MODEL_MODE_REQUIRED")
        if a.check_ready:
            if a.report_name:
                raise TemporalError("TEMPORAL_REPORT_MODE_REQUIRED")
            result=readiness()
            if a.model_dir:
                result["asr_checkpoint"]=verify_checkpoint(a.model_dir)
                result["asr_checkpoint_verified"]=True  # published weight digest, not all companion hashes
            print(json.dumps(result))
            return 0
        if not decide("synthetic_local",Operation.EVALUATE_SYNTHETIC.value).permitted:
            raise TemporalError("TEMPORAL_SYNTHETIC_POLICY_DENIED")
        if not a.report_name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json",a.report_name):
            raise TemporalError("TEMPORAL_PRIVATE_REPORT_NAME_REQUIRED")
        private=ROOT/"artifacts"/"private"
        if private.resolve()!=private.absolute():
            raise TemporalError("TEMPORAL_PRIVATE_ROOT_REDIRECTED")
        private.mkdir(mode=0o700,parents=True,exist_ok=True)
        target=private/a.report_name
        if target.exists() or target.is_symlink():
            raise TemporalError("TEMPORAL_PRIVATE_REPORT_EXISTS")
        if a.synthetic_asr:
            if a.model_dir is None:
                raise ASRError("ASR_LOCAL_MODEL_DIRECTORY_REQUIRED")
            report=run_asr_fixture_benchmark(a.model_dir)
        else:
            report=run_temporal_fixture_benchmark()
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(report,stream,ensure_ascii=False,indent=2)
        summary={k:v for k,v in report.items() if k!="cases"}
        if a.synthetic_asr:
            summary["case_summary"]=[{k:r[k] for k in ("case_id","reference_words","hypothesis_words","word_errors","wer","duration_s","inference_ms","real_time_factor")} for r in report["cases"]]
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
        code=exc.args[0] if isinstance(exc,(TemporalError,ASRError)) and exc.args and re.fullmatch(r"(?:TEMPORAL|ASR)_[A-Z_]+",str(exc.args[0])) else "TEMPORAL_LOCAL_ERROR"
        print(json.dumps({"status":"BLOCKED","code":code,"synthetic_only":True,
                          "real_media_processed":0,"external_data_accessed":False,
                          "database_mutated":False,"scientific_admissions":0}))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
