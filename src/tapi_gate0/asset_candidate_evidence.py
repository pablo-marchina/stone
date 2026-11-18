"""Protected, in-memory composition of persisted processor candidates.

This is not the text-only E1 contract, an admission decision, or a reusable
permission. A bundle is a snapshot for trusted local processing only. Its
fingerprint proves content identity, not model execution or correctness.
No persistence, model invocation, public API, or canonical rubric.
"""
from hashlib import sha256
import json
import re
from typing import Literal

from pydantic import Field, model_validator
from .asset_processor_results import (Contract, Digest, Id, ProcessorResult,
    encode, decode, validate_persisted_binding)
from .asset_derived_payloads import DerivedPayloadStore, _extra
from .asset_jobs import INPUT, _check_rights
from .asset_lineage import RetainedAssetRef, DerivedArtifactRef
from .asset_lineage_index import _load, _ancestors
from .asset_rights import AssetRightsDenied
from .storage import now_utc

VERSION = "asset-candidate-evidence-bundle.v1"
PROCESSORS = ("asr_vad", "ocr", "temporal", "vlm")
MAX_ARTIFACTS = 4


def _fail(code):
    raise AssetRightsDenied("ASSET_EVIDENCE_" + code)


class CandidateEvidence(Contract):
    artifact_id: Id
    payload_sha256: Digest
    observation: ProcessorResult = Field(repr=False)

    @model_validator(mode="after")
    def digest_binding(self):
        result = self.observation
        if sha256(encode(result)).hexdigest() != self.payload_sha256:
            raise ValueError("EVIDENCE_PAYLOAD_DIGEST")
        expected = "artifact." + sha256((result.job_id + ":" + self.payload_sha256).encode()).hexdigest()
        if self.artifact_id != expected:
            raise ValueError("EVIDENCE_ARTIFACT_BINDING")
        return self


class CandidateEvidenceBundle(Contract):
    schema_version: Literal["asset-candidate-evidence-bundle.v1"] = VERSION
    tenant_id: Id
    content_id: Id
    object_id: Digest
    input_sha256: Digest
    media_kind: Literal["audio", "image", "video"]
    purpose: Literal["research_analysis", "studio_creation"]
    entries: tuple[CandidateEvidence, ...] = Field(min_length=1, max_length=MAX_ARTIFACTS, repr=False)
    scientific_evidence: Literal[False] = False
    canonical_rubric: Literal[False] = False
    calibrated_probability: None = None

    @model_validator(mode="after")
    def common_root(self):
        processors = []
        shared = [e.observation.shared_av for e in self.entries]
        present = [x.source for x in shared if x is not None]
        if present and (self.media_kind!="video" or len(present)!=len(shared) or any(x!=present[0] for x in present)):
            raise ValueError("EVIDENCE_SHARED_AV_SOURCE_MISMATCH")
        for entry in self.entries:
            r = entry.observation
            processor = r.result.processor
            if (r.tenant_id, r.object_id, r.input_sha256, r.purpose) != (
                    self.tenant_id, self.object_id, self.input_sha256, self.purpose):
                raise ValueError("EVIDENCE_ROOT_BINDING")
            if self.media_kind not in INPUT[processor]:
                raise ValueError("EVIDENCE_MODALITY_MISMATCH")
            if r.result.state == "observed" and processor in ("ocr", "vlm"):
                frame = r.result.frame
                if self.media_kind == "image":
                    if frame.timeline != "image" or frame.frame_sha256 != self.input_sha256:
                        raise ValueError("EVIDENCE_IMAGE_FRAME_BINDING")
                elif frame.timeline != "resampled_uniform":
                    raise ValueError("EVIDENCE_VIDEO_FRAME_TIMELINE")
            processors.append(processor)
        if len(set(processors)) != len(processors) or processors != sorted(processors):
            raise ValueError("EVIDENCE_PROCESSOR_PARTITION")
        if len({entry.artifact_id for entry in self.entries}) != len(self.entries):
            raise ValueError("EVIDENCE_ARTIFACT_DUPLICATE")
        return self

    def coverage(self):
        """Missing is not a negative observation; not_applicable is input kind only."""
        present = {e.observation.result.processor:e.observation.result.state for e in self.entries}
        return {p:present.get(p, "missing" if self.media_kind in INPUT[p] else "not_applicable")
                for p in PROCESSORS}

    def fingerprint(self):
        """Deterministic snapshot identity. Does not extend any authorization."""
        raw = json.dumps(self.model_dump(mode="json"), sort_keys=True,
                         separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        return sha256(raw).hexdigest()


def assemble_candidate_bundle(store, tenant, object_id, artifact_ids, *, purpose):
    """Read a bounded set of co-referenced authenticated payloads atomically.

    Only the current trusted host may call this. All artifact reads and the
    final rights check share BEGIN IMMEDIATE. No caption supplied by caller,
    no automatic latest-selection, no mixing roots or duplicate processors.
    Bytes already returned to a host cannot be recalled by revocation; callers
    must reassemble at each processing boundary, not cache as authorization.
    """
    _validate_selection(store,tenant,object_id,artifact_ids,purpose)
    with store.queue._transaction() as (db,now):
        bundle,by_id,bindings = _assemble_in_transaction(store,db,now,tenant,object_id,artifact_ids,purpose=purpose)
        _recheck_bundle(store,db,now,by_id,bindings,purpose=purpose)
        return bundle


def _validate_selection(store,tenant,object_id,artifact_ids,purpose):
    if not isinstance(store, DerivedPayloadStore):
        _fail("STORE_REQUIRED")
    if (type(tenant) is not str or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}",tenant)
            or type(object_id) is not str or not re.fullmatch(r"[0-9a-f]{64}",object_id)
            or type(purpose) is not str or purpose not in ("research_analysis","studio_creation")):
        _fail("SCOPE_INVALID")
    if (type(artifact_ids) not in (tuple,list) or not 1<=len(artifact_ids)<=MAX_ARTIFACTS
            or any(type(a) is not str or not re.fullmatch(r"artifact\.[0-9a-f]{64}",a) for a in artifact_ids)
            or len(set(artifact_ids))!=len(artifact_ids)):
        _fail("ARTIFACT_SELECTION")


def _assemble_in_transaction(store,db,now,tenant,object_id,artifact_ids,*,purpose,by_id=None):
    """Private helper: caller holds the queue transaction and validates selection."""
    q = store.queue
    if by_id is None:
        _,_,by_id = _load(db,tenant)
    if object_id not in by_id or not isinstance(by_id[object_id][1],RetainedAssetRef):
        _fail("ROOT_UNKNOWN")
    root = by_id[object_id][1]
    _ancestors(by_id,object_id,now,purpose)
    entries, bindings = [], []
    for ident in artifact_ids:
        if ident not in by_id or not isinstance(by_id[ident][1],DerivedArtifactRef):
            _fail("ARTIFACT_UNKNOWN")
        if by_id[ident][1].parent_ids != (object_id,):
            _fail("ROOT_MISMATCH")
        raw,ref,spec,parent,attempt = store._read_in_transaction(db,now,tenant,ident,purpose=purpose,by_id=by_id)
        if parent != root or ref.parent_ids != (object_id,):
            _fail("ROOT_MISMATCH")
        try:
            result = decode(raw)
            validate_persisted_binding(result,spec=spec,ref=parent,attempt=attempt)
            if raw != encode(result):
                _fail("NONCANONICAL_PROCESSOR_PAYLOAD")
            entry = CandidateEvidence(artifact_id=ident,payload_sha256=ref.payload_sha256,observation=result)
        except ValueError:
            # Do not include pydantic errors containing raw text in public logs.
            raise AssetRightsDenied("ASSET_EVIDENCE_PROCESSOR_CONTRACT") from None
        entries.append(entry)
        bindings.append((ident,spec,parent))
    try:
        bundle = CandidateEvidenceBundle(tenant_id=tenant,content_id=root.target.content_id,
            object_id=object_id,input_sha256=root.target.sha256,media_kind=root.target.media_kind,
            purpose=purpose,entries=tuple(sorted(entries,key=lambda e:e.observation.result.processor)))
    except ValueError:
        _fail("BUNDLE_CONTRACT")
    return bundle,by_id,bindings


def _recheck_bundle(store,db,now,by_id,bindings,*,purpose):
    q = store.queue
    fresh = now_utc()
    if fresh < now:
        _fail("CLOCK_REGRESSION")
    for ident,spec,parent in bindings:
        _ancestors(by_id,ident,fresh,purpose)
        if _check_rights(db,spec,q.resolve_anchor,fresh) != parent:
            _fail("PARENT_CHANGED")
        _extra(db,q,spec,parent,fresh,read=True)
    return fresh
