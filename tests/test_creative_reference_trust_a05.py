import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import pytest
from tapi_gate0.creative_reference_trust_a05 import (
    ENABLE, TRUST_FILE, TRUST_SHA256, SCHEMA, load_reference_trust,
)

@pytest.fixture
def config(tmp_path):
    root=tmp_path/'checkout';root.mkdir()
    source=tmp_path/'host-trust.json'
    row={"tenant_id":"tenantA","platform":"instagram","issuer_id":"test-authority",
         "public_key_b64":base64.b64encode(bytes(range(1,33))).decode(),
         "min_revocation_revision":8,"revocation_claims_sha256":"a"*64}
    body={"schema_version":SCHEMA,"authorities":[row]}
    def write(payload=None, mode=0o600):
        source.write_bytes(json.dumps(payload if payload is not None else body).encode())
        source.chmod(mode)
        return {ENABLE:"1",TRUST_FILE:str(source),TRUST_SHA256:sha256(source.read_bytes()).hexdigest()}
    return root,source,body,write

def test_absent_is_disabled(config):
    root,*_=config
    assert load_reference_trust({},repository_root=root) is None

def test_valid_anchored_file(config):
    root,src,body,write=config
    pins=load_reference_trust(write(),repository_root=root)
    assert len(pins)==1
    k=pins[('tenantA','instagram')]
    assert k.min_revocation_revision==8
    assert len(k.public_key)==32
    assert k.tenant_platform_scope==frozenset({('tenantA','instagram')})

@pytest.mark.parametrize('updates', [
 {ENABLE:'0'}, {ENABLE:''},{TRUST_SHA256:'f'*64},
 {TRUST_FILE:'relative.json'},
])
def test_partial_or_nonmatching_config_denied(config,updates):
    root,src,body,write=config
    env=write();env.update(updates)
    with pytest.raises(RuntimeError,match='CREATIVE_REFERENCE_TRUST_CONFIG_INVALID'):
        load_reference_trust(env,repository_root=root)

def test_file_in_repo_denied(config):
    root,src,body,write=config
    file=root/'trust.json';file.write_bytes(src.read_bytes() if src.exists() else json.dumps(body).encode());file.chmod(0o600)
    env={ENABLE:'1',TRUST_FILE:str(file),TRUST_SHA256:sha256(file.read_bytes()).hexdigest()}
    with pytest.raises(RuntimeError):load_reference_trust(env,repository_root=root)

def test_symlink_denied(config):
    root,src,body,write=config
    env=write();other=src.parent/'link.json'
    try:
        other.symlink_to(src)
    except (OSError, NotImplementedError):
        # Symlink creation may require Windows Developer Mode. A directory
        # still verifies rejection of non-regular trust-file paths.
        other.mkdir()
    env[TRUST_FILE]=str(other)
    with pytest.raises(RuntimeError):load_reference_trust(env,repository_root=root)

@pytest.mark.parametrize('modify',[
 lambda d:d['authorities'].append(d['authorities'][0].copy()),
 lambda d:d['authorities'][0].update(min_revocation_revision=True),
 lambda d:d['authorities'][0].update(public_key_b64='not valid base64!'),
 lambda d:d['authorities'][0].update(tenant_id='../other'),
 lambda d:d['authorities'][0].update(platform='stone_internal'),
 lambda d:d.update(schema_version='unknown'),
])
def test_invalid_schema_denied(config,modify):
    root,src,body,write=config
    modify(body)
    env=write(body)
    with pytest.raises(RuntimeError,match='CREATIVE_REFERENCE_TRUST_CONFIG_INVALID'):
        load_reference_trust(env,repository_root=root)

def test_wrong_file_mode_denied(config):
    if os.name != 'posix':
        return
    root,src,body,write=config
    with pytest.raises(RuntimeError):load_reference_trust(write(mode=0o644),repository_root=root)

def test_duplicate_json_keys_denied(config):
    root,src,body,write=config
    source='{"schema_version":"'+SCHEMA+'","schema_version":"'+SCHEMA+'","authorities":[]}'
    src.write_text(source)
    src.chmod(0o600)
    env={ENABLE:'1',TRUST_FILE:str(src),TRUST_SHA256:sha256(src.read_bytes()).hexdigest()}
    with pytest.raises(RuntimeError):load_reference_trust(env,repository_root=root)
