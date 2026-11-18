"""Fixed header-only fixture adapters through Windows supervisor and AEAD store.

No arbitrary media, external model, rubric or EvidenceBundle admission. The
existing opaque store is unchanged: only this trusted path enforces the
candidate result contract. A header is not an audiovisual observation.
"""
from dataclasses import asdict
from hashlib import sha256
import json

from . import asset_supervisor as supervisor
from . import asset_windows_job as windows
from .asset_derived_payloads import DerivedPayloadStore
from .asset_processor_results import (ProcessorResult, Abstention, VERSION,
                                      encode, decode, validate_binding)
from .asset_rights import AssetRightsDenied

METHOD = "synthetic-typed-windows-v3"
PROCESSORS = ("asr_vad","ocr","temporal","vlm")
EXPECTED = b'{"state":"abstained","reason":"fixture_header_only"}'
_CHILD = r"""
import sys
data=sys.stdin.buffer.read(13)
if data != b"\x00\x00\x00\x0cftypisom":
    sys.exit(2)
sys.stdout.buffer.write(b'{"state":"abstained","reason":"fixture_header_only"}')
"""


def configuration_sha256(processor):
    if processor not in PROCESSORS:
        raise ValueError("PROCESSOR_FIXTURE_UNKNOWN")
    config={"schema":VERSION,"method":METHOD,"processor":processor,
            "child":_CHILD,"fixture_sha256":sha256(supervisor.FIXTURE).hexdigest(),
            "expected_sha256":sha256(EXPECTED).hexdigest(),
            "limits":asdict(supervisor.WINDOWS_LIMITS),
            "job_flags":windows.FLAGS,"job_name":windows.JOB_NAME}
    return sha256(json.dumps(config,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def run_typed_fixture_windows(queue,vault,store,lease):
    """Validate kernel cleanup, exact input, result binding and encrypted finish.

    The child cannot choose tenant, job, method, purpose, or evidence status.
    The host supplies these from the fenced job/retained reference. A denied
    finish leaves no payload; queue cancellation/retry remains caller-owned.
    """
    if not isinstance(store,DerivedPayloadStore) or store.queue is not queue:
        raise AssetRightsDenied("PROCESSOR_FIXTURE_STORE_MISMATCH")
    try:
        windows._native_api()
        spec,ref=queue.check_lease(lease)
        if spec.processor not in PROCESSORS:
            raise AssetRightsDenied("PROCESSOR_FIXTURE_UNKNOWN")
        data,check=supervisor._fixture_input(queue,vault,lease,METHOD,
            configuration_sha256(spec.processor),processor=spec.processor)
        output=windows._run_trusted_fixture(_CHILD,data,EXPECTED,check,
            limits=supervisor.WINDOWS_LIMITS)
        check()
        if output!=EXPECTED:
            raise AssetRightsDenied("PROCESSOR_FIXTURE_OUTPUT_INVALID")
        result=ProcessorResult(tenant_id=spec.tenant_id,job_id=spec.job_id,
            object_id=spec.object_id,input_sha256=ref.target.sha256,
            attempt=lease.attempt,purpose=spec.purpose,method_version=spec.method_version,
            configuration_sha256=spec.configuration_sha256,origin="synthetic_fixture",
            result=Abstention(processor=spec.processor,reason="fixture_header_only"))
        payload=encode(result)
        validate_binding(decode(payload),spec=spec,ref=ref,lease=lease)
        check()
        receipt=store.finish(lease,payload=payload)
        return {**receipt,"processor_result_schema":VERSION,"result_state":"abstained",
                "synthetic_fixture":True,"model_calls":0,"canonical_rubric":False}
    except windows.JobError as exc:
        raise AssetRightsDenied("PROCESSOR_FIXTURE_WINDOWS_"+str(exc)) from exc
