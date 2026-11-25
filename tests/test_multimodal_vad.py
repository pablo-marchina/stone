import hashlib
import json
import struct
from types import SimpleNamespace

import pytest

from tapi_gate0 import multimodal_vad as vad


def test_interval_score_exact_and_partial():
    r=vad.score_intervals([{"start":16000,"end":32000}],[{"start":16000,"end":32000}],48000)
    assert r["passed"] and r["iou"]==1 and r["max_boundary_error_s"]==0
    r=vad.score_intervals([{"start":0,"end":16000}],[{"start":8000,"end":24000}],48000)
    assert r["iou"]==pytest.approx(1/3) and not r["passed"]
    assert r["false_positive_s"]==r["missed_speech_s"]==0.5


def test_negative_empty_and_false_positive():
    assert vad.score_intervals([],[],48000)["passed"]
    assert not vad.score_intervals([{"start":0,"end":1}],[],48000)["passed"]
    assert not vad.score_intervals([], [{"start":0,"end":16000}],48000)["passed"]


@pytest.mark.parametrize("intervals",[
    [{"start":0,"end":0}],[{"start":0,"end":48001}],
    [{"start":-1,"end":2}],[{"start":True,"end":2}],
    [{"start":0,"end":10},{"start":9,"end":20}],[{"start":0,"end":1,"text":"x"}]])
def test_invalid_interval_rejected(intervals):
    with pytest.raises(vad.VADError,match="VAD_INTERVAL_INVALID"):
        vad.validate_intervals(intervals,48000)


def test_pcm_inspection_checks_bounds_and_hash():
    raw=bytes(96000)
    def detector(pcm):
        assert len(pcm)==48000 and pcm.dtype.name=="float32"
        return [{"start":0,"end":16000}]
    r=vad.inspect_pcm(raw,detector)
    assert r["pcm_sha256"]==hashlib.sha256(raw).hexdigest()
    assert r["duration_s"]==3 and r["intervals"]==[{"start":0,"end":16000}]
    with pytest.raises(vad.VADError,match="VAD_PCM_INVALID"):
        vad.inspect_pcm(b"x",detector)


def test_fixture_construction_deterministic(monkeypatch,tmp_path):
    speech=struct.pack("<hhhh",0,1000,-1000,0)*8000
    monkeypatch.setattr(vad,"_speech_pcm",lambda *args:speech)
    rows=vad.fixture_rows(None,None,tmp_path)
    assert len(rows)==9
    assert len([x for x in rows if x[2]])==6
    assert rows==vad.fixture_rows(None,None,tmp_path)
    for cid,raw,expected in rows:
        n=vad._validate_pcm(raw)
        vad.validate_intervals(expected,n)
    quiet=next(row for row in rows if row[0]=="quiet_speech")
    assert max(abs(x[0]) for x in struct.iter_unpack("<h",quiet[1]))==250
    mixed=next(row for row in rows if row[0]=="speech_with_noise")
    assert mixed[1]!=rows[0][1] and mixed[2]==rows[0][2]


def test_cli_vad_private_report_no_overwrite(tmp_path,monkeypatch,capsys):
    from scripts import a6_multimodal_readiness as cli
    monkeypatch.setattr(cli,"ROOT",tmp_path)
    monkeypatch.setattr(vad,"run_vad_fixture_benchmark",lambda:{"cases":[],"engineering_gate_passed":True})
    args=["--synthetic-vad","--report-name","vad.json"]
    assert cli.main(args)==0
    assert json.loads(capsys.readouterr().out)["report_name"]=="vad.json"
    assert cli.main(args)==2
    assert cli.main(["--synthetic-vad","--model-dir",str(tmp_path),"--report-name","blocked.json"])==2
    assert not (tmp_path/"artifacts"/"private"/"blocked.json").exists()
