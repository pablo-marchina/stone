"""IMP-083: opt-in read-only Rubric Lab for authored synthetic reports.

Local operator configuration binds an exact report triplet to one tenant.
This is NOT a rights grant, DB admission, canonical assessment or media API.
"""
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .domain import RUBRIC_FIELD_NAMES
from .identity import Principal, READ_ROLES
from . import multimodal_evidence_replay as evidence
from .policy import decide,Operation

MAX_BYTES=8_000_000
ROOT=Path(__file__).resolve().parents[2]
PREFIX="TAPI_EVIDENCE_LAB_"


@dataclass(frozen=True)
class ReportRef:
    name:str
    digest:str


@dataclass(frozen=True)
class LabConfig:
    tenant_id:str
    shared:ReportRef
    visual:ReportRef
    composed:ReportRef


def config_from_env(env):
    keys=("TENANT","SHARED_NAME","SHARED_SHA256","VLM_NAME","VLM_SHA256","REPORT_NAME","REPORT_SHA256")
    values={k:env.get(PREFIX+k,"") for k in keys}
    if not any(values.values()):
        return None
    if not all(values.values()):
        raise ValueError("EVIDENCE_LAB_CONFIG_INCOMPLETE")
    return LabConfig(values["TENANT"],ReportRef(values["SHARED_NAME"],values["SHARED_SHA256"]),
        ReportRef(values["VLM_NAME"],values["VLM_SHA256"]),ReportRef(values["REPORT_NAME"],values["REPORT_SHA256"]))


def read_pinned(root,ref):
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json",ref.name)
            or not re.fullmatch(r"[a-f0-9]{64}",ref.digest)):
        raise ValueError("EVIDENCE_LAB_REPORT_REF_INVALID")
    private=root/"artifacts"/"private"
    if private.resolve()!=private.absolute():
        raise ValueError("EVIDENCE_LAB_ROOT_REDIRECTED")
    path=private/ref.name
    if path.is_symlink() or path.resolve()!=path.absolute() or not path.is_file():
        raise ValueError("EVIDENCE_LAB_REPORT_UNAVAILABLE")
    if not 0<path.stat().st_size<=MAX_BYTES:
        raise ValueError("EVIDENCE_LAB_REPORT_SIZE_INVALID")
    with path.open("rb") as stream:
        raw=stream.read(MAX_BYTES+1)
    if not 0<len(raw)<=MAX_BYTES or sha256(raw).hexdigest()!=ref.digest:
        raise ValueError("EVIDENCE_LAB_REPORT_HASH_MISMATCH")
    result=json.loads(raw)
    if not isinstance(result,dict):
        raise ValueError("EVIDENCE_LAB_REPORT_INVALID")
    return result


class EvidenceLab:
    """Immutable in-memory snapshot; only the configured tenant may read it."""
    def __init__(self,config,root=ROOT):
        if not decide("synthetic_local",Operation.EVALUATE_SYNTHETIC.value).permitted:
            raise ValueError("EVIDENCE_LAB_POLICY_DENIED")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",config.tenant_id):
            raise ValueError("EVIDENCE_LAB_TENANT_INVALID")
        refs=(config.shared,config.visual,config.composed)
        if len({r.name for r in refs})!=3:
            raise ValueError("EVIDENCE_LAB_DISTINCT_REPORTS_REQUIRED")
        shared,visual,composed=(read_pinned(root,r) for r in refs)
        rebuilt=evidence.run(shared,visual,config.shared.digest)
        rebuilt.update(source_report_sha256=config.shared.digest,visual_report_sha256=config.visual.digest)
        if rebuilt!=composed:
            raise ValueError("EVIDENCE_LAB_COMPOSITION_MISMATCH")
        if any(rebuilt.get(k) is not False for k in ("production_approved","real_media_processing_allowed","database_mutated","independent_gold")):
            raise ValueError("EVIDENCE_LAB_SCOPE_INVALID")
        self.tenant_id=config.tenant_id
        self._digest=config.composed.digest
        self._cases={}
        summaries=[]
        for row,source in zip(rebuilt["cases"],shared["cases"]):
            case_id=row["case_id"]
            fields=row["field_evidence"]
            if case_id!=source["case_id"] or set(fields)!=set(RUBRIC_FIELD_NAMES) or any(v["canonical"] is not False for v in fields.values()):
                raise ValueError("EVIDENCE_LAB_FIELDS_INVALID")
            counts=dict(Counter(f["state"] for f in fields.values()))
            summaries.append({"case_id":case_id,"media_sha256":row["media_sha256"],"state_counts":counts})
            self._cases[case_id]=json.dumps({"case_id":case_id,"media_sha256":row["media_sha256"],
                "field_evidence":fields,"fragments":source["fragments"],
                "visual_observations":row["visual_observations"],"source_rights":row["source_rights"],
                "synthetic_only":True,"canonical":False,"media_player_available":False},ensure_ascii=False)
        self._summary=json.dumps({"policy_version":rebuilt["policy_version"],"report_sha256":self._digest,
            "source_report_sha256":config.shared.digest,"visual_report_sha256":config.visual.digest,
            "cases":summaries,"field_count":rebuilt["field_count"],"total_field_cells":rebuilt["total_field_cells"],
            "field_coverage":rebuilt["field_coverage"],"ablation":rebuilt["ablation"],
            "engineering_gate_passed":rebuilt["engineering_gate_passed"],
            "upstream_vlm_gate_passed":rebuilt["upstream_vlm_gate_passed"],
            "synthetic_only":True,"canonical":False,"production_approved":False,
            "independent_gold":False,"media_player_available":False},ensure_ascii=False)

    def summary(self):
        return json.loads(self._summary)

    def case(self,case_id):
        if case_id not in self._cases:
            raise HTTPException(status_code=404,detail="EVIDENCE_LAB_CASE_NOT_FOUND")
        return json.loads(self._cases[case_id])


def router_for_lab(current_principal,lab=None):
    router=APIRouter(prefix="/v1/studio/evidence-lab",tags=["Synthetic Evidence Lab"])

    def authorized(request:Request,p:Principal=Depends(current_principal)):
        # Even HTTPS clients must be local. No report path or tenant accepted
        # from request parameters, and no cross-tenant existence disclosure.
        if (request.client is None or request.client.host not in ("127.0.0.1","::1","testclient")
                or lab is None or p.tenant_id!=lab.tenant_id or p.role not in READ_ROLES):
            raise HTTPException(status_code=404,detail="EVIDENCE_LAB_UNAVAILABLE")
        return lab

    @router.get("")
    def summary(response:Response,service=Depends(authorized)):
        response.headers["Cache-Control"]="private, no-store"
        return service.summary()

    @router.get("/cases/{case_id}")
    def case(case_id:str,response:Response,service=Depends(authorized)):
        response.headers["Cache-Control"]="private, no-store"
        return service.case(case_id)

    return router
