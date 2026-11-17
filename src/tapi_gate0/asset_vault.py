"""A02.3 local encrypted asset vault, trusted-host library only.

No HTTP, network, decoder or operational configuration. Host must supply an
isolated private directory, independent authority pin and 32-byte encryption
key. A local OS administrator or another process with the same privileges is
outside this boundary. No media entrypoint calls this module yet.
"""
from hashlib import sha256
from pathlib import Path
import json
import os
import stat
import tempfile

from .asset_rights import AssetIdentity, Permission, AssetRightsDenied, TrustedAuthority

VERSION = b"TAPIASSET1\x00"
MAX_BYTES = 40_000_000
OVERHEAD = len(VERSION) + 12 + 16
MIME = {
    "image": ("image/jpeg", "image/png"),
    "video": ("video/mp4", "video/webm"),
    "audio": ("audio/wav",),
}


def _deny(code):
    raise AssetRightsDenied(code)


def _crypto():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.exceptions import InvalidTag
        return AESGCM, InvalidTag
    except ImportError:
        _deny("ASSET_VAULT_CRYPTO_REQUIRED")


def _mime_header(data, mime):
    # Bounded signature preflight, not full decoding or content safety.
    if mime == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")
    if mime == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "video/mp4":
        return len(data)>=12 and data[4:8]==b"ftyp" and 8<=int.from_bytes(data[:4],"big")<=len(data)
    if mime == "video/webm":
        return data.startswith(b"\x1a\x45\xdf\xa3")
    if mime == "audio/wav":
        return len(data)>=12 and data[:4]==b"RIFF" and data[8:12]==b"WAVE"
    return False


def _validate(data,target,mime):
    if type(data) is not bytes or not 0<len(data)<=MAX_BYTES:
        _deny("ASSET_VAULT_SIZE_INVALID")
    if mime not in MIME.get(target.media_kind,()) or not _mime_header(data,mime):
        _deny("ASSET_VAULT_MEDIA_SIGNATURE_INVALID")
    if sha256(data).hexdigest()!=target.sha256:
        _deny("ASSET_VAULT_DIGEST_MISMATCH")


def _binding(anchor,grant_id,target,mime):
    if not isinstance(anchor,TrustedAuthority):
        _deny("ASSET_VAULT_TRUST_REQUIRED")
    if not isinstance(grant_id,str) or not 1<=len(grant_id)<=128:
        _deny("ASSET_VAULT_GRANT_ID_INVALID")
    # No caller-selected filename, extension, URL or path. Every distinct
    # tenant/source/asset/grant/issuer/key/mime maps to a separate envelope.
    return json.dumps({"version":"asset-vault.v1","issuer_id":anchor.issuer_id,
        "issuer_key_sha256":sha256(anchor.public_key).hexdigest(),"grant_id":grant_id,
        "target":target.model_dump(mode="json"),"mime":mime},
        sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()


class AssetVault:
    def __init__(self,root:Path,key:bytes,registry):
        if type(key) is not bytes or len(key)!=32:
            _deny("ASSET_VAULT_KEY_INVALID")
        self.root=Path(root).absolute()
        self._check_root()
        aes,_=_crypto()
        self._cipher=aes(key)
        self._registry=registry

    def _check_root(self):
        if self.root.resolve()!=self.root or not self.root.is_dir():
            _deny("ASSET_VAULT_PRIVATE_ROOT_REQUIRED")
        if os.name=="posix" and stat.S_IMODE(self.root.stat().st_mode)&0o077:
            _deny("ASSET_VAULT_ROOT_PERMISSIONS")
        # Windows ACLs must be set/verified by the trusted OS operator.
        # This library does not create a private ACL or guarantee one.

    def _require(self,anchor,grant_id,target,operation,purpose):
        if operation not in ("retain","process") or purpose not in ("research_analysis","studio_creation"):
            _deny("ASSET_VAULT_OPERATION_UNSUPPORTED")
        decision=self._registry.decide(anchor,grant_id,target,
            Permission(operation=operation,purpose=purpose,field=target.media_kind))
        if not decision.permitted:
            _deny(decision.code)

    def _path(self,aad):
        self._check_root()
        return self.root/(sha256(aad).hexdigest()+".enc")

    def _read(self,path,aad,target,mime):
        if path.is_symlink() or path.resolve()!=path or not path.is_file():
            _deny("ASSET_VAULT_OBJECT_UNAVAILABLE")
        try:
            flags=os.O_RDONLY|getattr(os,"O_BINARY",0)|getattr(os,"O_NOFOLLOW",0)
            with os.fdopen(os.open(path,flags),"rb") as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or not OVERHEAD<info.st_size<=MAX_BYTES+OVERHEAD:
                    _deny("ASSET_VAULT_ENVELOPE_INVALID")
                envelope=stream.read(MAX_BYTES+OVERHEAD+1)
            if not OVERHEAD<len(envelope)<=MAX_BYTES+OVERHEAD or not envelope.startswith(VERSION):
                _deny("ASSET_VAULT_ENVELOPE_INVALID")
            _,invalid_tag=_crypto()
            try:
                data=self._cipher.decrypt(envelope[len(VERSION):len(VERSION)+12],
                    envelope[len(VERSION)+12:],aad)
            except (invalid_tag,ValueError):
                _deny("ASSET_VAULT_AUTHENTICATION_FAILED")
            _validate(data,target,mime)
            return data
        except OSError:
            _deny("ASSET_VAULT_OBJECT_UNAVAILABLE")

    def retain(self,anchor,grant_id,target:AssetIdentity,*,mime:str,purpose:str,data:bytes):
        """Accept already lawfully acquired bytes, never fetch or read a source path.

        The caller is responsible for lawful acquisition. A retention grant
        does not confer download rights. No content leaves the vault here.
        """
        self._require(anchor,grant_id,target,"retain",purpose)
        _validate(data,target,mime)
        aad=_binding(anchor,grant_id,target,mime)
        path=self._path(aad)
        if path.exists() or path.is_symlink():
            if self._read(path,aad,target,mime)!=data:
                _deny("ASSET_VAULT_OBJECT_CONFLICT")
            self._require(anchor,grant_id,target,"retain",purpose)
            return {"status":"already_retained","bytes":len(data),"sha256":target.sha256}
        nonce=os.urandom(12)
        envelope=VERSION+nonce+self._cipher.encrypt(nonce,data,aad)
        temp=None
        published=False
        try:
            fd,name=tempfile.mkstemp(prefix=".asset-stage-",dir=self.root)
            temp=Path(name)
            with os.fdopen(fd,"wb") as stream:
                stream.write(envelope)
                stream.flush()
                os.fsync(stream.fileno())
            self._require(anchor,grant_id,target,"retain",purpose)
            self._check_root()
            # Publish without overwriting; unsupported filesystems fail closed.
            os.link(temp,path)
            published=True
            self._require(anchor,grant_id,target,"retain",purpose)
            return {"status":"retained","bytes":len(data),"sha256":target.sha256}
        except Exception:
            if published:
                path.unlink(missing_ok=True)
            raise
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)

    def read_for_processing(self,anchor,grant_id,target:AssetIdentity,*,mime:str,purpose:str):
        """Return verified bytes only to trusted in-process caller.

        This is not the full processing PEP: must recheck before inference,
        before storing derivatives and at every output boundary.
        """
        self._require(anchor,grant_id,target,"retain",purpose)
        self._require(anchor,grant_id,target,"process",purpose)
        aad=_binding(anchor,grant_id,target,mime)
        data=self._read(self._path(aad),aad,target,mime)
        self._require(anchor,grant_id,target,"retain",purpose)
        self._require(anchor,grant_id,target,"process",purpose)
        return data
