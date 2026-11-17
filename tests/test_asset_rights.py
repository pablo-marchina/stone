from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest
from pydantic import ValidationError

from tapi_gate0.asset_rights import (
    AssetIdentity, AssetOperation, Permission, GrantClaims, SignedGrant,
    RevocationClaims, SignedRevocations, TrustedAuthority, signed_bytes,
    decide_asset, require_asset_rights, AssetRightsDenied,
)
from tapi_gate0.policy import decide, Operation
from tapi_gate0.multimodal import inspect_approved_local_media, MediaPermissionError

NOW = datetime(2026,11,17,20,0,tzinfo=timezone.utc)
TARGET = AssetIdentity(tenant_id="tenant-a",platform="instagram",
    source_account_id="12345",source_item_id="23456",content_id="content.a",
    asset_id="asset.a",media_kind="video",sha256="a"*64)
PERMISSION = Permission(operation="process",purpose="research_analysis",field="video")


def test_no_grant_or_legacy_path_can_enable_media(tmp_path):
    denied=decide_asset(authority=None,grant=None,revocations=None,target=TARGET,
        permission=PERMISSION,now=NOW)
    assert not denied.permitted
    assert denied.code=="ASSET_RIGHTS_EVIDENCE_REQUIRED"
    assert not decide("instagram_media",Operation.PROCESS_MEDIA.value).permitted
    with pytest.raises(MediaPermissionError,match="MEDIA_VERIFIED_ASSET_GRANT_REQUIRED"):
        inspect_approved_local_media(str(tmp_path/"absent.mp4"),"a"*64)
    with pytest.raises(AssetRightsDenied,match="EVIDENCE_REQUIRED"):
        require_asset_rights(authority=None,grant=None,revocations=None,target=TARGET,
            permission=PERMISSION,now=NOW)


@pytest.fixture
def rights():
    crypto=pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    private=crypto.Ed25519PrivateKey.generate()
    def sign(claims):
        return private.sign(signed_bytes(claims)).hex()
    def grant(**changes):
        values=dict(issuer_id="fixture-authority",grant_id="grant.a",target=TARGET,
            approval_evidence_sha256="b"*64,issued_at=NOW-timedelta(hours=1),
            not_before=NOW-timedelta(minutes=30),expires_at=NOW+timedelta(hours=1),
            retain_until=NOW+timedelta(minutes=30),permissions=(PERMISSION,
                Permission(operation="display",purpose="studio_creation",field="image")))
        g=GrantClaims(**(values|changes))
        return SignedGrant(claims=g,signature=sign(g))
    def state(**changes):
        values=dict(issuer_id="fixture-authority",revision=4,
            issued_at=NOW-timedelta(minutes=1),valid_until=NOW+timedelta(minutes=9),
            revoked_grant_ids=(),revoked_asset_ids=())
        rv=RevocationClaims(**(values|changes))
        return SignedRevocations(claims=rv,signature=sign(rv))
    def anchor(rv):
        return TrustedAuthority("fixture-authority",private.public_key().public_bytes_raw(),
            frozenset({("tenant-a","instagram")}),rv.claims.revision,
            sha256(signed_bytes(rv.claims)).hexdigest())
    return grant,state,anchor


def evaluate(rights, **changes):
    grant,state,anchor=rights
    rv=state()
    return decide_asset(**(dict(authority=anchor(rv),grant=grant(),revocations=rv,
        target=TARGET,permission=PERMISSION,now=NOW)|changes))


def test_signed_exact_scope_is_only_policy_decision(rights):
    decision=evaluate(rights)
    assert decision.permitted and decision.code=="ASSET_RIGHTS_EXACT_SCOPE"
    # Existing real processing entrypoint stays closed even after a valid
    # synthetic policy decision: no trusted operational registry/PEP yet.
    with pytest.raises(MediaPermissionError,match="MEDIA_VERIFIED_ASSET_GRANT_REQUIRED"):
        inspect_approved_local_media("does-not-exist.mp4","a"*64)


@pytest.mark.parametrize("operation",list(AssetOperation))
def test_operation_matrix_is_exact_not_cartesian(rights,operation):
    p=Permission(operation=operation,purpose="research_analysis",field="video")
    assert evaluate(rights,permission=p).permitted==(operation==AssetOperation.PROCESS)
    # Both studio_creation and image exist in another permission, but may
    # not be combined with process, nor research purpose with display.
    assert not evaluate(rights,permission=Permission(operation="process",purpose="studio_creation",field="image")).permitted


@pytest.mark.parametrize("field,value",[
    ("tenant_id","tenant-b"),("platform","youtube"),("source_account_id","other"),
    ("source_item_id","other"),("content_id","content.b"),("asset_id","asset.b"),
    ("media_kind","image"),("sha256","c"*64)])
def test_target_identity_binding(rights,field,value):
    assert not evaluate(rights,target=TARGET.model_copy(update={field:value})).permitted


def test_tampered_grant_signature_and_wrong_key(rights):
    grant,state,anchor=rights
    g=grant()
    tampered=g.model_copy(update={"claims":g.claims.model_copy(update={"approval_evidence_sha256":"c"*64})})
    assert evaluate(rights,grant=tampered).code=="ASSET_RIGHTS_SIGNATURE_INVALID"
    rv=state()
    assert evaluate(rights,authority=replace(anchor(rv),public_key=b"x"*32)).code=="ASSET_RIGHTS_SIGNATURE_INVALID"
    assert evaluate(rights,authority=replace(anchor(rv),issuer_id="other")).code=="ASSET_RIGHTS_UNTRUSTED_ISSUER"


@pytest.mark.parametrize("field,value",[("revoked_grant_ids",("grant.a",)),("revoked_asset_ids",("asset.a",))])
def test_revocation_denies_even_valid_signature(rights,field,value):
    _,state,anchor=rights
    rv=state(**{field:value})
    assert evaluate(rights,authority=anchor(rv),revocations=rv).code=="ASSET_RIGHTS_REVOKED"


def test_revocation_rollback_and_equivocation_denied(rights):
    _,state,anchor=rights
    rv=state()
    old=state(revision=3)
    assert evaluate(rights,authority=anchor(rv),revocations=old).code=="ASSET_RIGHTS_REVOCATION_STATE_MISMATCH"
    alternate=state(revoked_asset_ids=("asset.b",))
    assert evaluate(rights,authority=anchor(rv),revocations=alternate).code=="ASSET_RIGHTS_REVOCATION_STATE_MISMATCH"
    forged=rv.model_copy(update={"signature":"0"*128})
    assert evaluate(rights,authority=anchor(rv),revocations=forged).code=="ASSET_RIGHTS_SIGNATURE_INVALID"


def test_expiry_retention_and_stale_revocation(rights):
    grant,state,anchor=rights
    rv=state()
    assert evaluate(rights,now=rv.claims.valid_until).code=="ASSET_RIGHTS_REVOCATION_STALE"
    assert evaluate(rights,grant=grant(expires_at=NOW)).code=="ASSET_RIGHTS_GRANT_INACTIVE"
    assert evaluate(rights,grant=grant(retain_until=NOW)).code=="ASSET_RIGHTS_GRANT_INACTIVE"
    assert evaluate(rights,grant=grant(not_before=NOW+timedelta(seconds=1))).code=="ASSET_RIGHTS_GRANT_INACTIVE"
    assert evaluate(rights,now=NOW.replace(tzinfo=None)).code=="ASSET_RIGHTS_TRUSTED_CLOCK_REQUIRED"


def test_claim_validation_rejects_unsafe_schema(rights):
    grant,state,_=rights
    with pytest.raises(ValidationError):
        grant(permissions=(PERMISSION,PERMISSION))
    with pytest.raises(ValidationError):
        grant(expires_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        state(valid_until=NOW+timedelta(hours=1))
    with pytest.raises(ValidationError):
        AssetIdentity.model_validate(TARGET.model_dump()|{"path":"arbitrary"})
