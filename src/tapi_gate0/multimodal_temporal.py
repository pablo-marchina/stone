"""IMP-063/136: bounded temporal measurements on generated local fixtures.

No social-platform acquisition, real-media authorization, semantic hook, cut
score or RubricAssessment. The low-level reducer receives raw sampled frames;
only the fixture runner below invokes local media tools.
"""
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import json
import shutil
import subprocess
import tempfile

VERSION = "bd-temporal-fixture.v1"
WIDTH = HEIGHT = 64
FPS = 4
FRAME_BYTES = WIDTH * HEIGHT
MAX_SECONDS = 8
MAX_FRAMES = FPS * MAX_SECONDS
THRESHOLD = 0.20  # mean normalized absolute grayscale difference, not a semantic cut
FIXTURES = {
    "static": {"colors": ("black", "black", "black"), "expected": [], "audio": False},
    "two_transitions": {"colors": ("black", "white", "black"), "expected": [1.0, 2.0], "audio": True},
    "one_transition": {"colors": ("white", "white", "black"), "expected": [2.0], "audio": False},
}


class TemporalError(ValueError):
    pass


def _digest(data):
    return sha256(data).hexdigest()


def sample_measurements(raw):
    if not raw or len(raw) % FRAME_BYTES or len(raw) > MAX_FRAMES * FRAME_BYTES:
        raise TemporalError("TEMPORAL_INVALID_FRAME_PARTITION")
    frames = [raw[i:i+FRAME_BYTES] for i in range(0, len(raw), FRAME_BYTES)]
    transitions = []
    for i, (previous, current) in enumerate(zip(frames, frames[1:]), 1):
        difference = sum(abs(a-b) for a,b in zip(previous,current)) / (255 * FRAME_BYTES)
        if difference >= THRESHOLD:
            transitions.append({"sample_time_s": i/FPS, "previous_sample_time_s": (i-1)/FPS,
                                "previous_frame_sha256": _digest(previous),
                                "frame_sha256": _digest(current),
                                "normalized_difference": round(difference,6)})
    return {"samples":len(frames), "sample_fps":FPS, "sample_width":WIDTH,
            "sample_height":HEIGHT, "threshold":THRESHOLD,
            "timestamp_kind":"resampled_uniform_timeline_not_original_pts",
            "opening_samples":[{"sample_time_s":i/FPS,"frame_sha256":_digest(frame)}
                               for i,frame in enumerate(frames) if i/FPS < 3],
            "transition_candidates":transitions,
            "transition_candidate_count":len(transitions),
            "semantic_hook_assessed":False,"rubric_cut_score_assessed":False}


def _run(binary, args, *, timeout=30, output_limit=2_000_000):
    if not binary:
        raise TemporalError("TEMPORAL_LOCAL_BINARY_UNAVAILABLE")
    try:
        proc = subprocess.run([binary,*args], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout, check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise TemporalError("TEMPORAL_LOCAL_PROCESS_FAILED") from exc
    if proc.returncode or len(proc.stdout)>output_limit:
        raise TemporalError("TEMPORAL_LOCAL_PROCESS_FAILED")
    return proc.stdout


def _generate(ffmpeg, path, fixture):
    args=["-hide_banner","-loglevel","error","-nostdin","-n"]
    for color in fixture["colors"]:
        args.extend(["-f","lavfi","-i",f"color=c={color}:s=128x128:r=8:d=1"])
    if fixture["audio"]:
        args.extend(["-f","lavfi","-i","sine=frequency=440:sample_rate=16000:duration=3"])
    args.extend(["-filter_complex","[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]","-map","[v]"])
    if fixture["audio"]:
        args.extend(["-map","3:a","-c:a","aac"])
    args.extend(["-c:v","mpeg4","-q:v","2","-threads","1","-t","3",str(path)])
    _run(ffmpeg,args)


def _measure_generated(ffmpeg,ffprobe,path):
    # This path is only created in the private TemporaryDirectory by _generate.
    # No command-line input path, URL or user-supplied media is accepted.
    if not path.is_file() or path.stat().st_size>4_000_000:
        raise TemporalError("TEMPORAL_FIXTURE_SIZE_INVALID")
    before=_digest(path.read_bytes())
    probe=json.loads(_run(ffprobe,["-v","error","-protocol_whitelist","file,pipe",
        "-show_entries","format=duration:stream=codec_type","-of","json",str(path)]))
    duration=float(probe["format"]["duration"])
    streams=[s["codec_type"] for s in probe["streams"]]
    if not 0 < duration <= MAX_SECONDS or streams.count("video")!=1 or streams.count("audio")>1:
        raise TemporalError("TEMPORAL_FIXTURE_STREAM_INVALID")
    raw=_run(ffmpeg,["-hide_banner","-loglevel","error","-nostdin",
        "-protocol_whitelist","file,pipe","-i",str(path),"-map","0:v:0",
        "-vf",f"fps={FPS},scale={WIDTH}:{HEIGHT},format=gray",
        "-t",str(MAX_SECONDS),"-frames:v",str(MAX_FRAMES),"-threads","1","-f","rawvideo","pipe:1"],
        output_limit=MAX_FRAMES*FRAME_BYTES)
    if _digest(path.read_bytes())!=before:
        raise TemporalError("TEMPORAL_FIXTURE_CHANGED")
    return {"media_sha256":before,"duration_s":duration,"audio_stream_present":"audio" in streams,
            **sample_measurements(raw)}


def run_temporal_fixture_benchmark():
    ffmpeg,ffprobe=shutil.which("ffmpeg"),shutil.which("ffprobe")
    versions={}
    for name,binary in (("ffmpeg",ffmpeg),("ffprobe",ffprobe)):
        versions[name]=_run(binary,["-version"],output_limit=100_000).decode("utf-8","replace").splitlines()[0]
    cases=[]
    with tempfile.TemporaryDirectory(prefix="tapi-temporal-fixtures-") as temp:
        for key,fixture in FIXTURES.items():
            path=Path(temp)/(key+".mp4")
            _generate(ffmpeg,path,fixture)
            observation=_measure_generated(ffmpeg,ffprobe,path)
            actual=[r["sample_time_s"] for r in observation["transition_candidates"]]
            expected=fixture["expected"]
            timing_error=[round(abs(a-b),6) for a,b in zip(actual,expected)] if len(actual)==len(expected) else None
            passed=(timing_error is not None and all(e<=1/FPS for e in timing_error)
                    and abs(observation["duration_s"]-3)<=1/FPS
                    and observation["samples"]==3*FPS
                    and observation["audio_stream_present"] is fixture["audio"])
            cases.append({"case_id":key,"expected_transitions_s":expected,
                          "expected_audio_stream":fixture["audio"],
                          "transition_absolute_errors_s":timing_error,
                          "passed":passed,"observation":observation})
    return {"status":"TEMPORAL_FIXTURE_BENCHMARK_COMPLETED","policy_version":VERSION,
            "tool_versions":versions,"synthetic_only":True,"cases":cases,
            "cases_passed":sum(r["passed"] for r in cases),"cases_total":len(cases),
            "engineering_gate_passed":all(r["passed"] for r in cases),
            "real_media_processed":0,"external_data_accessed":False,"database_mutated":False,
            "rubric_assessments_written":0,"scientific_admissions":0,
            "independent_gold":False,"asr_evaluated":False,"vlm_evaluated":False,
            "production_approved":False,"real_media_processing_allowed":False}
