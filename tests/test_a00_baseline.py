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
                    "skipped_tests":[{"class":"","name":"skip"}],
                    "failed_tests":[{"class":"","name":"bad","kind":"failure"},
                                    {"class":"","name":"error","kind":"error"}]}
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


def _local_models(root):
    o=root/"ocr";a=root/"asr";v=root/"vlm";b=root/"bin"
    for p,names in ((o,("por.traineddata","eng.traineddata")),
                    (a,("config.json","model.bin","tokenizer.json","vocabulary.txt")),
                    (v,("Qwen3VL-2B-Instruct-Q4_K_M.gguf","mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf")),
                    (b,("llama-server.exe",))):
        p.mkdir()
        for n in names:
            (p/n).write_bytes(b"fixture")
    return dict(tessdata=o,asr_model=a,vlm_model=v,vlm_server=b/"llama-server.exe")


def test_model_opt_ins_explicit_only(tmp_path):
    paths=_local_models(tmp_path)
    env=baseline.model_opt_ins("full",**paths)
    assert env=={"TAPI_OCR_TEST_TESSDATA":str(paths["tessdata"]),
        "TAPI_ASR_TEST_MODEL_DIR":str(paths["asr_model"]),
        "TAPI_VLM_TEST_MODEL_DIR":str(paths["vlm_model"]),
        "TAPI_VLM_TEST_SERVER_EXE":str(paths["vlm_server"])}
    assert not baseline.model_opt_ins("full")
    assert not set(env)&set(baseline.child_environment(tmp_path,env))


@pytest.mark.parametrize("profile",["inventory","semantic"])
def test_model_opt_ins_require_full_profile(tmp_path,profile):
    with pytest.raises(baseline.BaselineError,match="MODEL_FULL_PROFILE_REQUIRED"):
        baseline.model_opt_ins(profile,asr_model=tmp_path)


def test_model_opt_ins_incomplete_pair_or_strict_missing(tmp_path):
    with pytest.raises(baseline.BaselineError,match="VLM_PAIR_REQUIRED"):
        baseline.model_opt_ins("full",vlm_model=tmp_path)
    with pytest.raises(baseline.BaselineError,match="MULTIMODAL_ALL_OPT_INS_REQUIRED"):
        baseline.model_opt_ins("full",require_multimodal=True)


def test_model_opt_ins_invalid_paths_and_names(tmp_path):
    paths=_local_models(tmp_path)
    with pytest.raises(baseline.BaselineError,match="ASR_PATH_INVALID"):
        baseline.model_opt_ins("full",asr_model=Path("relative"))
    (paths["asr_model"]/"model.bin").unlink()
    with pytest.raises(baseline.BaselineError,match="ASR_FILES_REQUIRED"):
        baseline.model_opt_ins("full",**paths)
    wrong=paths["vlm_server"].with_name("wrong.exe");wrong.write_bytes(b"x")
    with pytest.raises(baseline.BaselineError,match="VLM_SERVER_NAME_INVALID"):
        baseline.model_opt_ins("full",vlm_model=paths["vlm_model"],vlm_server=wrong)


def test_strict_requires_native_host(tmp_path,monkeypatch):
    paths=_local_models(tmp_path)
    monkeypatch.setattr(baseline.sys,"platform","linux")
    with pytest.raises(baseline.BaselineError,match="WINDOWS_X64_REQUIRED"):
        baseline.model_opt_ins("full",require_multimodal=True,**paths)


def _required_junit(path,*,defect=None):
    import xml.etree.ElementTree as ET
    root=ET.Element("testsuite")
    for group,cls,prefix,n in baseline.MULTIMODAL_GROUPS:
        for i in range(n):
            if defect=="missing" and group=="asr" and i==0:
                continue
            c=ET.SubElement(root,"testcase",classname=cls,name=prefix+"case["+str(i)+"]")
            if group=="asr" and i==0:
                if defect=="skip":
                    ET.SubElement(c,"skipped")
                elif defect=="failure":
                    ET.SubElement(c,"failure")
                elif defect=="duplicate":
                    ET.SubElement(root,"testcase",classname=cls,name=c.get("name"))
    ET.ElementTree(root).write(path,encoding="utf-8")


@pytest.mark.parametrize("defect",[None,"missing","skip","failure","duplicate"])
def test_multimodal_coverage_requires_executed_unique_cases(tmp_path,defect):
    p=tmp_path/"junit.xml";_required_junit(p,defect=defect)
    result=baseline.multimodal_coverage(p)
    assert result["all_required_passed"] is (defect is None)
    assert result["groups"]["asr"]["passed_required"] is (defect is None)
    assert not baseline.multimodal_coverage(tmp_path/"absent")["all_required_passed"]


@pytest.mark.parametrize("defect",[None,"skip"])
def test_full_strict_runner_scopes_opt_ins_and_checks_required_cases(tmp_path,monkeypatch,defect):
    paths=_local_models(tmp_path)
    monkeypatch.setattr(baseline,"inventory",lambda *_:{"commit":"a"*40,"node_test_files":["tests/test_fixture.mjs"]})
    monkeypatch.setattr(baseline,"check_checkout",lambda *_:None)
    explicit=baseline.model_opt_ins("full",**paths)
    monkeypatch.setattr(baseline,"model_opt_ins",lambda *a,**k:explicit)
    monkeypatch.setenv("TAPI_DATABASE_URL","fixture-secret")
    monkeypatch.setenv("TAPI_ASR_TEST_MODEL_DIR","untrusted-inherited")
    called=[]
    def fake_step(root,target,name,command,env,timeout=1800):
        called.append(name)
        assert "TAPI_DATABASE_URL" not in env
        if name=="pytest":
            assert all(env[k]==v for k,v in explicit.items())
            assert "--capture=tee-sys" in command
            _required_junit(target/"pytest.xml",defect=defect)
        else:
            assert not set(explicit)&set(env)
        return {"step":name,"exit_code":0}
    monkeypatch.setattr(baseline,"run_step",fake_step)
    report=baseline.execute(tmp_path,"a"*40,"full","fixture",require_multimodal=True,**paths)
    assert called==["legacy_gate0","zero_spend","documentary_mirror","pytest","node"]
    assert report["checks_passed"] is (defect is None)
    assert report["multimodal_coverage"]["all_required_passed"] is (defect is None)
    assert report["asr_integration_opt_in"] and report["vlm_integration_opt_in"]
    assert not report["operational_database_tested"]
