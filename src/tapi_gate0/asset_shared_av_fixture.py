"""Protected shared authored audiovisual fixture. No arbitrary media or provider I/O.

The host generates only fixed authored inputs. Every job decodes the same
retained MP4 via a bounded Windows Job, checks lossless pixels and PCM, then
uses the already pinned modality adapters. Intermediate plaintext exists in
trusted memory only; no media files are written by the protected decoder.
"""
from dataclasses import dataclass, asdict
from hashlib import sha256
from pathlib import Path
import io
import json
import os
import subprocess
import tempfile
import wave

from . import asset_asr_fixture as asr, asset_ocr_fixture as ocr
from . import asset_vlm_fixture as vlm, asset_temporal_fixture as temporal
from . import asset_windows_job as windows
from . import multimodal_temporal as reducer
from .asset_processor_results import (SHARED_AV_METHOD, SharedAVSource, SharedAVBinding,
    Frame, Temporal, Transition, ProcessorResult, Abstention, SharedAVQualityRejection,
    STRICT_QUALITY, PARTIAL_QUALITY, encode, decode, validate_binding)
from .asset_rights import AssetRightsDenied

METHOD=SHARED_AV_METHOD
# Fixed audiovisual recipes. Keep the two original recipes byte-compatible.
RECIPES={
    "inventory":("inventory","sales"),
    "silence":("silence","blank"),
    "agreement":("agreement","sales"),
    "conflict":("conflict","sales"),
    "complementary":("cta","sales"),
    "audio_only":("cta","blank"),
    "screen_only":("silence","sales"),
    "tone_negative":("tone","blank"),
}
CASES=tuple(RECIPES)
PROCESSORS=("temporal","ocr","asr_vad","vlm")
WIDTH,HEIGHT,FPS=960,540,4
PIXELS=WIDTH*HEIGHT
RATE=16000
MAX_CONTAINER=4_000_000
MAX_DECODE_OUTPUT=PIXELS+asr.MAX_PCM+32*4096
LIMITS=windows.JobLimits(memory_mib=512,cpu_user_seconds=10,active_processes=2,wall_seconds=30)


def _digest(raw):
    return sha256(raw).hexdigest()


def _deny(code):
    raise AssetRightsDenied("SHARED_AV_"+code)


def _rgb(png):
    from PIL import Image
    with Image.open(io.BytesIO(png)) as im:
        if im.format!="PNG" or im.size!=(WIDTH,HEIGHT):
            _deny("IMAGE_FORMAT")
        raw=im.convert("RGB").tobytes()
    if raw[::3]!=raw[1::3] or raw[::3]!=raw[2::3]:
        _deny("IMAGE_NOT_GRAYSCALE")
    return raw


def _sample(gray):
    if len(gray)!=PIXELS:
        _deny("FRAME_SIZE")
    return bytes(gray[(y*HEIGHT//64)*WIDTH+(x*WIDTH//64)] for y in range(64) for x in range(64))


def _wav(pcm):
    out=io.BytesIO()
    with wave.open(out,"wb") as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(RATE);w.writeframes(pcm)
    return out.getvalue()


@dataclass(frozen=True)
class AuthoredFixture:
    case: str
    data: bytes
    png: bytes
    wav: bytes
    expected_output: bytes
    source: SharedAVSource
    decoder_code: str
    asr_meta_json: str

    @property
    def screen_case(self):
        return RECIPES[self.case][1]


def _decoder(binary,data,source):
    # Full lossless RGB/PCM digest checks inside the protected child. The
    # selected frame and point samples are returned from actual decoded bytes.
    base=[binary,"-hide_banner","-loglevel","error","-nostdin","-protocol_whitelist","pipe",
          "-threads","1","-f","mp4","-i","pipe:0"]
    video=base+["-map","0:v:0","-an","-frames:v",str(source.frame_count+1),
                "-pix_fmt","rgb24","-threads","1","-f","rawvideo","pipe:1"]
    audio=base+["-map","0:a:0","-vn","-t","16","-ar","16000","-ac","1","-f","s16le","pipe:1"]
    return f'''import hashlib, subprocess, sys
x=sys.stdin.buffer.read({len(data)+1})
if len(x)!={len(data)} or hashlib.sha256(x).hexdigest()!={source.container_sha256!r}:
    sys.exit(2)
def decode(args,n,digest):
    p=subprocess.run(args,input=x,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,shell=False,close_fds=True)
    if p.returncode or len(p.stdout)!=n or hashlib.sha256(p.stdout).hexdigest()!=digest:
        sys.exit(3)
    return p.stdout
v=decode({video!r},{source.frame_count*PIXELS*3},{source.rgb_stream_sha256!r})
a=decode({audio!r},{source.pcm_samples*2},{source.pcm_sha256!r})
size={PIXELS*3}
frame=v[4*size:5*size:3]
samples=[]
for i in range({len(source.temporal_sample_sha256)}):
    gray=v[i*size:(i+1)*size:3]
    samples.append(bytes(gray[(y*{HEIGHT}//64)*{WIDTH}+(z*{WIDTH}//64)] for y in range(64) for z in range(64)))
if len(frame)!={PIXELS} or hashlib.sha256(frame).hexdigest()!={source.frame_sha256!r}:
    sys.exit(4)
if [hashlib.sha256(f).hexdigest() for f in samples]!={list(source.temporal_sample_sha256)!r}:
    sys.exit(5)
sys.stdout.buffer.write(frame+a+b"".join(samples))
'''


def prepare(case):
    """Build one fixed authored MP4. Never receives an input path or bytes.

    Lossless H.264 RGB + ALAC, 4 fps, PCM 16 kHz mono. The visual
    timeline is an explicit uniform sample index, not original source PTS.
    The container is local-runtime pinned; regeneration must match exact ID.
    """
    if case not in CASES:
        _deny("CASE")
    speech,screen=RECIPES[case]
    wav,meta=asr._authored_fixture(speech)
    pcm=asr._pcm(wav)
    count=(meta["samples"]+3999)//4000
    if not 5<=count<=60:
        _deny("DURATION")
    png,_=ocr.fixture(screen)
    rgb=_rgb(png)
    gray=rgb[::3]
    # In positive case choose the opposite uniform intensity so the
    # deterministic transition at one second is actually observable.
    first=bytes([0 if sum(gray)>127*len(gray) else 255])*len(rgb) if screen=="sales" else rgb
    raw=first*4+rgb*(count-4)
    samples=tuple(_sample((first if i<4 else rgb)[::3]) for i in range(min(count,32)))
    binary,binary_hash=temporal._runtime()
    env={k:os.environ[k] for k in ("SystemRoot","WINDIR") if k in os.environ}
    with tempfile.TemporaryDirectory(prefix="tapi-authored-av-") as temp:
        root=Path(temp)
        # These are solely authored inputs, never bytes from the vault.
        (root/"video.rgb").write_bytes(raw)
        (root/"audio.pcm").write_bytes(pcm)
        output=root/"fixture.mp4"
        args=[binary,"-hide_banner","-loglevel","error","-nostdin","-n",
              "-protocol_whitelist","file,pipe","-f","rawvideo","-pixel_format","rgb24",
              "-video_size",f"{WIDTH}x{HEIGHT}","-framerate",str(FPS),"-i",str(root/"video.rgb"),
              "-f","s16le","-ar",str(RATE),"-ac","1","-i",str(root/"audio.pcm"),
              "-map","0:v:0","-map","1:a:0","-c:v","libx264rgb","-qp","0","-preset","ultrafast",
              "-threads","1","-c:a","alac","-movflags","+faststart","-map_metadata","-1",str(output)]
        subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                       timeout=30,check=True,env=env,shell=False,close_fds=True)
        if not output.is_file() or not 0<output.stat().st_size<=MAX_CONTAINER:
            _deny("CONTAINER_SIZE")
        data=output.read_bytes()
    if temporal._runtime()!=(binary,binary_hash) or _wav(pcm)!=wav:
        _deny("RUNTIME_OR_WAV_CHANGED")
    src=SharedAVSource(container_sha256=_digest(data),decoder_sha256=binary_hash,
        rgb_stream_sha256=_digest(raw),pcm_sha256=_digest(pcm),frame_sha256=_digest(gray),
        frame_png_sha256=_digest(png),frame_count=count,pcm_samples=meta["samples"],
        temporal_sample_sha256=tuple(_digest(x) for x in samples))
    code=_decoder(binary,data,src)
    return AuthoredFixture(case,data,png,wav,gray+pcm+b"".join(samples),src,code,
                           json.dumps(meta,sort_keys=True,separators=(",",":")))


def _adapter_plan(fixture,processor,paths):
    t,a,v,s=paths
    if processor=="temporal":
        config={"method":"shared-av-point-temporal.v1","reducer":reducer.VERSION,
                "threshold":reducer.THRESHOLD}
        return {"configuration_sha256":_digest(json.dumps(config,sort_keys=True,separators=(",",":")).encode())},None
    if processor=="ocr" and t is not None:
        return ocr.plan(fixture.screen_case,t)
    if processor=="asr_vad" and a is not None:
        return asr._plan(fixture.wav,json.loads(fixture.asr_meta_json),a)
    if processor=="vlm" and v is not None and s is not None:
        expected="text_card" if fixture.screen_case=="sales" else "blank"
        return vlm._plan_image(fixture.png,expected,"shared_"+fixture.case,v,s)
    _deny("PROCESSOR_CONFIG")


def plan(fixture,processor,paths,*,quality_policy=STRICT_QUALITY):
    if quality_policy not in (STRICT_QUALITY,PARTIAL_QUALITY):
        _deny("QUALITY_POLICY")
    config,code=_adapter_plan(fixture,processor,paths)
    # Bind the exact decoder program, kernel budget and adapter identity.
    raw=json.dumps({"adapter":config["configuration_sha256"],
        "decoder_code":_digest(fixture.decoder_code.encode()),"decoder_limits":asdict(LIMITS),
        "max_input":MAX_CONTAINER,"max_output":MAX_DECODE_OUTPUT,"job_flags":windows.FLAGS,
        "job_name":windows.JOB_NAME},sort_keys=True,separators=(",",":")).encode()
    binding=SharedAVBinding(source=fixture.source,adapter_configuration_sha256=_digest(raw),
                            quality_policy=quality_policy)
    return binding,config,code


def _partition(fixture,raw):
    if type(raw) is not bytes or raw!=fixture.expected_output:
        _deny("DECODE_MISMATCH")
    n=fixture.source.pcm_samples*2
    gray,pcm,samples=raw[:PIXELS],raw[PIXELS:PIXELS+n],raw[PIXELS+n:]
    if (_digest(gray)!=fixture.source.frame_sha256 or _digest(pcm)!=fixture.source.pcm_sha256
            or _rgb(fixture.png)[::3]!=gray or _wav(pcm)!=fixture.wav):
        _deny("DECODE_BINDING")
    return gray,pcm,samples


def _temporal_result(raw):
    measured=reducer.sample_measurements(raw)
    return Temporal(samples=measured["samples"],threshold=measured["threshold"],
        candidates=tuple(Transition(
            previous=Frame(time_ms=int(x["previous_sample_time_s"]*1000),
                frame_sha256=x["previous_frame_sha256"],timeline="resampled_uniform"),
            current=Frame(time_ms=int(x["sample_time_s"]*1000),
                frame_sha256=x["frame_sha256"],timeline="resampled_uniform"),
            normalized_difference=x["normalized_difference"]) for x in measured["transition_candidates"]))


def _asr_result(meta,output,quality_policy):
    """Only a structurally validated WER failure may become a typed abstention."""
    if quality_policy not in (STRICT_QUALITY,PARTIAL_QUALITY):
        _deny("QUALITY_POLICY")
    try:
        observation,quality=asr.result_from_output(meta,output)
        return observation,quality,None
    except asr.ASRFixtureQualityError as exc:
        if quality_policy!=PARTIAL_QUALITY:
            raise
        names=("wer","vad_iou","vad_boundary_error_s","reference_words",
               "hypothesis_words","vad_calls","asr_calls")
        rejection=SharedAVQualityRejection(**{k:exc.quality[k] for k in names})
        return (Abstention(processor="asr_vad",reason="fixture_quality_rejected"),
                rejection.model_dump(mode="json"),rejection)


def run(queue,vault,store,lease,*,fixture,paths,quality_policy=STRICT_QUALITY):
    """Called only from the fixed fixture pipeline. A trusted host is not a sandbox."""
    from .asset_jobs import AssetJobQueue
    from .asset_indexed_vault import IndexedAssetVault
    from .asset_derived_payloads import DerivedPayloadStore
    if (not isinstance(queue,AssetJobQueue) or not isinstance(vault,IndexedAssetVault)
            or queue.index.engine is not vault._index.engine or not isinstance(store,DerivedPayloadStore)
            or store.queue is not queue or type(fixture) is not AuthoredFixture):
        _deny("HOST_MISMATCH")
    try:
        windows._native_api()
        spec,ref=queue.check_lease(lease)
        # Do not trust caller-constructed dataclasses or supplied decoder code.
        # Regenerate the fixed recipe on this runtime, then compare everything.
        if fixture!=prepare(fixture.case):
            _deny("FIXTURE_RECIPE_CHANGED")
        binding,config,code=plan(fixture,spec.processor,paths,quality_policy=quality_policy)
        if (spec.method_version!=METHOD or spec.configuration_sha256!=binding.configuration(spec.processor)
                or ref.target.sha256!=fixture.source.container_sha256 or ref.byte_count!=len(fixture.data)
                or ref.mime!="video/mp4" or _digest(fixture.data)!=fixture.source.container_sha256):
            _deny("JOB_BINDING")
        def check():
            current,current_ref=queue.check_lease(lease)
            if current!=spec or current_ref!=ref:
                _deny("LEASE_BINDING")
        actual=vault.read_indexed(queue.resolve_anchor(ref),spec.tenant_id,spec.object_id,purpose=spec.purpose)
        if actual!=fixture.data:
            _deny("FIXTURE_ONLY")
        binary,binary_hash=temporal._runtime()
        if (binary_hash!=fixture.source.decoder_sha256 or
                _decoder(binary,actual,fixture.source)!=fixture.decoder_code):
            _deny("DECODER_CHANGED")
        decode_resources={}
        raw=windows._run_fixture_output(fixture.decoder_code,actual,check,limits=LIMITS,
            max_input=MAX_CONTAINER,max_output=MAX_DECODE_OUTPUT,expected=fixture.expected_output,
            metrics=decode_resources)
        gray,pcm,samples=_partition(fixture,raw)
        lease=queue.heartbeat(lease)
        frame=Frame(time_ms=1000,frame_sha256=_digest(gray),timeline="resampled_uniform")
        calls=0
        model_resources=None
        ocr_resources=None
        quality=None
        rejection=None
        if spec.processor=="temporal":
            observation=_temporal_result(samples)
            expected=[1000] if fixture.screen_case=="sales" else []
            if [x.current.time_ms for x in observation.candidates]!=expected:
                _deny("TEMPORAL_GATE")
        elif spec.processor=="ocr":
            # Exact pinned PNG is the canonical encoding of the verified
            # decoded pixels, not a different frame or unverified text.
            ocr_resources={}
            output=windows._run_fixture_output(code,fixture.png,check,limits=ocr.LIMITS,
                max_output=ocr.MAX_TSV,expected=None,metrics=ocr_resources)
            observation=ocr.result_from_tsv(fixture.screen_case,output)
            if observation.state=="observed":
                observation=observation.model_copy(update={"frame":frame})
            calls=1
        elif spec.processor=="asr_vad":
            output,model_resources=windows._run_model_fixture(code,_wav(pcm),check,limits=asr.LIMITS,max_output=asr.MAX_OUTPUT)
            observation,quality,rejection=_asr_result(json.loads(fixture.asr_meta_json),output,quality_policy)
            calls=quality["vad_calls"]+quality["asr_calls"]
        elif spec.processor=="vlm":
            output,model_resources=windows._run_vlm_fixture(code,fixture.png,check,
                limits=windows.VlmFixtureLimits(),max_output=vlm.MAX_OUTPUT)
            expected="text_card" if fixture.screen_case=="sales" else "blank"
            observation,calls=vlm._result_for_image(fixture.png,expected,output)
            observation=observation.model_copy(update={"frame":frame})
        else:
            _deny("PROCESSOR")
        if temporal._runtime()!=(binary,binary_hash) or plan(fixture,spec.processor,paths,quality_policy=quality_policy)!=(binding,config,code):
            _deny("RUNTIME_CHANGED")
        result=ProcessorResult(tenant_id=spec.tenant_id,job_id=spec.job_id,object_id=spec.object_id,
            input_sha256=ref.target.sha256,attempt=lease.attempt,purpose=spec.purpose,
            method_version=spec.method_version,configuration_sha256=spec.configuration_sha256,
            origin="adapter_candidate",result=observation,shared_av=binding,
            shared_av_quality_rejection=rejection)
        payload=encode(result)
        validate_binding(decode(payload),spec=spec,ref=ref,lease=lease)
        check()
        receipt=store.finish(lease,payload=payload)
        return {**receipt,"model_calls":calls,"synthetic_fixture":True,"canonical_rubric":False,
                "kernel_job_limits_verified":True,"tree_empty_verified":True,
                "decode_resources":decode_resources,"model_resources":model_resources,
                "ocr_resources":ocr_resources,"quality":quality}
    except windows.JobError as exc:
        raise AssetRightsDenied("SHARED_AV_WINDOWS_"+str(exc)) from exc
