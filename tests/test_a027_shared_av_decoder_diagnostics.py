"""Fail-closed, redacted decoder error telemetry; no real media/model is needed."""
from hashlib import sha256
from types import SimpleNamespace
from pathlib import Path
import subprocess
import sys

import pytest

from tapi_gate0 import asset_shared_av_fixture as shared
from tapi_gate0.asset_windows_job import JobError


def _code(binary):
    raw=b"authored-probe-only"
    dummy=SimpleNamespace(
        frame_count=5,
        pcm_samples=1,
        container_sha256=sha256(raw).hexdigest(),
        rgb_stream_sha256="0"*64,
        pcm_sha256="0"*64,
        frame_sha256="0"*64,
        temporal_sample_sha256=("0"*64,),
    )
    code=shared._decoder(binary,raw,dummy)
    compile(code,"<authored-shared-av-decoder>","exec")
    return code,raw


def test_decoder_spawn_failure_reports_only_allowlisted_stage(tmp_path):
    binary=tmp_path/"missing-authored-ffmpeg"
    assert not binary.exists()
    code,raw=_code(str(binary))
    completed=subprocess.run(
        [sys.executable,"-I","-S","-c",code],input=raw,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=10)
    assert completed.returncode==31
    assert completed.stdout==b"TAPI_AV_DECODE_FAIL:video:spawn"
    diagnostic=shared._decode_failure(completed.stdout,completed.returncode,
        {"peak_job_commit_bytes":117071872})
    assert type(diagnostic) is JobError
    assert str(diagnostic).startswith("AV_DECODE_FAILURE;stage=video;reason=spawn;exit=0x0000001f")
    assert "peak_commit_bytes=117071872" in str(diagnostic)
    assert str(binary) not in str(diagnostic)
    assert raw.decode() not in str(diagnostic)


def test_decoder_child_nonzero_reports_only_allowlisted_stage():
    code,raw=_code(sys.executable)
    completed=subprocess.run(
        [sys.executable,"-I","-S","-c",code],input=raw,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=10)
    assert completed.returncode==31
    assert completed.stdout==b"TAPI_AV_DECODE_FAIL:video:nonzero"
    assert "reason=nonzero" in str(shared._decode_failure(
        completed.stdout,completed.returncode,{}))


@pytest.mark.parametrize("output,exit_code",[
    (b"TAPI_AV_DECODE_FAIL:video:spawn",0),
    (b"TAPI_AV_DECODE_FAIL:video:path-is-secret",31),
    (b"TAPI_AV_DECODE_FAIL:audio:spawn",1),
    (b"TAPI_AV_DECODE_FAIL:video:spawn"+b"SECRET"*16,31),
    (b"some /private/file/contents",1),
])
def test_decoder_unknown_markers_are_fail_closed_and_redacted(output,exit_code):
    diagnosis=shared._decode_failure(output,exit_code,{})
    assert type(diagnosis) is JobError
    assert "PROBE_OUTPUT_INVALID" in str(diagnosis)
    assert "SECRET" not in str(diagnosis)
    assert "/private/" not in str(diagnosis)
