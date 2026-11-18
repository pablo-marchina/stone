"""Supervised synthetic child probe; no real model execution enabled.

Only the fixed authored header fixture and pinned probe configuration are
accepted. Uses a direct Python child, no shell/credentials/temporary plaintext.
The child is fixed code with no descendants; not an OS sandbox or production
process-tree supervisor. Never pass external media to this probe.
"""
import json
import os
from dataclasses import asdict
import subprocess
import sys
import time
from hashlib import sha256

from .asset_rights import AssetRightsDenied
from .asset_jobs import AssetJobQueue,Lease
from .asset_indexed_vault import IndexedAssetVault
from . import asset_windows_job as windows

FIXTURE=b"\x00\x00\x00\x0cftypisom"
METHOD="synthetic-supervisor-v1"
EXPECTED=b'{"fixture":true,"input_bytes":12}'
_CHILD=r"""
import sys
data=sys.stdin.buffer.read(13)
if data != b"\x00\x00\x00\x0cftypisom":
    sys.exit(2)
sys.stdout.buffer.write(b'{"fixture":true,"input_bytes":12}')
"""
TIMEOUT_SECONDS=15
POLL_SECONDS=0.25


def configuration_sha256():
    return sha256(("synthetic-supervisor.v1:"+_CHILD).encode()).hexdigest()


def _deny(code):
    raise AssetRightsDenied("ASSET_SUPERVISOR_"+code)


def _run_child(data,check):
    check()
    deadline=time.monotonic()+TIMEOUT_SECONDS
    env={key:os.environ[key] for key in ("SystemRoot","WINDIR") if key in os.environ}
    process=subprocess.Popen([sys.executable,"-I","-S","-c",_CHILD],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        env=env,shell=False,close_fds=True)
    try:
        first=True
        while True:
            check()
            remaining=deadline-time.monotonic()
            if remaining<=0:
                _deny("TIMEOUT")
            try:
                output,_=process.communicate(input=data if first else None,
                    timeout=min(POLL_SECONDS,remaining))
                break
            except subprocess.TimeoutExpired:
                first=False
        check()
        if time.monotonic()>deadline:
            _deny("TIMEOUT")
        if process.returncode!=0 or output!=EXPECTED:
            _deny("PROBE_OUTPUT_INVALID")
        return output
    finally:
        # The fixed child cannot spawn descendants. On any failure terminate
        # this child and wait before returning control to the caller.
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
        process.wait(timeout=5)


def _fixture_input(queue,vault,lease,method,config):
    """Shared trusted-host rights/fence checks, exact fixture and method binding."""
    if not isinstance(queue,AssetJobQueue) or not isinstance(vault,IndexedAssetVault):
        _deny("HOST_REQUIRED")
    if queue.index.engine is not vault._index.engine:
        _deny("ENGINE_MISMATCH")
    spec,ref=queue.check_lease(lease)
    if (spec.processor!="temporal" or spec.method_version!=method
        or spec.configuration_sha256!=config
        or ref.target.sha256!=sha256(FIXTURE).hexdigest() or ref.byte_count!=len(FIXTURE)
        or ref.mime!="video/mp4"):
        _deny("FIXTURE_ONLY")
    def check():
        current,current_ref=queue.check_lease(lease)
        if current!=spec or current_ref!=ref:
            _deny("BINDING_CHANGED")
    anchor=queue.resolve_anchor(ref)
    data=vault.read_indexed(anchor,spec.tenant_id,spec.object_id,purpose=spec.purpose)
    if data!=FIXTURE:
        _deny("FIXTURE_ONLY")
    return data,check


def run_fixture_probe(queue:AssetJobQueue,vault:IndexedAssetVault,lease:Lease):
    """Legacy synthetic direct-child probe; never production processing."""
    data,check=_fixture_input(queue,vault,lease,METHOD,configuration_sha256())
    output=_run_child(data,check)
    check()
    receipt=queue.finish(lease,sha256(output).hexdigest())
    return {**receipt,"synthetic_probe":True,"model_calls":0,
        "scientific_evidence":False,"payload_persisted":False,"media_enabled":False}


# Distinct method/config identity: never silently promote a v1 receipt.
WINDOWS_METHOD="synthetic-windows-job-v2"
WINDOWS_LIMITS=windows.JobLimits()


def windows_configuration_sha256():
    config={"method":WINDOWS_METHOD,"child":_CHILD,"limits":asdict(WINDOWS_LIMITS),
        "job_flags":windows.FLAGS,"job_name":windows.JOB_NAME}
    return sha256(json.dumps(config,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def run_fixture_probe_windows(queue:AssetJobQueue,vault:IndexedAssetVault,lease:Lease):
    """Windows x64 synthetic probe; no production adapter or external asset.

    Kernel job assignment and limit readback are required; unsupported hosts
    fail closed, never fall back to the v1 direct-child probe. Job cleanup
    completes before the final fence/rights recheck and receipt. No heartbeat
    renewal, retry, or automatic cancellation acknowledgement.
    """
    try:
        windows._native_api()
        data,check=_fixture_input(queue,vault,lease,WINDOWS_METHOD,windows_configuration_sha256())
        output=windows._run_trusted_fixture(_CHILD,data,EXPECTED,check,limits=WINDOWS_LIMITS)
    except windows.JobError as exc:
        _deny("WINDOWS_"+str(exc))
    check()
    receipt=queue.finish(lease,sha256(output).hexdigest())
    return {**receipt,"synthetic_probe":True,"supervisor":"windows_job_v2",
        "kernel_job_limits_verified":True,"tree_empty_verified":True,"model_calls":0,
        "scientific_evidence":False,"payload_persisted":False,"media_enabled":False}
