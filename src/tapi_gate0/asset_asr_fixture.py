"""Whisper Medium + Silero VAD candidate adapter for authored WAV fixtures only.

No arbitrary audio path or bytes, remote model, evidence admission or rubric.
Fixtures are synthesized locally using the existing TTS recipe, then pinned
by WAV/PCM digest, not assumed byte-identical across synthesizer versions.
"""
from dataclasses import asdict
from hashlib import sha256
from importlib.metadata import distribution, version
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import sysconfig
import unicodedata
import wave

from . import asset_windows_job as windows
from .asset_processor_results import ASR, Speech, Interval, Abstention, ProcessorResult, encode, decode, validate_binding

METHOD="synthetic-asr-vad-whisper-medium-v8"
LIMITS=windows.ModelFixtureLimits()
MAX_OUTPUT=32768
RATE=16000
MAX_PCM=480000
CASES=("inventory","silence","tone")
REFERENCE="Confira o estoque antes de aceitar novos pedidos."
# Fixed authored challenge phrases; no caller-provided TTS text.
SHARED_SPEECH={
    "agreement":"Organize suas vendas e acompanhe suas vendas.",
    "conflict":"Calcule os custos fixos e a margem de contribuição.",
    "cta":"Salve este conteúdo para revisar mais tarde.",
}
VAD_PIN="4cbf549b8326f60f80f2536d9eefeb450a9abe83365a098031c89719f1be17d2"
OPTIONS={"threshold":0.5,"min_speech_duration_ms":250,"min_silence_duration_ms":300,"speech_pad_ms":150}
RUNTIME_PACKAGES=("faster-whisper","ctranslate2","onnxruntime","numpy","tokenizers","huggingface-hub","av")


def _digest(data):
    return sha256(data).hexdigest()


def _hash(path,limit):
    p=Path(path)
    if not p.is_file() or p.is_symlink() or not 0<p.stat().st_size<=limit:
        raise ValueError("ASR_FIXTURE_FILE_INVALID")
    h=sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()


def _speech_pcm(reference=REFERENCE):
    if reference not in (REFERENCE,*SHARED_SPEECH.values()):
        raise ValueError("ASR_FIXTURE_SPEECH_NOT_AUTHORED")
    espeak,ffmpeg=shutil.which("espeak-ng"),shutil.which("ffmpeg")
    if not espeak or not ffmpeg:
        raise ValueError("ASR_FIXTURE_SYNTH_TOOLS_REQUIRED")
    # Authored ASCII phrase, no caller-controlled text or input file. Only
    # synthetic output is generated outside the protected media job.
    env={k:os.environ[k] for k in ("SystemRoot","WINDIR","ESPEAK_DATA_PATH") if k in os.environ}
    a=subprocess.run([str(Path(espeak).resolve(strict=True)),"-v","pt-br","-b","1","-s","135","--stdout",reference],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30,check=True,env=env,shell=False,close_fds=True)
    if not 0<len(a.stdout)<=4_000_000:
        raise ValueError("ASR_FIXTURE_TTS_SIZE")
    b=subprocess.run([str(Path(ffmpeg).resolve(strict=True)),"-hide_banner","-loglevel","error","-nostdin","-protocol_whitelist","pipe",
        "-f","wav","-i","pipe:0","-ac","1","-ar",str(RATE),"-f","s16le","pipe:1"],
        input=a.stdout,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30,check=True,env=env,shell=False,close_fds=True)
    raw=b.stdout
    if not raw or len(raw)%2 or len(raw)>MAX_PCM-6*RATE:
        raise ValueError("ASR_FIXTURE_PCM_SIZE")
    nonzero=[i for i,(v,) in enumerate(struct.iter_unpack("<h",raw)) if v]
    if not nonzero:
        raise ValueError("ASR_FIXTURE_TTS_EMPTY")
    return raw[2*nonzero[0]:2*(nonzero[-1]+1)]


def fixture(case):
    if case not in CASES:
        raise ValueError("ASR_FIXTURE_UNKNOWN")
    return _authored_fixture(case)


def _authored_fixture(case):
    if case not in (*CASES,*SHARED_SPEECH):
        raise ValueError("ASR_FIXTURE_UNKNOWN")
    expected=[]
    reference=REFERENCE if case=="inventory" else SHARED_SPEECH.get(case,"")
    if reference:
        speech=_speech_pcm() if case=="inventory" else _speech_pcm(reference)
        expected=[{"start":2*RATE,"end":2*RATE+len(speech)//2}]
        raw=bytes(4*RATE)+speech+bytes(2*RATE)
    elif case=="silence":
        raw=bytes(6*RATE)
    else:
        raw=b"".join(struct.pack("<h",round(4096*math.sin(2*math.pi*440*i/RATE))) for i in range(3*RATE))
    out=io.BytesIO()
    with wave.open(out,"wb") as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(RATE);w.writeframes(raw)
    data=out.getvalue()
    if _pcm(data)!=raw:
        raise ValueError("ASR_FIXTURE_WAV_ROUNDTRIP")
    return data,{"case":case,"pcm_sha256":_digest(raw),"samples":len(raw)//2,
                 "expected_regions":expected,"reference":reference if expected else ""}


def _pcm(data):
    if type(data) is not bytes or not 44<len(data)<=MAX_PCM+44:
        raise ValueError("ASR_FIXTURE_WAV_SIZE")
    with wave.open(io.BytesIO(data),"rb") as w:
        if (w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getcomptype())!=(1,2,RATE,"NONE"):
            raise ValueError("ASR_FIXTURE_WAV_FORMAT")
        raw=w.readframes(w.getnframes())
        if len(raw)!=w.getnframes()*2 or not raw or len(raw)>MAX_PCM:
            raise ValueError("ASR_FIXTURE_PCM_SIZE")
    return raw


def _runtime(model_dir):
    from . import multimodal_asr as asr
    from . import multimodal_vad as vad
    if vad.OPTIONS!=OPTIONS:
        raise ValueError("ASR_FIXTURE_VAD_OPTIONS_CHANGED")
    model=Path(model_dir)
    checkpoint=asr.verify_checkpoint(model,"medium")
    versions={n:version(n) for n in RUNTIME_PACKAGES}
    if versions["faster-whisper"]!="1.2.1":
        raise ValueError("ASR_FIXTURE_RUNTIME_VERSION")
    asset=Path(distribution("faster-whisper").locate_file("faster_whisper/assets/silero_vad_v6.onnx"))
    if _hash(asset,30_000_000)!=VAD_PIN:
        raise ValueError("ASR_FIXTURE_VAD_PIN")
    root=Path(__file__).resolve().parent
    sources={n:_hash(root/n,2_000_000) for n in ("asset_asr_fixture.py","multimodal_asr.py","multimodal_vad.py","multimodal_vad_asr.py","multimodal_temporal.py")}
    return {"checkpoint":checkpoint,"versions":versions,"vad_sha256":VAD_PIN,"source_sha256":sources}


def _child(data,model_dir):
    # No site startup or model imports before the exact fixture is received.
    # Use only trusted local environment and repo directories; no .pth hooks.
    paths=list(dict.fromkeys([str(Path(__file__).resolve().parents[1]),sysconfig.get_path("purelib"),sysconfig.get_path("platlib")]))
    return f'''import sys, hashlib
x=sys.stdin.buffer.read({len(data)+1})
if len(x)!={len(data)} or hashlib.sha256(x).hexdigest()!={_digest(data)!r}:
    sys.exit(2)
pipe=sys.stdout.buffer
def mark(stage):
    pipe.write(("TAPI_ASR_STAGE:"+stage+"\\n").encode("ascii"));pipe.flush()
mark("bootstrap")
try:
    import os, contextlib, io, json
    os.environ.update(HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",HF_HUB_DISABLE_TELEMETRY="1",OMP_NUM_THREADS="4",OMP_THREAD_LIMIT="4")
    sys.path.extend({paths!r})
    _dll=[]
    if os.name=="nt":
        for p in (sys.prefix,os.path.join(sys.prefix,"Library","bin"),os.path.join(sys.prefix,"DLLs")):
            if os.path.isdir(p):
                _dll.append(os.add_dll_directory(p))
    mark("imports")
    with contextlib.redirect_stdout(sys.stderr):
        from tapi_gate0.asset_asr_fixture import _infer
        result=_infer(x,{str(model_dir)!r},stage=mark)
    mark("serialize")
    out=json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode("utf-8")
    if not 0<len(out)<={MAX_OUTPUT-1024}:
        raise ValueError("OUTPUT_SIZE")
    pipe.write(b"TAPI_ASR_RESULT\\n"+out);pipe.flush()
except Exception as exc:
    # Only fixed categories escape the child. No raw exception text/paths.
    kind=next((cls.__name__ for cls in (MemoryError,ImportError,OSError,RuntimeError,ValueError) if isinstance(exc,cls)),"Other")
    message=str(exc).lower()
    reason="memory" if kind=="MemoryError" or any(t in message for t in ("out of memory","not enough memory","bad allocation","bad_alloc","paging file","allocate memory")) else "dll" if "dll" in message else "file" if any(t in message for t in ("no such file","file not found","cannot open file","unable to open file")) else "other"
    pipe.write(("TAPI_ASR_ERROR:"+kind+":"+reason+"\\n").encode("ascii"));pipe.flush()
    sys.exit(4)
'''


def plan(case,model_dir):
    data,meta=fixture(case)
    return _plan(data,meta,model_dir)


def _plan(data,meta,model_dir):
    runtime=_runtime(model_dir)
    code=_child(data,model_dir)
    config={"method":METHOD,"case":meta["case"],"input_sha256":_digest(data),"fixture":meta,
            "runtime":runtime,"code_sha256":_digest(code.encode()),"limits":asdict(LIMITS),
            "job_name":windows.JOB_NAME,"job_flags":windows.FLAGS,"max_output":MAX_OUTPUT,
            "host_min_physical_mib":windows.MODEL_MIN_PHYSICAL_MIB,
            "host_commit_reserve_mib":windows.MODEL_COMMIT_RESERVE_MIB,
            "vad_options":OPTIONS,"device":"cpu","compute_type":"int8","cpu_threads":4}
    pin=_digest(json.dumps(config,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode())
    return {**config,"configuration_sha256":pin},code


def _infer(data,model_dir,*,stage=lambda _:None):
    """Child only, caller pinned exact authored bytes; no external entrypoint."""
    from . import multimodal_vad_asr as joint
    from . import multimodal_asr as asr
    from faster_whisper.vad import VadOptions,get_speech_timestamps,get_vad_model
    import gc
    raw=_pcm(data)
    # Exact silence guard: no VAD model load or Whisper load.
    intervals=[]
    vad_calls=int(any(raw))
    if vad_calls:
        stage("vad")
        get_vad_model.cache_clear()
        try:
            opts=VadOptions(**OPTIONS)
            observation=joint.detect_regions(raw,lambda pcm:get_speech_timestamps(pcm,opts,sampling_rate=RATE))
            intervals=observation["intervals"]
        finally:
            get_vad_model.cache_clear();gc.collect()
    segments=[]
    if intervals:
        stage("model_load")
        from faster_whisper import WhisperModel
        model=WhisperModel(str(model_dir),device="cpu",compute_type="int8",cpu_threads=4,num_workers=1,local_files_only=True)
        if not model.model.is_multilingual or model.feature_extractor.sampling_rate!=RATE:
            raise ValueError("ASR_FIXTURE_MODEL_FORMAT")
        stage("transcribe")
        result=joint.transcribe_regions(model,raw,intervals)
        if result["pcm_sha256"]!=_digest(raw) or result["asr_calls"]!=len(intervals):
            raise ValueError("ASR_FIXTURE_CHILD_BINDING")
        segments=[{k:s[k] for k in ("start_s","end_s","text","region_start_sample","region_end_sample")} for s in result["segments"]]
    return {"pcm_sha256":_digest(raw),"intervals":intervals,"segments":segments,
            "vad_calls":vad_calls,"asr_calls":len(intervals)}


def _words(text):
    return re.findall(r"[^\W_]+",unicodedata.normalize("NFC",text).casefold(),re.UNICODE)


def _wer(ref,hyp):
    a,b=_words(ref),_words(hyp)
    prev=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        curr=[i]
        for j,y in enumerate(b,1):
            curr.append(min(prev[j]+1,curr[-1]+1,prev[j-1]+(x!=y)))
        prev=curr
    return prev[-1]/len(a) if a else None


def result_from_output(meta,raw):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_OUTPUT:
        raise ValueError("ASR_FIXTURE_OUTPUT_SIZE")
    def unique(pairs):
        obj={}
        for k,v in pairs:
            if k in obj:
                raise ValueError("ASR_FIXTURE_DUPLICATE_KEY")
            obj[k]=v
        return obj
    r=json.loads(raw.decode("utf-8"),object_pairs_hook=unique)
    if not isinstance(r,dict) or set(r)!={"pcm_sha256","intervals","segments","vad_calls","asr_calls"} or r["pcm_sha256"]!=meta["pcm_sha256"]:
        raise ValueError("ASR_FIXTURE_OUTPUT_BINDING")
    expected=meta["expected_regions"]
    intervals=r["intervals"];segments=r["segments"]
    if (type(intervals) is not list or type(segments) is not list or len(intervals)>64 or len(segments)>128 or
        type(r["vad_calls"]) is not int or r["vad_calls"]!=int(meta["case"]!="silence") or
        type(r["asr_calls"]) is not int or r["asr_calls"]!=len(intervals)):
        raise ValueError("ASR_FIXTURE_OUTPUT_SHAPE")
    n=meta["samples"];last=0
    for row in intervals:
        if (not isinstance(row,dict) or set(row)!={"start","end"} or type(row["start"]) is not int or
            type(row["end"]) is not int or not last<=row["start"]<row["end"]<=n):
            raise ValueError("ASR_FIXTURE_VAD_INTERVAL")
        last=row["end"]
    if not expected:
        if intervals or segments or r["asr_calls"]:
            raise ValueError("ASR_FIXTURE_NEGATIVE_INSERTION")
        return Abstention(processor="asr_vad",reason="no_observable_signal"),{"vad_calls":r["vad_calls"],"asr_calls":0,"wer":None,"vad_iou":None}
    if len(intervals)!=len(expected):
        raise ValueError("ASR_FIXTURE_VAD_GATE")
    overlap=sum(max(0,min(a["end"],b["end"])-max(a["start"],b["start"])) for a in intervals for b in expected)
    union=sum(b["end"]-b["start"] for b in expected)+sum(a["end"]-a["start"] for a in intervals)-overlap
    iou=overlap/union
    boundary=max(abs(a[k]-b[k])/RATE for a,b in zip(intervals,expected) for k in ("start","end"))
    if iou<0.60 or boundary>0.75:
        raise ValueError("ASR_FIXTURE_VAD_GATE")
    typed=[];last_end=0
    for s in segments:
        if not isinstance(s,dict) or set(s)!={"start_s","end_s","text","region_start_sample","region_end_sample"}:
            raise ValueError("ASR_FIXTURE_SEGMENT")
        a,b=s["region_start_sample"],s["region_end_sample"]
        x,y=s["start_s"],s["end_s"]
        if (type(a) is not int or type(b) is not int or {"start":a,"end":b} not in intervals or
            type(x) not in (int,float) or type(y) not in (int,float) or not math.isfinite(x) or not math.isfinite(y) or
            not a/RATE-1e-9<=x<y<=b/RATE+1e-9 or type(s["text"]) is not str or not 0<len(s["text"].strip())<=2000):
            raise ValueError("ASR_FIXTURE_SEGMENT")
        start,end=math.ceil(x*1000-1e-7),math.floor(y*1000+1e-7)
        if not last_end<=start<end:
            raise ValueError("ASR_FIXTURE_SEGMENT_ORDER")
        typed.append(Speech(start_ms=start,end_ms=end,text=s["text"]))
        last_end=end
    wer=_wer(meta["reference"]," ".join(s.text for s in typed))
    if not typed or wer is None or wer>0.50:
        raise ValueError("ASR_FIXTURE_WER_GATE")
    observation=ASR(duration_ms=math.ceil(n*1000/RATE),segments=tuple(typed),
        vad=tuple(Interval(start_ms=a["start"]*1000//RATE,end_ms=math.ceil(a["end"]*1000/RATE)) for a in intervals))
    return observation,{"vad_calls":r["vad_calls"],"asr_calls":r["asr_calls"],"wer":wer,"vad_iou":iou,"vad_boundary_error_s":boundary}


def run_asr_fixture_windows(queue,vault,store,lease,*,case,model_dir):
    from .asset_jobs import AssetJobQueue
    from .asset_indexed_vault import IndexedAssetVault
    from .asset_derived_payloads import DerivedPayloadStore
    from .asset_rights import AssetRightsDenied
    if (not isinstance(queue,AssetJobQueue) or not isinstance(vault,IndexedAssetVault) or
        queue.index.engine is not vault._index.engine or not isinstance(store,DerivedPayloadStore) or store.queue is not queue):
        raise AssetRightsDenied("ASR_FIXTURE_HOST_MISMATCH")
    try:
        windows._native_api()
        spec,ref=queue.check_lease(lease)
        if spec.processor!="asr_vad" or spec.method_version!=METHOD or ref.mime!="audio/wav" or case not in CASES:
            raise AssetRightsDenied("ASR_FIXTURE_ONLY")
        data,meta=fixture(case)
        if ref.target.sha256!=_digest(data) or ref.byte_count!=len(data):
            raise AssetRightsDenied("ASR_FIXTURE_ONLY")
        config,code=_plan(data,meta,model_dir)
        if spec.configuration_sha256!=config["configuration_sha256"]:
            raise AssetRightsDenied("ASR_FIXTURE_CONFIG")
        def check():
            s,r=queue.check_lease(lease)
            if s!=spec or r!=ref:
                raise AssetRightsDenied("ASR_FIXTURE_BINDING")
        actual=vault.read_indexed(queue.resolve_anchor(ref),spec.tenant_id,spec.object_id,purpose=spec.purpose)
        if actual!=data:
            raise AssetRightsDenied("ASR_FIXTURE_ONLY")
        check()
        raw,metrics=windows._run_model_fixture(code,actual,check,limits=LIMITS,max_output=MAX_OUTPUT)
        if _runtime(model_dir)!=config["runtime"]:
            raise AssetRightsDenied("ASR_FIXTURE_RUNTIME_CHANGED")
        observation,quality=result_from_output(meta,raw)
        result=ProcessorResult(tenant_id=spec.tenant_id,job_id=spec.job_id,object_id=spec.object_id,
            input_sha256=ref.target.sha256,attempt=lease.attempt,purpose=spec.purpose,method_version=spec.method_version,
            configuration_sha256=spec.configuration_sha256,origin="adapter_candidate",result=observation)
        payload=encode(result)
        validate_binding(decode(payload),spec=spec,ref=ref,lease=lease)
        check()
        receipt=store.finish(lease,payload=payload)
        return {**receipt,"processor":"asr_vad","fixture_case":case,"synthetic_fixture":True,
            "result_state":observation.state,"canonical_rubric":False,"kernel_job_limits_verified":True,
            "tree_empty_verified":True,"model_calls":quality["vad_calls"]+quality["asr_calls"],
            "quality":quality,"resources":metrics}
    except windows.JobError as exc:
        raise AssetRightsDenied("ASR_FIXTURE_WINDOWS_"+str(exc)) from exc
