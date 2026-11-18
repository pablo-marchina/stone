"""Real FFmpeg temporal extraction on three exact authored MP4 fixtures only.

Pinned byte fixtures, runtime fingerprint and exact decoded frame oracle.
No external media, caller-provided paths, model, rubric or evidence admission.
"""
from base64 import b64decode
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import shutil

from . import asset_windows_job as windows
from .asset_processor_results import Frame, Transition, Temporal, ProcessorResult, encode, decode, validate_binding

METHOD = "synthetic-temporal-ffmpeg-v4"
LIMITS = windows.JobLimits(memory_mib=512,cpu_user_seconds=10,active_processes=2,wall_seconds=30)
FRAME_BYTES = 4096
FRAME_COUNT = 12
# Each file was generated locally with FFmpeg lavfi, 64x64, 4 fps,
# three one-second colors, MPEG4, faststart, no audio or source data.
FIXTURES = {
    'static': ('AAAAHGZ0eXBpc29tAAACAGlzb21pc28ybXA0MQAAA4Rtb292AAAAbG12aGQAAAAAAAAAAAAAAAAAAAPoAAALuAABAAABAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAAACr3RyYWsAAABcdGtoZAAAAAMAAAAAAAAAAAAAAAEAAAAAAAALuAAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAQAAAAEAAAAAAACRlZHRzAAAAHGVsc3QAAAAAAAAAAQAAC7gAAAAAAAEAAAAAAidtZGlhAAAAIG1kaGQAAAAAAAAAAAAAAAAAAEAAAADAAFXEAAAAAAAtaGRscgAAAAAAAAAAdmlkZQAAAAAAAAAAAAAAAFZpZGVvSGFuZGxlcgAAAAHSbWluZgAAABR2bWhkAAAAAQAAAAAAAAAAAAAAJGRpbmYAAAAcZHJlZgAAAAAAAAABAAAADHVybCAAAAABAAABknN0YmwAAADqc3RzZAAAAAAAAAABAAAA2m1wNHYAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAQABAAEgAAABIAAAAAAAAAAETTGF2YzYxLjE5LjEwMSBtcGVnNAAAAAAAAAAAAAAAAAAY//8AAABgZXNkcwAAAAADgICATwABAASAgIBBIBEAAAAAAw1AAAABpQWAgIAvAAABsAEAAAG1iRMAAAEAAAABIADEjYgAJQIECBRjAAABskxhdmM2MS4xOS4xMDEGgICAAQIAAAAQcGFzcAAAAAEAAAABAAAAFGJ0cnQAAAAAAAMNQAAAAaUAAAAYc3R0cwAAAAAAAAABAAAADAAAEAAAAAAUc3RzcwAAAAAAAAABAAAAAQAAABxzdHNjAAAAAAAAAAEAAAABAAAADAAAAAEAAABEc3RzegAAAAAAAAAAAAAADAAAADsAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAABRzdGNvAAAAAAAAAAEAAAOwAAAAYXVkdGEAAABZbWV0YQAAAAAAAAAhaGRscgAAAAAAAAAAbWRpcmFwcGwAAAAAAAAAAAAAAAAsaWxzdAAAACSpdG9vAAAAHGRhdGEAAAABAAAAAExhdmY2MS43LjEwMwAAAAhmcmVlAAAApm1kYXQAAAGzABAHAAABthMCjBHtv422/jbb+Ntv422/jbb+Ntv422/jbb+Ntv422/jbb+Ntv422/jbb+Ntv3wAAAbZXgR//9wAAAbZbAR//9wAAAbZfgR//9wAAAbZpgI//+wAAAbZXgR//9wAAAbZbAR//9wAAAbZfgR//9wAAAbZpgI//+wAAAbZXgR//9wAAAbZbAR//9wAAAbZfgR//9w==', '1842cfaed4e615472613278e211c10c190ae4a4cfb558fe77f08d16b8df3e100', (0, 0, 0)),
    'two': ('AAAAHGZ0eXBpc29tAAACAGlzb21pc28ybXA0MQAAA4xtb292AAAAbG12aGQAAAAAAAAAAAAAAAAAAAPoAAALuAABAAABAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAAACt3RyYWsAAABcdGtoZAAAAAMAAAAAAAAAAAAAAAEAAAAAAAALuAAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAQAAAAEAAAAAAACRlZHRzAAAAHGVsc3QAAAAAAAAAAQAAC7gAAAAAAAEAAAAAAi9tZGlhAAAAIG1kaGQAAAAAAAAAAAAAAAAAAEAAAADAAFXEAAAAAAAtaGRscgAAAAAAAAAAdmlkZQAAAAAAAAAAAAAAAFZpZGVvSGFuZGxlcgAAAAHabWluZgAAABR2bWhkAAAAAQAAAAAAAAAAAAAAJGRpbmYAAAAcZHJlZgAAAAAAAAABAAAADHVybCAAAAABAAABmnN0YmwAAADqc3RzZAAAAAAAAAABAAAA2m1wNHYAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAQABAAEgAAABIAAAAAAAAAAETTGF2YzYxLjE5LjEwMSBtcGVnNAAAAAAAAAAAAAAAAAAY//8AAABgZXNkcwAAAAADgICATwABAASAgIBBIBEAAAAAAw1AAAACsAWAgIAvAAABsAEAAAG1iRMAAAEAAAABIADEjYgAJQIECBRjAAABskxhdmM2MS4xOS4xMDEGgICAAQIAAAAQcGFzcAAAAAEAAAABAAAAFGJ0cnQAAAAAAAMNQAAAArAAAAAYc3R0cwAAAAAAAAABAAAADAAAEAAAAAAcc3RzcwAAAAAAAAADAAAAAQAAAAUAAAAJAAAAHHN0c2MAAAAAAAAAAQAAAAEAAAAMAAAAAQAAAERzdHN6AAAAAAAAAAAAAAAMAAAAOwAAAAkAAAAJAAAACQAAADsAAAAJAAAACQAAAAkAAAA7AAAACQAAAAkAAAAJAAAAFHN0Y28AAAAAAAAAAQAAA7gAAABhdWR0YQAAAFltZXRhAAAAAAAAACFoZGxyAAAAAAAAAABtZGlyYXBwbAAAAAAAAAAAAAAAACxpbHN0AAAAJKl0b28AAAAcZGF0YQAAAAEAAAAATGF2ZjYxLjcuMTAzAAAACGZyZWUAAAEKbWRhdAAAAbMAEAcAAAG2EwKMEe2/jbb+Ntv422/jbb+Ntv422/jbb+Ntv422/jbb+Ntv422/jbb+Ntv422/fAAABtleBH//3AAABtlsBH//3AAABtl+BH//3AAABswAQRwAAAbYTAowdbb+Ntv422/jbb+Ntv422/jbb+Ntv422/jbb+Ntv422/jbb+Ntv422/jbb98AAAG2V4Ef//cAAAG2WwEf//cAAAG2X4Ef//cAAAGzABCHAAABthMCjBHtv422/jbb+Ntv422/jbb+Ntv422/jbb+Ntv422/jbb+Ntv422/jbb+Ntv3wAAAbZXgR//9wAAAbZbAR//9wAAAbZfgR//9w==', '58dbbf9162d09b5b7d1196e0d6dc6917bbb9a1bbad85ba8e6a4b7f318dc628f8', (0, 255, 0)),
    'one': ('AAAAHGZ0eXBpc29tAAACAGlzb21pc28ybXA0MQAAA4htb292AAAAbG12aGQAAAAAAAAAAAAAAAAAAAPoAAALuAABAAABAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAAACs3RyYWsAAABcdGtoZAAAAAMAAAAAAAAAAAAAAAEAAAAAAAALuAAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAQAAAAEAAAAAAACRlZHRzAAAAHGVsc3QAAAAAAAAAAQAAC7gAAAAAAAEAAAAAAittZGlhAAAAIG1kaGQAAAAAAAAAAAAAAAAAAEAAAADAAFXEAAAAAAAtaGRscgAAAAAAAAAAdmlkZQAAAAAAAAAAAAAAAFZpZGVvSGFuZGxlcgAAAAHWbWluZgAAABR2bWhkAAAAAQAAAAAAAAAAAAAAJGRpbmYAAAAcZHJlZgAAAAAAAAABAAAADHVybCAAAAABAAABlnN0YmwAAADqc3RzZAAAAAAAAAABAAAA2m1wNHYAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAQABAAEgAAABIAAAAAAAAAAETTGF2YzYxLjE5LjEwMSBtcGVnNAAAAAAAAAAAAAAAAAAY//8AAABgZXNkcwAAAAADgICATwABAASAgIBBIBEAAAAAAw1AAAACKgWAgIAvAAABsAEAAAG1iRMAAAEAAAABIADEjYgAJQIECBRjAAABskxhdmM2MS4xOS4xMDEGgICAAQIAAAAQcGFzcAAAAAEAAAABAAAAFGJ0cnQAAAAAAAMNQAAAAioAAAAYc3R0cwAAAAAAAAABAAAADAAAEAAAAAAYc3RzcwAAAAAAAAACAAAAAQAAAAkAAAAcc3RzYwAAAAAAAAABAAAAAQAAAAwAAAABAAAARHN0c3oAAAAAAAAAAAAAAAwAAAA7AAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAADsAAAAJAAAACQAAAAkAAAAUc3RjbwAAAAAAAAABAAADtAAAAGF1ZHRhAAAAWW1ldGEAAAAAAAAAIWhkbHIAAAAAAAAAAG1kaXJhcHBsAAAAAAAAAAAAAAAALGlsc3QAAAAkqXRvbwAAABxkYXRhAAAAAQAAAABMYXZmNjEuNy4xMDMAAAAIZnJlZQAAANhtZGF0AAABswAQBwAAAbYTAowdbb+Ntv422/jbb+Ntv422/jbb+Ntv422/jbb+Ntv422/jbb+Ntv422/jbb98AAAG2V4Ef//cAAAG2WwEf//cAAAG2X4Ef//cAAAG2aYCP//sAAAG2V4Ef//cAAAG2WwEf//cAAAG2X4Ef//cAAAGzABCHAAABthMCjBHtv422/jbb+Ntv422/jbb+Ntv422/jbb+Ntv422/jbb+Ntv422/jbb+Ntv3wAAAbZXgR//9wAAAbZbAR//9wAAAbZfgR//9w==', 'a4bfc0f8cc869accc2fd12ec2a36c55416d64c022da3436af347570fedbd2e84', (255, 255, 0)),
}


def fixture(case):
    if case not in FIXTURES:
        raise ValueError("TEMPORAL_FIXTURE_UNKNOWN")
    encoded,digest,colors=FIXTURES[case]
    data=b64decode(encoded,validate=True)
    if sha256(data).hexdigest()!=digest:
        raise ValueError("TEMPORAL_FIXTURE_PIN")
    expected=b"".join(bytes([color])*(4*FRAME_BYTES) for color in colors)
    return data,expected


def _runtime():
    found=shutil.which("ffmpeg")
    if not found:
        raise ValueError("TEMPORAL_FFMPEG_REQUIRED")
    binary=Path(found).resolve(strict=True)
    if not binary.is_file() or not 0<binary.stat().st_size<=512*1024*1024:
        raise ValueError("TEMPORAL_FFMPEG_INVALID")
    h=sha256()
    with binary.open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            h.update(block)
    return str(binary),h.hexdigest()


def _child(binary, data):
    # The trusted child waits for a complete exact input before spawning FFmpeg.
    # Fixed dimensions/count bound the output by construction. No local media file.
    args=[binary,"-hide_banner","-loglevel","error","-nostdin","-protocol_whitelist","pipe",
          "-threads","1","-f","mp4","-i","pipe:0","-map","0:v:0","-an",
          "-filter_threads","1","-vf","fps=4,scale=64:64,format=gray",
          "-frames:v","12","-threads","1","-f","rawvideo","pipe:1"]
    return f'''import sys, hashlib, subprocess
x=sys.stdin.buffer.read({len(data)+1})
if len(x)!={len(data)} or hashlib.sha256(x).hexdigest()!={sha256(data).hexdigest()!r}:
    sys.exit(2)
r=subprocess.run({args!r},input=x,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,shell=False,close_fds=True)
if r.returncode or len(r.stdout)!={FRAME_COUNT*FRAME_BYTES}:
    sys.exit(3)
sys.stdout.buffer.write(r.stdout)
'''


def plan(case):
    data,expected=fixture(case)
    binary,runtime_sha=_runtime()
    code=_child(binary,data)
    config={"method":METHOD,"case":case,"input_sha256":sha256(data).hexdigest(),
            "decoded_sha256":sha256(expected).hexdigest(),"runtime_sha256":runtime_sha,
            "code_sha256":sha256(code.encode()).hexdigest(),"limits":asdict(LIMITS),
            "job_flags":windows.FLAGS,"job_name":windows.JOB_NAME,"reducer":"bd-temporal-fixture.v1"}
    pin=sha256(json.dumps(config,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return {**config,"configuration_sha256":pin},code


def result_from_frames(case,raw):
    from .multimodal_temporal import sample_measurements
    _,expected=fixture(case)
    if type(raw) is not bytes or raw!=expected:
        raise ValueError("TEMPORAL_FIXTURE_DECODE_MISMATCH")
    measured=sample_measurements(raw)
    candidates=tuple(Transition(previous=Frame(time_ms=int(x["previous_sample_time_s"]*1000),
        frame_sha256=x["previous_frame_sha256"],timeline="resampled_uniform"),
        current=Frame(time_ms=int(x["sample_time_s"]*1000),frame_sha256=x["frame_sha256"],
        timeline="resampled_uniform"),normalized_difference=x["normalized_difference"])
        for x in measured["transition_candidates"])
    return Temporal(samples=measured["samples"],threshold=measured["threshold"],candidates=candidates)


def run_temporal_fixture_windows(queue,vault,store,lease):
    from .asset_jobs import AssetJobQueue
    from .asset_indexed_vault import IndexedAssetVault
    from .asset_derived_payloads import DerivedPayloadStore
    from .asset_rights import AssetRightsDenied
    if (not isinstance(queue,AssetJobQueue) or not isinstance(vault,IndexedAssetVault)
            or queue.index.engine is not vault._index.engine or not isinstance(store,DerivedPayloadStore)
            or store.queue is not queue):
        raise AssetRightsDenied("TEMPORAL_FIXTURE_HOST_MISMATCH")
    try:
        windows._native_api()
        spec,ref=queue.check_lease(lease)
        case=next((c for c,(_,digest,_) in FIXTURES.items() if digest==ref.target.sha256),None)
        if case is None or spec.processor!="temporal" or spec.method_version!=METHOD or ref.mime!="video/mp4":
            raise AssetRightsDenied("TEMPORAL_FIXTURE_ONLY")
        data,expected=fixture(case)
        config,code=plan(case)
        if ref.byte_count!=len(data) or spec.configuration_sha256!=config["configuration_sha256"]:
            raise AssetRightsDenied("TEMPORAL_FIXTURE_CONFIG")
        def check():
            s,r=queue.check_lease(lease)
            if s!=spec or r!=ref:
                raise AssetRightsDenied("TEMPORAL_FIXTURE_BINDING")
        actual=vault.read_indexed(queue.resolve_anchor(ref),spec.tenant_id,spec.object_id,purpose=spec.purpose)
        if actual!=data:
            raise AssetRightsDenied("TEMPORAL_FIXTURE_ONLY")
        # Recheck the runtime before spawn; trusted host excludes hostile replacement.
        if plan(case)!=(config,code):
            raise AssetRightsDenied("TEMPORAL_FIXTURE_RUNTIME_CHANGED")
        raw=windows._run_exact_fixture(code,actual,expected,check,limits=LIMITS)
        if plan(case)!=(config,code):
            raise AssetRightsDenied("TEMPORAL_FIXTURE_RUNTIME_CHANGED")
        result=ProcessorResult(tenant_id=spec.tenant_id,job_id=spec.job_id,
            object_id=spec.object_id,input_sha256=ref.target.sha256,attempt=lease.attempt,
            purpose=spec.purpose,method_version=spec.method_version,
            configuration_sha256=spec.configuration_sha256,origin="adapter_candidate",
            result=result_from_frames(case,raw))
        payload=encode(result)
        validate_binding(decode(payload),spec=spec,ref=ref,lease=lease)
        check()
        receipt=store.finish(lease,payload=payload)
        return {**receipt,"synthetic_fixture":True,"result_state":"observed",
                "processor":"temporal","fixture_case":case,"model_calls":0,
                "canonical_rubric":False,"ffmpeg_sha256":config["runtime_sha256"],
                "kernel_job_limits_verified":True,"tree_empty_verified":True}
    except windows.JobError as exc:
        raise AssetRightsDenied("TEMPORAL_FIXTURE_WINDOWS_"+str(exc)) from exc
