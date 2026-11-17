"""Resource plan and private synthetic-only Qwen3-VL benchmark."""
import argparse
import json
import os
from hashlib import sha256
from pathlib import Path
import re
import shutil

from tapi_gate0 import multimodal_vlm as vlm
from tapi_gate0 import multimodal_semantic_replay as replay
from tapi_gate0.policy import Operation,decide
from scripts.a6_semantic_replay import local_report

ROOT=Path(__file__).resolve().parents[1]


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan",action="store_true")
    mode.add_argument("--verify",action="store_true")
    mode.add_argument("--benchmark",action="store_true")
    mode.add_argument("--single-scene",action="store_true")
    p.add_argument("--model-dir",required=True,type=Path)
    p.add_argument("--server-exe",type=Path)
    p.add_argument("--input-name")
    p.add_argument("--report-name")
    a=p.parse_args(argv)
    stage="policy"
    try:
        if not decide("synthetic_local",Operation.EVALUATE_SYNTHETIC.value).permitted:
            raise vlm.VLMError("VLM_SYNTHETIC_POLICY_DENIED")
        stage="resource_preflight"
        capacity=vlm.plan(a.model_dir)
        if a.plan:
            if a.input_name or a.report_name or a.server_exe:
                raise vlm.VLMError("VLM_PLAN_ARGUMENTS_INVALID")
            print(json.dumps(capacity))
            return 0 if capacity["provision_disk_ready"] and capacity["run_memory_ready"] else 2
        if a.server_exe is None:
            raise vlm.VLMError("VLM_LOCAL_SERVER_REQUIRED")
        if a.verify:
            if a.input_name or a.report_name:
                raise vlm.VLMError("VLM_VERIFY_ARGUMENTS_INVALID")
            stage="checkpoint_runtime"
            print(json.dumps({**capacity,"status":"VLM_CHECKPOINT_RUNTIME_VERIFIED",
                              "checkpoint_verified":True,"checkpoint":vlm.verify_checkpoint(a.model_dir),
                              "runtime":vlm.verify_runtime(a.server_exe)}))
            return 0
        if not a.input_name or not a.report_name:
            raise vlm.VLMError("VLM_PRIVATE_REPORT_REQUIRED")
        if not capacity["run_memory_ready"] or not capacity["run_disk_ready"]:
            print(json.dumps({**capacity,"status":"BLOCKED","code":"VLM_RESOURCE_PREFLIGHT_BLOCKED"}))
            return 2
        stage="report_validation"
        source=local_report(ROOT,a.input_name,existing=True)
        target=local_report(ROOT,a.report_name,existing=False)
        if not 0<source.stat().st_size<=replay.MAX_REPORT_BYTES:
            raise vlm.VLMError("VLM_PRIVATE_REPORT_SIZE_INVALID")
        raw=source.read_bytes()
        if len(raw)>replay.MAX_REPORT_BYTES:
            raise vlm.VLMError("VLM_PRIVATE_REPORT_SIZE_INVALID")
        report=json.loads(raw)
        replay.validate_report(report)
        if shutil.disk_usage(target.parent).free<vlm.MIN_RUN_DISK:
            raise vlm.VLMError("VLM_REPORT_VOLUME_INSUFFICIENT")
        stage="benchmark"
        if a.single_scene:
            from tapi_gate0.multimodal_vlm_single_scene import benchmark
            result=benchmark(report,a.model_dir,a.server_exe)
        else:
            result=vlm.benchmark(report,a.model_dir,a.server_exe)
        if source.read_bytes()!=raw:
            raise vlm.VLMError("VLM_INPUT_REPORT_CHANGED")
        result["source_report_sha256"]=sha256(raw).hexdigest()
        stage="report_write"
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(result,stream,ensure_ascii=False,indent=2)
        print(json.dumps({**{k:v for k,v in result.items() if k!="cases"},
            "case_summary":[{**{k:r[k] for k in ("case_id","suite","expected","prediction","inference_ms","reused_identical_image_result")},
                             **{k:r[k] for k in ("model_scene","inference_attempted","guard_reason") if k in r}} for r in result["cases"]],
            "report_name":a.report_name}))
        return 0 if result["engineering_gate_passed"] else 2
    except Exception as exc:
        code=str(exc.args[0]) if exc.args and re.fullmatch(r"[A-Z_]{3,100}",str(exc.args[0])) else "VLM_LOCAL_ERROR"
        print(json.dumps({"status":"BLOCKED","code":code,"stage":stage,"exception_type":type(exc).__name__,
                          "synthetic_only":True,"real_media_processed":0,"external_data_accessed":False,
                          "database_mutated":False,"scientific_admissions":0}))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
