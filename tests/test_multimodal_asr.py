import hashlib
import json
from types import SimpleNamespace

import pytest

from tapi_gate0 import multimodal_asr as asr


def test_wer_normalization_and_edits():
    assert asr.word_errors("Olá, seu negócio!", "OLÁ seu negócio.")["wer"]==0
    assert asr.word_errors("caixa da empresa","caixa empresa")["word_errors"]==1
    assert asr.word_errors("vendas","vendas hoje")["wer"]==1
    assert asr.word_errors("negócio","negocio")["wer"]==1
    assert asr.word_errors("","ruído")["wer"] is None
    assert asr.word_errors("","ruído")["word_errors"]==1


def _cases():
    return [{"case_id":cid,**asr.word_errors(text,text)} for cid,text,_ in asr.SPEECH_FIXTURES]+[
        {"case_id":cid,**asr.word_errors("","")} for cid in asr.NEGATIVE_FIXTURES]


def test_gate_requires_speech_and_negative_partition():
    rows=_cases()
    assert asr.evaluate_cases(rows)["engineering_gate_passed"]
    assert not asr.evaluate_cases(rows[:-1])["engineering_gate_passed"]
    rows[-1].update(asr.word_errors("","obrigado"))
    assert not asr.evaluate_cases(rows)["engineering_gate_passed"]
    rows=_cases()
    rows[0].update(asr.word_errors(asr.SPEECH_FIXTURES[0][1],""))
    assert not asr.evaluate_cases(rows)["engineering_gate_passed"]


def test_checkpoint_must_match_published_weights_and_exact_file_set(tmp_path,monkeypatch):
    for name in asr.REQUIRED_FILES:
        (tmp_path/name).write_bytes(name.encode())
    with pytest.raises(asr.ASRError,match="WEIGHTS_DIGEST"):
        asr.verify_checkpoint(tmp_path)
    monkeypatch.setattr(asr,"MODEL_SHA256",hashlib.sha256(b"model.bin").hexdigest())
    proof=asr.verify_checkpoint(tmp_path)
    assert proof["weights_digest_verified"] and not proof["supporting_files_independently_verified"]
    assert set(proof["file_sha256"])==set(asr.REQUIRED_FILES)
    (tmp_path/"preprocessor_config.json").write_text("{}")
    with pytest.raises(asr.ASRError,match="FILE_SET"):
        asr.verify_checkpoint(tmp_path)


def test_requires_tokenizer_prevents_fallback(tmp_path):
    (tmp_path/"model.bin").write_bytes(b"invalid")
    with pytest.raises(asr.ASRError,match="FILE_SET"):
        asr.verify_checkpoint(tmp_path)


def test_transcribe_uses_local_pcm_and_validates_timestamps():
    raw=asr._negative_pcm("silence")
    class Fake:
        def transcribe(self,pcm,**options):
            assert pcm.shape==(48000,)
            assert options["language"]=="pt" and options["initial_prompt"] is None
            assert options["vad_filter"] is False and options["temperature"]==0
            return iter([SimpleNamespace(start=0.1,end=1.0,text="Teste")]),SimpleNamespace(language="pt",duration=3.)
    r=asr._transcribe(Fake(),raw)
    assert r["transcript"]=="Teste" and not r["reference_prompt_used"]
    assert r["pcm_sha256"]==hashlib.sha256(raw).hexdigest()
    assert r["segments"][0]["text_sha256"]==hashlib.sha256(b"Teste").hexdigest()


@pytest.mark.parametrize("start,end",[(0,4),(-1,1),(1,0),(float("nan"),1)])
def test_invalid_segments_fail_closed(start,end):
    class Fake:
        def transcribe(self,pcm,**options):
            return [SimpleNamespace(start=start,end=end,text="texto")],SimpleNamespace(language="pt",duration=3.)
    with pytest.raises(asr.ASRError,match="SEGMENT_INVALID"):
        asr._transcribe(Fake(),asr._negative_pcm("tone"))


def test_cli_asr_requires_local_checkpoint_and_does_not_run_model(tmp_path,monkeypatch,capsys):
    from scripts import a6_multimodal_readiness as cli
    monkeypatch.setattr(cli,"ROOT",tmp_path)
    def forbidden(*args):
        pytest.fail("model must not run")
    monkeypatch.setattr(asr,"run_asr_fixture_benchmark",forbidden)
    assert cli.main(["--synthetic-asr","--report-name","asr.json"])==2
    assert json.loads(capsys.readouterr().out)["code"]=="ASR_LOCAL_MODEL_DIRECTORY_REQUIRED"
    assert cli.main(["--synthetic-temporal","--model-dir",str(tmp_path),"--report-name","asr.json"])==2
    assert json.loads(capsys.readouterr().out)["code"]=="ASR_MODEL_MODE_REQUIRED"
    assert not (tmp_path/"artifacts"/"private"/"asr.json").exists()


def test_negative_pcm_is_bounded_and_distinct():
    a,b=asr._negative_pcm("silence"),asr._negative_pcm("tone")
    assert len(a)==len(b)==96000 and not any(a) and any(b)


def test_tts_generated_pcm_when_local_tools_available(tmp_path):
    import shutil
    espeak,ffmpeg=shutil.which("espeak-ng"),shutil.which("ffmpeg")
    if not espeak or not ffmpeg:
        pytest.skip("local eSpeak NG/FFmpeg missing")
    cid,text,rate=asr.SPEECH_FIXTURES[0]
    raw=asr._speech_pcm(espeak,ffmpeg,tmp_path,cid,text,rate)
    assert 0.5<=len(raw)/(2*asr.SAMPLE_RATE)<=asr.MAX_SECONDS
    assert len(raw)%2==0 and any(raw)


def test_asr_report_no_overwrite_and_no_private_text_on_stdout(tmp_path,monkeypatch,capsys):
    from scripts import a6_multimodal_readiness as cli
    monkeypatch.setattr(cli,"ROOT",tmp_path)
    calls=[]
    def fixture(model_dir):
        calls.append(model_dir)
        return {"cases":[{"case_id":"sales","reference_words":7,"hypothesis_words":7,
                          "word_errors":0,"wer":0,"duration_s":3.,"inference_ms":100,
                          "real_time_factor":0.033333,"transcript":"private fixture text"}],
                "engineering_gate_passed":True,"synthetic_only":True}
    monkeypatch.setattr(asr,"run_asr_fixture_benchmark",fixture)
    args=["--synthetic-asr","--model-dir",str(tmp_path),"--report-name","asr.json"]
    assert cli.main(args)==0
    output=capsys.readouterr().out
    assert "private fixture text" not in output
    assert json.loads(output)["case_summary"][0]["wer"]==0
    assert json.loads((tmp_path/"artifacts"/"private"/"asr.json").read_text())["cases"][0]["transcript"]=="private fixture text"
    assert cli.main(args)==2
    assert len(calls)==1


def test_medium_requires_its_own_digest(tmp_path,monkeypatch):
    for name in asr.REQUIRED_FILES:
        (tmp_path/name).write_bytes(name.encode())
    monkeypatch.setattr(asr,"MEDIUM_SHA256",hashlib.sha256(b"model.bin").hexdigest())
    proof=asr.verify_checkpoint(tmp_path,"medium")
    assert proof["model_id"]==asr.MEDIUM_MODEL_ID
    assert proof["model_revision"]==asr.MEDIUM_REVISION
    with pytest.raises(asr.ASRError,match="WEIGHTS_DIGEST"):
        asr.verify_checkpoint(tmp_path,"small")
    with pytest.raises(asr.ASRError,match="UNKNOWN_CANDIDATE"):
        asr.verify_checkpoint(tmp_path,"arbitrary")


def test_challenge_gate_is_separate_and_keeps_thresholds():
    rows=[{"case_id":cid,**asr.word_errors(text,text)} for cid,text,_ in asr.CHALLENGE_SPEECH]+[
        {"case_id":cid,**asr.word_errors("","")} for cid in asr.CHALLENGE_NEGATIVE]
    result=asr.evaluate_cases(rows,asr.CHALLENGE_SPEECH,asr.CHALLENGE_NEGATIVE)
    assert result["engineering_gate_passed"]
    assert result["gate_criteria"]==asr.evaluate_cases(_cases())["gate_criteria"]
    assert not asr.evaluate_cases(rows)["engineering_gate_passed"]
    assert not set(cid for cid,_,_ in asr.CHALLENGE_SPEECH)&set(cid for cid,_,_ in asr.SPEECH_FIXTURES)
    rows[-1].update(asr.word_errors("","obrigado"))
    assert not asr.evaluate_cases(rows,asr.CHALLENGE_SPEECH,asr.CHALLENGE_NEGATIVE)["engineering_gate_passed"]


def test_seeded_noise_is_reproducible_bounded_and_nonzero():
    raw=asr._negative_pcm("noise")
    assert len(raw)==96000 and any(raw) and raw==asr._negative_pcm("noise")
    assert raw!=asr._negative_pcm("tone")


def test_cli_explicit_medium_challenge(tmp_path,monkeypatch,capsys):
    from scripts import a6_multimodal_readiness as cli
    monkeypatch.setattr(cli,"ROOT",tmp_path)
    calls=[]
    def fake(model_dir,candidate,suite):
        calls.append((candidate,suite))
        return {"cases":[],"engineering_gate_passed":False}
    monkeypatch.setattr(asr,"run_asr_fixture_benchmark",fake)
    assert cli.main(["--synthetic-asr","--model-dir",str(tmp_path),"--asr-candidate","medium",
                    "--asr-suite","challenge","--report-name","challenge.json"])==2
    assert calls==[("medium","challenge")]
    assert (tmp_path/"artifacts"/"private"/"challenge.json").is_file()
    capsys.readouterr()
    assert cli.main(["--synthetic-temporal","--asr-candidate","medium","--report-name","bad.json"])==2
    assert json.loads(capsys.readouterr().out)["code"]=="ASR_MODEL_MODE_REQUIRED"


def test_guard_skips_only_exact_digital_silence(monkeypatch):
    calls=[]
    def fake(model,raw):
        calls.append(raw)
        return {"transcript":"candidate"}
    monkeypatch.setattr(asr,"_transcribe",fake)
    for cid in ("silence","silence_repeat_2","silence_repeat_3"):
        raw=asr._negative_pcm(cid)
        result=asr.guarded_transcribe(None,raw)
        assert not result["inference_attempted"]
        assert result["abstention_reason"]=="EXACT_DIGITAL_SILENCE"
        assert result["transcript"]=="" and result["segments"]==[]
        assert result["pcm_sha256"]==hashlib.sha256(raw).hexdigest()
    assert not calls
    for raw in (asr._negative_pcm("tone"),asr._negative_pcm("noise"),b"\x01\x00"+bytes(95998)):
        assert asr.guarded_transcribe(None,raw)["inference_attempted"]
    assert len(calls)==3
    for raw in (b"",b"x",bytes(asr.MAX_BYTES+2)):
        with pytest.raises(asr.ASRError,match="PCM_INVALID"):
            asr.guarded_transcribe(None,raw)


def test_guarded_repeat_negatives_are_identical_and_required():
    for cid in ("silence","tone","noise"):
        assert asr._negative_pcm(cid)==asr._negative_pcm(cid+"_repeat_2")
    rows=[{"case_id":cid,**asr.word_errors(text,text)} for cid,text,_ in asr.CHALLENGE_SPEECH]+[
        {"case_id":cid,**asr.word_errors("","")} for cid in asr.GUARDED_NEGATIVE]
    assert len(rows)==13
    assert asr.evaluate_cases(rows,asr.CHALLENGE_SPEECH,asr.GUARDED_NEGATIVE)["engineering_gate_passed"]
    assert not asr.evaluate_cases(rows[:-1],asr.CHALLENGE_SPEECH,asr.GUARDED_NEGATIVE)["engineering_gate_passed"]
    rows[-2].update(asr.word_errors("","texto"))
    assert not asr.evaluate_cases(rows,asr.CHALLENGE_SPEECH,asr.GUARDED_NEGATIVE)["engineering_gate_passed"]


def test_stage_diagnostic_preserves_known_code_and_cause():
    with pytest.raises(asr.ASRError) as failure:
        with asr.asr_stage("inference","sales"):
            raise RuntimeError("private location")
    assert str(failure.value)=="ASR_INFERENCE_FAILED"
    assert failure.value.stage=="inference" and failure.value.case_id=="sales"
    assert failure.value.exception_type=="RuntimeError"
    with pytest.raises(asr.ASRError) as failure:
        with asr.asr_stage("inference","cta"):
            raise asr.ASRError("ASR_SEGMENT_INVALID")
    assert str(failure.value)=="ASR_SEGMENT_INVALID"
    assert failure.value.case_id=="cta"


def test_cli_guarded_failure_diagnostic_no_secret(tmp_path,monkeypatch,capsys):
    from scripts import a6_multimodal_readiness as cli
    monkeypatch.setattr(cli,"ROOT",tmp_path)
    def fake(model_dir,candidate,suite):
        assert (candidate,suite)==("medium","guarded")
        with asr.asr_stage("inference","delivery"):
            raise MemoryError("C:/private/path")
    monkeypatch.setattr(asr,"run_asr_fixture_benchmark",fake)
    assert cli.main(["--synthetic-asr","--model-dir",str(tmp_path),"--asr-candidate","medium",
                    "--asr-suite","guarded","--report-name","guarded.json"])==2
    stdout=capsys.readouterr().out
    assert "private/path" not in stdout
    result=json.loads(stdout)
    assert result["code"]=="ASR_INFERENCE_FAILED"
    assert result["exception_type"]=="MemoryError" and result["stage"]=="inference"
    assert result["case_id"]=="delivery"
    assert not (tmp_path/"artifacts"/"private"/"guarded.json").exists()


def test_temp_storage_preflight_fails_before_model(monkeypatch):
    monkeypatch.setattr(asr.shutil,"disk_usage",lambda _:SimpleNamespace(free=asr.MIN_TEMP_FREE_BYTES-1))
    with pytest.raises(asr.ASRError,match="TEMP_STORAGE_INSUFFICIENT"):
        asr.require_temp_capacity()


def test_cli_report_storage_preflight(tmp_path,monkeypatch,capsys):
    from scripts import a6_multimodal_readiness as cli
    monkeypatch.setattr(cli,"ROOT",tmp_path)
    monkeypatch.setattr(cli.shutil,"disk_usage",lambda _:SimpleNamespace(free=0))
    monkeypatch.setattr(asr,"run_asr_fixture_benchmark",lambda *args,**kwargs:pytest.fail("must stop before inference"))
    assert cli.main(["--synthetic-asr","--model-dir",str(tmp_path),"--report-name","blocked.json"])==2
    result=json.loads(capsys.readouterr().out)
    assert result["code"]=="TEMPORAL_REPORT_STORAGE_INSUFFICIENT"
    assert result["stage"]=="report_storage_preflight"


def test_experimental_decoder_options_and_word_alignment():
    raw=asr._negative_pcm("silence")
    class Fake:
        def transcribe(self,pcm,**opts):
            assert opts["beam_size"]==10 and opts["word_timestamps"] is True
            assert opts["initial_prompt"] is None and opts["temperature"]==0
            return [SimpleNamespace(start=0.0,end=1.0,text="Salve este",
                words=[SimpleNamespace(start=0.2,end=0.5,word=" Salve"),
                       SimpleNamespace(start=0.5,end=0.9,word=" este")])],SimpleNamespace(language="pt",duration=3.)
    r=asr._transcribe(Fake(),raw,beam_size=10,word_timestamps=True)
    assert r["segments"][0]["words"][0]=={"start_s":0.2,"end_s":0.5,"text":" Salve"}
    with pytest.raises(asr.ASRError,match="DECODING_PROFILE_INVALID"):
        asr._transcribe(Fake(),raw,beam_size=100)
