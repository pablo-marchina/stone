"""Offline GLiNER evaluation on the seven saved authored multimodal fixtures."""
import argparse
import json
import os
from hashlib import sha256
from pathlib import Path
import re
import shutil
from time import perf_counter
from importlib.metadata import version

from tapi_gate0 import multimodal_semantic_replay as replay
from tapi_gate0.policy import Operation,decide

ROOT=Path(__file__).resolve().parents[1]


def local_report(root,name,*,existing):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json",name):
        raise ValueError("PRIVATE_REPORT_NAME_REQUIRED")
    private=root/"artifacts"/"private"
    if private.resolve()!=private.absolute():
        raise ValueError("PRIVATE_REPORT_ROOT_REDIRECTED")
    private.mkdir(mode=0o700,parents=True,exist_ok=True)
    p=private/name
    if p.is_symlink() or (existing and not p.is_file()) or (not existing and p.exists()):
        raise ValueError("PRIVATE_REPORT_PATH_INVALID")
    return p


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-name",required=True)
    parser.add_argument("--report-name",required=True)
    parser.add_argument("--model-dir",required=True,type=Path)
    args=parser.parse_args(argv)
    stage="policy"
    try:
        if not decide("synthetic_local",Operation.EVALUATE_SYNTHETIC.value).permitted:
            raise ValueError("SYNTHETIC_POLICY_DENIED")
        stage="report_validation"
        source=local_report(ROOT,args.input_name,existing=True)
        target=local_report(ROOT,args.report_name,existing=False)
        if not 0<source.stat().st_size<=replay.MAX_REPORT_BYTES:
            raise ValueError("PRIVATE_REPORT_SIZE_INVALID")
        raw=source.read_bytes()
        if len(raw)>replay.MAX_REPORT_BYTES:
            raise ValueError("PRIVATE_REPORT_SIZE_INVALID")
        report=json.loads(raw)
        replay.validate_report(report)
        if shutil.disk_usage(target.parent).free<64*1024*1024:
            raise ValueError("PRIVATE_REPORT_STORAGE_INSUFFICIENT")
        os.environ.update(HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",
                          HF_DATASETS_OFFLINE="1",HF_HUB_DISABLE_TELEMETRY="1")
        stage="checkpoint"
        from scripts.prepare_gliner25_local_checkpoint import validate_local_checkpoint,_not_inside_project
        path=args.model_dir
        if not path.is_absolute() or path.resolve()!=path.absolute():
            raise ValueError("LOCAL_CHECKPOINT_PATH_INVALID")
        _not_inside_project(path)
        checkpoint=validate_local_checkpoint(path)
        if (not checkpoint["manifest_present"] or checkpoint["revision"]!=replay.MODEL_REVISION
                or checkpoint["files"]["model.safetensors"]["sha256"]!=replay.MODEL_WEIGHTS):
            raise ValueError("PINNED_GLINER_CHECKPOINT_REQUIRED")
        stage="model_load"
        import torch
        from tapi_gate0.system_one_e1 import LocalGLiNERDecider
        with torch.inference_mode():
            t=perf_counter()
            extractor=LocalGLiNERDecider(path)._load()
            load_ms=round((perf_counter()-t)*1000,3)
            stage="semantic_replay"
            output=replay.replay(report,extractor)
        stage="postflight"
        if validate_local_checkpoint(path)!=checkpoint or source.read_bytes()!=raw:
            raise ValueError("REPLAY_INPUT_CHANGED")
        output.update(source_report_sha256=sha256(raw).hexdigest(),model_revision=replay.MODEL_REVISION,
                      model_weights_sha256=replay.MODEL_WEIGHTS,model_load_ms=load_ms,
                      runtime_versions={n:version(n) for n in ("torch","gliner2","transformers","safetensors")})
        stage="report_write"
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(output,stream,ensure_ascii=False,indent=2)
        summary={k:v for k,v in output.items() if k!="cases"}
        summary["case_summary"]=[{"case_id":r["case_id"],"audio_diagnostic":r["audio_diagnostic"],
            "all_candidates":{variant:{field:arms["all"][field]["value"] for field in r["expected"]}
                              for variant,arms in r["variants"].items()},
            "audio_cta_diagnostics":[{"rule":p["rule"]["rule_value"],"rule_reason":p["rule"]["reason"],
                "pt":p["pt"],"en":p["en"]} for p in r["fragment_predictions"]["tipo_cta"] if p["modality"]=="audio"]}
            for r in output["cases"]]
        print(json.dumps({**summary,"report_name":args.report_name}))
        return 0 if output["engineering_gate_passed"] else 2
    except Exception as exc:
        code=str(exc.args[0]) if exc.args and re.fullmatch(r"[A-Z_]{3,100}",str(exc.args[0])) else "SEMANTIC_REPLAY_BLOCKED"
        print(json.dumps({"status":"BLOCKED","code":code,"stage":stage,"exception_type":type(exc).__name__,
                          "synthetic_only":True,"real_media_processed":0,"database_mutated":False,
                          "scientific_admissions":0}))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
