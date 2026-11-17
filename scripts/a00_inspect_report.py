"""A00.2: inspect saved baseline failure identities, without rerunning tests."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from scripts.a00_baseline import ROOT, BaselineError, junit_counts

LIMIT=32*1024*1024


def checked_file(directory,name):
    p=directory/name
    if p.is_symlink() or p.resolve()!=p.absolute() or not p.is_file():
        raise BaselineError("A00_REPORT_FILE_INVALID")
    if not 0<p.stat().st_size<=LIMIT:
        raise BaselineError("A00_REPORT_SIZE_INVALID")
    return p


def inspect_report(root,name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,90}",name):
        raise BaselineError("A00_REPORT_NAME_INVALID")
    directory=root/"artifacts"/"private"/name
    if directory.resolve()!=directory.absolute() or not directory.is_dir():
        raise BaselineError("A00_REPORT_DIRECTORY_INVALID")
    raw=checked_file(directory,"summary.json").read_bytes()
    report=json.loads(raw)
    if report.get("policy_version")!="a00-local-baseline.v1" or report.get("profile") not in ("full","semantic"):
        raise BaselineError("A00_REPORT_POLICY_INVALID")
    commit=report["inventory"]["commit"]
    tree=report["inventory"]["tree"]
    if not all(re.fullmatch(r"[a-f0-9]{40}",v) for v in (commit,tree)):
        raise BaselineError("A00_REPORT_COMMIT_INVALID")
    steps=report["steps"]
    expected={"legacy_gate0","zero_spend","pytest"}|({"node"} if report["profile"]=="full" else set())
    if len(steps)!=len(expected) or {s["step"] for s in steps}!=expected:
        raise BaselineError("A00_REPORT_STEPS_INVALID")
    for s in steps:
        filename=s["step"]+".log"
        if s["log"]!=filename or sha256(checked_file(directory,filename).read_bytes()).hexdigest()!=s["log_sha256"]:
            raise BaselineError("A00_REPORT_LOG_HASH_MISMATCH")
    xml=checked_file(directory,"pytest.xml")
    xml_hash=sha256(xml.read_bytes()).hexdigest()
    if "pytest_xml_sha256" in report and report["pytest_xml_sha256"]!=xml_hash:
        raise BaselineError("A00_REPORT_XML_HASH_MISMATCH")
    counts=junit_counts(xml)
    old=report["pytest"]
    required={"tests","passed","failed","errors","skipped","skipped_tests"}
    if not isinstance(old,dict) or not required<=set(old) or not set(old)<=required|{"failed_tests"}:
        raise BaselineError("A00_REPORT_COUNTS_INVALID")
    for k,v in old.items():
        if counts.get(k)!=v:
            raise BaselineError("A00_REPORT_COUNTS_MISMATCH")
    # Test identities are public source identifiers, but parameterized names
    # may include arbitrary values: bound their size, do not emit tracebacks.
    identities=[]
    for f in counts["failed_tests"]:
        identities.append({"class":f["class"][:200],"name":f["name"][:200],"kind":f["kind"]})
    return {"status":"A00_REPORT_INSPECTED","profile":report["profile"],"commit":commit,
            "tree":tree,"report_name":name,"summary_sha256":sha256(raw).hexdigest(),
            "pytest_xml_sha256":xml_hash,
            "xml_digest_previously_recorded":"pytest_xml_sha256" in report,
            "logs_match_recorded_digests":True,
            "counts":{k:counts[k] for k in ("tests","passed","failed","errors","skipped")},
            "failed_tests":identities,"skipped_tests":counts["skipped_tests"],
            "checks_passed":report["checks_passed"],"tests_rerun":False,
            "database_mutated":False,"independent_attestation":False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report-name",required=True)
    a=p.parse_args(argv)
    try:
        print(json.dumps(inspect_report(ROOT,a.report_name),ensure_ascii=False))
        return 0
    except (BaselineError,OSError,ValueError,KeyError,TypeError,ET.ParseError) as exc:
        print(json.dumps({"status":"BLOCKED","code":str(exc) if isinstance(exc,BaselineError) else "A00_REPORT_INVALID","exception_type":type(exc).__name__}))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
