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
import struct
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


# Minimum collected parameterizations, pinned to the approved native suite.
# Missing/duplicate/skipped required cases cannot be called a full multimodal pass.
MULTIMODAL_GROUPS=(
    ("kernel","tests.test_asset_windows_job","test_native_",8),
    ("supervisor","tests.test_asset_rights_registry","test_windows_supervisor_",3),
    ("typed","tests.test_asset_rights_registry","test_typed_fixture_",7),
    ("temporal_decode","tests.test_asset_temporal_fixture","test_real_ffmpeg_",3),
    ("temporal","tests.test_asset_rights_registry","test_real_temporal_",6),
    ("ocr_decode","tests.test_asset_ocr_fixture","test_real_tesseract_",3),
    ("ocr","tests.test_asset_rights_registry","test_real_ocr_",6),
    ("asr","tests.test_asset_rights_registry","test_real_asr_",6),
    ("vlm","tests.test_asset_rights_registry","test_real_vlm_",6),
    ("bundle","tests.test_asset_rights_registry","test_candidate_bundle_real_blank_",1),
    ("maintenance","tests.test_asset_rights_registry","test_maintenance_",9),
    ("fusion","tests.test_asset_rights_registry","test_candidate_fusion_",11),
    ("fixture_pipeline","tests.test_asset_rights_registry","test_fixture_pipeline_",12),
    ("shared_av_contract","tests.test_asset_processor_results","test_shared_av_",4),
    ("shared_av","tests.test_asset_rights_registry","test_shared_av_",19),
)


class BaselineError(ValueError):
    pass


def _local_path(value,*,directory,code):
    p=Path(value)
    if (not p.is_absolute() or p.is_symlink() or p.resolve()!=p.absolute()
            or (not p.is_dir() if directory else not p.is_file())):
        raise BaselineError(code)
    return p


def model_opt_ins(profile,*,tessdata=None,asr_model=None,vlm_model=None,vlm_server=None,
                  require_multimodal=False):
    """Explicit paths only; no ambient opt-ins, downloads, or model loads."""
    values=(tessdata,asr_model,vlm_model,vlm_server)
    if profile!="full" and (any(v is not None for v in values) or require_multimodal):
        raise BaselineError("BASELINE_MODEL_FULL_PROFILE_REQUIRED")
    if (vlm_model is None)!=(vlm_server is None):
        raise BaselineError("BASELINE_VLM_PAIR_REQUIRED")
    if require_multimodal:
        if any(v is None for v in values):
            raise BaselineError("BASELINE_MULTIMODAL_ALL_OPT_INS_REQUIRED")
        if sys.platform!="win32" or struct.calcsize("P")!=8:
            raise BaselineError("BASELINE_MULTIMODAL_WINDOWS_X64_REQUIRED")
    env={}
    def directory(value,files,code):
        p=_local_path(value,directory=True,code=code+"_PATH_INVALID")
        for f in files:
            _local_path(p/f,directory=False,code=code+"_FILES_REQUIRED")
        return p
    if tessdata is not None:
        env["TAPI_OCR_TEST_TESSDATA"]=str(directory(tessdata,("por.traineddata","eng.traineddata"),"BASELINE_TESSDATA"))
    if asr_model is not None:
        env["TAPI_ASR_TEST_MODEL_DIR"]=str(directory(asr_model,("config.json","model.bin","tokenizer.json","vocabulary.txt"),"BASELINE_ASR"))
    if vlm_model is not None:
        env["TAPI_VLM_TEST_MODEL_DIR"]=str(directory(vlm_model,("Qwen3VL-2B-Instruct-Q4_K_M.gguf","mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf"),"BASELINE_VLM"))
        binary=_local_path(vlm_server,directory=False,code="BASELINE_VLM_SERVER_PATH_INVALID")
        if binary.name.lower()!="llama-server.exe":
            raise BaselineError("BASELINE_VLM_SERVER_NAME_INVALID")
        env["TAPI_VLM_TEST_SERVER_EXE"]=str(binary)
    return env


def multimodal_coverage(xml):
    """Verify minimum required case groups from JUnit, not process exit alone."""
    cases=list(ET.parse(xml).getroot().iter("testcase")) if xml.is_file() else []
    result={}
    for group,cls,prefix,minimum in MULTIMODAL_GROUPS:
        matched=[c for c in cases if c.get("classname")==cls and c.get("name","").startswith(prefix)]
        names=[c.get("name") for c in matched]
        passed=sum(all(c.find(k) is None for k in ("failure","error","skipped")) for c in matched)
        result[group]={"minimum":minimum,"collected":len(matched),"passed":passed,
            "passed_required":len(matched)>=minimum and passed==len(matched) and len(names)==len(set(names))}
    return {"groups":result,"all_required_passed":all(g["passed_required"] for g in result.values())}



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


def execute(root,expected,profile,name,tessdata=None,*,asr_model=None,vlm_model=None,
            vlm_server=None,require_multimodal=False):
    info=inventory(root,expected)
    env=child_environment(root,os.environ)
    opt_ins=model_opt_ins(profile,tessdata=tessdata,asr_model=asr_model,vlm_model=vlm_model,
                          vlm_server=vlm_server,require_multimodal=require_multimodal)
    pytest_env={**env,**opt_ins}
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
    report={"status":"BASELINE_INVENTORY_COMPLETED" if profile=="inventory" else "BASELINE_REGRESSION_COMPLETED","policy_version":"a00-local-baseline.v2",
            "profile":profile,"inventory":info,"python":sys.version.split()[0],
            "conda_environment":os.environ.get("CONDA_DEFAULT_ENV"),"packages":packages,
            "tools":{k:bool(shutil.which(k)) for k in ("git","node","ffmpeg","ffprobe","tesseract","espeak-ng")},
            "ocr_integration_opt_in":tessdata is not None,
            "asr_integration_opt_in":asr_model is not None,"vlm_integration_opt_in":vlm_model is not None,
            "multimodal_required":require_multimodal,"steps":[],
            "operational_database_url_forwarded":False,"external_credential_environment_forwarded":False,
            "network_sandbox":False,"global_gates_released":False,"production_approved":False}
    for step,file in (("legacy_gate0","scripts/check_gate0.py"),("zero_spend","scripts/verify_zero_spend.py")):
        report["steps"].append(run_step(root,target,step,[sys.executable,file],env,timeout=120))
    if profile=="full":
        report["steps"].append(run_step(root,target,"documentary_mirror",
            [sys.executable,"docs/base_atemporal/ferramentas/validar_espelho.py"],env,timeout=120))
    if profile!="inventory":
        xml=target/"pytest.xml"
        tests=["tests"] if profile=="full" else list(SEMANTIC_TESTS)
        report["steps"].append(run_step(root,target,"pytest",
            [sys.executable,"-m","pytest","-q","--capture=tee-sys",*tests,"--junitxml",str(xml)],pytest_env))
        try:
            report["pytest"]=junit_counts(xml)
            if xml.is_file():
                report["pytest_xml_sha256"]=sha256(xml.read_bytes()).hexdigest()
        except ET.ParseError:
            report["pytest"]=None
            report["pytest_junit_invalid"]=True
        if profile=="full":
            try:
                report["multimodal_coverage"]=multimodal_coverage(xml)
            except ET.ParseError:
                report["multimodal_coverage"]={"groups":{},"all_required_passed":False}
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
    if require_multimodal:
        report["checks_passed"]=bool(report["checks_passed"] and report["multimodal_coverage"]["all_required_passed"])
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
    p.add_argument("--asr-model-dir",type=Path)
    p.add_argument("--vlm-model-dir",type=Path)
    p.add_argument("--vlm-server-exe",type=Path)
    p.add_argument("--require-multimodal",action="store_true")
    a=p.parse_args(argv)
    try:
        result=execute(ROOT,a.expected_head,a.profile,a.report_name,a.tessdata_dir,
            asr_model=a.asr_model_dir,vlm_model=a.vlm_model_dir,vlm_server=a.vlm_server_exe,
            require_multimodal=a.require_multimodal)
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
