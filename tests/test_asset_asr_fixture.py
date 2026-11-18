import json
import math
import shutil
from dataclasses import replace
from hashlib import sha256

import pytest
from tapi_gate0 import asset_asr_fixture as a
from tapi_gate0 import asset_windows_job as w


def positive(monkeypatch):
    monkeypatch.setattr(a,"_speech_pcm",lambda:b"\x01\x00"*32000)
    data,meta=a.fixture("inventory")
    result={"pcm_sha256":meta["pcm_sha256"],"intervals":[{"start":32000,"end":64000}],
            "segments":[{"start_s":2.0,"end_s":4.0,"text":a.REFERENCE,"region_start_sample":32000,"region_end_sample":64000}],
            "vad_calls":1,"asr_calls":1}
    return data,meta,result


def emit(result):
    return json.dumps(result).encode()


@pytest.mark.parametrize("case",["silence","tone"])
def test_negative_wav_and_abstention(case):
    data,meta=a.fixture(case)
    assert data==a.fixture(case)[0] and data[:4]==b"RIFF" and data[8:12]==b"WAVE"
    assert len(a._pcm(data))==96000 and sha256(a._pcm(data)).hexdigest()==meta["pcm_sha256"]
    result,quality=a.result_from_output(meta,emit({"pcm_sha256":meta["pcm_sha256"],"intervals":[],"segments":[],"vad_calls":int(case=="tone"),"asr_calls":0}))
    assert result.state=="abstained" and quality["asr_calls"]==0
    assert bool(any(a._pcm(data)))==(case=="tone")


def test_real_tts_fixture_reproducible():
    if not shutil.which("espeak-ng") or not shutil.which("ffmpeg"):
        pytest.skip("local eSpeak NG and FFmpeg required")
    data,meta=a.fixture("inventory")
    assert (data,meta)==a.fixture("inventory")
    assert meta["expected_regions"][0]["start"]==32000
    assert 0<meta["expected_regions"][0]["end"]<meta["samples"]
    assert len(data)<=480044


def test_positive_observation_and_quality(monkeypatch):
    _,meta,r=positive(monkeypatch)
    result,q=a.result_from_output(meta,emit(r))
    assert result.state=="observed" and result.segments[0].start_ms==2000 and result.segments[0].end_ms==4000
    assert result.segments[0].text==a.REFERENCE and result.duration_ms==5000
    assert q["wer"]==0 and q["vad_iou"]==1 and q["asr_calls"]==q["vad_calls"]==1


@pytest.mark.parametrize("mutation,code",[
    (lambda r:r.update(pcm_sha256="0"*64),"OUTPUT_BINDING"),
    (lambda r:r.update(vad_calls=True),"OUTPUT_SHAPE"),
    (lambda r:r.update(asr_calls=0),"OUTPUT_SHAPE"),
    (lambda r:r["intervals"][0].update(start=-1),"VAD_INTERVAL"),
    (lambda r:r["intervals"][0].update(end=40000),"VAD_GATE"),
    (lambda r:r["segments"][0].update(start_s=1.9),"SEGMENT"),
    (lambda r:r["segments"][0].update(end_s=4.1),"SEGMENT"),
    (lambda r:r["segments"][0].update(start_s=float("nan")),"SEGMENT"),
    (lambda r:r["segments"][0].update(region_end_sample=65000),"SEGMENT"),
    (lambda r:r["segments"][0].update(text="palavra errada"),"WER_GATE"),
    (lambda r:r.update(segments=[]),"WER_GATE"),
    (lambda r:r["segments"].append(dict(r["segments"][0])),"SEGMENT_ORDER"),
])
def test_reject_invalid_observation(monkeypatch,mutation,code):
    _,meta,r=positive(monkeypatch);mutation(r)
    with pytest.raises(ValueError,match=code):
        a.result_from_output(meta,emit(r))


@pytest.mark.parametrize("case",["silence","tone"])
def test_negative_no_hallucination(case):
    _,meta=a.fixture(case)
    r={"pcm_sha256":meta["pcm_sha256"],"intervals":[{"start":1,"end":10}],"segments":[],"vad_calls":int(case=="tone"),"asr_calls":1}
    with pytest.raises(ValueError,match="NEGATIVE_INSERTION"):
        a.result_from_output(meta,emit(r))


def test_duplicate_and_oversize_output(monkeypatch):
    _,meta,r=positive(monkeypatch)
    with pytest.raises(ValueError,match="DUPLICATE_KEY"):
        a.result_from_output(meta,emit(r)[:-1]+b',"vad_calls":1}')
    with pytest.raises(ValueError,match="OUTPUT_SIZE"):
        a.result_from_output(meta,b"x"*(a.MAX_OUTPUT+1))


def test_config_binds_runtime_and_case(monkeypatch):
    monkeypatch.setattr(a,"_runtime",lambda p:{"checkpoint":"a"})
    x,code=a.plan("silence","C:/trusted/medium")
    assert x["configuration_sha256"]!=a.plan("tone","C:/trusted/medium")[0]["configuration_sha256"]
    assert code.index("sys.stdin.buffer.read")<code.index("from tapi_gate0.asset_asr_fixture import _infer")
    assert a.REFERENCE not in code
    monkeypatch.setattr(a,"_runtime",lambda p:{"checkpoint":"b"})
    assert x["configuration_sha256"]!=a.plan("silence","C:/trusted/medium")[0]["configuration_sha256"]


def test_invalid_fixture_and_model_budget():
    with pytest.raises(ValueError,match="UNKNOWN"):
        a.fixture("arbitrary")
    with pytest.raises(w.JobError,match="MODEL_FIXTURE_LIMIT_INVALID"):
        replace(a.LIMITS,memory_mib=8192)
    with pytest.raises(w.JobError,match="FIXTURE_BOUNDS"):
        w._run_model_fixture("",b"x",lambda:None,limits=w.JobLimits())
    with pytest.raises(w.JobError,match="FIXTURE_BOUNDS"):
        w._run_model_fixture("",b"x"*480045,lambda:None)
    with pytest.raises(w.JobError,match="FIXTURE_BOUNDS"):
        w._run_model_fixture("",b"x",lambda:None,max_output=32769)


def test_tts_child_environment_reduced(monkeypatch,tmp_path):
    from types import SimpleNamespace
    exe=tmp_path/"fake.exe";exe.write_bytes(b"x")
    monkeypatch.setattr(a.shutil,"which",lambda name:str(exe))
    monkeypatch.setenv("TAPI_DATABASE_URL","private")
    monkeypatch.setenv("HF_TOKEN","private")
    calls=[]
    def run(args,**kw):
        assert "TAPI_DATABASE_URL" not in kw["env"] and "HF_TOKEN" not in kw["env"]
        assert set(kw["env"])<= {"SystemRoot","WINDIR","ESPEAK_DATA_PATH"}
        assert kw["shell"] is False and kw["close_fds"] is True
        calls.append(args)
        return SimpleNamespace(stdout=b"\x01\x00"*16)
    monkeypatch.setattr(a.subprocess,"run",run)
    assert a._speech_pcm()==b"\x01\x00"*16 and len(calls)==2
