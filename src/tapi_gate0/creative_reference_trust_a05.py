"""Read-only, explicitly enabled A05 reference trust bootstrapping.

The file contains PUBLIC keys and independently pinned revocation hashes,
never private keys, grants or approval decisions. It is stored outside Git.
No environment variable alone provisions a right to external material: grants,
source binding, revocations and session checks remain mandatory in the PEP.
"""
from __future__ import annotations

import base64
import binascii
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Mapping

from .creative_reference_rights_a05 import TrustedReferenceAuthority

ENABLE = "TAPI_CREATIVE_REFERENCE_PEP_ENABLE"
TRUST_FILE = "TAPI_CREATIVE_REFERENCE_TRUST_FILE"
TRUST_SHA256 = "TAPI_CREATIVE_REFERENCE_TRUST_SHA256"
SCHEMA = "tapi-creative-reference-trust-bundle.v1"
MAX_BYTES = 65536
SHA_PATTERN = re.compile(r"[a-f0-9]{64}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
ALLOWED_PLATFORMS = frozenset({"instagram", "youtube"})
ROW_FIELDS = frozenset({
    "tenant_id", "platform", "issuer_id", "public_key_b64",
    "min_revocation_revision", "revocation_claims_sha256",
})


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _load(env: Mapping[str, str], root: Path):
    enabled, name, expected = (env.get(ENABLE), env.get(TRUST_FILE),
                               env.get(TRUST_SHA256))
    if enabled is None and name is None and expected is None:
        return None  # Default deny; callers must not manufacture an authority.
    if (enabled != "1" or not name or not expected
            or not SHA_PATTERN.fullmatch(expected)):
        raise ValueError("partial or invalid trust config")
    path = Path(name)
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("trust file must be an absolute regular path")
    resolved = path.resolve(strict=True)
    if resolved.is_relative_to(root.resolve(strict=True)):
        raise ValueError("trust bundle must not be repository-managed")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_size <= 0
                or info.st_size > MAX_BYTES):
            raise ValueError("invalid trust file")
        # POSIX restricts group/other access; Windows relies on independently
        # pinned digest and deployment-managed ACLs for public-key material.
        if os.name == "posix" and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
            raise ValueError("insecure trust file ownership or permissions")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(MAX_BYTES + 1)
    finally:
        os.close(fd)
    if len(raw) > MAX_BYTES or sha256(raw).hexdigest() != expected:
        raise ValueError("trust digest mismatch")
    body = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    if (not isinstance(body, dict) or set(body) != {"schema_version", "authorities"}
            or body["schema_version"] != SCHEMA
            or not isinstance(body["authorities"], list)
            or not 1 <= len(body["authorities"]) <= 32):
        raise ValueError("trust schema invalid")
    anchors = {}
    for row in body["authorities"]:
        if not isinstance(row, dict) or set(row) != ROW_FIELDS:
            raise ValueError("trust anchor fields invalid")
        tenant, platform, issuer = (row["tenant_id"], row["platform"], row["issuer_id"])
        if (not isinstance(tenant, str) or not IDENTIFIER.fullmatch(tenant)
                or not isinstance(issuer, str) or not IDENTIFIER.fullmatch(issuer)
                or platform not in ALLOWED_PLATFORMS):
            raise ValueError("trust scope invalid")
        revision, digest = row["min_revocation_revision"], row["revocation_claims_sha256"]
        if (type(revision) is not int or revision < 0
                or not isinstance(digest, str) or not SHA_PATTERN.fullmatch(digest)):
            raise ValueError("trust pin invalid")
        key_string = row["public_key_b64"]
        if not isinstance(key_string, str):
            raise ValueError("public key invalid")
        key = base64.b64decode(key_string, validate=True)
        if len(key) != 32 or key == bytes(32):
            raise ValueError("public key invalid")
        scope = (tenant, platform)
        if scope in anchors:
            raise ValueError("duplicate trust scope")
        anchors[scope] = TrustedReferenceAuthority(
            issuer_id=issuer, public_key=key,
            tenant_platform_scope=frozenset({scope}),
            min_revocation_revision=revision,
            revocation_claims_sha256=digest,
        )
    return anchors


def load_reference_trust(env: Mapping[str, str], *, repository_root: Path):
    """Fail closed at startup, never expose file paths, keys or parser internals."""
    try:
        return _load(env, repository_root)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, binascii.Error):
        raise RuntimeError("CREATIVE_REFERENCE_TRUST_CONFIG_INVALID") from None
