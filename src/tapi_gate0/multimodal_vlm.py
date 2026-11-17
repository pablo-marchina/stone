"""IMP-063: resource-bounded Qwen3-VL synthetic frame evaluation.

Uses a private authenticated loopback llama-server child; no remote model
requests, user images, real media or canonical rubric decisions.
"""
import base64
from contextlib import contextmanager
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time

from . import multimodal_shared_fixture as shared
from . import multimodal_semantic_replay as replay
from .multimodal_asr import _file_hash

VERSION="bd-vlm-frame-fixture.v1"
MODEL_ID="Qwen/Qwen3-VL-2B-Instruct-GGUF"
MODEL_REVISION="d38d39f5972e27cd58023f9b1e9f994b0c85ca47"
FILES={
    "Qwen3VL-2B-Instruct-Q4_K_M.gguf":"089d75c52f4b7ffc56ba998ffc50aae89fcafc755f9e7208aacca281dca6c2ae",
    "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf":"f9a68fabba69c3b81e153367b2c7521030b0fa8bb0de400c9599c8e6725f9c82",
}
RUNTIME_BUILD="6907"
RUNTIME_COMMIT="bea0452"
MIN_RAM=4*1024**3
MIN_PROVISION_DISK=4*1024**3
MIN_RUN_DISK=512*1024**2
SCHEMA={"type":"object","properties":{"text_present":{"type":"string","enum":["yes","no","uncertain"]},
        "scene":{"type":"string","enum":["blank","text_card","geometry","uncertain"]}},
        "required":["text_present","scene"],"additionalProperties":False}
PROMPT=("Observe somente os pixels. Há texto escrito legível, não apenas formas que lembram letras? "
        "Classifique text_present como yes, no ou uncertain. Classifique scene como blank para fundo vazio, "
        "text_card para imagem que contém texto escrito, geometry para figuras sem texto, ou uncertain. "
        "Não adivinhe. Responda somente com o objeto JSON solicitado.")
class VLMError(ValueError):
    pass


def available_ram():
    if os.name=="nt":
        import ctypes
        class Memory(ctypes.Structure):
            _fields_=[("length",ctypes.c_ulong),("load",ctypes.c_ulong)]+[
                (name,ctypes.c_ulonglong) for name in ("total_phys","avail_phys","total_page","avail_page",
                                                       "total_virtual","avail_virtual","avail_extended")]
        status=Memory()
        status.length=ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.avail_phys)
        return None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1])*1024
    except (OSError,ValueError):
        pass
    return None


def model_root(directory):
    root=Path(directory)
    project=Path(__file__).resolve().parents[2]
    if not root.is_absolute() or root.resolve()!=root.absolute() or root.is_relative_to(project):
        raise VLMError("VLM_EXTERNAL_LOCAL_MODEL_DIRECTORY_REQUIRED")
    return root


def plan(directory):
    root=model_root(directory)
    existing=root
    while not existing.exists():
        existing=existing.parent
    if not existing.is_dir():
        raise VLMError("VLM_MODEL_VOLUME_INVALID")
    free=shutil.disk_usage(existing).free
    ram=available_ram()
    return {"status":"VLM_RESOURCE_PLAN","model_id":MODEL_ID,"model_revision":MODEL_REVISION,
            "files_sha256":FILES,"estimated_weights_bytes":1_560_000_000,
            "available_ram_bytes":ram,"model_volume_free_bytes":free,
            "min_ram_bytes":MIN_RAM,"min_provision_disk_bytes":MIN_PROVISION_DISK,
            "min_run_disk_bytes":MIN_RUN_DISK,"provision_disk_ready":free>=MIN_PROVISION_DISK,
            "run_memory_ready":ram is not None and ram>=MIN_RAM,"run_disk_ready":free>=MIN_RUN_DISK,
            "runtime_build":RUNTIME_BUILD,"checkpoint_verified":False,"vlm_evaluated":False,
            "threshold_kind":"conservative_engineering_preflight_not_vendor_requirement",
            "external_data_accessed":False,"real_media_processing_allowed":False}


def verify_checkpoint(directory):
    root=model_root(directory)
    result={}
    for name,expected in FILES.items():
        p=root/name
        if p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=2_000_000_000:
            raise VLMError("VLM_LOCAL_GGUF_REQUIRED")
        with p.open("rb") as stream:
            if stream.read(4)!=b"GGUF":
                raise VLMError("VLM_GGUF_MAGIC_INVALID")
        digest=_file_hash(p)
        if digest!=expected:
            raise VLMError("VLM_PUBLISHED_HASH_MISMATCH")
        result[name]={"sha256":digest,"bytes":p.stat().st_size}
    return result


def server_env():
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(("LLAMA_","HF_","GGML_"))
         and k.upper() not in ("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY")}
    env.update(LLAMA_OFFLINE="1",HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",
               HF_HUB_DISABLE_TELEMETRY="1")
    return env


def verify_runtime(executable):
    p=Path(executable)
    if (not p.is_absolute() or p.resolve()!=p.absolute() or not p.is_file()
            or p.name.lower() not in ("llama-server.exe","llama-server")):
        raise VLMError("VLM_LOCAL_SERVER_REQUIRED")
    proc=subprocess.run([str(p),"--version"],capture_output=True,stdin=subprocess.DEVNULL,
                        env=server_env(),timeout=20,check=False)
    raw=proc.stdout+proc.stderr
    if proc.returncode or len(raw)>100_000 or not re.search(rb"version:\s*6907\b[^\r\n]*bea0452",raw,re.I):
        raise VLMError("VLM_RUNTIME_BUILD_MISMATCH")
    return {"build":RUNTIME_BUILD,"commit_prefix":RUNTIME_COMMIT,"binary_sha256":_file_hash(p),
            "binary_digest_independently_verified":False}


def make_frames(report):
    replay.validate_report(report)
    from PIL import Image,ImageDraw,ImageFont
    rows=[]
    for case,row in zip(shared.CASES,report["cases"]):
        cid,caption,speech,screen,late,geometry,*_=case
        for t,observation in zip((0,3),row["ocr_frames"]):
            text=screen if not late or t==3 else ""
            raw=shared._pixels(text,inverted=late and t==3,geometry=geometry)
            if sha256(raw).hexdigest()!=observation["frame_sha256"]:
                raise VLMError("VLM_SHARED_PIXEL_HASH_MISMATCH")
            image=Image.frombytes("L",(shared.ocr.WIDTH,shared.ocr.HEIGHT),raw)
            rows.append({"case_id":cid+"_"+str(t),"suite":"shared","image":image,
                         "media_sha256":row["media_sha256"],"timestamp_s":t,
                         "expected":{"text_present":"yes" if text else "no",
                                     "scene":"text_card" if text else "geometry" if geometry else "blank"},
                         "ocr_positive_candidate":bool(observation["words"])})
    # New authored colored/layout challenge, fixed before inference.
    specs=(("blue_text","Organize seu estoque",False,44),("small_text","Vendas",False,26),
           ("mixed_text","Calcule o preço",True,38),("white_blank","",False,0),
           ("colored_blocks","",True,0),("three_circles","",True,0))
    for cid,text,shapes,size in specs:
        image=Image.new("RGB",(960,540),(230,240,250) if cid!="white_blank" else (255,255,255))
        draw=ImageDraw.Draw(image)
        if shapes:
            if cid=="three_circles":
                for x in (110,380,650):
                    draw.ellipse((x,180,x+140,320),outline=(20,40,100),width=9)
            else:
                draw.rectangle((50,50,210,160),fill=(40,80,160))
                draw.rectangle((710,370,900,490),fill=(190,50,60))
        if text:
            draw.text((65,270),text,fill=(15,30,85),font=ImageFont.load_default(size=size),anchor="lm")
        rows.append({"case_id":cid,"suite":"challenge","image":image,
                     "media_sha256":None,"timestamp_s":None,
                     "expected":{"text_present":"yes" if text else "no",
                                 "scene":"text_card" if text else "geometry" if shapes else "blank"},
                     "ocr_positive_candidate":None})
    return rows


def encode_image(image):
    stream=io.BytesIO()
    image.save(stream,format="PNG")
    raw=stream.getvalue()
    if not 0<len(raw)<=2_000_000:
        raise VLMError("VLM_IMAGE_SIZE_INVALID")
    return raw


def parse_prediction(raw):
    try:
        value=json.loads(raw)
    except (TypeError,ValueError):
        return None
    if not isinstance(value,dict) or set(value)!=set(SCHEMA["properties"]):
        return None
    if any(not isinstance(value[k],str) or value[k] not in spec["enum"] for k,spec in SCHEMA["properties"].items()):
        return None
    return value


def metrics(rows):
    suites={}
    for suite in ("shared","challenge"):
        group=[r for r in rows if r["suite"]==suite]
        result={}
        for field in ("text_present","scene"):
            labels=sorted({r["expected"][field] for r in group})
            per_class={}
            for label in labels:
                expected=[r for r in group if r["expected"][field]==label]
                correct=sum(r["prediction"] is not None and r["prediction"][field]==label for r in expected)
                per_class[label]={"expected":len(expected),"correct":correct,"recall":correct/len(expected)}
            wrong=sum(r["prediction"] is not None and r["prediction"][field] not in ("uncertain",r["expected"][field]) for r in group)
            invalid=sum(r["prediction"] is None for r in group)
            result[field]={"per_class":per_class,"wrong_nonabstained":wrong,"invalid":invalid,
                           "abstentions":sum(r["prediction"] is not None and r["prediction"][field]=="uncertain" for r in group),
                           "engineering_gate_passed":bool(per_class) and wrong==0 and invalid==0 and all(m["recall"]>=0.75 for m in per_class.values())}
        suites[suite]=result
    complete=len(rows)==20 and sum(r["suite"]=="shared" for r in rows)==14 and len({r["case_id"] for r in rows})==20
    return {"suites":suites,"engineering_gate_passed":complete and all(m["engineering_gate_passed"] for s in suites.values() for m in s.values()),
            "gate_criteria":{"each_class_min_recall":0.75,"wrong_nonabstained":0,"invalid":0,"all_20_frame_cases_required":True}}


@contextmanager
def local_server(executable,model_dir,*,schema=SCHEMA,prompt=PROMPT):
    import httpx
    with tempfile.TemporaryDirectory(prefix="tapi-vlm-server-") as temp:
        root=Path(temp)
        secret=secrets.token_hex(32)
        alias="tapi-fixture-"+secrets.token_hex(8)
        key=root/"key.txt"
        fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w",encoding="ascii") as stream:
            stream.write(secret+"\n")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0))
            port=sock.getsockname()[1]
        names=list(FILES)
        args=[str(executable),"--offline","--host","127.0.0.1","--port",str(port),
              "--api-key-file",str(key),"--alias",alias,"--no-webui",
              "-m",str(Path(model_dir)/names[0]),"--mmproj",str(Path(model_dir)/names[1]),
              "-ngl","0","--no-mmproj-offload","-c","2048","-t","4","-np","1"]
        child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                               env=server_env(),cwd=str(Path(executable).parent))
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}",trust_env=False,follow_redirects=False,
                              headers={"Authorization":"Bearer "+secret},timeout=180) as client:
                deadline=time.monotonic()+180
                while time.monotonic()<deadline:
                    if child.poll() is not None:
                        raise VLMError("VLM_SERVER_EXITED")
                    try:
                        response=client.get("/health",timeout=2)
                        if response.status_code==200 and response.json().get("status")=="ok":
                            response=client.get("/v1/models",timeout=5)
                            response.raise_for_status()
                            if alias not in {m.get("id") for m in response.json()["data"]}:
                                raise VLMError("VLM_SERVER_ALIAS_MISMATCH")
                            break
                    except (httpx.ConnectError,httpx.TimeoutException):
                        pass
                    time.sleep(1)
                else:
                    raise VLMError("VLM_SERVER_START_TIMEOUT")
                def infer(image):
                    if child.poll() is not None:
                        raise VLMError("VLM_SERVER_EXITED")
                    encoded=base64.b64encode(image).decode("ascii")
                    response=client.post("/v1/chat/completions",json={"model":alias,"temperature":0,
                        "seed":20261117,"max_tokens":64,"stream":False,
                        "response_format":{"type":"json_object","schema":schema},
                        "messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,"+encoded}},
                                                                {"type":"text","text":prompt}]}]})
                    response.raise_for_status()
                    if len(response.content)>100_000:
                        raise VLMError("VLM_RESPONSE_SIZE_INVALID")
                    payload=response.json()
                    if payload.get("model")!=alias or child.poll() is not None:
                        raise VLMError("VLM_SERVER_ALIAS_MISMATCH")
                    return payload["choices"][0]["message"]["content"]
                yield infer
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=10)


def benchmark(report,model_dir,executable):
    capacity=plan(model_dir)
    if not capacity["run_memory_ready"] or not capacity["run_disk_ready"]:
        raise VLMError("VLM_RESOURCE_PREFLIGHT_BLOCKED")
    checkpoint=verify_checkpoint(model_dir)
    runtime=verify_runtime(executable)
    frames=make_frames(report)
    rows=[]
    cache={}
    start=time.perf_counter()
    with local_server(executable,model_dir) as infer:
        load_ms=round((time.perf_counter()-start)*1000,3)
        for frame in frames:
            raw=encode_image(frame.pop("image"))
            digest=sha256(raw).hexdigest()
            cached=digest in cache
            if not cached:
                t=time.perf_counter()
                response=infer(raw)
                cache[digest]=(parse_prediction(response),sha256(response.encode("utf-8")).hexdigest(),
                               round((time.perf_counter()-t)*1000,3))
            prediction,response_hash,latency=cache[digest]
            rows.append({**frame,"image_png_sha256":digest,"prediction":prediction,
                         "response_sha256":response_hash,"inference_ms":0 if cached else latency,
                         "reused_identical_image_result":cached})
    if verify_checkpoint(model_dir)!=checkpoint or verify_runtime(executable)!=runtime:
        raise VLMError("VLM_RUNTIME_OR_MODEL_CHANGED")
    return {"status":"VLM_FRAME_BENCHMARK_COMPLETED","policy_version":VERSION,
            "model_id":MODEL_ID,"model_revision":MODEL_REVISION,"checkpoint":checkpoint,
            "runtime":runtime,"capacity_preflight":capacity,"model_load_ms":load_ms,
            "prompt_sha256":sha256(PROMPT.encode()).hexdigest(),"unique_inference_images":len(cache),
            "cases":rows,**metrics(rows),"synthetic_only":True,"vlm_evaluated":True,
            "source_report_consistency_revalidated":True,"shared_pixels_hash_matched":True,
            "source_container_redecoded":False,"network_scope":"authenticated_local_loopback_only",
            "independent_gold":False,"real_media_processed":0,"real_media_processing_allowed":False,
            "external_data_accessed":False,"database_mutated":False,"scientific_admissions":0,
            "rubric_assessments_written":0,"production_approved":False}
