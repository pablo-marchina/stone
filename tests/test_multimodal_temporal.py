import json
import shutil

import pytest

from tapi_gate0.multimodal_temporal import (
    FRAME_BYTES, MAX_FRAMES, TemporalError, sample_measurements, run_temporal_fixture_benchmark,
)


def test_sample_measurements_opening_and_transition_provenance():
    black=bytes(FRAME_BYTES)
    white=bytes([255])*FRAME_BYTES
    r=sample_measurements(black*4+white*4+black*4)
    assert r["samples"]==12 and len(r["opening_samples"])==12
    assert [t["sample_time_s"] for t in r["transition_candidates"]]==[1.,2.]
    assert r["transition_candidates"][0]["previous_sample_time_s"]==.75
    assert r["transition_candidates"][0]["frame_sha256"]==r["opening_samples"][4]["frame_sha256"]
    assert r["transition_candidates"][0]["normalized_difference"]==1.
    assert not r["semantic_hook_assessed"] and not r["rubric_cut_score_assessed"]
    assert r["timestamp_kind"]=="resampled_uniform_timeline_not_original_pts"


@pytest.mark.parametrize("raw",[b"",b"x",bytes(FRAME_BYTES*(MAX_FRAMES+1))])
def test_bad_frame_partition(raw):
    with pytest.raises(TemporalError,match="PARTITION"):
        sample_measurements(raw)


def test_static_and_small_changes_are_not_negative_rubric_claims():
    r=sample_measurements(bytes(FRAME_BYTES)+bytes([5])*FRAME_BYTES)
    assert r["transition_candidate_count"]==0
    assert not r["rubric_cut_score_assessed"]


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                    reason="local FFmpeg/ffprobe unavailable")
def test_real_local_generated_video_benchmark():
    r=run_temporal_fixture_benchmark()
    assert r["engineering_gate_passed"] and r["cases_passed"]==r["cases_total"]==3
    assert r["real_media_processed"]==r["scientific_admissions"]==0
    assert not r["external_data_accessed"] and not r["asr_evaluated"] and not r["vlm_evaluated"]
    assert not r["real_media_processing_allowed"]
    assert all(len(c["observation"]["media_sha256"])==64 for c in r["cases"])


def test_readiness_never_grants_external_media(capsys):
    from scripts.a6_multimodal_readiness import main
    assert main(["--check-ready"])==0
    r=json.loads(capsys.readouterr().out)
    assert not r["real_media_processing_allowed"] and not r["asr_checkpoint_verified"]
    assert r["instagram_media_policy"]=="EXTERNAL_DENIED_PENDING_VERIFIED_GRANT"
    assert r["youtube_media_policy"]=="EXTERNAL_DENIED_PENDING_VERIFIED_GRANT"


def test_cli_does_not_accept_media_input(tmp_path,monkeypatch,capsys):
    from scripts import a6_multimodal_readiness as runner
    monkeypatch.setattr(runner,"ROOT",tmp_path)
    with pytest.raises(SystemExit):
        runner.main(["--synthetic-temporal","--media-path","video.mp4"])
    assert runner.main(["--synthetic-temporal","--report-name","../invalid.json"])==2
    assert json.loads(capsys.readouterr().out)["code"]=="TEMPORAL_PRIVATE_REPORT_NAME_REQUIRED"
    assert not (tmp_path/"artifacts").exists()


def test_private_report_and_no_overwrite(tmp_path,monkeypatch,capsys):
    from scripts import a6_multimodal_readiness as runner
    monkeypatch.setattr(runner,"ROOT",tmp_path)
    calls=[]
    def fixture():
        calls.append(True)
        return {"cases":[],"engineering_gate_passed":False,"synthetic_only":True}
    monkeypatch.setattr(runner,"run_temporal_fixture_benchmark",fixture)
    args=["--synthetic-temporal","--report-name","test.json"]
    assert runner.main(args)==2
    assert json.loads(capsys.readouterr().out)["report_name"]=="test.json"
    target=tmp_path/"artifacts"/"private"/"test.json"
    assert json.loads(target.read_text())["cases"]==[]
    assert runner.main(args)==2
    assert json.loads(capsys.readouterr().out)["code"]=="TEMPORAL_PRIVATE_REPORT_EXISTS"
    assert calls==[True]
