"""Local visual adapter: file attestation, path confinement and conservative evidence."""
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import os

import pytest

from tapi_gate0.multimodal import inspect_approved_local_media, inspect_generated_visual_fixture, _approved_media, MediaPermissionError, VisualObservation
from tapi_gate0.classification import classify_metadata_caption
from tapi_gate0.connectors import NormalizedItem


def test_requires_approved_root(tmp_path,monkeypatch):
    p=tmp_path/'fake.png';p.write_bytes(b'not an image')
    monkeypatch.delenv('TAPI_APPROVED_MEDIA_ROOT',raising=False)
    with pytest.raises(MediaPermissionError,match='APPROVED_MEDIA_ROOT_REQUIRED'):
        _approved_media(str(p),sha256(p.read_bytes()).hexdigest())


def test_cannot_open_outside_root_or_incorrect_digest(tmp_path,monkeypatch):
    root=tmp_path/'approved';root.mkdir()
    outside=tmp_path/'elsewhere.png';outside.write_bytes(b'not real')
    monkeypatch.setenv('TAPI_APPROVED_MEDIA_ROOT',str(root))
    with pytest.raises(MediaPermissionError,match='OUTSIDE_APPROVED_ROOT'):
        _approved_media(str(outside),sha256(outside.read_bytes()).hexdigest())
    inside=root/'file.png';inside.write_bytes(b'invalid')
    with pytest.raises(MediaPermissionError,match='MEDIA_DIGEST_MISMATCH'):
        _approved_media(str(inside),'0'*64)


def test_visual_observation_adds_only_positive_provisional_signals():
    post=NormalizedItem(platform='instagram',source_account_id='1781',source_item_id='1791',
        creator_handle='owner',media_type='reels',source_url='https://www.instagram.com/reel/XX/',
        published_at=datetime.now(timezone.utc),caption='Marketing local')
    obs=VisualObservation(sha256='a'*64,frames_examined=3,face_detected=True,
       text_detected=False,face_locator='sha256:'+'a'*64+'#frame-t=1',
       text_locator=None,face_timestamp_s=1.0,text_timestamp_s=None)
    result=classify_metadata_caption(post,'tenant','content',visual=obs)
    assert result.values.tem_rosto is True
    assert result.field_evidence['tem_rosto'].modality.value=='video'
    assert result.values.texto_na_tela is None
    assert result.values.hook_primeiros_3s is None
    assert 'review' in result.field_evidence['tem_rosto'].note


def test_offline_scan_generated_image():
    result=inspect_generated_visual_fixture()
    assert result.frames_examined==1
    assert not result.face_detected and not result.text_detected
    assert result.requires_human_review


def test_matching_path_hash_never_grants_media_processing(tmp_path,monkeypatch):
    root=tmp_path/'approved';root.mkdir()
    p=root/'file.png';p.write_bytes(b'caller-controlled')
    monkeypatch.setenv('TAPI_APPROVED_MEDIA_ROOT',str(root))
    digest=sha256(p.read_bytes()).hexdigest()
    assert _approved_media(str(p),digest)[1]==digest
    from tapi_gate0 import multimodal
    monkeypatch.setattr(multimodal,"_approved_media",lambda *_:pytest.fail("must deny before path access"))
    monkeypatch.setattr(multimodal,"_inspect_attested_file",lambda *_:pytest.fail("must deny before decode"))
    with pytest.raises(MediaPermissionError,match="MEDIA_VERIFIED_ASSET_GRANT_REQUIRED"):
        inspect_approved_local_media(str(p),digest)
