import os
import subprocess
import sys
from hashlib import sha256

import pytest
from tapi_gate0 import asset_temporal_fixture as a

@pytest.mark.parametrize("case,times",[("static",[]),("one",[2000]),("two",[1000,2000])])
def test_real_ffmpeg_pinned_fixture_and_typed_measurements(case,times):
    data,expected=a.fixture(case)
    config,code=a.plan(case)
    # Portable isolated decoder check, not a native Windows containment test.
    r=subprocess.run([sys.executable,"-I","-S","-c",code],input=data,
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30,check=True,
        env={k:os.environ[k] for k in ("SystemRoot","WINDIR") if k in os.environ})
    assert r.stdout==expected and sha256(r.stdout).hexdigest()==config["decoded_sha256"]
    result=a.result_from_frames(case,r.stdout)
    assert result.samples==12 and [x.current.time_ms for x in result.candidates]==times
    assert all(x.normalized_difference==1.0 for x in result.candidates)

@pytest.mark.parametrize("case",["static","one","two"])
def test_rejects_wrong_frames(case):
    _,raw=a.fixture(case)
    with pytest.raises(ValueError,match="DECODE_MISMATCH"):
        a.result_from_frames(case,bytes([raw[0]^1])+raw[1:])


def test_unknown_fixture_rejected():
    with pytest.raises(ValueError,match="UNKNOWN"):
        a.fixture("other")


def test_configuration_binds_runtime_and_fixture(monkeypatch):
    monkeypatch.setattr(a,"_runtime",lambda:("C:/trusted/ffmpeg.exe","a"*64))
    p,_=a.plan("static")
    q,_=a.plan("two")
    assert p["configuration_sha256"]!=q["configuration_sha256"]
    monkeypatch.setattr(a,"_runtime",lambda:("C:/trusted/ffmpeg.exe","b"*64))
    assert p["configuration_sha256"]!=a.plan("static")[0]["configuration_sha256"]


def test_fixed_payload_bounds_before_job():
    with pytest.raises(a.windows.JobError,match="FIXTURE_BOUNDS"):
        a.windows._run_exact_fixture("",b"x"*131073,b"",lambda:None,limits=a.LIMITS)
