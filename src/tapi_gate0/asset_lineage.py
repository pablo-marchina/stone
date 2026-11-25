"""A02.3/4: metadata contract and pure invalidation plan for future asset index.

No durable persistence, filesystem deletion, grants, inference or authorization.
The graph records dependencies, not rights; unknown parents and mixed tenants
are rejected rather than inferred. Only verified registry/PEP output may
eventually populate a durable index.
"""
from collections import defaultdict, deque
from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import Field, model_validator

from .asset_rights import AssetIdentity, Digest, Id, RightsModel, TrustedAuthority
from .asset_vault import MIME, MAX_BYTES, _binding, _binding_fields


class RetainedAssetRef(RightsModel):
    target: AssetIdentity
    issuer_id: Id
    issuer_key_sha256: Digest
    grant_id: Id
    mime: str
    object_id: Digest
    byte_count: int = Field(gt=0, le=MAX_BYTES, strict=True)
    retained_at: datetime
    retain_until: datetime

    @model_validator(mode="after")
    def consistent(self):
        if self.mime not in MIME.get(self.target.media_kind,()):
            raise ValueError("LINEAGE_ASSET_MIME_INVALID")
        if self.object_id!=sha256(_binding_fields(self.issuer_id,self.issuer_key_sha256,
                self.grant_id,self.target,self.mime)).hexdigest():
            raise ValueError("LINEAGE_OBJECT_BINDING_MISMATCH")
        if any(t.tzinfo is None or t.utcoffset() is None for t in (self.retained_at,self.retain_until)):
            raise ValueError("LINEAGE_AWARE_TIME_REQUIRED")
        if self.retained_at>=self.retain_until:
            raise ValueError("LINEAGE_RETENTION_INVALID")
        return self


def expected_object_id(anchor:TrustedAuthority, grant_id:str, target:AssetIdentity, mime:str) -> str:
    """Same binding as the vault; a filename identifier, not an access token."""
    return sha256(_binding(anchor,grant_id,target,mime)).hexdigest()


class DerivedArtifactRef(RightsModel):
    tenant_id: Id
    artifact_id: Id
    kind: Literal["transcript","ocr","visual_features","rubric_evidence","creative_derivative",
                  "ranking_reference","retrieval_index","analysis_run"]
    payload_sha256: Digest
    parent_ids: tuple[Id,...] = Field(min_length=1,max_length=64)
    run_id: Id
    method_version: Id
    created_at: datetime
    retain_until: datetime

    @model_validator(mode="after")
    def consistent(self):
        if len(set(self.parent_ids))!=len(self.parent_ids) or self.artifact_id in self.parent_ids:
            raise ValueError("LINEAGE_PARENT_INVALID")
        if any(t.tzinfo is None or t.utcoffset() is None for t in (self.created_at,self.retain_until)):
            raise ValueError("LINEAGE_AWARE_TIME_REQUIRED")
        if self.created_at>=self.retain_until:
            raise ValueError("LINEAGE_RETENTION_INVALID")
        return self


def invalidation_plan(tenant:str, assets:list[RetainedAssetRef], artifacts:list[DerivedArtifactRef],
                      *, invalid_asset_ids:set[str], invalid_artifact_ids:set[str], now:datetime):
    """Validate a bounded, complete tenant graph, then compute closure.

    Expired nodes and descendants are included. All references use object_id
    for roots, artifact_id for derivatives. Output is a deterministic plan,
    not a revocation event or permission to delete any file.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("LINEAGE_AWARE_TIME_REQUIRED")
    if len(assets)+len(artifacts)>20000:
        raise ValueError("LINEAGE_LOCAL_LIMIT")
    roots={x.object_id:x for x in assets}
    derived={x.artifact_id:x for x in artifacts}
    if len(roots)!=len(assets) or len(derived)!=len(artifacts) or roots.keys() & derived.keys():
        raise ValueError("LINEAGE_DUPLICATE_ID")
    if any(x.target.tenant_id!=tenant for x in assets) or any(x.tenant_id!=tenant for x in artifacts):
        raise ValueError("LINEAGE_TENANT_MISMATCH")
    nodes={**roots,**derived}
    children=defaultdict(list)
    degree={key:0 for key in nodes}
    for item in artifacts:
        for pid in item.parent_ids:
            if pid not in nodes:
                raise ValueError("LINEAGE_PARENT_MISSING")
            parent=nodes[pid]
            parent_created=parent.retained_at if isinstance(parent,RetainedAssetRef) else parent.created_at
            if item.created_at<parent_created or item.retain_until>parent.retain_until:
                raise ValueError("LINEAGE_PARENT_TIME_OR_RETENTION")
            children[pid].append(item.artifact_id)
            degree[item.artifact_id]+=1
    queue=deque(sorted(k for k,v in degree.items() if not v))
    visited=0
    while queue:
        key=queue.popleft()
        visited+=1
        for child in children[key]:
            degree[child]-=1
            if degree[child]==0:
                queue.append(child)
    if visited!=len(nodes):
        raise ValueError("LINEAGE_CYCLE")
    # A signed asset_id can be retained under multiple distinct grants.
    # Revoke all matching object IDs; never silently accept unknown targets.
    if not invalid_asset_ids <= {x.target.asset_id for x in assets} or not invalid_artifact_ids <= derived.keys():
        raise ValueError("LINEAGE_INVALIDATION_TARGET_UNKNOWN")
    affected={x.object_id for x in assets if x.target.asset_id in invalid_asset_ids}
    affected.update(invalid_artifact_ids)
    affected.update(k for k,v in nodes.items() if v.retain_until<=now)
    queue=deque(sorted(affected))
    while queue:
        for child in children[queue.popleft()]:
            if child not in affected:
                affected.add(child)
                queue.append(child)
    return {"schema_version":"asset-lineage-plan.v1",
        "tenant_id":tenant,"object_ids":sorted(affected & roots.keys()),
        "artifact_ids":sorted(affected & derived.keys()),
        "nodes_checked":len(nodes),"filesystem_mutated":False,
        "database_mutated":False,"authorization_granted":False}
