from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from tapi_gate0.asset_rights import AssetIdentity, AssetRightsDenied, TrustedAuthority
from tapi_gate0.asset_vault import AssetVault, MAX_BYTES
from tapi_gate0.policy import Decision

# Header-only synthetic data: signature checks are not full media validation.
DATA=b"\x89PNG\r\n\x1a\nfixture-not-a-decoded-image"
TARGET=AssetIdentity(tenant_id="fixture",platform="instagram",source_account_id="source",
    source_item_id="item",content_id="post",asset_id="asset",media_kind="image",
    sha256=sha256(DATA).hexdigest())
ANCHOR=TrustedAuthority("fixture-issuer",b"k"*32,frozenset({("fixture","instagram")}),1,"a"*64)


class RegistryStub:
    def __init__(self):
        self.calls=[]
        self.allowed={"retain","process"}
        self.deny_after=None

    def decide(self,anchor,grant_id,target,permission):
        self.calls.append(permission.operation.value)
        ok=(permission.operation.value in self.allowed and anchor==ANCHOR and
            grant_id=="fixture-grant" and target==TARGET and
            permission.purpose=="research_analysis" and permission.field=="image" and
            (self.deny_after is None or len(self.calls)<=self.deny_after))
        return Decision(ok,"FIXTURE_ALLOW" if ok else "FIXTURE_DENY","fixture")


@pytest.fixture
def vault(tmp_path):
    pytest.importorskip("cryptography.hazmat.primitives.ciphers.aead")
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    registry=RegistryStub()
    return AssetVault(root,b"z"*32,registry),registry,root


def retain(v, data=DATA, mime="image/png", target=TARGET):
    return v.retain(ANCHOR,"fixture-grant",target,mime=mime,purpose="research_analysis",data=data)


def read(v, target=TARGET):
    return v.read_for_processing(ANCHOR,"fixture-grant",target,mime="image/png",purpose="research_analysis")


def test_encrypted_roundtrip_and_immutable_idempotency(vault):
    v,registry,root=vault
    assert retain(v)["status"]=="retained"
    files=list(root.iterdir())
    assert len(files)==1 and files[0].suffix==".enc"
    encrypted=files[0].read_bytes()
    assert DATA not in encrypted
    assert read(v)==DATA
    assert retain(v)["status"]=="already_retained"
    assert files[0].read_bytes()==encrypted
    assert "process" in registry.calls and "retain" in registry.calls


def test_denied_before_storage_and_processing(vault):
    v,registry,root=vault
    registry.allowed=set()
    with pytest.raises(AssetRightsDenied,match="FIXTURE_DENY"):
        retain(v)
    assert list(root.iterdir())==[]
    registry.allowed={"retain"}
    retain(v)
    with pytest.raises(AssetRightsDenied,match="FIXTURE_DENY"):
        read(v)
    registry.allowed={"process"}
    with pytest.raises(AssetRightsDenied,match="FIXTURE_DENY"):
        read(v)


@pytest.mark.parametrize("data,mime,code",[
    (b"","image/png","SIZE_INVALID"),
    (b"not-media","image/png","MEDIA_SIGNATURE_INVALID"),
    (DATA,"video/mp4","MEDIA_SIGNATURE_INVALID"),
    (DATA+b"changed","image/png","DIGEST_MISMATCH"),
])
def test_preflight_rejects_invalid_bytes(vault,data,mime,code):
    v,_,root=vault
    with pytest.raises(AssetRightsDenied,match=code):
        retain(v,data,mime)
    assert not list(root.iterdir())


def test_tamper_wrong_key_and_no_overwrite(vault):
    v,registry,root=vault
    retain(v)
    path=next(root.iterdir())
    other=AssetVault(root,b"y"*32,registry)
    with pytest.raises(AssetRightsDenied,match="AUTHENTICATION_FAILED"):
        read(other)
    envelope=path.read_bytes()
    altered=envelope[:-1]+bytes([envelope[-1]^1])
    path.write_bytes(altered)
    with pytest.raises(AssetRightsDenied,match="AUTHENTICATION_FAILED"):
        read(v)
    with pytest.raises(AssetRightsDenied,match="AUTHENTICATION_FAILED"):
        retain(v)
    assert path.read_bytes()==altered


def test_revocation_during_retain_removes_new_object(vault):
    v,registry,root=vault
    registry.deny_after=2
    with pytest.raises(AssetRightsDenied,match="FIXTURE_DENY"):
        retain(v)
    assert not list(root.iterdir())


def test_revocation_after_decryption_withholds_bytes(vault):
    v,registry,root=vault
    retain(v)
    registry.calls.clear()
    registry.deny_after=3
    with pytest.raises(AssetRightsDenied,match="FIXTURE_DENY"):
        read(v)
    # Physical purge is intentionally not implemented by the read adapter.
    assert len(list(root.iterdir()))==1


def test_scope_and_filesystem_preconditions(vault,tmp_path):
    v,registry,root=vault
    with pytest.raises(AssetRightsDenied,match="FIXTURE_DENY"):
        read(v,TARGET.model_copy(update={"tenant_id":"other"}))
    with pytest.raises(AssetRightsDenied,match="KEY_INVALID"):
        AssetVault(root,b"short",registry)
    with pytest.raises(AssetRightsDenied,match="PRIVATE_ROOT_REQUIRED"):
        AssetVault(tmp_path/"absent",b"z"*32,registry)


def test_envelope_binding_rejects_copied_object_under_other_grant(vault):
    from tapi_gate0.asset_vault import _binding
    v,registry,root=vault
    retain(v)
    original=next(root.iterdir())
    other=TARGET.model_copy(update={"asset_id":"other"})
    aad=_binding(ANCHOR,"other-grant",other,"image/png")
    copied=root/(sha256(aad).hexdigest()+".enc")
    copied.write_bytes(original.read_bytes())
    # Even a trusted caller authorized for a different object cannot
    # substitute encrypted bytes from another grant's envelope.
    registry.decide=lambda *a:Decision(True,"FIXTURE_ALLOW","fixture")
    with pytest.raises(AssetRightsDenied,match="AUTHENTICATION_FAILED"):
        v.read_for_processing(ANCHOR,"other-grant",other,mime="image/png",purpose="research_analysis")


def test_legacy_real_processing_still_denied(vault):
    from tapi_gate0.multimodal import inspect_approved_local_media, MediaPermissionError
    v,_,root=vault
    retain(v)
    with pytest.raises(MediaPermissionError,match="MEDIA_VERIFIED_ASSET_GRANT_REQUIRED"):
        inspect_approved_local_media(str(next(root.iterdir())),TARGET.sha256)
