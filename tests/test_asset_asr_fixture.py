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


@pytest.mark.parametrize("body,expected_stage,expected_error,expected_reason,exit_code",[
    ('stage("vad"); stage("model_load"); raise RuntimeError("out of memory SECRET_PATH")',"model_load","RuntimeError","memory",4),
    ('stage("vad"); stage("model_load"); import os; os._exit(42)',"model_load","unknown","unknown",42),
    ('stage("vad"); stage("model_load"); stage("transcribe"); raise ImportError("DLL load failed SECRET_PATH")',"transcribe","ImportError","dll",4),
])
def test_child_diagnostic_no_raw_exception(monkeypatch,tmp_path,body,expected_stage,expected_error,expected_reason,exit_code):
    import os
    import subprocess
    import sys
    package=tmp_path/"tapi_gate0";package.mkdir()
    (package/"__init__.py").write_text("")
    module=package/"asset_asr_fixture.py"
    module.write_text("def _infer(data,model_dir,*,stage):\n    "+body+"\n")
    monkeypatch.setattr(a,"__file__",str(module))
    data,_=a.fixture("silence")
    result=subprocess.run([sys.executable,"-I","-S","-c",a._child(data,"SECRET_PATH")],input=data,
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,
        env={k:os.environ[k] for k in ("SystemRoot","WINDIR") if k in os.environ})
    assert result.returncode==exit_code
    assert w._model_trace(result.stdout)==(expected_stage,expected_error,expected_reason,None)
    message=str(w._model_failure(result.stdout,result.returncode,{"peak_job_commit_bytes":123}))
    assert f"stage={expected_stage}" in message and f"exit=0x{exit_code:08x}" in message
    assert "peak_commit_bytes=123" in message and "SECRET_PATH" not in message
    assert b"SECRET_PATH" not in result.stdout


def test_child_success_framing(monkeypatch,tmp_path):
    import os
    import subprocess
    import sys
    package=tmp_path/"tapi_gate0";package.mkdir()
    (package/"__init__.py").write_text("")
    module=package/"asset_asr_fixture.py"
    module.write_text('def _infer(data,model_dir,*,stage):\n    return {"ok": True}\n')
    monkeypatch.setattr(a,"__file__",str(module))
    data,_=a.fixture("silence")
    result=subprocess.run([sys.executable,"-I","-S","-c",a._child(data,"unused")],input=data,
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,check=True,
        env={k:os.environ[k] for k in ("SystemRoot","WINDIR") if k in os.environ})
    assert w._model_trace(result.stdout)==("serialize","unknown","unknown",b'{"ok":true}')


def test_model_trace_fail_closed_and_no_untrusted_text():
    assert w._model_trace(b'TAPI_ASR_STAGE:bootstrap\nTAPI_ASR_STAGE:SECRET\nTAPI_ASR_RESULT\n{}')==("bootstrap","unknown","unknown",None)
    assert w._model_trace(b'TAPI_ASR_STAGE:bootstrap\nTAPI_ASR_ERROR:RuntimeError:SECRET\n')==("bootstrap","unknown","unknown",None)
    assert w._model_trace(b'TAPI_ASR_STAGE:serialize\nTAPI_ASR_RESULT\n{}')[3] is None
    assert w._model_trace(b'TAPI_ASR_STAGE:bootstrap\nTAPI_ASR_STAGE:serialize\nTAPI_ASR_RESULT\n'+b'x'*32768)[3] is None
    assert "exit=0xc0000005" in str(w._model_failure(b'',-1073741819,{}))


@pytest.mark.parametrize("physical_mib,commit_mib,allowed",[
    (4096,7168,True),(8192,8192,True),(4095,8192,False),
    (8192,7167,False),(0,0,False),
])
def test_model_host_headroom(monkeypatch,physical_mib,commit_mib,allowed):
    snapshot={"available_physical_bytes":physical_mib*w.MIB,
        "available_commit_bytes":commit_mib*w.MIB,"total_physical_bytes":16384*w.MIB}
    monkeypatch.setattr(w,"model_host_capacity",lambda:snapshot)
    if allowed:
        assert w.require_model_headroom(a.LIMITS)==snapshot
    else:
        with pytest.raises(w.JobError,match="MODEL_HOST_HEADROOM_INSUFFICIENT"):
            w.require_model_headroom(a.LIMITS)


def test_model_headroom_denial_before_spawn(monkeypatch):
    events=[]
    monkeypatch.setattr(w,"model_host_capacity",lambda:{"available_physical_bytes":0,"available_commit_bytes":0})
    monkeypatch.setattr(w,"_run_fixture_output",lambda *args,**kwargs:pytest.fail("must not spawn"))
    with pytest.raises(w.JobError,match="MODEL_HOST_HEADROOM_INSUFFICIENT"):
        w._run_model_fixture("",b"x",lambda:events.append("rights"))
    assert events==["rights"]


def test_model_budget_fixed_and_legacy_limits_unchanged():
    assert a.LIMITS==w.ModelFixtureLimits(6144,240,1,90)
    assert w.JobLimits().memory_mib==128
    for memory in (4096,6145,8192):
        with pytest.raises(w.JobError,match="MODEL_FIXTURE_LIMIT_INVALID"):
            replace(a.LIMITS,memory_mib=memory)
    assert w.C.sizeof(w.MemoryStatus)==64


# A02.7.3: diagnostics must not loosen the existing WER gate or select a
# profile based on the oracle. Native inference is an explicit separate run.
def test_recovery_wer_failure_has_sanitized_metrics(monkeypatch):
    from tapi_gate0.asset_asr_recovery import _score
    _,meta,r=positive(monkeypatch)
    r["segments"][0]["text"]="palavra errada"
    with pytest.raises(a.ASRFixtureQualityError,match="ASR_FIXTURE_WER_GATE") as exc:
        a.result_from_output(meta,emit(r))
    assert exc.value.quality["wer"]>0.50
    assert exc.value.quality["reference_words"]==8
    assert exc.value.quality["hypothesis_words"]==2
    assert "palavra errada" not in str(exc.value)
    score=_score("inventory",meta,emit(r))
    assert score["quality_passed"] is False and score["values"] is None
    assert score["semantic_exact_match"] is False


def test_recovery_context_profile_pin_and_no_reference_prompt(monkeypatch):
    monkeypatch.setattr(a,"_runtime",lambda p:{"checkpoint":"a"})
    data,meta=a.fixture("silence")
    base,code=a._plan(data,meta,"C:/trusted/medium")
    candidate,child=a._plan(data,meta,"C:/trusted/medium",profile="context_500ms")
    assert base["configuration_sha256"]!=candidate["configuration_sha256"]
    assert base["input_sha256"]==candidate["input_sha256"]
    assert "profile='context_500ms'" in child and "profile=" not in code
    assert a.REFERENCE not in child
    with pytest.raises(ValueError,match="RECOVERY_PROFILE"):
        a._plan(data,meta,"C:/trusted/medium",profile="arbitrary")


def test_recovery_context_decodes_padding_and_preserves_vad(monkeypatch):
    from tapi_gate0 import multimodal_asr as decoder
    raw=b"\x01\x00"*64000
    calls=[]
    def infer(model,chunk):
        calls.append(chunk)
        return {"pcm_sha256":sha256(chunk).hexdigest(),
                "segments":[{"start_s":0.4,"end_s":1.6,"text":"Salve este conteúdo."}]}
    monkeypatch.setattr(decoder,"_transcribe",infer)
    result=a._transcribe_context(None,raw,[{"start":16000,"end":32000}])
    assert len(calls[0])==64000
    assert result["segments"]==[{"start_s":1.0,"end_s":2.0,"text":"Salve este conteúdo.",
                                  "region_start_sample":16000,"region_end_sample":32000}]
    assert result["asr_calls"]==1 and result["pcm_sha256"]==sha256(raw).hexdigest()
    def outside(model,chunk):
        return {"pcm_sha256":sha256(chunk).hexdigest(),
                "segments":[{"start_s":0.0,"end_s":1.6,"text":"irrelevante"}]}
    monkeypatch.setattr(decoder,"_transcribe",outside)
    with pytest.raises(ValueError,match="CONTEXT_TIMESTAMP"):
        a._transcribe_context(None,raw,[{"start":16000,"end":32000}])


def test_recovery_tts_utf8_transport_only_fixed_cta(monkeypatch,tmp_path):
    from types import SimpleNamespace
    exe=tmp_path/"fake.exe";exe.write_bytes(b"x")
    monkeypatch.setattr(a.shutil,"which",lambda name:str(exe))
    calls=[]
    def run(args,**kw):
        calls.append((args,kw))
        return SimpleNamespace(stdout=b"\x01\x00"*16)
    monkeypatch.setattr(a.subprocess,"run",run)
    a._authored_fixture("cta",transport="utf8_stdin")
    assert calls[0][0][-1]=="--stdin"
    assert calls[0][1]["input"]==a.SHARED_SPEECH["cta"].encode("utf-8")
    assert a.SHARED_SPEECH["cta"] not in calls[0][0]
    with pytest.raises(ValueError,match="TTS_TRANSPORT"):
        a._authored_fixture("inventory",transport="utf8_stdin")
    with pytest.raises(ValueError,match="SPEECH_NOT_AUTHORED"):
        a._speech_pcm("arbitrary",transport="utf8_stdin")


def test_recovery_semantic_diagnostic_does_not_join_fragments():
    from tapi_gate0.asset_asr_recovery import _semantic
    assert _semantic(["Salve","este conteúdo."])["tipo_cta"] is None
    assert _semantic(["Salve este conteúdo."])["tipo_cta"]=="salvar"
    assert _semantic(["Confira o estoque."])["tema_principal"]=="gestão"


def test_recovery_context_rejection_is_never_a_processor_observation():
    from tapi_gate0.asset_asr_recovery import _score
    _,meta=a.fixture("silence")
    data=emit({"pcm_sha256":meta["pcm_sha256"],"diagnostic_error":"ASR_RECOVERY_CONTEXT_TIMESTAMP"})
    score=_score("silence",meta,data,profile="context_500ms")
    assert score["quality_passed"] is False and score["values"] is None
    assert score["error_code"]=="ASR_RECOVERY_CONTEXT_TIMESTAMP"
    with pytest.raises(ValueError,match="OUTPUT_BINDING"):
        a.result_from_output(meta,data)
    with pytest.raises(ValueError,match="OUTPUT_BINDING"):
        _score("silence",meta,data,profile="baseline")


def test_recovery_word_context_preserves_words_and_original_vad(monkeypatch):
    from tapi_gate0 import multimodal_asr as decoder
    raw=b"\x01\x00"*64000
    def infer(model,chunk,**options):
        assert options=={"word_timestamps":True}
        assert len(chunk)==64000
        return {"pcm_sha256":sha256(chunk).hexdigest(),"segments":[{
            "start_s":0.0,"end_s":2.0,"text":"Salve este conteúdo.",
            "words":[{"start_s":0.45,"end_s":0.7,"text":" Salve"},
                     {"start_s":0.7,"end_s":0.9,"text":" este"},
                     {"start_s":0.9,"end_s":1.45,"text":" conteúdo."}]}]}
    monkeypatch.setattr(decoder,"_transcribe",infer)
    result=a._transcribe_word_context(None,raw,[{"start":16000,"end":32000}])
    assert result["segments"]==[{"start_s":1.0,"end_s":1.95,"text":"Salve este conteúdo.",
        "region_start_sample":16000,"region_end_sample":32000}]
    assert result["pcm_sha256"]==sha256(raw).hexdigest()


@pytest.mark.parametrize("words,code",[
    ([{"start_s":0.1,"end_s":0.2,"text":" Salve"},{"start_s":0.7,"end_s":1.4,"text":" este"}],
     "WORD_TIMESTAMP"),
    ([{"start_s":0.6,"end_s":1.4,"text":" este"}],"WORD_TEXT_MISMATCH"),
])
def test_recovery_word_context_rejects_unsupported_or_missing_words(monkeypatch,words,code):
    from tapi_gate0 import multimodal_asr as decoder
    raw=b"\x01\x00"*64000
    monkeypatch.setattr(decoder,"_transcribe",lambda m,p,**kw:{
        "pcm_sha256":sha256(p).hexdigest(),"segments":[{"text":"Salve este","words":words}]})
    with pytest.raises(a.ASRContextRejected,match=code):
        a._transcribe_word_context(None,raw,[{"start":16000,"end":32000}])


def test_recovery_round_summary_no_vacuous_pass():
    from tapi_gate0.asset_asr_recovery import _summaries,CASES,ROUNDS
    profiles=ROUNDS["v2"]
    rows=[{"case":case,"profile":profiles[0],"transport":"argv","quality_passed":True,
        "semantic_exact_match":True,"matches_v1_pcm":True} for case in CASES]
    summary=_summaries(rows,profiles)
    assert set(summary)==set(profiles)
    assert summary[profiles[0]]["engineering_gate_passed"]
    assert not summary[profiles[1]]["engineering_gate_passed"]
    rows[0]["matches_v1_pcm"]=False
    assert not _summaries(rows,profiles)[profiles[0]]["engineering_gate_passed"]
    assert not _summaries(rows[1:],profiles)[profiles[0]]["complete"]
