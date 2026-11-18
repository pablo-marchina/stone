"""Protected deterministic Stone-S1 candidate decisions, never rubric admission.

Only a trusted host can evaluate selected persisted processor results. No
model invocation, arbitrary caption, API, write, ranking or publication.
"""
from typing import Literal
from pydantic import Field, model_validator
from .asset_processor_results import Contract, Digest, Id
from .asset_candidate_evidence import (_validate_selection, _assemble_in_transaction,
    _recheck_bundle)
from .asset_lineage import RetainedAssetRef
from .asset_lineage_index import _load, _ancestors, _grant
from .asset_rights import AssetRightsDenied, Permission
from .domain import RUBRIC_FIELD_NAMES
from . import multimodal_fusion as fusion
from . import multimodal_cta_directed as directed
from .discovery_rubric_grounded import rule_evidence, UNKNOWN, PATTERNS

VERSION = "asset-s1-candidate-fusion.v1"
FIELDS = ("tema_principal","tipo_cta","tem_cta","texto_na_tela")
MAX_FRAGMENTS = 128


class Support(Contract):
    artifact_id: Id
    payload_sha256: Digest
    processor: Literal["asr_vad","ocr","vlm"]
    segment_index: int | None = Field(default=None,ge=0,le=255)
    start_ms: int | None = Field(default=None,ge=0,le=86400000)
    end_ms: int | None = Field(default=None,ge=0,le=86400000)
    frame_sha256: Digest | None = None
    timeline: Literal["decoded_pcm","image","resampled_uniform"]
    word_indices: tuple[int,...] = Field(default=(),max_length=256)
    text_sha256: Digest | None = None

    @model_validator(mode="after")
    def locator(self):
        if self.processor == "asr_vad":
            if (self.segment_index is None or self.start_ms is None or self.end_ms is None
                    or self.start_ms >= self.end_ms or self.frame_sha256 is not None
                    or self.timeline != "decoded_pcm" or self.word_indices or not self.text_sha256):
                raise ValueError("S1_AUDIO_LOCATOR")
        else:
            if (self.segment_index is not None or self.start_ms is None or self.end_ms is not None
                    or not self.frame_sha256 or self.timeline == "decoded_pcm"):
                raise ValueError("S1_FRAME_LOCATOR")
            if self.processor == "ocr":
                if (not self.word_indices or self.word_indices != tuple(sorted(set(self.word_indices)))
                        or any(not 0<=i<256 for i in self.word_indices)):
                    raise ValueError("S1_WORD_LOCATOR")
            elif self.word_indices or self.text_sha256 is not None:
                raise ValueError("S1_VISUAL_LOCATOR")
        return self


class FieldCandidate(Contract):
    field_id: str
    state: Literal["candidate","abstained","not_assessed"]
    value: str | bool | None = None
    reason: str = Field(min_length=1,max_length=128)
    supports: tuple[Support,...] = Field(default=(),max_length=128)
    vetoes: tuple[Support,...] = Field(default=(),max_length=130)

    @model_validator(mode="after")
    def decision(self):
        if self.field_id not in RUBRIC_FIELD_NAMES:
            raise ValueError("S1_FIELD_UNKNOWN")
        if self.state == "candidate":
            if self.field_id not in FIELDS or self.value is None or not self.supports:
                raise ValueError("S1_CANDIDATE_INVALID")
            if self.field_id in ("tem_cta","texto_na_tela"):
                if self.value is not True:
                    raise ValueError("S1_POSITIVE_ONLY")
            elif type(self.value) is not str or self.value not in PATTERNS[self.field_id]:
                raise ValueError("S1_LABEL_INVALID")
        elif self.value is not None:
            raise ValueError("S1_NONCANDIDATE_VALUE")
        if self.state == "not_assessed" and (self.supports or self.vetoes):
            raise ValueError("S1_NOT_ASSESSED_SUPPORT")
        return self


class CandidateDecisions(Contract):
    schema_version: Literal["asset-s1-candidate-fusion.v1"] = VERSION
    evidence_fingerprint: Digest
    tenant_id: Id
    content_id: Id
    object_id: Digest
    purpose: Literal["research_analysis","studio_creation"]
    fields: tuple[FieldCandidate,...] = Field(min_length=20,max_length=20)
    scientific_evidence: Literal[False] = False
    canonical_rubric: Literal[False] = False
    calibrated_probability: None = None

    @model_validator(mode="after")
    def partition(self):
        if tuple(d.field_id for d in self.fields) != RUBRIC_FIELD_NAMES:
            raise ValueError("S1_FIELD_PARTITION")
        by = {d.field_id:d for d in self.fields}
        if any(by[k].state != "not_assessed" for k in by.keys()-set(FIELDS)):
            raise ValueError("S1_UNSUPPORTED_FIELD")
        a,b = by["tipo_cta"],by["tem_cta"]
        if (a.state,a.supports,a.vetoes)!=(b.state,b.supports,b.vetoes) or b.value is not (True if a.state=="candidate" else None):
            raise ValueError("S1_CTA_RELATION")
        return self


def _support(entry, **kwargs):
    return Support(artifact_id=entry.artifact_id,payload_sha256=entry.payload_sha256,
                   processor=entry.observation.result.processor,**kwargs)


def _ocr_line(words):
    """One horizontal row only; no assembly across rows or large gaps.

    The contract has no OCR line IDs; this conservative geometry rule is an
    engineering proposal, not a calibrated semantic eligibility classifier.
    """
    boxes = [w.box_px for w in words]
    if max(y for x,y,w,h in boxes) >= min(y+h for x,y,w,h in boxes):
        return None
    for (x,y,w,h),(u,v,a,b) in zip(boxes,boxes[1:]):
        if u<x+w or u-(x+w)>2*max(h,b):
            return None
    text = " ".join(w.text for w in words)
    return text if len(text)<=10000 else None


def _evaluate(bundle):
    entries = {e.observation.result.processor:e for e in bundle.entries
               if e.observation.result.state=="observed"}
    fragments, refs = [], []
    def add(modality,text,ref):
        if len(fragments)>=MAX_FRAGMENTS:
            raise AssetRightsDenied("ASSET_S1_FRAGMENT_LIMIT")
        fragments.append(fusion.fragment(bundle.input_sha256,modality,text,{"index":len(refs)}))
        refs.append(ref)
    if "asr_vad" in entries:
        e=entries["asr_vad"]
        for i,s in enumerate(e.observation.result.segments):
            add("audio",s.text,_support(e,segment_index=i,start_ms=s.start_ms,end_ms=s.end_ms,
                 timeline="decoded_pcm",text_sha256=fusion.digest(s.text)))
    screen, conflict = (), ()
    if "ocr" in entries:
        e=entries["ocr"]; o=e.observation.result
        loc=dict(start_ms=o.frame.time_ms,frame_sha256=o.frame.frame_sha256,
                 timeline=o.frame.timeline,word_indices=tuple(range(len(o.words))))
        screen=(_support(e,**loc),)
        if "vlm" in entries:
            v=entries["vlm"]; vr=v.observation.result
            if vr.frame==o.frame and vr.text_present=="no":
                conflict=screen+(_support(v,start_ms=vr.frame.time_ms,
                    frame_sha256=vr.frame.frame_sha256,timeline=vr.frame.timeline),)
        if not conflict:
            line=_ocr_line(o.words)
            if line is not None:
                add("ocr",line,_support(e,**loc,text_sha256=fusion.digest(line)))
    fusion.validate_fragments(bundle.input_sha256,fragments)
    def decision(field,value,reason,supports=(),vetoes=()):
        return FieldCandidate(field_id=field,state="candidate" if value is not None else "abstained",
                              value=value,reason=reason,supports=tuple(supports),vetoes=tuple(vetoes))
    if conflict:
        topic=decision("tema_principal",None,"SAME_FRAME_MODALITY_CONFLICT",vetoes=conflict)
        cta=decision("tipo_cta",None,"SAME_FRAME_MODALITY_CONFLICT",vetoes=conflict)
    else:
        t=fusion.field_candidate("tema_principal",fragments,("audio","ocr"))
        topic=decision("tema_principal",t["value"],t["reason"],
                       [refs[a["locator"]["index"]] for a in t["supports"]],
                       [refs[a["locator"]["index"]] for a in t["vetoes"]])
        preds=[{"rule":rule_evidence("tipo_cta",f["text"]),
                "directed":directed.directed_evidence(f["text"])} for f in fragments]
        value=directed.directed_decision(preds,hybrid=False)
        support=[r for p,r in zip(preds,refs) if value is not None and p["directed"]["value"]==value]
        veto=[r for p,r in zip(preds,refs) if p["directed"]["reason"] in ("CONTEXT_VETO","MULTIPLE_REQUESTS")
              or (value is None and (p["directed"]["value"]!=UNKNOWN or p["rule"]["rule_value"]!=UNKNOWN))]
        cta=decision("tipo_cta",value,"DIRECTED_REQUEST_V2" if value is not None else "NO_UNAMBIGUOUS_DIRECTED_REQUEST",support,veto)
    presence=decision("tem_cta",True if cta.value is not None else None,cta.reason,cta.supports,cta.vetoes)
    text=decision("texto_na_tela",True if screen and not conflict else None,
                  "SAME_FRAME_MODALITY_CONFLICT" if conflict else "PARTIAL_OCR_WORDS" if screen else "NO_POSITIVE_OCR_EVIDENCE",
                  screen if not conflict else (),conflict)
    assessed={x.field_id:x for x in (topic,cta,presence,text)}
    return CandidateDecisions(evidence_fingerprint=bundle.fingerprint(),tenant_id=bundle.tenant_id,
        content_id=bundle.content_id,object_id=bundle.object_id,purpose=bundle.purpose,
        fields=tuple(assessed[k] if k in assessed else FieldCandidate(field_id=k,state="not_assessed",
            reason="REQUIRES_ADDITIONAL_EVIDENCE_OR_CALIBRATION") for k in RUBRIC_FIELD_NAMES))


def evaluate_candidate_bundle(store,tenant,object_id,artifact_ids,*,purpose):
    """One local transaction; derive rubric permission before decrypt and after decision.

    Only in-memory candidates, no retain/display/export rights conferred.
    Never take a caller-constructed bundle as authorization. Re-evaluate on
    each boundary; returned results cannot be recalled from trusted memory.
    """
    _validate_selection(store,tenant,object_id,artifact_ids,purpose)
    q=store.queue
    with q._transaction() as (db,now):
        _,_,by_id=_load(db,tenant)
        if object_id not in by_id or not isinstance(by_id[object_id][1],RetainedAssetRef):
            raise AssetRightsDenied("ASSET_EVIDENCE_ROOT_UNKNOWN")
        root=by_id[object_id][1]
        _ancestors(by_id,object_id,now,purpose)
        permission=Permission(operation="derive",purpose=purpose,field="rubric_evidence")
        _grant(db,q.resolve_anchor(root),root,now,permission)
        bundle,by_id,bindings=_assemble_in_transaction(store,db,now,tenant,object_id,artifact_ids,purpose=purpose,by_id=by_id)
        try:
            result=_evaluate(bundle)
        except ValueError:
            raise AssetRightsDenied("ASSET_S1_CONTRACT") from None
        fresh=_recheck_bundle(store,db,now,by_id,bindings,purpose=purpose)
        _grant(db,q.resolve_anchor(root),root,fresh,permission)
        return result
