"""CAP-023 E7: bounded, local, rights-gated video-source editing and multi-track draft render.

Intentional constraints: no URLs, remote media, shell interpolation, automatic
publication, unrestricted FFmpeg input, background loops or paid services.
Assets are content-hashed and tenant-scoped. Draft outputs retain source rights.
"""
from __future__ import annotations

from array import array
import base64
import binascii
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import (Table, Column, String, Integer, Text, LargeBinary,
                        ForeignKeyConstraint, select, insert, update, or_)
from sqlalchemy.exc import IntegrityError

from .domain import Id
from .sa_store import metadata, tenants
from .studio_e1 import StudioError
from .studio_render_e6 import LocalDraftRenderer, _now, studio_render_audio
from .studio_video_e5 import StoryboardStore

VIDEO_LIMIT_BYTES = 7 * 1024 * 1024
OUTPUT_LIMIT_BYTES = 18 * 1024 * 1024
MAX_SCENES = 4
MAX_TOTAL_MS = 15000
MAX_AUDIO_TRACKS = 4
WIDTH, HEIGHT, FPS = 540, 960, 12
# E8: two explicitly enumerated zero-cost local draft profiles; NEVER caller-chosen dimensions.
QUALITY_PROFILES = {
    "preview_540p": (540, 960, 12, 15000),
    "quality_720p": (720, 1280, 24, 6000),
}
LEASE_SECONDS = 480
MAX_ATTEMPTS = 3
ENCODE_TIMEOUT = 65
PROBE_TIMEOUT = 12


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UploadVideoSource(Strict):
    data_base64: str = Field(min_length=100, max_length=9_800_000)
    evidence_reference: str = Field(min_length=16, max_length=512)
    expires_at: datetime
    rights_attested: Literal[True]
    embedded_audio_rights_attested: bool = False
    embedded_audio_evidence_reference: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def check(self):
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("VIDEO_RIGHTS_TIMEZONE_REQUIRED")
        if self.expires_at <= datetime.now(timezone.utc):
            raise ValueError("VIDEO_RIGHTS_EXPIRED")
        if self.embedded_audio_rights_attested and (
                not self.embedded_audio_evidence_reference or
                len(self.embedded_audio_evidence_reference) < 16):
            raise ValueError("SOURCE_AUDIO_EVIDENCE_REQUIRED")
        if not self.embedded_audio_rights_attested and self.embedded_audio_evidence_reference:
            raise ValueError("SOURCE_AUDIO_ATTESTATION_REQUIRED")
        return self


class SceneInput(Strict):
    scene_id: Id
    video_asset_id: Id | None = None
    image_asset_id: Id | None = None
    trim_start_ms: int = Field(default=0, ge=0, le=30000)
    include_source_audio: bool = False
    source_audio_gain_percent: int = Field(default=100, ge=0, le=100)

    @model_validator(mode="after")
    def one_source(self):
        if (self.video_asset_id is None) == (self.image_asset_id is None):
            raise ValueError("EXACTLY_ONE_VISUAL_SOURCE_REQUIRED")
        if self.image_asset_id and self.trim_start_ms:
            raise ValueError("STATIC_IMAGE_CANNOT_BE_TRIMMED")
        if self.image_asset_id and self.include_source_audio:
            raise ValueError("STATIC_IMAGE_CANNOT_HAVE_SOURCE_AUDIO")
        return self


class AudioTrack(Strict):
    asset_id: Id
    start_ms: int = Field(ge=0, le=MAX_TOTAL_MS)
    gain_percent: int = Field(default=100, ge=0, le=100)


class QueueAdvancedDraft(Strict):
    job_id: Id
    storyboard_id: Id
    storyboard_version: int = Field(ge=1)
    scenes: list[SceneInput] = Field(min_length=1, max_length=MAX_SCENES)
    audio_tracks: list[AudioTrack] = Field(default_factory=list, max_length=MAX_AUDIO_TRACKS)
    quality_profile: Literal["preview_540p", "quality_720p"] = "preview_540p"


class AdvancedJobStatus(Strict):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed", "canceled"]
    attempts: int
    error_code: str | None
    artifact_id: str | None
    artifact_sha256: str | None = None
    draft_only: Literal[True] = True
    production_approved: Literal[False] = False


video_sources = Table("studio_e7_video_sources", metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("asset_id", String(128), primary_key=True),
    Column("content_sha256", String(64), nullable=False),
    Column("data", LargeBinary, nullable=False),
    Column("duration_ms", Integer, nullable=False),
    Column("width", Integer, nullable=False),
    Column("height", Integer, nullable=False),
    Column("expires_at", String(48), nullable=False),
    Column("rights_status", String(16), nullable=False),
    Column("evidence_reference", String(512), nullable=False),
    Column("attested_by", String(128), nullable=False),
    Column("has_embedded_audio", Integer, nullable=False, server_default="0"),
    Column("embedded_audio_rights_status", String(16), nullable=False, server_default="not_attested"),
    Column("embedded_audio_evidence_reference", String(512), nullable=True),
    ForeignKeyConstraint(["tenant_id"], [tenants.c.tenant_id]))

advanced_jobs = Table("studio_e7_render_jobs", metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("job_id", String(128), primary_key=True),
    Column("storyboard_id", String(128), nullable=False),
    Column("storyboard_version", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("lease_token", String(36), nullable=True),
    Column("lease_until", String(48), nullable=True),
    Column("manifest", Text, nullable=False),
    Column("manifest_sha256", String(64), nullable=False),
    Column("artifact_id", String(128), nullable=True),
    Column("error_code", String(80), nullable=True),
    Column("created_at", String(48), nullable=False),
    Column("created_by", String(128), nullable=False),
    ForeignKeyConstraint(["tenant_id"], [tenants.c.tenant_id]))

advanced_artifacts = Table("studio_e7_render_artifacts", metadata,
    Column("tenant_id", String(128), primary_key=True),
    Column("artifact_id", String(128), primary_key=True),
    Column("job_id", String(128), nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("duration_ms", Integer, nullable=False),
    Column("data", LargeBinary, nullable=False),
    ForeignKeyConstraint(["tenant_id", "job_id"],
                         ["studio_e7_render_jobs.tenant_id", "studio_e7_render_jobs.job_id"]))

advanced_events = Table("studio_e7_render_events", metadata,
    Column("event_id", String(36), primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column("job_id", String(128), nullable=True),
    Column("asset_id", String(128), nullable=True),
    Column("action", String(32), nullable=False),
    Column("actor", String(128), nullable=False),
    Column("occurred_at", String(48), nullable=False),
    ForeignKeyConstraint(["tenant_id"], [tenants.c.tenant_id]))


def _event(db, tenant, actor, action, *, job=None, asset=None):
    db.execute(insert(advanced_events).values(event_id=str(uuid4()), tenant_id=tenant,
        job_id=job, asset_id=asset, action=action, actor=actor, occurred_at=_now()))


def _run_ffmpeg(args: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "WINDIR", "TMP", "TEMP")
           if k in os.environ}
    env["HOME"] = str(cwd)
    try:
        return subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                              cwd=cwd, env=env, timeout=timeout, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise StudioError("STUDIO_E7_FFMPEG_FAILED", 503) from exc


def _probe_mp4(raw: bytes, *, permit_audio: bool = False) -> tuple[int, int, int, bool]:
    """No URLs: ffprobe can see only a temp file from an uploaded byte array."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise StudioError("STUDIO_E7_FFPROBE_UNAVAILABLE", 503)
    if not (100 <= len(raw) <= VIDEO_LIMIT_BYTES and raw[4:8] == b"ftyp"):
        raise StudioError("STUDIO_E7_MP4_REQUIRED", 422)
    with tempfile.TemporaryDirectory(prefix="tapi_e7_probe_") as folder:
        root = Path(folder); src = root / "upload.mp4"; src.write_bytes(raw)
        cmd = [ffprobe, "-v", "error", "-protocol_whitelist", "file",
               "-show_entries", "format=format_name,duration:stream=codec_type,codec_name,pix_fmt,width,height,channels,sample_rate",
               "-of", "json", str(src)]
        try:
            parsed = json.loads(_run_ffmpeg(cmd, root, PROBE_TIMEOUT).stdout)
        except (ValueError, UnicodeDecodeError) as exc:
            raise StudioError("STUDIO_E7_VIDEO_INVALID", 422) from exc
    info = parsed.get("format") or {}
    if "mov" not in info.get("format_name", ""):
        raise StudioError("STUDIO_E7_MP4_REQUIRED", 422)
    streams = parsed.get("streams") or []
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audios) > 1 or len(streams) != len(videos) + len(audios):
        raise StudioError("STUDIO_E7_VIDEO_ONLY_REQUIRED", 422)
    if audios:
        if not permit_audio:
            raise StudioError("STUDIO_E7_VIDEO_ONLY_REQUIRED", 422)
        audio = audios[0]
        if audio.get("codec_name") != "aac" or not (1 <= int(audio.get("channels") or 0) <= 2) or (
                not 8000 <= int(audio.get("sample_rate") or 0) <= 48000):
            raise StudioError("STUDIO_E8_EMBEDDED_AUDIO_CODEC_INVALID", 422)
    video = videos[0]
    if video.get("codec_name") != "h264" or video.get("pix_fmt") not in {"yuv420p", "yuvj420p"}:
        raise StudioError("STUDIO_E7_H264_YUV420P_REQUIRED", 422)
    w, h = int(video.get("width") or 0), int(video.get("height") or 0)
    try:
        duration = int(float(info.get("duration")) * 1000)
    except (ValueError, TypeError, OverflowError) as exc:
        raise StudioError("STUDIO_E7_VIDEO_DURATION_INVALID", 422) from exc
    if not (16 <= w <= 1080 and 16 <= h <= 1920 and w * h <= 2_073_600
            and 500 <= duration <= 30000):
        raise StudioError("STUDIO_E7_VIDEO_SIZE_OR_DURATION_INVALID", 422)
    return duration, w, h, bool(audios)


def _interpolate(keyframes, ms: int) -> tuple[int, int, int]:
    if not keyframes:
        return 100, 100, 100
    a = keyframes[0]
    if ms <= a.at_ms:
        return a.x, a.y, a.opacity
    for b in keyframes[1:]:
        if ms <= b.at_ms:
            t = (ms - a.at_ms) / max(1, b.at_ms - a.at_ms)
            return tuple(round(getattr(a, k) * (1 - t) + getattr(b, k) * t)
                         for k in ("x", "y", "opacity"))
        a = b
    return a.x, a.y, a.opacity


def _frame_overlays(base, scene, local_ms):
    from PIL import Image, ImageDraw, ImageFont
    image = base.convert("RGBA")
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", max(16, round(image.height * 29 / HEIGHT)))
    except OSError:
        font = ImageFont.load_default()
    for layer in scene.overlays:
        if not (layer.start_ms <= local_ms < layer.end_ms):
            continue
        x, y, opacity = _interpolate(layer.keyframes, local_ms)
        alpha = round(255 * opacity / 100)
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        # Untrusted text is rasterized and never included in an FFmpeg expression.
        d.text((round(x * image.width / 1000), round(y * image.height / 1000)),
               layer.text[:100], fill=(255, 255, 255, alpha), font=font,
               stroke_width=2, stroke_fill=(0, 0, 0, alpha))
        image = Image.alpha_composite(image, overlay)
    return image.convert("RGB")


def _mix_wavs(tracks: list[tuple[bytes, int, int]], duration_ms: int) -> bytes | None:
    """Deterministic mono PCM mix with saturation, timeline offsets and gain."""
    if not tracks:
        return None
    import wave
    frames = duration_ms * 16
    mixed = [0] * frames
    for payload, start_ms, gain in tracks:
        with wave.open(io.BytesIO(payload), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getframerate() != 16000 or wav.getsampwidth() != 2:
                raise StudioError("STUDIO_E7_AUDIO_FORMAT_INVALID", 422)
            audio = array('h'); audio.frombytes(wav.readframes(wav.getnframes()))
            if sys.byteorder != "little":
                audio.byteswap()
        begin = start_ms * 16
        for i in range(min(len(audio), frames - begin)):
            mixed[begin + i] += round(int(audio[i]) * gain / 100)
    samples = array('h', (max(-32768, min(32767, item)) for item in mixed))
    if sys.byteorder != "little":
        samples.byteswap()
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(samples.tobytes())
    return out.getvalue()


class AdvancedStudioRenderer:
    def __init__(self, engine):
        self.engine = engine
        self.legacy = LocalDraftRenderer(engine)
        self.storyboards = StoryboardStore(engine)

    @staticmethod
    def _gates():
        LocalDraftRenderer._gates()
        if os.getenv("TAPI_E7_VIDEO_RENDER_ENABLED") != "1":
            raise StudioError("STUDIO_E7_DISABLED", 403)

    def upload_video(self, tenant, actor, request: UploadVideoSource):
        self._gates()
        try:
            raw = base64.b64decode(request.data_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise StudioError("STUDIO_E7_VIDEO_BASE64_INVALID", 422) from exc
        duration, width, height, has_audio = _probe_mp4(
            raw, permit_audio=request.embedded_audio_rights_attested)
        digest = sha256(raw).hexdigest()
        asset_id = "mp4." + digest[:32]
        with self.engine.begin() as db:
            existing = db.execute(select(video_sources.c.asset_id).where(
                video_sources.c.tenant_id == tenant,
                video_sources.c.asset_id == asset_id)).scalar_one_or_none()
            record = dict(expires_at=request.expires_at.isoformat(),
                rights_status="attested", evidence_reference=request.evidence_reference,
                attested_by=actor, has_embedded_audio=int(has_audio),
                embedded_audio_rights_status="attested" if has_audio else "not_attested",
                embedded_audio_evidence_reference=(request.embedded_audio_evidence_reference
                    if has_audio else None))
            if existing:
                db.execute(update(video_sources).where(video_sources.c.tenant_id == tenant,
                    video_sources.c.asset_id == asset_id).values(**record))
            else:
                db.execute(insert(video_sources).values(tenant_id=tenant, asset_id=asset_id,
                    content_sha256=digest, data=raw, duration_ms=duration,
                    width=width, height=height, **record))
            _event(db, tenant, actor, "video_attested", asset=asset_id)
        return {"asset_id":asset_id, "sha256":digest, "duration_ms":duration,
                "width":width, "height":height, "rights_status":"operator_attested_for_local_draft",
                "independently_verified":False, "has_embedded_audio":has_audio,
                "source_audio_rights_attested":bool(has_audio)}

    def revoke_video(self, tenant, actor, asset_id):
        with self.engine.begin() as db:
            updated = db.execute(update(video_sources).where(
                video_sources.c.tenant_id == tenant,
                video_sources.c.asset_id == asset_id,
                video_sources.c.rights_status == "attested").values(rights_status="revoked"))
            if updated.rowcount != 1:
                raise StudioError("STUDIO_E7_VIDEO_NOT_FOUND_OR_REVOKED", 404)
            _event(db, tenant, actor, "video_revoked", asset=asset_id)
        return {"asset_id":asset_id, "rights_status":"revoked"}

    def revoke_embedded_audio(self, tenant, actor, asset_id):
        """Independently revoke the embedded-audio grant, preserving video rights."""
        with self.engine.begin() as db:
            changed = db.execute(update(video_sources).where(
                video_sources.c.tenant_id == tenant,
                video_sources.c.asset_id == asset_id,
                video_sources.c.rights_status == "attested",
                video_sources.c.embedded_audio_rights_status == "attested",
            ).values(embedded_audio_rights_status="revoked"))
            if changed.rowcount != 1:
                raise StudioError("STUDIO_E8_AUDIO_NOT_FOUND_OR_REVOKED", 404)
            _event(db, tenant, actor, "source_audio_revoked", asset=asset_id)
        return {"asset_id": asset_id, "embedded_audio_rights_status": "revoked",
                "video_rights_unchanged": True}

    @staticmethod
    def _video_bytes(db, tenant, asset_id, *, expected_hash=None,
                     require_source_audio=False):
        row = db.execute(select(video_sources).where(
            video_sources.c.tenant_id == tenant,
            video_sources.c.asset_id == asset_id)).mappings().first()
        if not row or row["rights_status"] != "attested" or datetime.fromisoformat(
                row["expires_at"]) <= datetime.now(timezone.utc):
            raise StudioError("STUDIO_E7_VIDEO_RIGHTS_INACTIVE", 403)
        if require_source_audio and not (row["has_embedded_audio"] == 1 and
                row["embedded_audio_rights_status"] == "attested" and
                row["embedded_audio_evidence_reference"]):
            raise StudioError("STUDIO_E8_SOURCE_AUDIO_NOT_AUTHORIZED", 403)
        actual = sha256(bytes(row["data"])).hexdigest()
        if actual != row["content_sha256"] or (expected_hash and actual != expected_hash):
            raise StudioError("STUDIO_E7_VIDEO_HASH_MISMATCH", 403)
        return bytes(row["data"]), dict(row)

    def _check_sources(self, db, tenant, entries):
        for entry in entries:
            if entry["kind"] == "video":
                self._video_bytes(db, tenant, entry["asset_id"], expected_hash=entry["sha256"],
                    require_source_audio=entry.get("include_source_audio", False))
            else:
                digest, _ = self.legacy._active_rights(db, tenant, entry["asset_id"], "png")
                if digest != entry["sha256"]:
                    raise StudioError("STUDIO_E7_IMAGE_CHANGED", 403)

    def _check_audios(self, db, tenant, tracks):
        for track in tracks:
            digest, _ = self.legacy._active_rights(db, tenant, track["asset_id"], "wav")
            if digest != track["sha256"]:
                raise StudioError("STUDIO_E7_AUDIO_CHANGED", 403)

    def queue(self, tenant, actor, request: QueueAdvancedDraft):
        self._gates()
        story = self.storyboards.get(tenant, request.storyboard_id)
        if story.version != request.storyboard_version:
            raise StudioError("STUDIO_E7_STORYBOARD_VERSION_CONFLICT", 409)
        if (len(story.scenes) > MAX_SCENES or
                sum(scene.duration_ms for scene in story.scenes) > MAX_TOTAL_MS):
            raise StudioError("STUDIO_E7_DURATION_OR_SCENE_LIMIT", 422)
        quality = QUALITY_PROFILES[request.quality_profile]
        if request.quality_profile == "quality_720p" and os.getenv("TAPI_E8_HQ_ENABLED") != "1":
            raise StudioError("STUDIO_E8_HQ_DISABLED", 403)
        if sum(scene.duration_ms for scene in story.scenes) > quality[3]:
            raise StudioError("STUDIO_E8_PROFILE_DURATION_EXCEEDED", 422)
        if len(request.audio_tracks) + sum(x.include_source_audio for x in request.scenes) > MAX_AUDIO_TRACKS:
            raise StudioError("STUDIO_E8_TOO_MANY_AUDIO_TRACKS", 422)
        names = [scene.scene_id for scene in request.scenes]
        order = [clip.scene_id for clip in story.clips]
        if len(set(names)) != len(names) or set(names) != set(order):
            raise StudioError("STUDIO_E7_SCENES_MUST_MATCH_STORYBOARD", 422)
        sources = {scene.scene_id:scene for scene in request.scenes}
        with self.engine.begin() as db:
            entries=[]
            for clip in story.clips:
                source = sources[clip.scene_id]
                if source.video_asset_id:
                    _, video=self._video_bytes(db, tenant, source.video_asset_id,
                        require_source_audio=source.include_source_audio)
                    if source.trim_start_ms + clip.duration_ms > video["duration_ms"] - 25:
                        raise StudioError("STUDIO_E7_TRIM_OUT_OF_BOUNDS", 422)
                    entry={"scene_id":clip.scene_id, "kind":"video",
                           "asset_id":source.video_asset_id, "sha256":video["content_sha256"],
                           "trim_start_ms":source.trim_start_ms,
                           "include_source_audio":source.include_source_audio,
                           "source_audio_gain_percent":source.source_audio_gain_percent}
                else:
                    digest,_=self.legacy._active_rights(db,tenant,source.image_asset_id,"png")
                    entry={"scene_id":clip.scene_id,"kind":"png",
                           "asset_id":source.image_asset_id,"sha256":digest,"trim_start_ms":0}
                entries.append(entry)
            tracks=[]
            for track in request.audio_tracks:
                digest,_=self.legacy._active_rights(db,tenant,track.asset_id,"wav")
                if track.start_ms >= sum(clip.duration_ms for clip in story.clips):
                    raise StudioError("STUDIO_E7_AUDIO_START_OUT_OF_BOUNDS",422)
                tracks.append({"asset_id":track.asset_id,"sha256":digest,
                               "start_ms":track.start_ms,"gain_percent":track.gain_percent})
            manifest={"schema":"studio-render-job.v2","storyboard_id":story.storyboard_id,
                      "storyboard_version":story.version,"sources":entries,"audio_tracks":tracks,
                      "duration_ms":sum(clip.duration_ms for clip in story.clips),
                      "fps":quality[2],"width":quality[0],"height":quality[1],
                      "quality_profile":request.quality_profile,"draft_only":True}
            raw=json.dumps(manifest,sort_keys=True,separators=(",",":"))
            try:
                db.execute(insert(advanced_jobs).values(tenant_id=tenant,job_id=request.job_id,
                    storyboard_id=story.storyboard_id,storyboard_version=story.version,
                    status="queued", attempts=0,lease_token=None,lease_until=None,
                    manifest=raw,manifest_sha256=sha256(raw.encode()).hexdigest(),
                    artifact_id=None,error_code=None,created_by=actor,created_at=_now()))
            except IntegrityError as exc:
                raise StudioError("STUDIO_E7_JOB_DUPLICATE",409) from exc
            _event(db,tenant,actor,"queued",job=request.job_id)
        return self.get(tenant,request.job_id)

    def get(self,tenant,job_id):
        with self.engine.connect() as db:
            row=db.execute(select(advanced_jobs).where(advanced_jobs.c.tenant_id==tenant,
                advanced_jobs.c.job_id==job_id)).mappings().first()
            if not row:
                raise StudioError("STUDIO_E7_JOB_NOT_FOUND",404)
            digest=None
            if row["artifact_id"]:
                digest=db.execute(select(advanced_artifacts.c.content_sha256).where(
                    advanced_artifacts.c.tenant_id==tenant,
                    advanced_artifacts.c.artifact_id==row["artifact_id"])).scalar_one_or_none()
        return AdvancedJobStatus(job_id=job_id,status=row["status"],attempts=row["attempts"],
            error_code=row["error_code"],artifact_id=row["artifact_id"],artifact_sha256=digest)

    def cancel(self,tenant,actor,job_id):
        with self.engine.begin() as db:
            updated=db.execute(update(advanced_jobs).where(
                advanced_jobs.c.tenant_id==tenant,advanced_jobs.c.job_id==job_id,
                advanced_jobs.c.status.in_(["queued","running"])).values(
                status="canceled",lease_token=None,lease_until=None))
            if updated.rowcount!=1:
                raise StudioError("STUDIO_E7_CANCEL_NOT_ALLOWED",409)
            _event(db,tenant,actor,"canceled",job=job_id)
        return self.get(tenant,job_id)

    def recover_stale(self,tenant,actor="local-worker"):
        self._gates()
        recovered=0
        with self.engine.begin() as db:
            rows=db.execute(select(advanced_jobs).where(
                advanced_jobs.c.tenant_id==tenant,advanced_jobs.c.status=="running",
                advanced_jobs.c.lease_until <= _now())).mappings().all()
            for row in rows:
                failed=row["attempts"]>=MAX_ATTEMPTS
                changed=db.execute(update(advanced_jobs).where(
                    advanced_jobs.c.tenant_id==tenant,
                    advanced_jobs.c.job_id==row["job_id"],
                    advanced_jobs.c.status=="running",
                    advanced_jobs.c.lease_token==row["lease_token"]).values(
                    status="failed" if failed else "queued",
                    error_code="STUDIO_E7_LEASE_EXHAUSTED" if failed else None,
                    lease_token=None,lease_until=None))
                if changed.rowcount:
                    _event(db,tenant,actor,"recovered_failed" if failed else "recovered_queued",
                           job=row["job_id"])
                    recovered+=1
        return recovered

    def retry(self,tenant,actor,job_id):
        self._gates()
        with self.engine.begin() as db:
            changed=db.execute(update(advanced_jobs).where(
                advanced_jobs.c.tenant_id==tenant,advanced_jobs.c.job_id==job_id,
                advanced_jobs.c.status=="failed",advanced_jobs.c.attempts<MAX_ATTEMPTS).values(
                    status="queued",error_code=None,lease_token=None,lease_until=None))
            if changed.rowcount!=1:
                raise StudioError("STUDIO_E7_RETRY_NOT_ALLOWED",409)
            _event(db,tenant,actor,"retried",job=job_id)
        return self.get(tenant,job_id)

    def artifact(self,tenant,artifact_id):
        with self.engine.connect() as db:
            row=db.execute(select(advanced_artifacts).where(
                advanced_artifacts.c.tenant_id==tenant,
                advanced_artifacts.c.artifact_id==artifact_id)).mappings().first()
            if not row:raise StudioError("STUDIO_E7_ARTIFACT_NOT_FOUND",404)
            job=db.execute(select(advanced_jobs).where(
                advanced_jobs.c.tenant_id==tenant,
                advanced_jobs.c.job_id==row["job_id"],
                advanced_jobs.c.status=="succeeded")).mappings().first()
            if not job:raise StudioError("STUDIO_E7_ARTIFACT_NOT_FOUND",404)
            manifest=json.loads(job["manifest"])
            self._check_sources(db,tenant,manifest["sources"])
            self._check_audios(db,tenant,manifest["audio_tracks"])
            blob=bytes(row["data"])
        if sha256(blob).hexdigest()!=row["content_sha256"]:
            raise StudioError("STUDIO_E7_ARTIFACT_CORRUPTED",500)
        return blob

    def _decode_scene(self,root,scene_index,entry,duration_ms,db,tenant,
                      width=WIDTH,height=HEIGHT,fps=FPS):
        """Yield RGB frames one at a time from bounded temporary files."""
        from PIL import Image
        num=math.ceil(duration_ms*fps/1000)
        if entry["kind"]=="png":
            _, raw=self.legacy._active_rights(db,tenant,entry["asset_id"],"png")
            with Image.open(io.BytesIO(raw)) as im:
                image=im.convert("RGB")
                image.thumbnail((width,height))
                bg=Image.new("RGB",(width,height),(20,24,28))
                bg.paste(image,((width-image.width)//2,(height-image.height)//2))
            return (bg.copy() for _ in range(num))
        raw,_=self._video_bytes(db,tenant,entry["asset_id"],expected_hash=entry["sha256"])
        ffmpeg=shutil.which("ffmpeg")
        if not ffmpeg:raise StudioError("STUDIO_E7_FFMPEG_MISSING",503)
        src=root/f"source_{scene_index}.mp4";src.write_bytes(raw)
        target=root/f"s{scene_index}_%04d.png"
        vf=f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=rgb24"
        cmd=[ffmpeg,"-nostdin","-hide_banner","-loglevel","error","-y",
             "-threads","1","-filter_threads","1", "-ss",f"{entry['trim_start_ms']/1000:.3f}",
             "-protocol_whitelist","file","-i",str(src),"-t",f"{duration_ms/1000:.3f}",
             "-vf",vf,"-frames:v",str(num),str(target)]
        _run_ffmpeg(cmd,root,ENCODE_TIMEOUT)
        files=sorted(root.glob(f"s{scene_index}_*.png"))
        if not files:raise StudioError("STUDIO_E7_NO_DECODED_FRAMES",422)
        def frames():
            last = None
            for frame_file in files[:num]:
                with Image.open(frame_file) as im:
                    last = im.convert("RGB")
                frame_file.unlink(missing_ok=True)
                yield last
            # Some encoders return a shorter final frame; repeat a single frame
            # at most until the bounded logical clip duration is covered.
            for _ in range(max(0, num - len(files))):
                yield last.copy()
        return frames()

    def _render(self,tenant,story,manifest):
        """Stream bounded scene frames to disk instead of retaining all in RAM."""
        from PIL import Image, ImageDraw
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise StudioError("STUDIO_E7_FFMPEG_MISSING", 503)
        quality_name = manifest.get("quality_profile", "preview_540p")
        profile = QUALITY_PROFILES.get(quality_name)
        if (not profile or list(profile[:3]) != [manifest["width"],manifest["height"],manifest["fps"]]
                or manifest["duration_ms"] > profile[3]):
            raise StudioError("STUDIO_E8_RENDER_PROFILE_INVALID", 403)
        if quality_name == "quality_720p" and os.getenv("TAPI_E8_HQ_ENABLED") != "1":
            raise StudioError("STUDIO_E8_HQ_DISABLED", 403)
        width, height, fps = profile[:3]
        with tempfile.TemporaryDirectory(prefix="tapi_e8_render_") as folder:
            root = Path(folder)
            frame_number = 0; boundaries = []; source_audio = []
            scene_lookup = {scene.scene_id:scene for scene in story.scenes}
            with self.engine.connect() as db:
                for i, entry in enumerate(manifest["sources"]):
                    scene = scene_lookup[entry["scene_id"]]
                    frames = self._decode_scene(root,i,entry,scene.duration_ms,db,tenant,
                                                width=width,height=height,fps=fps)
                    for j, img in enumerate(frames):
                        img = _frame_overlays(img,scene,round(j*1000/fps))
                        draw = ImageDraw.Draw(img)
                        label_height = max(46,round(height*52/HEIGHT))
                        draw.rectangle((0,height-label_height,width,height),fill=(10,10,10))
                        draw.text((15,height-label_height+14),"RASCUNHO - NAO PUBLICAR",fill="white")
                        img.save(root/f"f_{frame_number:04d}.png",format="PNG",compress_level=1)
                        frame_number += 1
                    del frames
                    boundaries.append(frame_number)
                    if entry.get("include_source_audio"):
                        data, video = self._video_bytes(db,tenant,entry["asset_id"],
                            expected_hash=entry["sha256"],require_source_audio=True)
                        src = root / f"source_{i}.mp4"
                        if not src.exists():src.write_bytes(data)
                        wav_path = root / f"embedded_{i}.wav"
                        _run_ffmpeg([ffmpeg,"-nostdin","-hide_banner","-loglevel","error","-y",
                                     "-protocol_whitelist","file","-ss",
                                     f"{entry['trim_start_ms']/1000:.3f}","-i",str(src),
                                     "-map","0:a:0","-t",f"{scene.duration_ms/1000:.3f}",
                                     "-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",
                                     str(wav_path)],root,ENCODE_TIMEOUT)
                        if wav_path.stat().st_size>1_200_000:
                            raise StudioError("STUDIO_E8_SOURCE_AUDIO_TOO_LARGE",422)
                        # Scenes are ordered by timeline clips, not by arbitrary scene-list order.
                        origin = sum(scene_lookup[x["scene_id"]].duration_ms
                                     for x in manifest["sources"][:i])
                        source_audio.append((wav_path.read_bytes(),origin,
                                             entry["source_audio_gain_percent"]))
                audios = list(source_audio)
                for track in manifest["audio_tracks"]:
                    _, raw = self.legacy._active_rights(db,tenant,track["asset_id"],"wav")
                    audios.append((raw,track["start_ms"],track["gain_percent"]))
            # Apply transition blending to frame pairs on disk (bounded memory).
            for i, clip in enumerate(story.clips[:-1]):
                if clip.transition != "crossfade" or clip.transition_ms <= 0:continue
                center = boundaries[i]
                half = max(1,round((clip.transition_ms/1000*fps)/2))
                half = min(half,center,frame_number-center)
                for k in range(half):
                    left = root/f"f_{center-half+k:04d}.png"
                    right = root/f"f_{center+k:04d}.png"
                    with Image.open(left) as a, Image.open(right) as b:
                        before = a.convert("RGB"); after = b.convert("RGB")
                    Image.blend(before,after,(k+1)/(2*half+1)).save(left,format="PNG")
                    Image.blend(before,after,(k+1+half)/(2*half+1)).save(right,format="PNG")
            audio = _mix_wavs(audios,manifest["duration_ms"])
            cmd=[ffmpeg,"-nostdin","-hide_banner","-loglevel","error","-y",
                 "-threads","1","-filter_threads","1","-framerate",str(fps),
                 "-i",str(root/"f_%04d.png")]
            if audio:
                wav=root/"mix.wav";wav.write_bytes(audio)
                cmd.extend(["-protocol_whitelist","file","-i",str(wav)])
            out=root/"draft_e8.mp4"
            cmd.extend(["-map","0:v:0"])
            if audio:cmd.extend(["-map","1:a:0","-c:a","aac","-b:a","160k"])
            else:cmd.append("-an")
            cmd.extend(["-c:v","libx264","-preset","veryfast" if quality_name=="preview_540p" else "medium",
                        "-crf","22" if quality_name=="preview_540p" else "18",
                        "-pix_fmt","yuv420p","-r",str(fps),"-t",
                        f"{manifest['duration_ms']/1000:.3f}","-movflags","+faststart",str(out)])
            _run_ffmpeg(cmd,root,ENCODE_TIMEOUT * 2 if quality_name=="quality_720p" else ENCODE_TIMEOUT)
            if not out.is_file() or not 100 <= out.stat().st_size <= OUTPUT_LIMIT_BYTES:
                raise StudioError("STUDIO_E7_OUTPUT_SIZE_INVALID",422)
            return out.read_bytes()

    def process_next(self,tenant,actor="local-worker"):
        self._gates()
        self.recover_stale(tenant,actor)
        token=str(uuid4())
        lease_until=(datetime.now(timezone.utc)+timedelta(seconds=LEASE_SECONDS)).isoformat()
        with self.engine.begin() as db:
            candidate=db.execute(select(advanced_jobs).where(
                advanced_jobs.c.tenant_id==tenant,advanced_jobs.c.status=="queued",
                advanced_jobs.c.attempts<MAX_ATTEMPTS).order_by(
                advanced_jobs.c.created_at,advanced_jobs.c.job_id).limit(1)).mappings().first()
            if candidate is None:return None
            claimed=db.execute(update(advanced_jobs).where(
                advanced_jobs.c.tenant_id==tenant,advanced_jobs.c.job_id==candidate["job_id"],
                advanced_jobs.c.status=="queued").values(status="running",
                attempts=candidate["attempts"]+1,lease_token=token,lease_until=lease_until))
            if claimed.rowcount!=1:return None
            _event(db,tenant,actor,"running",job=candidate["job_id"])
        error=None;result=None
        try:
            if sha256(candidate["manifest"].encode()).hexdigest()!=candidate["manifest_sha256"]:
                raise StudioError("STUDIO_E7_MANIFEST_CORRUPTED",403)
            manifest=json.loads(candidate["manifest"])
            quality=QUALITY_PROFILES.get(manifest.get("quality_profile", "preview_540p"))
            if (not quality or [manifest.get("width"),manifest.get("height"),manifest.get("fps")] != list(quality[:3])
                    or manifest.get("duration_ms", 0)>quality[3]):
                raise StudioError("STUDIO_E8_RENDER_PROFILE_INVALID", 403)
            if manifest.get("schema")!="studio-render-job.v2":
                raise StudioError("STUDIO_E7_MANIFEST_SCHEMA_INVALID",422)
            story=self.storyboards.get(tenant,candidate["storyboard_id"],candidate["storyboard_version"])
            if ([clip.scene_id for clip in story.clips] !=
                    [entry["scene_id"] for entry in manifest["sources"]] or
                    sum(s.duration_ms for s in story.scenes)!=manifest["duration_ms"]):
                raise StudioError("STUDIO_E7_STORYBOARD_MISMATCH",403)
            with self.engine.connect() as db:
                self._check_sources(db,tenant,manifest["sources"])
                self._check_audios(db,tenant,manifest["audio_tracks"])
            result=self._render(tenant,story,manifest)
        except StudioError as exc:
            error=exc.code
        except Exception:
            error="STUDIO_E7_UNEXPECTED_FAILURE"
        with self.engine.begin() as db:
            active=db.execute(select(advanced_jobs).where(
                advanced_jobs.c.tenant_id==tenant,advanced_jobs.c.job_id==candidate["job_id"])).mappings().first()
            if active["status"]!="running" or active["lease_token"]!=token:
                # Cancellation or recovery won the race: discard result.
                return self.get(tenant,candidate["job_id"])
            if result:
                try:
                    self._check_sources(db,tenant,manifest["sources"])
                    self._check_audios(db,tenant,manifest["audio_tracks"])
                except StudioError as exc:
                    result=None;error=exc.code
            if result:
                digest=sha256(result).hexdigest();artifact_id="video."+digest[:32]
                exists=db.execute(select(advanced_artifacts.c.artifact_id).where(
                    advanced_artifacts.c.tenant_id==tenant,
                    advanced_artifacts.c.artifact_id==artifact_id)).scalar_one_or_none()
                if exists:artifact_id="video."+str(uuid4())
                db.execute(insert(advanced_artifacts).values(tenant_id=tenant,
                    artifact_id=artifact_id,job_id=candidate["job_id"],
                    content_sha256=digest,duration_ms=manifest["duration_ms"],data=result))
                db.execute(update(advanced_jobs).where(
                    advanced_jobs.c.tenant_id==tenant,advanced_jobs.c.job_id==candidate["job_id"],
                    advanced_jobs.c.lease_token==token).values(status="succeeded",
                    artifact_id=artifact_id,error_code=None,lease_token=None,lease_until=None))
                _event(db,tenant,actor,"succeeded",job=candidate["job_id"])
            else:
                db.execute(update(advanced_jobs).where(
                    advanced_jobs.c.tenant_id==tenant,advanced_jobs.c.job_id==candidate["job_id"],
                    advanced_jobs.c.lease_token==token).values(status="failed",error_code=error,
                    lease_token=None,lease_until=None))
                _event(db,tenant,actor,"failed",job=candidate["job_id"])
        return self.get(tenant,candidate["job_id"])
