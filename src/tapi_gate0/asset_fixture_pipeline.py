"""A02.7 explicit trusted-host fixture pipeline; no arbitrary media or scheduler."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

from . import asset_processor_fixture as typed, asset_supervisor as supervisor
from . import asset_temporal_fixture as temporal, asset_ocr_fixture as ocr
from . import asset_asr_fixture as asr, asset_vlm_fixture as vlm
from .asset_jobs import AssetJobQueue, JobSpec, _check_rights
from .asset_derived_payloads import DerivedPayloadStore, _extra, _artifact_id
from .asset_indexed_vault import IndexedAssetVault
from .asset_lineage_index import _grant
from .asset_rights import AssetRightsDenied, Permission
from .asset_candidate_fusion import evaluate_candidate_bundle
from . import asset_shared_av_fixture as shared

VERSION="fixture-pipeline.v1"


def _deny(code):
    raise AssetRightsDenied("FIXTURE_PIPELINE_"+code)


@dataclass(frozen=True)
class FixturePlan:
    mode: str
    case: str
    specs: tuple[JobSpec,...]

    @property
    def fingerprint(self):
        raw=json.dumps({"version":VERSION,"mode":self.mode,"case":self.case,
                        "jobs":[s.job_id for s in self.specs]},sort_keys=True,separators=(",",":"))
        return sha256(raw.encode()).hexdigest()


class FixturePipeline:
    """One explicit tick at a time. Save plan fingerprint to resume unchanged.

    No automatic retry/release after adapter exceptions: existing queue
    fencing/maintenance remain authoritative; no claim of child cleanup.
    """
    def __init__(self,queue,vault,store,*,tenant,object_id,purpose,mode,case,
                 tessdata_dir=None,asr_model_dir=None,vlm_model_dir=None,vlm_server_exe=None,
                 expected_plan=None):
        if (not isinstance(queue,AssetJobQueue) or not isinstance(vault,IndexedAssetVault)
                or not isinstance(store,DerivedPayloadStore) or store.queue is not queue
                or queue.index.engine is not vault._index.engine):
            _deny("HOST_MISMATCH")
        if purpose!="research_analysis":
            _deny("PURPOSE")
        self.queue,self.vault,self.store=queue,vault,store
        self.paths=tuple(Path(p) if p is not None else None for p in
            (tessdata_dir,asr_model_dir,vlm_model_dir,vlm_server_exe))
        t,a,v,s=self.paths
        self._shared=None
        if mode=="shared_av" and case in shared.CASES and all(x is not None for x in self.paths):
            self._shared=shared.prepare(case)
            data,mime=self._shared.data,"video/mp4"
            entries=[(p,shared.METHOD,shared.plan(self._shared,p,self.paths)[0].configuration(p))
                     for p in shared.PROCESSORS]
        elif mode=="header" and case=="header":
            data,mime=supervisor.FIXTURE,"video/mp4"
            entries=[(p,typed.METHOD,typed.configuration_sha256(p)) for p in typed.PROCESSORS]
        elif mode=="temporal" and case in temporal.FIXTURES:
            data,_=temporal.fixture(case)
            mime="video/mp4"
            entries=[("temporal",temporal.METHOD,temporal.plan(case)[0]["configuration_sha256"])]
        elif mode=="asr" and case in asr.CASES and a is not None:
            data,_=asr.fixture(case)
            mime="audio/wav"
            entries=[("asr_vad",asr.METHOD,asr.plan(case,a)[0]["configuration_sha256"])]
        elif mode=="ocr" and case in ocr.FIXTURES and t is not None:
            data,_=ocr.fixture(case)
            mime="image/png"
            entries=[("ocr",ocr.METHOD,ocr.plan(case,t)[0]["configuration_sha256"])]
        elif mode=="vlm" and case in vlm.CASES and v is not None and s is not None:
            data,_=vlm.fixture(case)
            mime="image/png"
            entries=[("vlm",vlm.METHOD,vlm.plan(case,v,s)[0]["configuration_sha256"])]
        elif mode=="image_pair" and case=="blank" and t is not None and v is not None and s is not None:
            data,_=ocr.fixture(case)
            if data!=vlm.fixture(case)[0]:
                _deny("FIXTURE_MISMATCH")
            mime="image/png"
            entries=[("ocr",ocr.METHOD,ocr.plan(case,t)[0]["configuration_sha256"]),
                     ("vlm",vlm.METHOD,vlm.plan(case,v,s)[0]["configuration_sha256"])]
        else:
            _deny("MODE_OR_CONFIG")
        self.plan=FixturePlan(mode,case,tuple(JobSpec(tenant_id=tenant,object_id=object_id,
            purpose=purpose,processor=p,method_version=m,configuration_sha256=h)
            for p,m,h in entries))
        if expected_plan is not None and self.plan.fingerprint!=expected_plan:
            _deny("PLAN_CHANGED")
        self._digest,self._size,self._mime=sha256(data).hexdigest(),len(data),mime
        self._preflight()

    def _preflight(self):
        q=self.queue
        with q._transaction() as (db,now):
            for spec in self.plan.specs:
                ref=_check_rights(db,spec,q.resolve_anchor,now)
                if (ref.target.sha256,ref.byte_count,ref.mime)!=(self._digest,self._size,self._mime):
                    _deny("FIXTURE_ONLY")
                _extra(db,q,spec,ref,now,read=True)
                _grant(db,q.resolve_anchor(ref),ref,now,Permission(operation="derive",
                    purpose=spec.purpose,field="rubric_evidence"))

    def _dispatch(self,lease,spec):
        q,vault,store=self.queue,self.vault,self.store
        t,a,v,s=self.paths
        mode,case=self.plan.mode,self.plan.case
        if mode=="shared_av":
            return shared.run(q,vault,store,lease,fixture=self._shared,paths=self.paths)
        if mode=="header":
            return typed.run_typed_fixture_windows(q,vault,store,lease)
        if mode=="temporal":
            return temporal.run_temporal_fixture_windows(q,vault,store,lease)
        if mode=="asr":
            return asr.run_asr_fixture_windows(q,vault,store,lease,case=case,model_dir=a)
        if spec.processor=="ocr" and mode in ("ocr","image_pair"):
            return ocr.run_ocr_fixture_windows(q,vault,store,lease,tessdata_dir=t)
        if spec.processor=="vlm" and mode in ("vlm","image_pair"):
            return vlm.run_vlm_fixture_windows(q,vault,store,lease,case=case,model_dir=v,server_exe=s)
        _deny("DISPATCH")

    def step(self,worker,*,retry_stopped=False):
        # An expired logical lease is not evidence of physical worker exit.
        # Only a trusted host that has verified stop may request a retry,
        # after existing maintenance has reconciled the expired lease.
        if type(retry_stopped) is not bool:
            _deny("RETRY_FLAG")
        started=perf_counter()
        self._preflight()
        artifacts=[]
        for spec in self.plan.specs:
            row=self.queue.enqueue(spec)
            state=row["state"]
            if state=="completed":
                if row["reason"]!="encrypted_payload" or not row["receipt_sha256"]:
                    _deny("RECEIPT_ONLY")
                artifacts.append(_artifact_id(spec,row["receipt_sha256"]))
                continue
            if state in ("failed","canceled","cancel_requested"):
                return self._status("blocked",spec,state)
            if state=="running":
                current=self.queue.status(spec.tenant_id,spec.job_id)
                return self._status("recovery_required" if current["lease_expired"] else "busy",spec,state)
            if state=="queued" and row["attempt"]>0 and not retry_stopped:
                return self._status("recovery_required",spec,state)
            claim=self.queue.claim(spec.tenant_id,worker,job_id=spec.job_id)
            if claim["status"]!="claimed":
                return self._status(claim["status"],spec,state)
            if claim["spec"]!=spec or claim["lease"].job_id!=spec.job_id:
                _deny("CLAIM_MISMATCH")
            receipt=self._dispatch(claim["lease"],spec)
            stored=self.queue.status(spec.tenant_id,spec.job_id)
            if (stored["state"]!="completed" or stored["reason"]!="encrypted_payload"
                    or receipt.get("artifact_id")!=_artifact_id(spec,stored["receipt_sha256"])):
                _deny("RECEIPT_MISMATCH")
            result={**self._status("processed",spec,"completed"),
                    "artifact_id":receipt["artifact_id"],"model_calls":receipt["model_calls"]}
            if self.plan.mode=="shared_av":
                result.update({key:receipt[key] for key in ("decode_resources","model_resources","ocr_resources","quality")})
            if self.plan.mode=="shared_av":
                result["step_wall_ms"]=round((perf_counter()-started)*1000,3)
            return result
        first=self.plan.specs[0]
        # Reauthenticate exact persisted typed results under the fusion
        # transaction; never emit a partial final decision.
        decisions=evaluate_candidate_bundle(self.store,first.tenant_id,first.object_id,
            artifacts,purpose=first.purpose)
        return {"status":"candidate_complete","plan_sha256":self.plan.fingerprint,
                "artifact_ids":tuple(artifacts),"decisions":decisions,
                "synthetic_fixture":True,"scientific_evidence":False,"canonical_rubric":False}

    def _status(self,status,spec,state):
        return {"status":status,"plan_sha256":self.plan.fingerprint,"job_id":spec.job_id,
                "processor":spec.processor,"job_state":state,"synthetic_fixture":True,
                "scientific_evidence":False,"canonical_rubric":False}
