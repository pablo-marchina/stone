"""A00.1: reproducible local baseline inventory and regression, without live DB.

No fetch, install, migration, model benchmark, API call or merge is performed.
Runs the existing test suite with a reduced child environment; this is not an
OS network sandbox. Reports are private and never overwrite existing files.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
MATRICES=Path("planning/v5_2/audit_2026-11-05/synced")
EXPECTED={
    "BACKLOG_UNICO_IMPORTAVEL.csv":("id",204),
    "MATRIZ_CAPACIDADES.csv":("feature_id",23),
    "MATRIZ_DECISOES.csv":("decision_id",18),
    "MATRIZ_GATE_GLOBAL.csv":("gate_id",7),
    "DEPENDENCIAS.csv":(None,543),
}
SEMANTIC_TESTS=(
    "tests/test_system_one_e1.py",
    "tests/test_contextual_diagnostics.py",
    "tests/test_discovery_audience_contextual.py",
    "tests/test_discovery_audience_grounded.py",
    "tests/test_discovery_rubric_benchmark.py",
    "tests/test_discovery_rubric_grounded.py",
    "tests/test_multimodal_semantic_replay.py",
    "tests/test_multimodal_cta_challenge.py",
    "tests/test_multimodal_cta_directed.py",
)
ENV_KEYS={"PATH","SYSTEMROOT","WINDIR","COMSPEC","PATHEXT","TEMP","TMP","TMPDIR",
          "USERPROFILE","HOME","HOMEDRIVE","HOMEPATH","APPDATA","LOCALAPPDATA",
          "PROGRAMDATA","PROGRAMFILES","PROGRAMFILES(X86)","COMMONPROGRAMFILES",
          "PROCESSOR_ARCHITECTURE","NUMBER_OF_PROCESSORS","OS","LANG","LC_ALL",
          "CONDA_PREFIX","CONDA_DEFAULT_ENV","CONDA_SHLVL","LD_LIBRARY_PATH",
          "ESPEAK_DATA_PATH"}
PACKAGES=("pytest","fastapi","starlette","pydantic","sqlalchemy","alembic","httpx",
          "numpy","opencv-python-headless","Pillow","faster-whisper","ctranslate2",
          "onnxruntime","torch","gliner2","transformers","safetensors","cryptography")


class BaselineError(ValueError):
    pass


def child_environment(root,source):
    env={k:v for k,v in source.items() if k.upper() in ENV_KEYS}
    env.update(PYTHONPATH=str(root/"src"),PYTHONUTF8="1",PYTHONDONTWRITEBYTECODE="1",
               HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",HF_DATASETS_OFFLINE="1",
               HF_HUB_DISABLE_TELEMETRY="1",HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
               GIT_TERMINAL_PROMPT="0",GIT_OPTIONAL_LOCKS="0")
    return env


def git(root,*args):
    result=subprocess.run(["git","-C",str(root),*args],capture_output=True,check=True,
        env=child_environment(root,os.environ),timeout=30)
    return result.stdout.decode("utf-8",errors="strict").strip()


def check_checkout(root,expected):
    if not re.fullmatch(r"[0-9a-f]{40}",expected):
        raise BaselineError("BASELINE_FULL_COMMIT_REQUIRED")
    if git(root,"rev-parse","HEAD")!=expected:
        raise BaselineError("BASELINE_HEAD_MISMATCH")
    if git(root,"status","--porcelain=v1","--untracked-files=normal"):
        raise BaselineError("BASELINE_DIRTY_CHECKOUT")


def read_matrices(root):
    tables={}
    summaries={}
    for name,(key,n) in EXPECTED.items():
        raw=(root/MATRICES/name).read_bytes()
        import io
        rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        if len(rows)!=n or any(None in row or any(v is None for v in row.values()) for row in rows):
            raise BaselineError("BASELINE_MATRIX_COUNT_OR_SHAPE")
        if key and (len({row[key] for row in rows})!=n or any(not row[key] for row in rows)):
            raise BaselineError("BASELINE_MATRIX_ID_INVALID")
        tables[name]=rows
        summaries[name]={"rows":n,"sha256":sha256(raw).hexdigest()}
    tasks={r["id"]:r for r in tables["BACKLOG_UNICO_IMPORTAVEL.csv"]}
    caps={r["feature_id"] for r in tables["MATRIZ_CAPACIDADES.csv"]}
    decisions={r["decision_id"] for r in tables["MATRIZ_DECISOES.csv"]}
    gates={r["gate_id"] for r in tables["MATRIZ_GATE_GLOBAL.csv"]}
    if (set(tasks)!={f"IMP-{i:03d}" for i in range(1,205)}
            or caps!={f"CAP-{i:03d}" for i in range(1,24)}
            or decisions!={f"DEC-{i:03d}" for i in range(1,19)}):
        raise BaselineError("BASELINE_MATRIX_ID_SET_INVALID")
    if tasks["IMP-062"]["status"]!="DISPENSADO_POR_DEC018_DECLARADA_NAO_CUMPRIDO":
        raise BaselineError("BASELINE_DEC018_MISMATCH")
    edges=[(r["predecessor"],r["successor"]) for r in tables["DEPENDENCIAS.csv"]]
    if len(set(edges))!=len(edges) or any(a not in tasks or b not in tasks or a==b for a,b in edges):
        raise BaselineError("BASELINE_DEPENDENCY_INVALID")
    children=defaultdict(list)
    indegree=dict.fromkeys(tasks,0)
    for a,b in edges:
        children[a].append(b)
        indegree[b]+=1
    todo=[k for k,v in indegree.items() if v==0]
    visited=0
    while todo:
        a=todo.pop()
        visited+=1
        for b in children[a]:
            indegree[b]-=1
            if indegree[b]==0:
                todo.append(b)
    if visited!=len(tasks):
        raise BaselineError("BASELINE_DEPENDENCY_CYCLE")
    for row in tasks.values():
        for column,allowed in (("capability_ids",caps),("decision_ids",decisions),("gates",gates),("dependencies",set(tasks))):
            if not set(filter(None,row[column].split(";")))<=allowed:
                raise BaselineError("BASELINE_TASK_REFERENCE_INVALID")
    raw=(root/"planning/action_2026-11-17/phase_map.json").read_bytes()
    overlay=json.loads(raw)
    phases=overlay["phases"]
    if (overlay.get("kind")!="execution_overlay_not_acceptance"
            or set(phases)!={f"A{i:02d}" for i in range(12)}
            or any(not isinstance(ids,list) or not ids for ids in phases.values())):
        raise BaselineError("BASELINE_PHASE_MAP_INVALID")
    assigned=[task for ids in phases.values() for task in ids]
    if len(assigned)!=len(tasks) or set(assigned)!=set(tasks):
        raise BaselineError("BASELINE_PHASE_PARTITION_INVALID")
    return {"matrices":summaries,"dependency_dag_acyclic":True,
            "phase_map_sha256":sha256(raw).hexdigest(),
            "phase_task_counts":{k:len(v) for k,v in sorted(phases.items())},
            "historical_task_status_counts":dict(Counter(r["status"] for r in tasks.values())),
            "imp062_status":tasks["IMP-062"]["status"],"independent_human_review_completed":False,
            "matrix_statuses_are_historical_not_current_certification":True}


def inventory(root,expected):
    check_checkout(root,expected)
    tracked=git(root,"ls-files","-z").split("\0")
    paths=[p for p in tracked if p]
    modules=[p for p in paths if p.startswith("src/tapi_gate0/") and p.endswith(".py")]
    python_tests=[p for p in paths if p.startswith("tests/") and Path(p).name.startswith("test_") and p.endswith(".py")]
    node_tests=[p for p in paths if p.startswith("tests/") and Path(p).name.startswith("test_") and p.endswith(".mjs")]
    migrations=[p for p in paths if p.startswith("migrations/versions/") and p.endswith(".py")]
    return {"commit":expected,"tree":git(root,"rev-parse","HEAD^{tree}"),
        "branch":git(root,"rev-parse","--abbrev-ref","HEAD"),"tracked_files":len(paths),
        "python_modules":sorted(modules),"python_test_files":sorted(python_tests),
        "node_test_files":sorted(node_tests),"migrations":sorted(migrations),
        **read_matrices(root)}


def junit_counts(path):
    if not path.is_file():
        return None
    root=ET.parse(path).getroot()
    cases=list(root.iter("testcase"))
    counts={"tests":len(cases),"passed":0,"failed":0,"errors":0,"skipped":0}
    skipped=[]
    failed=[]
    for c in cases:
        identity={"class":c.get("classname",""),"name":c.get("name","")}
        if c.find("error") is not None:
            counts["errors"]+=1
            failed.append({**identity,"kind":"error"})
        elif c.find("failure") is not None:
            counts["failed"]+=1
            failed.append({**identity,"kind":"failure"})
        elif c.find("skipped") is not None:
            counts["skipped"]+=1
            skipped.append(identity)
        else:
            counts["passed"]+=1
    return {**counts,"skipped_tests":skipped,"failed_tests":failed}


def private_run_dir(root,name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,90}",name) or name in (".",".."):
        raise BaselineError("BASELINE_PRIVATE_NAME_INVALID")
    private=root/"artifacts"/"private"
    if private.resolve()!=private.absolute():
        raise BaselineError("BASELINE_PRIVATE_ROOT_REDIRECTED")
    private.mkdir(parents=True,exist_ok=True)
    target=private/name
    target.mkdir(mode=0o700,exist_ok=False)
    return target


def run_step(root,target,name,command,env,timeout=1800):
    log=target/(name+".log")
    start=datetime.now(timezone.utc)
    with log.open("xb") as stream:
        try:
            proc=subprocess.run(command,cwd=root,env=env,stdin=subprocess.DEVNULL,
                stdout=stream,stderr=subprocess.STDOUT,timeout=timeout,check=False)
            code=proc.returncode
        except subprocess.TimeoutExpired:
            code=124
        except OSError:
            code=127
    return {"step":name,"exit_code":code,"log":log.name,
            "log_sha256":sha256(log.read_bytes()).hexdigest(),
            "seconds":round((datetime.now(timezone.utc)-start).total_seconds(),3)}


def execute(root,expected,profile,name,tessdata=None):
    info=inventory(root,expected)
    env=child_environment(root,os.environ)
    if tessdata is not None:
        p=Path(tessdata)
        if not p.is_absolute() or p.resolve()!=p.absolute() or not p.is_dir():
            raise BaselineError("BASELINE_TESSDATA_PATH_INVALID")
        if any(not (p/(lang+".traineddata")).is_file() or (p/(lang+".traineddata")).is_symlink() for lang in ("por","eng")):
            raise BaselineError("BASELINE_TESSDATA_FILES_REQUIRED")
        env["TAPI_OCR_TEST_TESSDATA"]=str(p)
    if shutil.disk_usage(root).free<128*1024*1024:
        raise BaselineError("BASELINE_STORAGE_INSUFFICIENT")
    if profile=="full" and not info["node_test_files"]:
        raise BaselineError("BASELINE_NODE_TESTS_MISSING")
    target=private_run_dir(root,name)
    packages={}
    for package in PACKAGES:
        try:
            packages[package]=version(package)
        except PackageNotFoundError:
            packages[package]=None
    report={"status":"BASELINE_INVENTORY_COMPLETED" if profile=="inventory" else "BASELINE_REGRESSION_COMPLETED","policy_version":"a00-local-baseline.v1",
            "profile":profile,"inventory":info,"python":sys.version.split()[0],
            "conda_environment":os.environ.get("CONDA_DEFAULT_ENV"),"packages":packages,
            "tools":{k:bool(shutil.which(k)) for k in ("git","node","ffmpeg","ffprobe","tesseract","espeak-ng")},
            "ocr_integration_opt_in":tessdata is not None,"steps":[],
            "operational_database_url_forwarded":False,"external_credential_environment_forwarded":False,
            "network_sandbox":False,"global_gates_released":False,"production_approved":False}
    for step,file in (("legacy_gate0","scripts/check_gate0.py"),("zero_spend","scripts/verify_zero_spend.py")):
        report["steps"].append(run_step(root,target,step,[sys.executable,file],env,timeout=120))
    if profile!="inventory":
        xml=target/"pytest.xml"
        tests=["tests"] if profile=="full" else list(SEMANTIC_TESTS)
        report["steps"].append(run_step(root,target,"pytest",
            [sys.executable,"-m","pytest","-q",*tests,"--junitxml",str(xml)],env))
        try:
            report["pytest"]=junit_counts(xml)
            if xml.is_file():
                report["pytest_xml_sha256"]=sha256(xml.read_bytes()).hexdigest()
        except ET.ParseError:
            report["pytest"]=None
            report["pytest_junit_invalid"]=True
        if profile=="full":
            node_files=info["node_test_files"]
            report["steps"].append(run_step(root,target,"node",["node","--test",*node_files],env))
    try:
        check_checkout(root,expected)
        report["checkout_unchanged"]=True
    except (BaselineError,subprocess.SubprocessError):
        report["checkout_unchanged"]=False
    report["checks_passed"]=report["checkout_unchanged"] and all(s["exit_code"]==0 for s in report["steps"])
    if profile!="inventory":
        report["checks_passed"]=bool(report["checks_passed"] and report["pytest"] and report["pytest"]["passed"]>0
            and report["pytest"]["failed"]==report["pytest"]["errors"]==0)
    report["full_regression_profile_executed"]=profile=="full"
    report["full_regression_without_skips"]=bool(profile=="full" and report["checks_passed"] and report["pytest"]["skipped"]==0)
    report["skips_are_not_passes"]=True
    report["standalone_model_benchmark_commands_invoked"]=False
    report["operational_database_tested"]=False
    with (target/"summary.json").open("x",encoding="utf-8") as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-head",required=True)
    p.add_argument("--profile",required=True,choices=("inventory","full","semantic"))
    p.add_argument("--report-name",required=True)
    p.add_argument("--tessdata-dir",type=Path)
    a=p.parse_args(argv)
    try:
        if a.tessdata_dir is not None and a.profile!="full":
            raise BaselineError("BASELINE_OCR_FULL_PROFILE_REQUIRED")
        result=execute(ROOT,a.expected_head,a.profile,a.report_name,a.tessdata_dir)
        print(json.dumps({k:v for k,v in result.items() if k!="inventory"}|{"commit":result["inventory"]["commit"],
            "tree":result["inventory"]["tree"],"inventory_counts":{k:len(result["inventory"][k]) for k in ("python_modules","python_test_files","node_test_files","migrations")},"matrix_counts":{k:v["rows"] for k,v in result["inventory"]["matrices"].items()},
            "phase_task_counts":result["inventory"]["phase_task_counts"],
            "report_name":a.report_name},ensure_ascii=False))
        return 0 if result["checks_passed"] else 2
    except (BaselineError,FileExistsError,OSError,ValueError,KeyError,subprocess.SubprocessError,ET.ParseError) as exc:
        code=str(exc) if isinstance(exc,BaselineError) else "BASELINE_LOCAL_ERROR"
        print(json.dumps({"status":"BLOCKED","code":code,"exception_type":type(exc).__name__}))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
