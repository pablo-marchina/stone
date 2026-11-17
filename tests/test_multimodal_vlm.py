import json
from pathlib import Path

import pytest

from tapi_gate0 import multimodal_vlm as vlm


def test_strict_prediction_schema():
    assert vlm.parse_prediction('{"text_present":"yes","scene":"text_card"}')=={"text_present":"yes","scene":"text_card"}
    for raw in ('{"text_present":"yes","scene":"text_card","extra":1}',
                '{"text_present":true,"scene":"blank"}',
                '{"text_present":"no","scene":"face"}',"not json","[]"):
        assert vlm.parse_prediction(raw) is None


def rows():
    out=[]
    for suite,count in (("shared",14),("challenge",6)):
        for i in range(count):
            expected={"text_present":"yes" if i%2 else "no",
                      "scene":"text_card" if i%2 else "blank"}
            out.append({"suite":suite,"case_id":f"{suite}_{i}","expected":expected,"prediction":dict(expected)})
    return out


def test_gate_requires_both_suites_and_no_false_candidates():
    data=rows()
    assert vlm.metrics(data)["engineering_gate_passed"]
    assert not vlm.metrics(data[:-1])["engineering_gate_passed"]
    data[0]["prediction"]["text_present"]="yes"
    assert not vlm.metrics(data)["engineering_gate_passed"]
    data[0]["prediction"]=None
    assert not vlm.metrics(data)["engineering_gate_passed"]


def test_abstention_is_not_a_correct_negative():
    data=rows()
    for row in data:
        if row["suite"]=="challenge" and row["expected"]["text_present"]=="no":
            row["prediction"]["text_present"]="uncertain"
    score=vlm.metrics(data)
    assert score["suites"]["challenge"]["text_present"]["per_class"]["no"]["recall"]==0
    assert not score["engineering_gate_passed"]


def test_checkpoint_pins_both_files_and_gguf_magic(tmp_path,monkeypatch):
    import hashlib
    names=list(vlm.FILES)
    for i,n in enumerate(names):
        (tmp_path/n).write_bytes(b"GGUF"+bytes([i]))
    monkeypatch.setattr(vlm,"FILES",{n:hashlib.sha256((tmp_path/n).read_bytes()).hexdigest() for n in names})
    assert set(vlm.verify_checkpoint(tmp_path))==set(names)
    (tmp_path/names[1]).write_bytes(b"GGUFwrong")
    with pytest.raises(vlm.VLMError,match="PUBLISHED_HASH_MISMATCH"):
        vlm.verify_checkpoint(tmp_path)
    (tmp_path/names[0]).write_bytes(b"wrong")
    with pytest.raises(vlm.VLMError,match="GGUF_MAGIC_INVALID"):
        vlm.verify_checkpoint(tmp_path)


def test_runtime_env_drops_remote_overrides(monkeypatch):
    monkeypatch.setenv("LLAMA_ARG_MODEL_URL","https://example.invalid")
    monkeypatch.setenv("HF_TOKEN","secret")
    monkeypatch.setenv("HTTP_PROXY","http://example.invalid")
    env=vlm.server_env()
    assert "LLAMA_ARG_MODEL_URL" not in env and "HF_TOKEN" not in env and "HTTP_PROXY" not in env
    assert env["LLAMA_OFFLINE"]=="1" and env["HF_HUB_OFFLINE"]=="1"


def test_plan_blocks_low_ram_without_model_load(tmp_path,monkeypatch,capsys):
    from scripts import a6_vlm_benchmark as cli
    monkeypatch.setattr(vlm,"available_ram",lambda:1024**3)
    monkeypatch.setattr(vlm,"verify_checkpoint",lambda *_:pytest.fail("unexpected checkpoint read"))
    assert cli.main(["--plan","--model-dir",str(tmp_path)])==2
    result=json.loads(capsys.readouterr().out)
    assert not result["run_memory_ready"] and not result["checkpoint_verified"]
    assert cli.main(["--benchmark","--model-dir",str(tmp_path),"--server-exe",str(tmp_path/"llama-server"),
                     "--input-name","input.json","--report-name","out.json"])==2
    assert json.loads(capsys.readouterr().out)["code"]=="VLM_RESOURCE_PREFLIGHT_BLOCKED"


def test_plan_no_unknown_ram_pass(tmp_path,monkeypatch):
    monkeypatch.setattr(vlm,"available_ram",lambda:None)
    assert not vlm.plan(tmp_path)["run_memory_ready"]


def test_runtime_requires_exact_build(tmp_path,monkeypatch):
    from types import SimpleNamespace
    p=tmp_path/"llama-server"
    p.write_bytes(b"runtime")
    monkeypatch.setattr(vlm.subprocess,"run",lambda *a,**k:SimpleNamespace(returncode=0,stdout=b"",stderr=b"version: 6907 (bea0452d)"))
    assert vlm.verify_runtime(p)["build"]=="6907"
    monkeypatch.setattr(vlm.subprocess,"run",lambda *a,**k:SimpleNamespace(returncode=0,stdout=b"version: 6908 (bea0452d)",stderr=b""))
    with pytest.raises(vlm.VLMError,match="RUNTIME_BUILD_MISMATCH"):
        vlm.verify_runtime(p)
