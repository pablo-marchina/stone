"""Real Tesseract OCR on three exact authored PNG fixtures only.

No arbitrary image, model download, external media, rubric or EvidenceBundle.
Trusted host provides the local tessdata directory; job pin binds its contents.
"""
from base64 import b64decode
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import shutil
import csv
import io

from . import asset_windows_job as windows
from .asset_processor_results import Frame, Word, OCR, Abstention, ProcessorResult, encode, decode, validate_binding

METHOD = "synthetic-ocr-tesseract-v5"
LIMITS = windows.JobLimits(memory_mib=512,cpu_user_seconds=10,active_processes=2,wall_seconds=30)
MAX_TSV = 16384
WIDTH,HEIGHT = 960,540
# Authored grayscale PNG text cards (Pillow default font) and blank control.
FIXTURES = {
    'sales': ('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', ('Organize', 'suas', 'vendas')),
    'cta': ('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AQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBgjYMAYAQPGCBgwRsCAMQIGjBEwYIyAAWMEDBj7f5+yKOvPQ+vcAAAAAElFTkSuQmCC', '8cfc054bd53bba7323c2bbe4954dabc4a67b908cb30a73f917cd3245f3cba570', ('Salve', 'para', 'revisar', 'depois')),
    'blank': ('iVBORw0KGgoAAAANSUhEUgAAA8AAAAIcCAAAAAAcNpinAAAGL0lEQVR4nO3TMQ0AIBDAQMC/4p/wwEKa3Cno0j0LqDq/A4B3BoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ9gF4ZIFMgBofqAAAAAASUVORK5CYII=', 'da0203296d11d53b640bf3f34ea434bdcd2675c8a5b7774628318a4279d560c2', ()),
}


def fixture(case):
    if case not in FIXTURES:
        raise ValueError("OCR_FIXTURE_UNKNOWN")
    encoded,digest,words=FIXTURES[case]
    data=b64decode(encoded,validate=True)
    if sha256(data).hexdigest()!=digest:
        raise ValueError("OCR_FIXTURE_PIN")
    return data,words


def _runtime(directory):
    from .multimodal_ocr import verify_tessdata
    from .multimodal_asr import _file_hash
    found=shutil.which("tesseract")
    if not found:
        raise ValueError("OCR_FIXTURE_TESSERACT_REQUIRED")
    binary=Path(found).resolve(strict=True)
    if not binary.is_file() or not 0<binary.stat().st_size<=512*1024*1024:
        raise ValueError("OCR_FIXTURE_RUNTIME_INVALID")
    return str(binary),_file_hash(binary),verify_tessdata(directory)


def _child(binary,directory,data):
    args=[binary,"stdin","stdout","--tessdata-dir",str(directory),"-l","por+eng",
          "--oem","1","--psm","11","-c","tessedit_create_tsv=1","-c","tessedit_create_txt=0"]
    # Fixed PNG and decoder. Bound stdout read before forwarding any bytes.
    # If an unexpected blocking decoder occurs, the parent job terminates it.
    return f'''import sys, hashlib, subprocess, os
x=sys.stdin.buffer.read({len(data)+1})
if len(x)!={len(data)} or hashlib.sha256(x).hexdigest()!={sha256(data).hexdigest()!r}:
    sys.exit(2)
env=dict(os.environ,OMP_THREAD_LIMIT="1")
p=subprocess.Popen({args!r},stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,shell=False,close_fds=True)
try:
    p.stdin.write(x)
    p.stdin.close()
    out=p.stdout.read({MAX_TSV+1})
    if not out or len(out)>{MAX_TSV}:
        sys.exit(3)
    if p.wait()!=0:
        sys.exit(4)
    sys.stdout.buffer.write(out)
finally:
    if p.poll() is None:
        p.kill()
    p.wait()
'''


def plan(case,directory):
    data,words=fixture(case)
    binary,runtime_sha,language_sha=_runtime(directory)
    code=_child(binary,directory,data)
    config={"method":METHOD,"case":case,"input_sha256":sha256(data).hexdigest(),
            "expected_words":list(words),"runtime_sha256":runtime_sha,"language_sha256":language_sha,
            "code_sha256":sha256(code.encode()).hexdigest(),"limits":asdict(LIMITS),
            "max_tsv":MAX_TSV,"job_flags":windows.FLAGS,"job_name":windows.JOB_NAME,
            "parser":"bd-ocr-fixture.v1"}
    pin=sha256(json.dumps(config,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return {**config,"configuration_sha256":pin},code


def result_from_tsv(case,raw):
    from .multimodal_ocr import parse_tsv
    data,expected=fixture(case)
    if type(raw) is not bytes or not 0<len(raw)<=MAX_TSV:
        raise ValueError("OCR_FIXTURE_TSV_SIZE")
    # Require a complete single-page TSV (blank must have a page row too).
    # Reject malformed/truncated rows rather than treating them as no words.
    header="level page_num block_num par_num line_num word_num left top width height conf text".split()
    reader=csv.reader(io.StringIO(raw.decode("utf-8-sig")),delimiter="\t",quoting=csv.QUOTE_NONE)
    rows=list(reader)
    if not rows or rows[0]!=header or len(rows)<2 or len(rows)>1024:
        raise ValueError("OCR_FIXTURE_TSV_STRUCTURE")
    page=["1","1","0","0","0","0","0","0",str(WIDTH),str(HEIGHT),"-1",""]
    # Tesseract may print -1 or -1.000000 on nonword rows.
    if (len(rows[1])!=12 or rows[1][:10]!=page[:10] or rows[1][10] not in ("-1","-1.000000") or rows[1][11]!=""):
        raise ValueError("OCR_FIXTURE_TSV_PAGE")
    seen=set()
    for row in rows[2:]:
        if len(row)!=12 or row[0] not in ("2","3","4","5") or row[1]!="1":
            raise ValueError("OCR_FIXTURE_TSV_STRUCTURE")
        if row[0]=="5":
            key=tuple(row[1:6])
            if key in seen or not row[11].strip():
                raise ValueError("OCR_FIXTURE_TSV_WORD")
            seen.add(key)
        elif row[11]!="":
            raise ValueError("OCR_FIXTURE_TSV_STRUCTURE")
    measured=parse_tsv(raw)
    if tuple(w["text"] for w in measured)!=expected or len(measured)!=len(seen):
        raise ValueError("OCR_FIXTURE_WORD_MISMATCH")
    if not measured:
        return Abstention(processor="ocr",reason="no_observable_signal")
    return OCR(frame=Frame(time_ms=0,frame_sha256=sha256(data).hexdigest(),timeline="image"),
               width=WIDTH,height=HEIGHT,words=tuple(Word(text=w["text"],box_px=tuple(w["box_px"]),
               confidence_raw=w["confidence_raw"]) for w in measured))


def run_ocr_fixture_windows(queue,vault,store,lease,*,tessdata_dir):
    from .asset_jobs import AssetJobQueue
    from .asset_indexed_vault import IndexedAssetVault
    from .asset_derived_payloads import DerivedPayloadStore
    from .asset_rights import AssetRightsDenied
    if (not isinstance(queue,AssetJobQueue) or not isinstance(vault,IndexedAssetVault)
            or queue.index.engine is not vault._index.engine or not isinstance(store,DerivedPayloadStore)
            or store.queue is not queue):
        raise AssetRightsDenied("OCR_FIXTURE_HOST_MISMATCH")
    try:
        windows._native_api()
        spec,ref=queue.check_lease(lease)
        case=next((c for c,(_,digest,_) in FIXTURES.items() if digest==ref.target.sha256),None)
        if case is None or spec.processor!="ocr" or spec.method_version!=METHOD or ref.mime!="image/png":
            raise AssetRightsDenied("OCR_FIXTURE_ONLY")
        data,_=fixture(case)
        config,code=plan(case,tessdata_dir)
        if ref.byte_count!=len(data) or spec.configuration_sha256!=config["configuration_sha256"]:
            raise AssetRightsDenied("OCR_FIXTURE_CONFIG")
        def check():
            s,r=queue.check_lease(lease)
            if s!=spec or r!=ref:
                raise AssetRightsDenied("OCR_FIXTURE_BINDING")
        actual=vault.read_indexed(queue.resolve_anchor(ref),spec.tenant_id,spec.object_id,purpose=spec.purpose)
        if actual!=data:
            raise AssetRightsDenied("OCR_FIXTURE_ONLY")
        if plan(case,tessdata_dir)!=(config,code):
            raise AssetRightsDenied("OCR_FIXTURE_RUNTIME_CHANGED")
        raw=windows._run_bounded_fixture(code,actual,check,limits=LIMITS,max_output=MAX_TSV)
        if plan(case,tessdata_dir)!=(config,code):
            raise AssetRightsDenied("OCR_FIXTURE_RUNTIME_CHANGED")
        observation=result_from_tsv(case,raw)
        result=ProcessorResult(tenant_id=spec.tenant_id,job_id=spec.job_id,
            object_id=spec.object_id,input_sha256=ref.target.sha256,attempt=lease.attempt,
            purpose=spec.purpose,method_version=spec.method_version,
            configuration_sha256=spec.configuration_sha256,origin="adapter_candidate",result=observation)
        payload=encode(result)
        validate_binding(decode(payload),spec=spec,ref=ref,lease=lease)
        check()
        receipt=store.finish(lease,payload=payload)
        return {**receipt,"synthetic_fixture":True,"result_state":observation.state,
                "processor":"ocr","fixture_case":case,"model_calls":1,
                "canonical_rubric":False,"tesseract_sha256":config["runtime_sha256"],
                "language_sha256":config["language_sha256"],
                "kernel_job_limits_verified":True,"tree_empty_verified":True}
    except windows.JobError as exc:
        raise AssetRightsDenied("OCR_FIXTURE_WINDOWS_"+str(exc)) from exc
