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
