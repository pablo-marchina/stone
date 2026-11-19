"""Summarize local synthetic pytest rows; never runs or authorizes jobs."""
import argparse
import json
from pathlib import Path
from tapi_gate0.asset_shared_av_routing import summarize

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--log",required=True,type=Path)
    args=parser.parse_args()
    if not args.log.is_file() or args.log.is_symlink() or args.log.stat().st_size>4_000_000:
        raise ValueError("ROUTING_LOG_INVALID")
    rows=[]
    for line in args.log.read_text(encoding="utf-8-sig").splitlines():
        if "SHARED_AV_ROUTING " in line:
            rows.append(json.loads(line.split("SHARED_AV_ROUTING ",1)[1]))
    print(json.dumps(summarize(rows),ensure_ascii=True,sort_keys=True))

if __name__=="__main__":
    main()
