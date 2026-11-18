"""Run the fixed authored ASR recovery comparison with local pinned models."""
import argparse
import json
from tapi_gate0.asset_asr_recovery import run

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--model-dir",required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.model_dir),ensure_ascii=False,sort_keys=True,allow_nan=False))
