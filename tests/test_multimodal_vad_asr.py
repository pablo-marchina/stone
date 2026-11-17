import hashlib
import json
import pytest

from tapi_gate0 import multimodal_vad_asr as joint
from tapi_gate0 import multimodal_asr as asr


def test_no_speech_never_calls_whisper(monkeypatch):
    monkeypatch.setattr(asr,"_transcribe",lambda *_:pytest.fail("unexpected inference"))
    raw=bytes(96000)
    r=joint.transcribe_regions(None,raw,[])
    assert r["asr_calls"]==0 and r["transcript"]=="" and not r["inference_attempted"]
    assert r["abstention_reason"]=="NO_VAD_SPEECH_REGION"
    assert r["pcm_sha256"]==hashlib.sha256(raw).hexdigest()


def test_regions_preserve_gaps_and_hashes(monkeypatch):
    raw=bytes(16000*2*6)
    def fake(model,pcm):
        return {"pcm_sha256":hashlib.sha256(pcm).hexdigest(),
                "transcript":"teste","segments":[{"start_s":0.1,"end_s":1.1,"text":"teste"}]}
    monkeypatch.setattr(asr,"_transcribe",fake)
    r=joint.transcribe_regions(None,raw,[{"start":16000,"end":32000},{"start":64000,"end":80000}])
    assert r["asr_calls"]==2 and r["transcript"]=="teste teste"
    assert r["segments"][0]["start_s"]==1.1
    assert r["segments"][0]["end_s"]==2
    assert r["segments"][1]["start_s"]==4.1
    assert r["segments"][1]["end_s"]==5
    assert all(s["end_clipped"] for s in r["segments"])
    assert r["segments"][0]["chunk_end_s"]==1.1


def test_chunk_hash_and_excess_timestamp_fail(monkeypatch):
    raw=bytes(32000)
    monkeypatch.setattr(asr,"_transcribe",lambda *_:{"pcm_sha256":"wrong","segments":[],"transcript":""})
    with pytest.raises(asr.ASRError,match="HASH_MISMATCH"):
        joint.transcribe_regions(None,raw,[{"start":0,"end":16000}])
    monkeypatch.setattr(asr,"_transcribe",lambda m,p:{"pcm_sha256":hashlib.sha256(p).hexdigest(),
        "segments":[{"start_s":0.1,"end_s":1.3,"text":"x"}],"transcript":"x"})
    with pytest.raises(asr.ASRError,match="TIMESTAMP_INVALID"):
        joint.transcribe_regions(None,raw,[{"start":0,"end":16000}])


def test_joint_gate_checks_vad_and_negative_calls():
    ids=("inventory_padded","quiet_speech","speech_with_noise","costs_padded",
         "two_speech_regions","planning_padded","silence","tone","noise")
    rows=[]
    for cid in ids:
        ref=joint.reference_for(cid)
        rows.append({"case_id":cid,**asr.word_errors(ref,ref),"vad_score":{"passed":True},
                     "inference_attempted":bool(ref),"asr_calls":2 if cid=="two_speech_regions" else int(bool(ref))})
    assert joint.evaluate(rows)["engineering_gate_passed"]
    assert joint.evaluate(rows)["speech_reference_words"]==60
    assert joint.evaluate(rows)["total_asr_calls"]==7
    rows[-1]["asr_calls"]=1
    assert not joint.evaluate(rows)["engineering_gate_passed"]
    rows[-1]["asr_calls"]=0
    rows[0]["vad_score"]["passed"]=False
    assert not joint.evaluate(rows)["engineering_gate_passed"]


def test_cli_joint_requires_explicit_medium(tmp_path,monkeypatch,capsys):
    from scripts import a6_multimodal_readiness as cli
    monkeypatch.setattr(cli,"ROOT",tmp_path)
    monkeypatch.setattr(joint,"run_vad_asr_benchmark",lambda _:{"cases":[],"engineering_gate_passed":True})
    args=["--synthetic-vad-asr","--model-dir",str(tmp_path),"--report-name","joint.json"]
    assert cli.main(args)==2
    assert json.loads(capsys.readouterr().out)["code"]=="ASR_VAD_MEDIUM_REQUIRED"
    assert cli.main(args+["--asr-candidate","medium"])==0
    assert json.loads(capsys.readouterr().out)["report_name"]=="joint.json"
    assert cli.main(args+["--asr-candidate","medium"])==2
