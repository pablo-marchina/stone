"""Run the fixed authored ASR recovery comparison with local pinned models."""
import argparse
import json
import sys
from tapi_gate0.asset_asr_recovery import run

def progress(event):
    # stdout remains one final JSON report, stderr contains only fixed IDs.
    print("ASR_RECOVERY_PROGRESS "+json.dumps(event,sort_keys=True),file=sys.stderr,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--model-dir",required=True)
    parser.add_argument("--round",choices=("v1","v2","v3"),default="v2")
    parser.add_argument("--small-model-dir")
    args=parser.parse_args()
    print(json.dumps(run(args.model_dir,round_id=args.round,progress=progress,small_model_dir=args.small_model_dir),ensure_ascii=False,sort_keys=True,allow_nan=False))
