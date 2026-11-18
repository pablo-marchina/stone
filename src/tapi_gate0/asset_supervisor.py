"""Supervised synthetic child probe; no real model execution enabled.

Only the fixed authored header fixture and pinned probe configuration are
accepted. Uses a direct Python child, no shell/credentials/temporary plaintext.
The child is fixed code with no descendants; not an OS sandbox or production
process-tree supervisor. Never pass external media to this probe.
"""
import os
import subprocess
import sys
import time
from hashlib import sha256

from .asset_rights import AssetRightsDenied
from .asset_jobs import AssetJobQueue,Lease
from .asset_indexed_vault import IndexedAssetVault

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


def run_fixture_probe(queue:AssetJobQueue,vault:IndexedAssetVault,lease:Lease):
    """Run a bounded synthetic probe through the real queue and indexed vault.

    Completion is a receipt only, never a visual feature or scientific label.
    On denial/error the caller must reconcile/cancel the lease or let it expire.
    No automatic retry, heartbeat renewal, scheduler or external media.
    """
    if not isinstance(queue,AssetJobQueue) or not isinstance(vault,IndexedAssetVault):
        _deny("HOST_REQUIRED")
    if queue.index.engine is not vault._index.engine:
        _deny("ENGINE_MISMATCH")
    spec,ref=queue.check_lease(lease)
    if (spec.processor!="temporal" or spec.method_version!=METHOD
        or spec.configuration_sha256!=configuration_sha256()
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
    output=_run_child(data,check)
    check()
    receipt=queue.finish(lease,sha256(output).hexdigest())
    return {**receipt,"synthetic_probe":True,"model_calls":0,
        "scientific_evidence":False,"payload_persisted":False,"media_enabled":False}
