from datetime import datetime,timedelta,timezone
from hashlib import sha256

import pytest
from pydantic import ValidationError
from tapi_gate0.asset_rights import AssetIdentity,TrustedAuthority
from tapi_gate0.asset_lineage import RetainedAssetRef,DerivedArtifactRef,expected_object_id,invalidation_plan

NOW=datetime(2026,11,17,tzinfo=timezone.utc)
ANCHOR=TrustedAuthority("issuer",b"k"*32,frozenset({("tenant","instagram")}),1,"a"*64)


def root(grant="grant.a",asset="asset.a",tenant="tenant"):
    t=AssetIdentity(tenant_id=tenant,platform="instagram",source_account_id="source",
        source_item_id="item",content_id="content",asset_id=asset,media_kind="video",sha256="a"*64)
    return RetainedAssetRef(target=t,issuer_id=ANCHOR.issuer_id,
        issuer_key_sha256=sha256(ANCHOR.public_key).hexdigest(),grant_id=grant,mime="video/mp4",
        object_id=expected_object_id(ANCHOR,grant,t,"video/mp4"),byte_count=12,
        retained_at=NOW,retain_until=NOW+timedelta(days=1))


def artifact(id,parents,**kwargs):
    return DerivedArtifactRef(**(dict(tenant_id="tenant",artifact_id=id,kind="rubric_evidence",
        payload_sha256="b"*64,parent_ids=tuple(parents),run_id="run",method_version="v1",
        created_at=NOW,retain_until=NOW+timedelta(hours=12))|kwargs))


def plan(assets,artifacts,*,invalid_asset_ids=None,invalid_artifact_ids=None,now=NOW):
    return invalidation_plan("tenant",assets,artifacts,invalid_asset_ids=invalid_asset_ids or set(),
        invalid_artifact_ids=invalid_artifact_ids or set(),now=now)


def test_transitive_revocation_across_grants_and_shared_descendants():
    a,b,c=root(),root("grant.b"),root("grant.c","asset.other")
    x,y=artifact("x",[a.object_id]),artifact("y",[b.object_id,c.object_id])
    z=artifact("z",["x","y"])
    unaffected=artifact("u",[c.object_id])
    p=plan([a,b,c],[z,unaffected,x,y],invalid_asset_ids={"asset.a"})
    assert p["object_ids"]==sorted([a.object_id,b.object_id])
    assert p["artifact_ids"]==["x","y","z"]
    assert not p["authorization_granted"] and not p["filesystem_mutated"]


def test_expiration_and_derivative_revocation():
    a=root()
    x=artifact("x",[a.object_id],retain_until=NOW+timedelta(hours=1))
    y=artifact("y",["x"],retain_until=x.retain_until)
    assert plan([a],[x,y],now=x.retain_until)["artifact_ids"]==["x","y"]
    assert plan([a],[x,y],invalid_artifact_ids={"x"})["object_ids"]==[]
    assert plan([a],[x,y],now=a.retain_until)["object_ids"]==[a.object_id]


def test_unknown_parent_tenant_and_duplicates_denied():
    a=root()
    for assets,artifacts,code in [
        ([a],[artifact("x",["missing"])],"PARENT_MISSING"),
        ([root(tenant="other")],[],"TENANT_MISMATCH"),
        ([a,a],[],"DUPLICATE_ID"),
        ([a],[artifact("x",[a.object_id],tenant_id="other")],"TENANT_MISMATCH"),
        ([a],[artifact("x",[a.object_id]),artifact("x",[a.object_id])],"DUPLICATE_ID")]:
        with pytest.raises(ValueError,match=code):
            plan(assets,artifacts)
    with pytest.raises(ValueError,match="TARGET_UNKNOWN"):
        plan([a],[],invalid_asset_ids={"unknown"})


def test_retention_never_outlives_parents_and_cycles_denied():
    a=root()
    with pytest.raises(ValueError,match="PARENT_TIME_OR_RETENTION"):
        plan([a],[artifact("x",[a.object_id],retain_until=a.retain_until+timedelta(seconds=1))])
    with pytest.raises(ValueError,match="CYCLE"):
        plan([a],[artifact("x",["y"]),artifact("y",["x"])])
    with pytest.raises(ValidationError,match="PARENT_INVALID"):
        artifact("x",["x"])


def test_object_binding_rejects_changed_grant_and_mime():
    a=root()
    with pytest.raises(ValidationError,match="OBJECT_BINDING_MISMATCH"):
        RetainedAssetRef.model_validate(a.model_dump()|{"grant_id":"grant.other"})
    with pytest.raises(ValidationError,match="ASSET_MIME_INVALID"):
        RetainedAssetRef.model_validate(a.model_dump()|{"mime":"image/png"})
