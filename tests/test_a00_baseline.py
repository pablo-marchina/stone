import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts import a00_baseline as baseline


def test_real_synced_matrices_and_phase_partition():
    result=baseline.read_matrices(baseline.ROOT)
    assert result["dependency_dag_acyclic"]
    assert sum(result["phase_task_counts"].values())==204
    assert result["phase_task_counts"]["A00"]==44
    assert result["imp062_status"]=="DISPENSADO_POR_DEC018_DECLARADA_NAO_CUMPRIDO"
    assert not result["independent_human_review_completed"]


def test_matrix_copy_rejects_duplicate_task_assignment(tmp_path):
    shutil.copytree(baseline.ROOT/baseline.MATRICES,tmp_path/baseline.MATRICES)
    p=tmp_path/"planning/action_2026-11-17/phase_map.json"
    p.parent.mkdir(parents=True)
    data=json.loads((baseline.ROOT/"planning/action_2026-11-17/phase_map.json").read_text(encoding="utf-8"))
    data["phases"]["A00"][0]=data["phases"]["A01"][0]
    p.write_text(json.dumps(data),encoding="utf-8")
    with pytest.raises(baseline.BaselineError,match="BASELINE_PHASE_PARTITION_INVALID"):
        baseline.read_matrices(tmp_path)


def test_child_environment_does_not_inherit_operational_config(tmp_path):
    original={"PATH":"local-path","SYSTEMROOT":"windows","TAPI_DATABASE_URL":"private-db",
              "TAPI_TENANT_ID":"tenant","TAPI_SYSTEM_ONE_ENABLED":"1","TAPI_META_ACCESS_TOKEN":"secret",
              "TAPI_EVIDENCE_LAB_TENANT":"tenant","HF_TOKEN":"secret","OPENAI_API_KEY":"secret",
              "PYTEST_ADDOPTS":"--maxfail=1","HTTP_PROXY":"remote","ESPEAK_DATA_PATH":"local-tts"}
    env=baseline.child_environment(tmp_path,original)
    assert env["PATH"]=="local-path" and env["ESPEAK_DATA_PATH"]=="local-tts"
    assert env["HF_HUB_OFFLINE"]==env["TRANSFORMERS_OFFLINE"]=="1"
    assert env["PYTHONPATH"]==str(tmp_path/"src")
    assert not set(env)&{"TAPI_DATABASE_URL","TAPI_TENANT_ID","TAPI_SYSTEM_ONE_ENABLED",
                        "TAPI_META_ACCESS_TOKEN","TAPI_EVIDENCE_LAB_TENANT","HF_TOKEN","OPENAI_API_KEY",
                        "PYTEST_ADDOPTS","HTTP_PROXY"}


def test_checkout_pins_exact_clean_commit(tmp_path,monkeypatch):
    commit="a"*40
    def fake_git(root,*args):
        if args[0]=="rev-parse":
            return commit
        return ""
    monkeypatch.setattr(baseline,"git",fake_git)
    baseline.check_checkout(tmp_path,commit)
    with pytest.raises(baseline.BaselineError,match="FULL_COMMIT_REQUIRED"):
        baseline.check_checkout(tmp_path,commit[:7])
    with pytest.raises(baseline.BaselineError,match="HEAD_MISMATCH"):
        baseline.check_checkout(tmp_path,"b"*40)
    monkeypatch.setattr(baseline,"git",lambda root,*args:commit if args[0]=="rev-parse" else " M tracked.py")
    with pytest.raises(baseline.BaselineError,match="DIRTY_CHECKOUT"):
        baseline.check_checkout(tmp_path,commit)


def test_private_report_exclusive(tmp_path):
    p=baseline.private_run_dir(tmp_path,"regression-1")
    assert p==tmp_path/"artifacts/private/regression-1"
    with pytest.raises(FileExistsError):
        baseline.private_run_dir(tmp_path,"regression-1")
    with pytest.raises(baseline.BaselineError,match="PRIVATE_NAME_INVALID"):
        baseline.private_run_dir(tmp_path,"../outside")


def test_junit_counts_do_not_count_skips_as_passes(tmp_path):
    p=tmp_path/"pytest.xml"
    p.write_text('<testsuites><testsuite><testcase name="pass"/><testcase name="skip"><skipped/></testcase>'
                 '<testcase name="bad"><failure/></testcase><testcase name="error"><error/></testcase></testsuite></testsuites>',encoding="utf-8")
    report=baseline.junit_counts(p)
    assert report=={"tests":4,"passed":1,"failed":1,"errors":1,"skipped":1,
                    "skipped_tests":[{"class":"","name":"skip"}]}
    assert baseline.junit_counts(tmp_path/"absent.xml") is None


def test_step_logs_nonzero_and_does_not_print_child_output(tmp_path,capsys):
    result=baseline.run_step(tmp_path,tmp_path,"test",[sys.executable,"-c","print('fixture output'); raise SystemExit(3)"],
                             baseline.child_environment(tmp_path,baseline.os.environ),timeout=30)
    assert result["exit_code"]==3
    assert len(result["log_sha256"])==64
    assert "fixture output" in (tmp_path/"test.log").read_text(encoding="utf-8")
    assert capsys.readouterr().out==""


def test_inventory_profile_never_invokes_regression_or_operational_db(tmp_path,monkeypatch):
    monkeypatch.setattr(baseline,"inventory",lambda *_:{"commit":"a"*40,"node_test_files":[]})
    monkeypatch.setattr(baseline,"check_checkout",lambda *_:None)
    called=[]
    def fake_step(root,target,name,command,env,timeout=1800):
        called.append(name)
        assert "TAPI_DATABASE_URL" not in env
        return {"step":name,"exit_code":0}
    monkeypatch.setattr(baseline,"run_step",fake_step)
    result=baseline.execute(tmp_path,"a"*40,"inventory","inv")
    assert called==["legacy_gate0","zero_spend"]
    assert result["checks_passed"] and not result["full_regression_profile_executed"]
    assert not result["full_regression_without_skips"]
    assert not result["operational_database_tested"]
    assert (tmp_path/"artifacts/private/inv/summary.json").is_file()
