"""Private synthetic-only four-modality evidence report replay."""
import argparse
import json
import os
from hashlib import sha256
from pathlib import Path
import re
import shutil

from tapi_gate0 import multimodal_evidence_replay as replay
from tapi_gate0.policy import Operation,decide
from scripts.a6_semantic_replay import local_report

ROOT=Path(__file__).resolve().parents[1]
MAX_BYTES=8_000_000


def read_report(name):
    path=local_report(ROOT,name,existing=True)
    if not 0<path.stat().st_size<=MAX_BYTES:
        raise ValueError("EVIDENCE_PRIVATE_REPORT_SIZE_INVALID")
    raw=path.read_bytes()
    if not 0<len(raw)<=MAX_BYTES:
        raise ValueError("EVIDENCE_PRIVATE_REPORT_SIZE_INVALID")
    report=json.loads(raw)
    if not isinstance(report,dict):
        raise ValueError("EVIDENCE_PRIVATE_REPORT_INVALID")
    return path,raw,report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared-name",required=True)
    parser.add_argument("--vlm-name",required=True)
    parser.add_argument("--report-name",required=True)
    a=parser.parse_args(argv)
    stage="policy"
    try:
        if not decide("synthetic_local",Operation.EVALUATE_SYNTHETIC.value).permitted:
            raise ValueError("EVIDENCE_SYNTHETIC_POLICY_DENIED")
        stage="input"
        target=local_report(ROOT,a.report_name,existing=False)
        shared,raw,report=read_report(a.shared_name)
        vlm,visual_raw,visual_report=read_report(a.vlm_name)
        if shared==vlm:
            raise ValueError("EVIDENCE_DISTINCT_INPUTS_REQUIRED")
        if shutil.disk_usage(target.parent).free<64*1024*1024:
            raise ValueError("EVIDENCE_REPORT_STORAGE_INSUFFICIENT")
        stage="composition"
        digest=sha256(raw).hexdigest()
        result=replay.run(report,visual_report,digest)
        if shared.read_bytes()!=raw or vlm.read_bytes()!=visual_raw:
            raise ValueError("EVIDENCE_INPUT_CHANGED")
        result.update(source_report_sha256=digest,visual_report_sha256=sha256(visual_raw).hexdigest())
        stage="report_write"
        encoded=json.dumps(result,ensure_ascii=False,indent=2).encode("utf-8")
        if len(encoded)>MAX_BYTES:
            raise ValueError("EVIDENCE_OUTPUT_SIZE_INVALID")
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as stream:
            stream.write(encoded)
        summary={k:v for k,v in result.items() if k not in ("cases","ablation")}
        summary["arm_summary"]={arm:{f:{"correct":m["correct_candidates"],"expected":m["expected_candidates"],
                                        "wrong":m["wrong_nonabstained"],"recall":m["candidate_recall"]}
                                    for f,m in fields.items()} for arm,fields in result["ablation"].items()}
        summary["case_summary"]=[{"case_id":r["case_id"],"expected":r["expected"],
            "candidates":{f:x["value"] for f,x in r["field_evidence"].items() if x["state"]=="candidate"},
            "state_counts":dict(__import__("collections").Counter(x["state"] for x in r["field_evidence"].values()))}
            for r in result["cases"]]
        print(json.dumps({**summary,"report_name":a.report_name}))
        return 0 if result["engineering_gate_passed"] else 2
    except Exception as exc:
        code=str(exc.args[0]) if exc.args and re.fullmatch(r"[A-Z_]{3,100}",str(exc.args[0])) else "EVIDENCE_REPLAY_BLOCKED"
        print(json.dumps({"status":"BLOCKED","code":code,"stage":stage,"exception_type":type(exc).__name__,
            "synthetic_only":True,"real_media_processed":0,"external_data_accessed":False,
            "database_mutated":False,"scientific_admissions":0}))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
