import io
import json
import os
import subprocess
import sys

import pytest
from PIL import Image
from tapi_gate0 import asset_vlm_fixture as a


def envelope(case,**updates):
    raw,scene=a.fixture(case)
    r={"input_sha256":a.digest(raw),"scene":scene,"model_scene":scene if case!="blank" else None,
       "response_sha256":"a"*64 if case!="blank" else None,"model_calls":int(case!="blank")}
    return json.dumps(r|updates).encode()


@pytest.mark.parametrize("case",list(a.CASES))
def test_fixture_pinned_and_valid(case):
    data,expected=a.fixture(case)
    assert a.digest(data)==a.FIXTURES[case][1]
    assert (data,expected)==a.fixture(case)
    with Image.open(io.BytesIO(data)) as im:
        assert im.size==(960,540) and im.mode=="L" and im.format=="PNG"
        assert (im.getextrema()[0]==im.getextrema()[1])==(case=="blank")
    result,calls=a.result_from_output(case,envelope(case))
    assert result.scene==expected and result.frame.frame_sha256==a.digest(data)
    assert result.text_present==("yes" if case=="sales" else "no")
    assert calls==int(case!="blank")


@pytest.mark.parametrize("updates,code",[
    ({"input_sha256":"0"*64},"OUTPUT_BINDING"),({"model_calls":True},"CALLS"),
    ({"model_calls":0},"CALLS"),({"response_sha256":"secret"},"RESPONSE_HASH"),
    ({"scene":"geometry"},"SCENE_CONFLICT"),
    ({"scene":"uncertain","model_scene":"uncertain"},"QUALITY_GATE"),
    ({"scene":"geometry","model_scene":"geometry"},"QUALITY_GATE"),
    ({"scene":"uncertain","model_scene":"blank"},"SCENE_CONFLICT"),
])
def test_wrong_prediction_rejected(updates,code):
    with pytest.raises(ValueError,match=code): a.result_from_output("sales",envelope("sales",**updates))


@pytest.mark.parametrize("raw",['{"scene":"geometry","scene":"blank"}','{"scene":"unknown"}','{"scene":"blank","extra":1}','{"scene":NaN}','[]'])
def test_strict_scene_json(raw):
    with pytest.raises(ValueError): a.parse_scene(raw)


def test_blank_is_guard_not_model(monkeypatch):
    monkeypatch.setattr(a,"_request",lambda *args,**kw:pytest.fail("blank called model"))
    raw,_=a.fixture("blank")
    r=a._infer(raw,None,None,stage=lambda _:None)
    assert r["model_calls"]==0 and r["model_scene"] is None
    assert a.result_from_output("blank",json.dumps(r).encode())[1]==0
    with pytest.raises(ValueError,match="GUARD"): a.result_from_output("blank",envelope("blank",model_scene="blank"))


def test_nonuniform_blank_abstains_and_gate_rejects(monkeypatch):
    monkeypatch.setattr(a,"_request",lambda *args,**kw:("blank","a"*64))
    raw,_=a.fixture("geometry")
    r=a._infer(raw,None,None,stage=lambda _:None)
    assert r["scene"]=="uncertain" and r["model_scene"]=="blank"
    with pytest.raises(ValueError): a.result_from_output("geometry",json.dumps(r).encode())


def test_server_env_does_not_forward_secrets(monkeypatch):
    for n in ("TAPI_DATABASE_URL","HF_TOKEN","HTTP_PROXY","LLAMA_ARG_HOST","PATH"):
        monkeypatch.setenv(n,"private")
    env=a._server_env("ephemeral")
    assert env["LLAMA_API_KEY"]=="ephemeral" and env["LLAMA_OFFLINE"]=="1"
    assert all(n not in env for n in ("TAPI_DATABASE_URL","HF_TOKEN","HTTP_PROXY","LLAMA_ARG_HOST","PATH"))


def test_bounded_http_json():
    import httpx
    def handler(request):
        return httpx.Response(200,content=b'x'*(a.MAX_HTTP+1) if request.url.path=="/big" else b'{"ok":true}')
    with httpx.Client(base_url="http://127.0.0.1",transport=httpx.MockTransport(handler),trust_env=False) as c:
        assert a._bounded_json(c,"GET","/ok")=={"ok":True}
        with pytest.raises(ValueError,match="HTTP_SIZE"): a._bounded_json(c,"GET","/big")


def test_fixture_tamper_and_unknown(monkeypatch):
    with pytest.raises(ValueError,match="UNKNOWN"): a.fixture("external")
    b64,_=a.FIXTURES["blank"]
    monkeypatch.setitem(a.FIXTURES,"blank",(b64,"0"*64))
    with pytest.raises(ValueError,match="PIN"): a.fixture("blank")


def test_child_framed_error_redacted(monkeypatch,tmp_path):
    package=tmp_path/"tapi_gate0";package.mkdir()
    (package/"__init__.py").write_text("")
    module=package/"asset_vlm_fixture.py"
    module.write_text('def _infer(raw,model,server,*,stage):\n    stage("model_load"); raise RuntimeError("out of memory SECRET_PATH")\n')
    monkeypatch.setattr(a,"__file__",str(module))
    raw,_=a.fixture("sales")
    p=subprocess.run([sys.executable,"-I","-S","-c",a._child(raw,"SECRET_PATH","server")],input=raw,
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,
        env={k:os.environ[k] for k in ("SystemRoot","WINDIR") if k in os.environ})
    assert p.returncode==4 and b"TAPI_VLM_STAGE:model_load\n" in p.stdout
    assert b"TAPI_VLM_ERROR:RuntimeError:memory\n" in p.stdout and b"SECRET_PATH" not in p.stdout
