"""Local visual adapter: file attestation, path confinement and conservative evidence."""
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import os

import pytest

from tapi_gate0.multimodal import inspect_approved_local_media, MediaPermissionError, VisualObservation
from tapi_gate0.classification import classify_metadata_caption
from tapi_gate0.connectors import NormalizedItem


def test_requires_approved_root(tmp_path,monkeypatch):
    p=tmp_path/'fake.png';p.write_bytes(b'not an image')
    monkeypatch.delenv('TAPI_APPROVED_MEDIA_ROOT',raising=False)
    with pytest.raises(MediaPermissionError,match='APPROVED_MEDIA_ROOT_REQUIRED'):
        inspect_approved_local_media(str(p),sha256(p.read_bytes()).hexdigest())


def test_cannot_open_outside_root_or_incorrect_digest(tmp_path,monkeypatch):
    root=tmp_path/'approved';root.mkdir()
    outside=tmp_path/'elsewhere.png';outside.write_bytes(b'not real')
    monkeypatch.setenv('TAPI_APPROVED_MEDIA_ROOT',str(root))
    with pytest.raises(MediaPermissionError,match='OUTSIDE_APPROVED_ROOT'):
        inspect_approved_local_media(str(outside),sha256(outside.read_bytes()).hexdigest())
    inside=root/'file.png';inside.write_bytes(b'invalid')
    with pytest.raises(MediaPermissionError,match='MEDIA_DIGEST_MISMATCH'):
        inspect_approved_local_media(str(inside),'0'*64)


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


def test_offline_scan_real_image(tmp_path,monkeypatch):
    import cv2,numpy as np
    root=tmp_path/'approved';root.mkdir()
    p=root/'dark.jpg'
    assert cv2.imwrite(str(p),np.zeros((128,192,3),dtype=np.uint8))
    monkeypatch.setenv('TAPI_APPROVED_MEDIA_ROOT',str(root))
    result=inspect_approved_local_media(str(p),sha256(p.read_bytes()).hexdigest())
    assert result.frames_examined==1
    assert not result.face_detected and not result.text_detected
    assert result.requires_human_review
