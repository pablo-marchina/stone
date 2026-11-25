"""Qwen3-VL single-scene candidate on exact authored PNG fixtures only."""
from dataclasses import asdict
from hashlib import sha256
import base64
import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import sysconfig
import time

METHOD="synthetic-vlm-qwen3-single-scene-v1"
CASES={"sales":"text_card","geometry":"geometry","blank":"blank"}
SERVER_PIN="4b7b76781602666a54170536852c0975c71b0344e9a3b2f9b9bc95d36713414d"
MAX_OUTPUT=32768
MAX_HTTP=100000


def digest(raw):
    return sha256(raw).hexdigest()


# Authored 960x540 grayscale PNGs; exact bytes fixed at development.
FIXTURES = {'sales': ('iVBORw0KGgoAAAANSUhEUgAAA8AAAAIcCAAAAAAcNpinAAAYRklEQVR4nO3de5yUdb3A8c9yWZA7q2heyVNCwkHNtDQ5mkmihnq8oXk7opaZd09eysoup6OVd08WnFOkvigrQyIlLyimGSiYBpqZlRdES2BZUG4L7J4/ZmbneWZnZmfhcfd8z+vz/sPmeZ6Z3/6Y5rPzzDPPzNY1IymqHt09AUmbz4ClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgKzIClwAxYCsyApcAMWArMgKXADFgK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'), 'geometry': ('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', 'a2cc71701afd90ccb84265365e5f2d939b9ba288990205aaf1c45d09cde5c3eb'), 'blank': ('iVBORw0KGgoAAAANSUhEUgAAA8AAAAIcCAAAAAAcNpinAAAGL0lEQVR4nO3TMQ0AIBDAQMC/4p/wwEKa3Cno0j0LqDq/A4B3BoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ9gF4ZIFMgBofqAAAAAASUVORK5CYII=', 'da0203296d11d53b640bf3f34ea434bdcd2675c8a5b7774628318a4279d560c2')}

def fixture(case):
    if case not in CASES:
        raise ValueError("VLM_FIXTURE_UNKNOWN")
    encoded,pin=FIXTURES[case]
    raw=base64.b64decode(encoded,validate=True)
    if not 0<len(raw)<=131072 or digest(raw)!=pin:
        raise ValueError("VLM_FIXTURE_PIN")
    return raw,CASES[case]


def _hash_file(p,limit):
    p=Path(p)
    if not p.is_file() or p.is_symlink() or not 0<p.stat().st_size<=limit:
        raise ValueError("VLM_FIXTURE_FILE_INVALID")
    h=sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()


def _runtime(model_dir,server_exe):
    from . import multimodal_vlm as base
    from importlib.metadata import version
    checkpoint=base.verify_checkpoint(model_dir)
    binary=Path(server_exe)
    if (not binary.is_absolute() or binary.resolve()!=binary.absolute() or
            binary.name.lower()!="llama-server.exe" or _hash_file(binary,512*1024**2)!=SERVER_PIN):
        raise ValueError("VLM_FIXTURE_SERVER_PIN")
    dlls=sorted(binary.parent.glob("*.dll"))
    if len(dlls)>64:
        raise ValueError("VLM_FIXTURE_DLL_COUNT")
    root=Path(__file__).resolve().parent
    return {"checkpoint":checkpoint,"server_sha256":SERVER_PIN,
            "dll_sha256":{p.name:_hash_file(p,512*1024**2) for p in dlls},
            "versions":{n:version(n) for n in ("Pillow","httpx","pydantic")},
            "sources":{n:_hash_file(root/n,2_000_000) for n in ("asset_vlm_fixture.py","multimodal_vlm.py","multimodal_vlm_single_scene.py")}}


def _child(data,model_dir,server_exe):
    paths=list(dict.fromkeys([str(Path(__file__).resolve().parents[1]),sysconfig.get_path("purelib"),sysconfig.get_path("platlib")]))
    return f'''import sys, hashlib
x=sys.stdin.buffer.read({len(data)+1})
if len(x)!={len(data)} or hashlib.sha256(x).hexdigest()!={digest(data)!r}:
    sys.exit(2)
wire=sys.stdout.buffer
def stage(name):
    wire.write(("TAPI_VLM_STAGE:"+name+"\\n").encode("ascii"));wire.flush()
stage("bootstrap")
try:
    import os, json, contextlib
    sys.path.extend({paths!r})
    os.environ.update(HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",HF_HUB_DISABLE_TELEMETRY="1",LLAMA_OFFLINE="1")
    _dll=[]
    if os.name=="nt":
        for p in (sys.prefix,os.path.join(sys.prefix,"Library","bin"),os.path.join(sys.prefix,"DLLs")):
            if os.path.isdir(p): _dll.append(os.add_dll_directory(p))
    stage("imports")
    from tapi_gate0.asset_vlm_fixture import _infer
    with contextlib.redirect_stdout(sys.stderr):
        result=_infer(x,{str(model_dir)!r},{str(server_exe)!r},stage=stage)
    stage("serialize")
    out=json.dumps(result,allow_nan=False,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    if not 0<len(out)<=31744: sys.exit(3)
    sys.stdout.buffer.write(b"TAPI_VLM_RESULT\\n"+out)
except Exception as exc:
    name=type(exc).__name__
    if name not in ("MemoryError","ImportError","OSError","RuntimeError","ValueError"): name="Other"
    message=str(exc).lower()
    reason="memory" if name=="MemoryError" or "out of memory" in message or "allocat" in message else "dll" if "dll" in message else "file" if "file" in message else "other"
    sys.stdout.buffer.write(("TAPI_VLM_ERROR:"+name+":"+reason+"\\n").encode("ascii"));sys.stdout.buffer.flush()
    sys.exit(4)
'''


def plan(case,model_dir,server_exe):
    data,expected=fixture(case)
    return _plan_image(data,expected,case,model_dir,server_exe)


def _plan_image(data,expected,case,model_dir,server_exe):
    from . import asset_windows_job as windows
    from . import multimodal_vlm_single_scene as scene
    runtime=_runtime(model_dir,server_exe)
    code=_child(data,model_dir,server_exe)
    config={"method":METHOD,"case":case,"input_sha256":digest(data),"expected":expected,
            "runtime":runtime,"code_sha256":digest(code.encode()),"limits":asdict(windows.VlmFixtureLimits()),
            "job_flags":windows.FLAGS,"job_name":windows.JOB_NAME,"max_output":MAX_OUTPUT,
            "prompt_sha256":digest(scene.PROMPT.encode()),"schema":scene.SCHEMA,
            "context":2048,"threads":4,"max_tokens":64,"seed":20261117,"temperature":0,
            "min_physical_mib":windows.MODEL_MIN_PHYSICAL_MIB,"commit_reserve_mib":windows.MODEL_COMMIT_RESERVE_MIB}
    return {**config,"configuration_sha256":digest(json.dumps(config,sort_keys=True,separators=(",",":")).encode())},code


def _json(raw):
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d: raise ValueError("VLM_FIXTURE_DUPLICATE_KEY")
            d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError("VLM_FIXTURE_NONFINITE")))


def _bounded_json(client,method,path,**kwargs):
    with client.stream(method,path,**kwargs) as response:
        response.raise_for_status()
        raw=bytearray()
        for block in response.iter_bytes(chunk_size=8192):
            raw.extend(block)
            if len(raw)>MAX_HTTP: raise ValueError("VLM_FIXTURE_HTTP_SIZE")
    return _json(bytes(raw))


def _server_env(key):
    # Ephemeral local key in the child environment, no key file or argv secret.
    return {**{k:os.environ[k] for k in ("SystemRoot","WINDIR") if k in os.environ},
            "LLAMA_API_KEY":key,"LLAMA_OFFLINE":"1","HF_HUB_OFFLINE":"1",
            "TRANSFORMERS_OFFLINE":"1","HF_HUB_DISABLE_TELEMETRY":"1"}


def _request(raw,model_dir,server_exe,*,stage):
    import httpx
    from . import multimodal_vlm as base
    from . import multimodal_vlm_single_scene as scene
    key=secrets.token_hex(32);alias="tapi-fixture-"+secrets.token_hex(8)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    names=list(base.FILES)
    args=[str(server_exe),"--offline","--host","127.0.0.1","--port",str(port),"--alias",alias,"--no-webui",
          "-m",str(Path(model_dir)/names[0]),"--mmproj",str(Path(model_dir)/names[1]),
          "-ngl","0","--no-mmproj-offload","-c","2048","-t","4","-np","1"]
    stage("model_load")
    p=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        cwd=str(Path(server_exe).parent),env=_server_env(key),shell=False,close_fds=True)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}",trust_env=False,follow_redirects=False,
                headers={"Authorization":"Bearer "+key},timeout=60) as client:
            deadline=time.monotonic()+25
            while time.monotonic()<deadline:
                if p.poll() is not None: raise RuntimeError("VLM_FIXTURE_SERVER_EXIT")
                try:
                    health=_bounded_json(client,"GET","/health",timeout=2)
                    if health.get("status")=="ok": break
                except (httpx.ConnectError,httpx.TimeoutException): pass
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code!=503: raise
                time.sleep(.25)
            else: raise RuntimeError("VLM_FIXTURE_SERVER_START_TIMEOUT")
            # Health/models may be public; require auth on the inference endpoint
            # using an empty invalid request (no image or inference prompt).
            with httpx.Client(base_url=f"http://127.0.0.1:{port}",trust_env=False,follow_redirects=False,timeout=2) as anon:
                with anon.stream("POST","/v1/chat/completions",json={}) as resp:
                    if resp.status_code!=401: raise ValueError("VLM_FIXTURE_AUTH_REQUIRED")
            models=_bounded_json(client,"GET","/v1/models",timeout=5)
            if alias not in {m.get("id") for m in models["data"]}: raise ValueError("VLM_FIXTURE_ALIAS")
            stage("inference")
            result=_bounded_json(client,"POST","/v1/chat/completions",json={"model":alias,"temperature":0,"seed":20261117,
                "max_tokens":64,"stream":False,"response_format":{"type":"json_object","schema":scene.SCHEMA},
                "messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,"+base64.b64encode(raw).decode("ascii")}},{"type":"text","text":scene.PROMPT}]}]})
            if result.get("model")!=alias or p.poll() is not None: raise ValueError("VLM_FIXTURE_ALIAS")
            choices=result.get("choices")
            if not isinstance(choices,list) or len(choices)!=1: raise ValueError("VLM_FIXTURE_RESPONSE")
            content=choices[0]["message"]["content"]
            if type(content) is not str or len(content.encode("utf-8"))>1024: raise ValueError("VLM_FIXTURE_RESPONSE")
            return parse_scene(content),digest(content.encode())
    finally:
        if p.poll() is None:
            p.terminate()
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired: p.kill();p.wait(timeout=5)


def parse_scene(raw):
    if type(raw) is not str or not 0<len(raw.encode())<=1024: raise ValueError("VLM_FIXTURE_RESPONSE")
    obj=_json(raw)
    if type(obj) is not dict or set(obj)!={"scene"} or obj["scene"] not in ("blank","text_card","geometry","uncertain"):
        raise ValueError("VLM_FIXTURE_SCENE")
    return obj["scene"]


def _infer(raw,model_dir,server_exe,*,stage):
    from PIL import Image
    from .multimodal_vlm_single_scene import exact_uniform
    with Image.open(io.BytesIO(raw)) as im:
        if im.format!="PNG": raise ValueError("VLM_FIXTURE_IMAGE")
        uniform=exact_uniform(im)
    if uniform:
        return {"input_sha256":digest(raw),"scene":"blank","model_scene":None,"response_sha256":None,"model_calls":0}
    model_scene,response_hash=_request(raw,model_dir,server_exe,stage=stage)
    return {"input_sha256":digest(raw),"scene":"uncertain" if model_scene=="blank" else model_scene,
            "model_scene":model_scene,"response_sha256":response_hash,"model_calls":1}


def result_from_output(case,raw):
    data,expected=fixture(case)
    return _result_for_image(data,expected,raw)


def _result_for_image(data,expected,raw):
    from .asset_processor_results import VLM,Frame
    if type(raw) is not bytes or not 0<len(raw)<=MAX_OUTPUT: raise ValueError("VLM_FIXTURE_OUTPUT_SIZE")
    r=_json(raw)
    if type(r) is not dict or set(r)!={"input_sha256","scene","model_scene","response_sha256","model_calls"} or r["input_sha256"]!=digest(data):
        raise ValueError("VLM_FIXTURE_OUTPUT_BINDING")
    if type(r["model_calls"]) is not int or r["model_calls"]!=int(expected!="blank"):
        raise ValueError("VLM_FIXTURE_CALLS")
    if expected=="blank":
        if r["scene"]!="blank" or r["model_scene"] is not None or r["response_sha256"] is not None: raise ValueError("VLM_FIXTURE_GUARD")
    else:
        h=r["response_sha256"]
        if type(h) is not str or len(h)!=64 or any(c not in "0123456789abcdef" for c in h): raise ValueError("VLM_FIXTURE_RESPONSE_HASH")
        if r["model_scene"]!=r["scene"]: raise ValueError("VLM_FIXTURE_SCENE_CONFLICT")
    # Three-class one-example-per-class integration gate, no incorrect or abstained case.
    if r["scene"]!=expected: raise ValueError("VLM_FIXTURE_QUALITY_GATE")
    return VLM(frame=Frame(time_ms=0,frame_sha256=digest(data),timeline="image"),scene=expected,
               text_present="yes" if expected=="text_card" else "no"),r["model_calls"]


def run_vlm_fixture_windows(queue,vault,store,lease,*,case,model_dir,server_exe):
    from . import asset_windows_job as windows
    from .asset_jobs import AssetJobQueue
    from .asset_indexed_vault import IndexedAssetVault
    from .asset_derived_payloads import DerivedPayloadStore
    from .asset_rights import AssetRightsDenied
    from .asset_processor_results import ProcessorResult,encode,decode,validate_binding
    if (not isinstance(queue,AssetJobQueue) or not isinstance(vault,IndexedAssetVault) or
        queue.index.engine is not vault._index.engine or not isinstance(store,DerivedPayloadStore) or store.queue is not queue):
        raise AssetRightsDenied("VLM_FIXTURE_HOST_MISMATCH")
    try:
        windows._native_api()
        spec,ref=queue.check_lease(lease)
        if case not in CASES or spec.processor!="vlm" or spec.method_version!=METHOD or ref.mime!="image/png": raise AssetRightsDenied("VLM_FIXTURE_ONLY")
        data,_=fixture(case)
        if ref.target.sha256!=digest(data) or ref.byte_count!=len(data): raise AssetRightsDenied("VLM_FIXTURE_ONLY")
        config,code=plan(case,model_dir,server_exe)
        if spec.configuration_sha256!=config["configuration_sha256"]: raise AssetRightsDenied("VLM_FIXTURE_CONFIG")
        def check():
            s,r=queue.check_lease(lease)
            if s!=spec or r!=ref: raise AssetRightsDenied("VLM_FIXTURE_BINDING")
        actual=vault.read_indexed(queue.resolve_anchor(ref),spec.tenant_id,spec.object_id,purpose=spec.purpose)
        if actual!=data: raise AssetRightsDenied("VLM_FIXTURE_ONLY")
        check()
        output,metrics=windows._run_vlm_fixture(code,actual,check,limits=windows.VlmFixtureLimits(),max_output=MAX_OUTPUT)
        if _runtime(model_dir,server_exe)!=config["runtime"]: raise AssetRightsDenied("VLM_FIXTURE_RUNTIME_CHANGED")
        observation,calls=result_from_output(case,output)
        result=ProcessorResult(tenant_id=spec.tenant_id,job_id=spec.job_id,object_id=spec.object_id,input_sha256=ref.target.sha256,
            attempt=lease.attempt,purpose=spec.purpose,method_version=spec.method_version,configuration_sha256=spec.configuration_sha256,
            origin="adapter_candidate",result=observation)
        payload=encode(result);validate_binding(decode(payload),spec=spec,ref=ref,lease=lease);check()
        receipt=store.finish(lease,payload=payload)
        return {**receipt,"processor":"vlm","fixture_case":case,"synthetic_fixture":True,"result_state":observation.state,
                "canonical_rubric":False,"kernel_job_limits_verified":True,"tree_empty_verified":True,"model_calls":calls,"resources":metrics}
    except windows.JobError as exc:
        raise AssetRightsDenied("VLM_FIXTURE_WINDOWS_"+str(exc)) from exc
