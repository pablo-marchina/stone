"""Offline visual-observation adapter; arbitrary media entry fails closed.

NEVER downloads from a social platform. Uses optional local OpenCV/Tesseract and
ffmpeg executables; no paid model service. Positive detections are preliminary,
not ground truth. Unknown/negative detections do not become negative claims.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import shutil
import subprocess
import tempfile


class MediaPermissionError(Exception):pass


@dataclass(frozen=True)
class VisualObservation:
    sha256: str
    frames_examined: int
    face_detected: bool
    text_detected: bool
    face_locator: str | None
    text_locator: str | None
    face_timestamp_s: float | None
    text_timestamp_s: float | None
    method: str = "opencv-haar+tesseract-local-preliminary"
    requires_human_review: bool = True


def _approved_media(path:str,expected_digest:str)->tuple[Path,str]:
    root=os.getenv("TAPI_APPROVED_MEDIA_ROOT")
    if not root:raise MediaPermissionError("APPROVED_MEDIA_ROOT_REQUIRED")
    safe_root=Path(root).resolve(strict=True)
    target=Path(path).resolve(strict=True)
    if not target.is_relative_to(safe_root) or not target.is_file():
        raise MediaPermissionError("MEDIA_PATH_OUTSIDE_APPROVED_ROOT")
    if target.suffix.lower() not in {".jpg",".jpeg",".png",".mp4",".mov",".webm"}:
        raise MediaPermissionError("MEDIA_EXTENSION_UNSUPPORTED")
    if target.stat().st_size>40_000_000:raise MediaPermissionError("MEDIA_SIZE_EXCEEDS_LIMIT")
    if len(expected_digest)!=64 or not all(x in '0123456789abcdef' for x in expected_digest):
        raise MediaPermissionError("MEDIA_DIGEST_REQUIRED")
    actual=sha256(target.read_bytes()).hexdigest()
    if actual!=expected_digest:raise MediaPermissionError("MEDIA_DIGEST_MISMATCH")
    return target,actual


def _frame_bytes(path:Path,timestamp:float):
    if path.suffix.lower() in {'.jpg','.jpeg','.png'}:
        return path.read_bytes()
    binary=shutil.which('ffmpeg')
    if not binary:raise MediaPermissionError("LOCAL_FFMPEG_UNAVAILABLE")
    cmd=[binary,'-hide_banner','-loglevel','error','-nostdin','-ss',str(timestamp),
         '-protocol_whitelist','file,pipe','-i',str(path),'-frames:v','1','-vf','scale=640:-1',
         '-f','image2pipe','-vcodec','png','pipe:1']
    try:
        result=subprocess.run(cmd,capture_output=True,timeout=12,check=False)
    except subprocess.TimeoutExpired as exc:
        raise MediaPermissionError("LOCAL_VIDEO_DECODE_TIMEOUT") from exc
    if result.returncode or not result.stdout or len(result.stdout)>8_000_000:
        raise MediaPermissionError("LOCAL_VIDEO_FRAME_UNAVAILABLE")
    return result.stdout


def inspect_approved_local_media(path:str,expected_sha256:str)->VisualObservation:
    # A matching local path and digest are not a rights grant. No verified
    # asset-level authorization service is wired to this legacy entrypoint.
    # Fail before opening any caller-supplied file, even if root/hash match.
    raise MediaPermissionError("MEDIA_VERIFIED_ASSET_GRANT_REQUIRED")


def inspect_generated_visual_fixture()->VisualObservation:
    """Run only a locally generated black JPEG; accepts no path or bytes."""
    from .policy import decide,Operation
    if not decide("synthetic_local",Operation.EVALUATE_SYNTHETIC.value).permitted:
        raise MediaPermissionError("SYNTHETIC_POLICY_DENIED")
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise MediaPermissionError("LOCAL_OPENCV_UNAVAILABLE") from exc
    with tempfile.TemporaryDirectory(prefix="tapi-visual-fixture-") as temp:
        target=Path(temp)/"generated-black.jpg"
        if not cv2.imwrite(str(target),np.zeros((128,192,3),dtype=np.uint8)):
            raise MediaPermissionError("LOCAL_FIXTURE_GENERATION_FAILED")
        digest=sha256(target.read_bytes()).hexdigest()
        observation=_inspect_attested_file(target,digest)
        if sha256(target.read_bytes()).hexdigest()!=digest:
            raise MediaPermissionError("LOCAL_FIXTURE_CHANGED")
        return observation


def _inspect_attested_file(target:Path,digest:str)->VisualObservation:
    # Private implementation helper, not an authorization boundary.
    try:import cv2
    except ImportError as exc:raise MediaPermissionError("LOCAL_OPENCV_UNAVAILABLE") from exc
    import numpy as np
    face_detector=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    if face_detector.empty():raise MediaPermissionError("FACE_DETECTOR_UNAVAILABLE")
    face=text=False
    face_loc=text_loc=None
    face_time=text_time=None
    total=0
    frames=[0.] if target.suffix.lower() in {'.jpg','.jpeg','.png'} else [0.,1.,3.]
    for second in frames:
        try:encoded=_frame_bytes(target,second)
        except MediaPermissionError:
            if second==0:raise
            continue
        img=cv2.imdecode(np.frombuffer(encoded,dtype=np.uint8),cv2.IMREAD_COLOR)
        if img is None:raise MediaPermissionError("UNREADABLE_MEDIA")
        total+=1
        gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
        if not face:
            detected=face_detector.detectMultiScale(gray,scaleFactor=1.2,minNeighbors=6,minSize=(36,36))
            if len(detected):
                face=True;face_time=second;face_loc=f"sha256:{digest}#frame-t={second}"
        if not text and shutil.which('tesseract'):
            try:
                proc=subprocess.run([shutil.which('tesseract'),'stdin','stdout','-l','por+eng'],
                    input=encoded,capture_output=True,timeout=5,check=False)
                # OCR is only weak positive signal; require at least 2 words with alphabetic chars.
                words=[w for w in proc.stdout.decode('utf-8','replace')[:2048].split()
                       if len(w)>=3 and any(ch.isalpha() for ch in w)]
                if proc.returncode==0 and len(words)>=2:
                    text=True;text_time=second;text_loc=f"sha256:{digest}#frame-t={second}"
            except subprocess.TimeoutExpired:
                pass
    return VisualObservation(sha256=digest,frames_examined=total,
             face_detected=face,text_detected=text,face_locator=face_loc,
             text_locator=text_loc,face_timestamp_s=face_time,text_timestamp_s=text_time)
