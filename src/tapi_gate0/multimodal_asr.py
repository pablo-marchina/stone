"""IMP-063: fixed, offline Portuguese ASR engineering benchmark.

Only internally generated PCM is passed to the recognizer by the benchmark.
No arbitrary media paths, downloads, external inference or canonical labels.
"""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from importlib.metadata import version
from time import perf_counter
import math
import os
import re
import shutil
import struct
import tempfile
import unicodedata
import wave

from .multimodal_temporal import _run

VERSION = "bd-asr-fixture.v1"
MODEL_ID = "Systran/faster-whisper-small"
MODEL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"
MODEL_SHA256 = "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"
REQUIRED_FILES = ("config.json","model.bin","tokenizer.json","vocabulary.txt")
ASR_VERSION = "1.2.1"
MEDIUM_MODEL_ID = "Systran/faster-whisper-medium"
MEDIUM_REVISION = "7832330bcea9a8d5fd6d6637c49fe5d256e98277"
MEDIUM_SHA256 = "9b45e1009dcc4ab601eff815b61d80e60ce3fd8c74c1a14f4a282258286b51ae"
CHALLENGE_VERSION = "bd-asr-fixture-challenge.v2"
GUARDED_VERSION = "bd-asr-fixture-guarded.v3"
MIN_TEMP_FREE_BYTES = 64 * 1024 * 1024
SAMPLE_RATE = 16000
MAX_SECONDS = 15
MAX_BYTES = 2*SAMPLE_RATE*MAX_SECONDS
SPEECH_FIXTURES = (
    ("sales","Organize suas vendas e acompanhe os pedidos.",145),
    ("cash","Separe o dinheiro pessoal do caixa da empresa.",160),
    ("customer","Escute seu cliente e explique o benefício do produto.",150),
    ("cta","Salve este conteúdo para revisar mais tarde.",175),
)
NEGATIVE_FIXTURES = ("silence","tone")
CHALLENGE_SPEECH = (
    ("inventory","Confira o estoque antes de aceitar novos pedidos.",135),
    ("costs","Calcule os custos fixos e a margem de contribuição.",165),
    ("planning","Planeje o fluxo de caixa para os próximos meses.",155),
    ("service","Responda às dúvidas do cliente com clareza e respeito.",180),
    ("pricing","O preço precisa cobrir as despesas do negócio.",140),
    ("delivery","Avise o comprador quando a entrega estiver atrasada.",170),
)
CHALLENGE_NEGATIVE = ("silence","tone","noise")
GUARDED_NEGATIVE = ("silence","tone","noise","silence_repeat_2","tone_repeat_2","noise_repeat_2","silence_repeat_3")
MAX_POOLED_WER = 0.30
MAX_CASE_WER = 0.50


class ASRError(ValueError):
    """Sanitized failure; no paths, captions, transcript or exception message on stdout."""


@contextmanager
def asr_stage(stage,case_id=None):
    try:
        yield
    except Exception as exc:
        if isinstance(exc,ASRError):
            error=exc
        else:
            error=ASRError("ASR_"+stage.upper()+"_FAILED")
        error.stage=stage
        error.case_id=case_id
        error.exception_type=type(exc).__name__
        if error is exc:
            raise
        raise error from exc


def require_temp_capacity():
    if shutil.disk_usage(tempfile.gettempdir()).free<MIN_TEMP_FREE_BYTES:
        raise ASRError("ASR_TEMP_STORAGE_INSUFFICIENT")


def _file_hash(path):
    digest=sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            digest.update(block)
    return digest.hexdigest()


def verify_checkpoint(model_dir,candidate="small"):
    if candidate=="small":
        model_id,revision,weights,limit_bytes=MODEL_ID,MODEL_REVISION,MODEL_SHA256,600_000_000
    elif candidate=="medium":
        model_id,revision,weights,limit_bytes=MEDIUM_MODEL_ID,MEDIUM_REVISION,MEDIUM_SHA256,1_700_000_000
    else:
        raise ASRError("ASR_UNKNOWN_CANDIDATE")
    root=Path(model_dir)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir() or root.resolve()!=root.absolute():
        raise ASRError("ASR_LOCAL_MODEL_DIRECTORY_REQUIRED")
    # Reject unexpected top-level model files, including extra preprocessor
    # configuration that could change inference. HF download metadata may exist.
    actual={p.name for p in root.iterdir() if p.name!=".cache"}
    if actual!=set(REQUIRED_FILES):
        raise ASRError("ASR_CHECKPOINT_FILE_SET_MISMATCH")
    hashes={}
    for name in REQUIRED_FILES:
        path=root/name
        limit=limit_bytes if name=="model.bin" else 10_000_000
        if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=limit:
            raise ASRError("ASR_CHECKPOINT_FILE_INVALID")
        hashes[name]=_file_hash(path)
    if hashes["model.bin"]!=weights:
        raise ASRError("ASR_MODEL_WEIGHTS_DIGEST_MISMATCH")
    return {"model_id":model_id,"model_revision":revision,
            "weights_sha256":hashes["model.bin"],"file_sha256":hashes,
            "weights_digest_verified":True,"supporting_files_independently_verified":False}


def normalize_words(text):
    if not isinstance(text,str) or len(text)>20000:
        raise ASRError("ASR_TEXT_INVALID")
    return re.findall(r"[^\W_]+",unicodedata.normalize("NFC",text).casefold(),re.UNICODE)


def word_errors(reference,hypothesis):
    """Levenshtein WER, with Portuguese accents retained; no WER for empty reference."""
    ref,hyp=normalize_words(reference),normalize_words(hypothesis)
    previous=list(range(len(hyp)+1))
    for i,a in enumerate(ref,1):
        current=[i]
        for j,b in enumerate(hyp,1):
            current.append(min(previous[j]+1,current[-1]+1,previous[j-1]+(a!=b)))
        previous=current
    n=previous[-1]
    return {"reference_words":len(ref),"hypothesis_words":len(hyp),"word_errors":n,
            "wer":n/len(ref) if ref else None}


def _negative_pcm(kind):
    if kind in GUARDED_NEGATIVE:
        kind=kind.split("_repeat_")[0]
    if kind=="silence":
        return bytes(2*SAMPLE_RATE*3)
    if kind=="tone":
        return b"".join(struct.pack("<h",round(4096*math.sin(2*math.pi*440*i/SAMPLE_RATE)))
                        for i in range(SAMPLE_RATE*3))
    if kind=="noise":
        import random
        rng=random.Random(20261117)
        return b"".join(struct.pack("<h",rng.randint(-2048,2048)) for _ in range(SAMPLE_RATE*3))
    raise ASRError("ASR_FIXTURE_INVALID")


def _speech_pcm(espeak,ffmpeg,temp,case_id,text,rate):
    source=Path(temp)/(case_id+".txt")
    target=Path(temp)/(case_id+".wav")
    source.write_text(text,encoding="utf-8")
    _run(espeak,["-v","pt-br","-b","1","-s",str(rate),"-f",str(source),"-w",str(target)])
    if not target.is_file() or target.stat().st_size>4_000_000:
        raise ASRError("ASR_FIXTURE_INVALID")
    with wave.open(str(target),"rb") as stream:
        duration=stream.getnframes()/stream.getframerate()
        if not 0.5<=duration<=MAX_SECONDS:
            raise ASRError("ASR_FIXTURE_DURATION_INVALID")
    raw=_run(ffmpeg,["-hide_banner","-loglevel","error","-nostdin","-protocol_whitelist","file,pipe",
        "-i",str(target),"-ac","1","-ar",str(SAMPLE_RATE),"-f","s16le","pipe:1"],output_limit=MAX_BYTES)
    if abs(len(raw)/(2*SAMPLE_RATE)-duration)>0.1:
        raise ASRError("ASR_FIXTURE_RESAMPLE_MISMATCH")
    return raw


def _transcribe(model,raw,*,beam_size=5,word_timestamps=False):
    if type(beam_size) is not int or beam_size not in (5,10) or type(word_timestamps) is not bool:
        raise ASRError("ASR_DECODING_PROFILE_INVALID")
    if not raw or len(raw)%2 or len(raw)>MAX_BYTES:
        raise ASRError("ASR_PCM_INVALID")
    import numpy as np
    pcm=np.frombuffer(raw,dtype="<i2").astype(np.float32)/32768
    duration=len(pcm)/SAMPLE_RATE
    segments,info=model.transcribe(pcm,language="pt",task="transcribe",beam_size=beam_size,
        temperature=0.0,condition_on_previous_text=False,vad_filter=False,
        word_timestamps=word_timestamps,initial_prompt=None,without_timestamps=False)
    if info.language!="pt" or not math.isfinite(info.duration) or abs(info.duration-duration)>0.1:
        raise ASRError("ASR_TRANSCRIPTION_INFO_INVALID")
    observed=[]
    last_end=0.0
    for segment in segments:
        start,end,text=float(segment.start),float(segment.end),segment.text.strip()
        if (len(observed)>=128 or not math.isfinite(start) or not math.isfinite(end)
                or start<last_end-0.001 or end<start or start<0 or end>duration+0.25
                or len(text)>2000):
            raise ASRError("ASR_SEGMENT_INVALID")
        if text:
            row={"start_s":start,"end_s":end,"text":text,
                 "text_sha256":sha256(text.encode("utf-8")).hexdigest()}
            if word_timestamps:
                words=[]
                previous=0.0
                for w in segment.words or ():
                    x,y,token=float(w.start),float(w.end),w.word
                    if (len(words)>=256 or not math.isfinite(x) or not math.isfinite(y)
                            or not 0<=x<=y<=duration+0.25 or x<previous-0.001
                            or type(token) is not str or not 0<len(token)<=256):
                        raise ASRError("ASR_WORD_ALIGNMENT_INVALID")
                    words.append({"start_s":x,"end_s":y,"text":token})
                    previous=y
                row["words"]=words
            observed.append(row)
        last_end=end
    return {"pcm_sha256":sha256(raw).hexdigest(),"duration_s":duration,"segments":observed,
            "transcript":" ".join(s["text"] for s in observed),
            "timestamp_kind":"model_estimate_on_decoded_pcm_not_original_pts",
            "language_forced":"pt","reference_prompt_used":False}


def guarded_transcribe(model,raw):
    """Abstain only on exact digital zero. This is not a speech detector."""
    if not raw or len(raw)%2 or len(raw)>MAX_BYTES:
        raise ASRError("ASR_PCM_INVALID")
    if not any(raw):
        return {"pcm_sha256":sha256(raw).hexdigest(),"duration_s":len(raw)/(2*SAMPLE_RATE),
                "segments":[],"transcript":"","timestamp_kind":"decoded_pcm_no_model_segments",
                "language_forced":"pt","reference_prompt_used":False,
                "inference_attempted":False,"abstention_reason":"EXACT_DIGITAL_SILENCE"}
    return {**_transcribe(model,raw),"inference_attempted":True,"abstention_reason":None}


def evaluate_cases(cases,speech_fixtures=SPEECH_FIXTURES,negative_fixtures=NEGATIVE_FIXTURES):
    speech=[c for c in cases if c["reference_words"]>0]
    negative=[c for c in cases if c["reference_words"]==0]
    errors=sum(c["word_errors"] for c in speech)
    words=sum(c["reference_words"] for c in speech)
    pooled=errors/words if words else None
    expected={x[0] for x in speech_fixtures}|set(negative_fixtures)
    partition=len(cases)==len(expected) and {c["case_id"] for c in cases}==expected
    gate=(partition and len(speech)==len(speech_fixtures) and len(negative)==len(negative_fixtures)
          and pooled is not None and pooled<=MAX_POOLED_WER
          and all(c["wer"]<=MAX_CASE_WER for c in speech)
          and all(c["hypothesis_words"]==0 for c in negative))
    return {"speech_cases":len(speech),"non_speech_cases":len(negative),
            "speech_reference_words":words,"speech_word_errors":errors,"pooled_wer":pooled,
            "non_speech_inserted_words":sum(c["hypothesis_words"] for c in negative),
            "engineering_gate_passed":bool(gate),
            "gate_criteria":{"max_pooled_wer":MAX_POOLED_WER,"max_case_wer":MAX_CASE_WER,
                             "non_speech_inserted_words":0,"all_cases_required":True}}


def run_asr_fixture_benchmark(model_dir,candidate="small",suite="baseline"):
    if suite=="baseline":
        speech_fixtures,negative_fixtures,policy=SPEECH_FIXTURES,NEGATIVE_FIXTURES,VERSION
    elif suite=="challenge":
        speech_fixtures,negative_fixtures,policy=CHALLENGE_SPEECH,CHALLENGE_NEGATIVE,CHALLENGE_VERSION
    elif suite=="guarded":
        speech_fixtures,negative_fixtures,policy=CHALLENGE_SPEECH,GUARDED_NEGATIVE,GUARDED_VERSION
    else:
        raise ASRError("ASR_UNKNOWN_SUITE")
    with asr_stage("checkpoint_preflight"):
        before=verify_checkpoint(model_dir,candidate)
    with asr_stage("temp_preflight"):
        require_temp_capacity()
    # Set before importing the model library. Local directory and tokenizer
    # are mandatory; no model ID is passed to the inference constructor.
    os.environ.update(HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",HF_HUB_DISABLE_TELEMETRY="1")
    with asr_stage("runtime_preflight"):
        if version("faster-whisper")!=ASR_VERSION:
            raise ASRError("ASR_RUNTIME_VERSION_MISMATCH")
        espeak,ffmpeg=shutil.which("espeak-ng"),shutil.which("ffmpeg")
        if not espeak or not ffmpeg:
            raise ASRError("ASR_LOCAL_BINARY_UNAVAILABLE")
        versions={name:version(name) for name in ("faster-whisper","ctranslate2","numpy","tokenizers","huggingface-hub")}
        versions["espeak-ng"]=_run(espeak,["--version"],output_limit=100000).decode("utf-8","replace").splitlines()[0]
        versions["ffmpeg"]=_run(ffmpeg,["-version"],output_limit=100000).decode("utf-8","replace").splitlines()[0]
    with asr_stage("model_load"):
        from faster_whisper import WhisperModel
        started=perf_counter()
        model=WhisperModel(str(model_dir),device="cpu",compute_type="int8",
                           cpu_threads=4,num_workers=1,local_files_only=True)
        if not model.model.is_multilingual or model.feature_extractor.sampling_rate!=SAMPLE_RATE:
            raise ASRError("ASR_MULTILINGUAL_MODEL_REQUIRED")
        load_ms=round((perf_counter()-started)*1000,3)
    cases=[]
    with tempfile.TemporaryDirectory(prefix="tapi-asr-fixtures-") as temp:
        fixtures=[]
        for cid,text,rate in speech_fixtures:
            with asr_stage("fixture_generation",cid):
                fixtures.append((cid,text,_speech_pcm(espeak,ffmpeg,temp,cid,text,rate)))
        for cid in negative_fixtures:
            with asr_stage("fixture_generation",cid):
                fixtures.append((cid,"",_negative_pcm(cid)))
        for cid,reference,raw in fixtures:
            started=perf_counter()
            with asr_stage("inference",cid):
                observed=guarded_transcribe(model,raw) if suite=="guarded" else _transcribe(model,raw)
                latency=round((perf_counter()-started)*1000,3)
            with asr_stage("scoring",cid):
                cases.append({"case_id":cid,"reference":reference,**observed,
                              **word_errors(reference,observed["transcript"]),"inference_ms":latency,
                              "real_time_factor":round(latency/(1000*observed["duration_s"]),6)})
    with asr_stage("checkpoint_postflight"):
        if before!=verify_checkpoint(model_dir,candidate):
            raise ASRError("ASR_CHECKPOINT_CHANGED")
    return {"status":"ASR_FIXTURE_BENCHMARK_COMPLETED","policy_version":policy,"candidate":candidate,"suite":suite,
            "synthetic_only":True,"checkpoint":before,"runtime_versions":versions,
            "model_load_ms":load_ms,"device":"cpu","compute_type":"int8","cases":cases,
            "exact_digital_silence_guard":suite=="guarded",
            "guard_abstentions":sum(r.get("inference_attempted") is False for r in cases),
            "repeat_negative_cases":sum("_repeat_" in r["case_id"] for r in cases),
            **evaluate_cases(cases,speech_fixtures,negative_fixtures),"asr_evaluated_on_synthetic":True,
            "asr_validated_on_real_speech":False,"independent_gold":False,
            "real_media_processed":0,"real_media_processing_allowed":False,
            "external_data_accessed":False,"database_mutated":False,
            "rubric_assessments_written":0,"scientific_admissions":0,"production_approved":False}
