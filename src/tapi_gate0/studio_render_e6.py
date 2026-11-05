"""CAP-023 E6: opt-in, locally bounded draft MP4 render queue.

Only already-uploaded PNG frames and validated, locally uploaded mono PCM WAV
may enter FFmpeg. Every PNG requires a separate, expiring operator rights
attestation; grants are checked when enqueued AND when executed. No URLs,
remote models, publication, arbitrary CLI input, paid APIs or external media.
The output is explicitly an unapproved draft and carries a visible watermark.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import uuid
import wave
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Table, Column, String, Integer, Text, LargeBinary, ForeignKeyConstraint, select, insert, update
from sqlalchemy.exc import IntegrityError

from .domain import Id
from .sa_store import metadata, tenants
from .studio_canvas_c2 import studio_assets, decode_png
from .studio_e1 import StudioError
from .studio_video_e5 import StoryboardStore

MAX_WAV_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_RENDER_SCENES = 4
MAX_RENDER_MILLISECONDS = 20000
FFMPEG_TIMEOUT_SECONDS = 45


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class AttestRights(StrictModel):
    asset_id: Id
    evidence_reference: str = Field(min_length=16, max_length=512)
    expires_at: datetime
    rights_attested: Literal[True]

    @model_validator(mode='after')
    def valid_expiry(self):
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError('STUDIO_RIGHTS_TIMEZONE_REQUIRED')
        if self.expires_at <= datetime.now(timezone.utc):
            raise ValueError('STUDIO_RIGHTS_ALREADY_EXPIRED')
        return self


class UploadAudio(StrictModel):
    data_base64: str = Field(min_length=16, max_length=2_800_000)
    evidence_reference: str = Field(min_length=16, max_length=512)
    expires_at: datetime
    rights_attested: Literal[True]

    @model_validator(mode='after')
    def valid_expiry(self):
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError('STUDIO_RIGHTS_TIMEZONE_REQUIRED')
        if self.expires_at <= datetime.now(timezone.utc):
            raise ValueError('STUDIO_RIGHTS_ALREADY_EXPIRED')
        return self


class SceneFrame(StrictModel):
    scene_id: Id
    asset_id: Id


class QueueDraftVideo(StrictModel):
    job_id: Id
    storyboard_id: Id
    storyboard_version: int = Field(ge=1)
    frames: list[SceneFrame] = Field(min_length=1, max_length=MAX_RENDER_SCENES)
    audio_asset_id: Id | None = None


class RenderJobInfo(StrictModel):
    job_id: Id
    storyboard_id: Id
    storyboard_version: int
    status: Literal['queued', 'running', 'succeeded', 'failed', 'canceled']
    attempts: int
    error_code: str | None
    artifact_id: str | None
    sha256: str | None = None
    draft_only: Literal[True] = True
    production_approved: Literal[False] = False


studio_render_rights = Table('studio_render_rights', metadata,
    Column('tenant_id',String(128),primary_key=True),
    Column('asset_id',String(128),primary_key=True),
    Column('kind',String(12),nullable=False),
    Column('content_sha256',String(64),nullable=False),
    Column('evidence_reference',String(512),nullable=False),
    Column('expires_at',String(48),nullable=False),
    Column('status',String(12),nullable=False),
    Column('attested_by',String(128),nullable=False),
    ForeignKeyConstraint(['tenant_id'],[tenants.c.tenant_id]))

studio_render_rights_events = Table('studio_render_rights_events',metadata,
    Column('event_id',String(36),primary_key=True),
    Column('tenant_id',String(128),nullable=False),
    Column('asset_id',String(128),nullable=False),
    Column('action',String(16),nullable=False),
    Column('actor',String(128),nullable=False),
    Column('at',String(48),nullable=False),
    Column('evidence_reference',String(512),nullable=True),
    Column('content_sha256',String(64),nullable=True),
    ForeignKeyConstraint(['tenant_id','asset_id'],
        ['studio_render_rights.tenant_id','studio_render_rights.asset_id']))


def _rights_event(db,tenant,asset,action,actor,reference=None,digest=None):
    db.execute(insert(studio_render_rights_events).values(event_id=str(uuid.uuid4()),
        tenant_id=tenant,asset_id=asset,action=action,actor=actor,
        at=_now(),evidence_reference=reference,content_sha256=digest))


studio_render_audio = Table('studio_render_audio',metadata,
    Column('tenant_id',String(128),primary_key=True),
    Column('asset_id',String(128),primary_key=True),
    Column('content_sha256',String(64),nullable=False),
    Column('duration_ms',Integer,nullable=False),
    Column('data',LargeBinary,nullable=False),
    ForeignKeyConstraint(['tenant_id'],[tenants.c.tenant_id]))

studio_render_jobs = Table('studio_render_jobs',metadata,
    Column('tenant_id',String(128),primary_key=True),
    Column('job_id',String(128),primary_key=True),
    Column('storyboard_id',String(128),nullable=False),
    Column('storyboard_version',Integer,nullable=False),
    Column('status',String(12),nullable=False),
    Column('attempts',Integer,nullable=False),
    Column('cancel_requested',Integer,nullable=False),
    Column('manifest',Text,nullable=False),
    Column('manifest_sha256',String(64),nullable=False),
    Column('artifact_id',String(128),nullable=True),
    Column('error_code',String(64),nullable=True),
    Column('created_by',String(128),nullable=False),
    Column('created_at',String(48),nullable=False),
    ForeignKeyConstraint(['tenant_id'],[tenants.c.tenant_id]))

studio_render_artifacts = Table('studio_render_artifacts',metadata,
    Column('tenant_id',String(128),primary_key=True),
    Column('artifact_id',String(128),primary_key=True),
    Column('job_id',String(128),nullable=False),
    Column('content_sha256',String(64),nullable=False),
    Column('byte_size',Integer,nullable=False),
    Column('duration_ms',Integer,nullable=False),
    Column('data',LargeBinary,nullable=False),
    ForeignKeyConstraint(['tenant_id','job_id'],
        ['studio_render_jobs.tenant_id','studio_render_jobs.job_id']))

studio_render_events = Table('studio_render_events',metadata,
    Column('event_id',String(36),primary_key=True),
    Column('tenant_id',String(128),nullable=False),
    Column('job_id',String(128),nullable=False),
    Column('action',String(20),nullable=False),
    Column('actor',String(128),nullable=False),
    Column('at',String(48),nullable=False),
    ForeignKeyConstraint(['tenant_id','job_id'],
        ['studio_render_jobs.tenant_id','studio_render_jobs.job_id']))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(db, tenant, job, action, actor):
    db.execute(insert(studio_render_events).values(event_id=str(uuid.uuid4()),
        tenant_id=tenant,job_id=job,action=action,actor=actor,at=_now()))


def _decode_wav(value: str) -> tuple[bytes,int]:
    try:
        raw=base64.b64decode(value,validate=True)
    except (ValueError, binascii.Error) as exc:
        raise StudioError('STUDIO_AUDIO_BAD_BASE64',422) from exc
    if not 44 <= len(raw) <= MAX_WAV_BYTES or raw[:4]!=b'RIFF' or raw[8:12]!=b'WAVE':
        raise StudioError('STUDIO_PCM_WAV_REQUIRED',422)
    if int.from_bytes(raw[4:8],'little')+8!=len(raw):
        raise StudioError('STUDIO_WAV_LENGTH_INVALID',422)
    try:
        with wave.open(io.BytesIO(raw),'rb') as wav:
            if (wav.getcomptype()!='NONE' or wav.getnchannels()!=1 or wav.getsampwidth()!=2
                    or wav.getframerate()!=16000):
                raise StudioError('STUDIO_WAV_PCM16_MONO_16K_REQUIRED',422)
            duration=(wav.getnframes()*1000)//16000
            if not 500 <= duration <= 30000 or wav.getnframes()*2 > MAX_WAV_BYTES:
                raise StudioError('STUDIO_WAV_DURATION_INVALID',422)
            decoded=wav.readframes(wav.getnframes())
            if len(decoded)!=wav.getnframes()*2:
                raise StudioError('STUDIO_WAV_TRUNCATED',422)
    except (wave.Error, EOFError) as exc:
        raise StudioError('STUDIO_WAV_INVALID',422) from exc
    return raw,duration


class LocalDraftRenderer:
    def __init__(self,engine):
        self.engine=engine
        self.storyboards=StoryboardStore(engine)

    def attest_png(self,tenant,actor,payload:AttestRights):
        with self.engine.begin() as db:
            item=db.execute(select(studio_assets.c.sha256).where(
                studio_assets.c.tenant_id==tenant,
                studio_assets.c.asset_id==payload.asset_id)).scalar_one_or_none()
            if not item:raise StudioError('STUDIO_ASSET_NOT_FOUND',404)
            current=db.execute(select(studio_render_rights.c.asset_id).where(
                studio_render_rights.c.tenant_id==tenant,
                studio_render_rights.c.asset_id==payload.asset_id)).scalar_one_or_none()
            record=dict(kind='png',content_sha256=item,
                evidence_reference=payload.evidence_reference,
                expires_at=payload.expires_at.isoformat(),status='attested',attested_by=actor)
            if current:
                db.execute(update(studio_render_rights).where(
                    studio_render_rights.c.tenant_id==tenant,
                    studio_render_rights.c.asset_id==payload.asset_id).values(**record))
            else:
                db.execute(insert(studio_render_rights).values(tenant_id=tenant,
                    asset_id=payload.asset_id,**record))
            _rights_event(db,tenant,payload.asset_id,'attested',actor,payload.evidence_reference,item)
        return {'asset_id':payload.asset_id,'rights_status':'operator_attested_for_local_draft',
                'independently_verified':False}

    def upload_audio(self,tenant,actor,payload:UploadAudio):
        raw,duration=_decode_wav(payload.data_base64)
        digest=sha256(raw).hexdigest();id_='audio.'+digest[:32]
        with self.engine.begin() as db:
            existing=db.execute(select(studio_render_audio.c.asset_id).where(
                studio_render_audio.c.tenant_id==tenant,
                studio_render_audio.c.asset_id==id_)).scalar_one_or_none()
            if not existing:
                db.execute(insert(studio_render_audio).values(tenant_id=tenant,
                    asset_id=id_,content_sha256=digest,duration_ms=duration,data=raw))
            previous=db.execute(select(studio_render_rights.c.asset_id).where(
                studio_render_rights.c.tenant_id==tenant,
                studio_render_rights.c.asset_id==id_)).scalar_one_or_none()
            record=dict(kind='wav',content_sha256=digest,
                evidence_reference=payload.evidence_reference,
                expires_at=payload.expires_at.isoformat(),status='attested',attested_by=actor)
            if previous:
                db.execute(update(studio_render_rights).where(
                    studio_render_rights.c.tenant_id==tenant,
                    studio_render_rights.c.asset_id==id_).values(**record))
            else:
                db.execute(insert(studio_render_rights).values(tenant_id=tenant,
                    asset_id=id_,**record))
            _rights_event(db,tenant,id_,'attested',actor,payload.evidence_reference,digest)
        return {'asset_id':id_,'sha256':digest,'duration_ms':duration,
                'rights_status':'operator_attested_for_local_draft','independently_verified':False}

    def revoke(self,tenant,actor,asset_id):
        with self.engine.begin() as db:
            result=db.execute(update(studio_render_rights).where(
                studio_render_rights.c.tenant_id==tenant,
                studio_render_rights.c.asset_id==asset_id,
                studio_render_rights.c.status=='attested').values(status='revoked'))
            if result.rowcount!=1:raise StudioError('STUDIO_ASSET_RIGHTS_NOT_FOUND_OR_REVOKED',404)
            _rights_event(db,tenant,asset_id,'revoked',actor)
        return {'asset_id':asset_id,'rights_status':'revoked'}

    @staticmethod
    def _active_rights(db,tenant,asset_id,kind):
        rights=db.execute(select(studio_render_rights).where(
            studio_render_rights.c.tenant_id==tenant,
            studio_render_rights.c.asset_id==asset_id,
            studio_render_rights.c.kind==kind)).mappings().first()
        if not rights or rights['status']!='attested' or datetime.fromisoformat(rights['expires_at'])<=datetime.now(timezone.utc):
            raise StudioError('STUDIO_RENDER_RIGHTS_NOT_ACTIVE',403)
        if kind=='png':
            entry=db.execute(select(studio_assets.c.sha256,studio_assets.c.data).where(
                studio_assets.c.tenant_id==tenant,studio_assets.c.asset_id==asset_id)).first()
        else:
            entry=db.execute(select(studio_render_audio.c.content_sha256,studio_render_audio.c.data).where(
                studio_render_audio.c.tenant_id==tenant,studio_render_audio.c.asset_id==asset_id)).first()
        if not entry or entry[0]!=rights['content_sha256'] or sha256(bytes(entry[1])).hexdigest()!=rights['content_sha256']:
            raise StudioError('STUDIO_RENDER_ASSET_INTEGRITY_FAILURE',403)
        return rights['content_sha256'],bytes(entry[1])

    @staticmethod
    def _gates():
        if os.getenv('TAPI_LOCAL_RENDER_ENABLED')!='1':
            raise StudioError('STUDIO_RENDER_DISABLED',403)
        if os.getenv('TAPI_ZERO_BILLING_CONFIRMED')!='1':
            raise StudioError('STUDIO_RENDER_ZERO_BILLING_REQUIRED',403)

    def queue(self,tenant,actor,req:QueueDraftVideo):
        self._gates()
        sb=self.storyboards.get(tenant,req.storyboard_id)
        if sb.version!=req.storyboard_version:
            raise StudioError('STUDIO_STORYBOARD_VERSION_CONFLICT',409)
        if len(sb.scenes)>MAX_RENDER_SCENES or sum(s.duration_ms for s in sb.scenes)>MAX_RENDER_MILLISECONDS:
            raise StudioError('STUDIO_RENDER_LOCAL_PILOT_LIMIT',422)
        names=[f.scene_id for f in req.frames]
        if len(names)!=len(set(names)) or set(names)!={s.scene_id for s in sb.scenes}:
            raise StudioError('STUDIO_RENDER_FRAMES_MUST_COVER_SCENES',422)
        frames={f.scene_id:f.asset_id for f in req.frames}
        with self.engine.begin() as db:
            checks={s.scene_id:{'asset_id':frames[s.scene_id],
                'sha256':self._active_rights(db,tenant,frames[s.scene_id],'png')[0]} for s in sb.scenes}
            audio=None
            if req.audio_asset_id:
                hash_,_=self._active_rights(db,tenant,req.audio_asset_id,'wav')
                audio={'asset_id':req.audio_asset_id,'sha256':hash_}
            manifest={'schema':'studio-render-job.v1','storyboard_id':sb.storyboard_id,
                'version':sb.version,'frames':checks,'audio':audio,
                'duration_ms':sum(s.duration_ms for s in sb.scenes),
                'scene_durations_ms':{s.scene_id:s.duration_ms for s in sb.scenes},
                'draft_only':True}
            raw=json.dumps(manifest,sort_keys=True,separators=(',',':'))
            digest=sha256(raw.encode()).hexdigest()
            try:
                db.execute(insert(studio_render_jobs).values(tenant_id=tenant,job_id=req.job_id,
                    storyboard_id=sb.storyboard_id,storyboard_version=sb.version,status='queued',
                    attempts=0,cancel_requested=0,manifest=raw,manifest_sha256=digest,
                    artifact_id=None,error_code=None,created_by=actor,created_at=_now()))
            except IntegrityError as exc:
                raise StudioError('STUDIO_RENDER_JOB_ALREADY_EXISTS',409) from exc
            _event(db,tenant,req.job_id,'queued',actor)
        return self.get(tenant,req.job_id)

    def get(self,tenant,job_id):
        with self.engine.connect() as db:
            j=db.execute(select(studio_render_jobs).where(
                studio_render_jobs.c.tenant_id==tenant,
                studio_render_jobs.c.job_id==job_id)).mappings().first()
            if not j:raise StudioError('STUDIO_RENDER_JOB_NOT_FOUND',404)
            sha=None
            if j['artifact_id']:
                sha=db.execute(select(studio_render_artifacts.c.content_sha256).where(
                    studio_render_artifacts.c.tenant_id==tenant,
                    studio_render_artifacts.c.artifact_id==j['artifact_id'])).scalar_one_or_none()
        return RenderJobInfo(job_id=j['job_id'],storyboard_id=j['storyboard_id'],
            storyboard_version=j['storyboard_version'],status=j['status'],
            attempts=j['attempts'],error_code=j['error_code'],
            artifact_id=j['artifact_id'],sha256=sha)

    def cancel(self,tenant,actor,job_id):
        with self.engine.begin() as db:
            affected=db.execute(update(studio_render_jobs).where(
                studio_render_jobs.c.tenant_id==tenant,
                studio_render_jobs.c.job_id==job_id,
                studio_render_jobs.c.status.in_(['queued','running'])).values(
                    cancel_requested=1,status='canceled'))
            if affected.rowcount!=1:raise StudioError('STUDIO_RENDER_CANCEL_NOT_ALLOWED',409)
            _event(db,tenant,job_id,'canceled',actor)
        return self.get(tenant,job_id)

    def retry(self,tenant,actor,job_id):
        self._gates()
        with self.engine.begin() as db:
            affected=db.execute(update(studio_render_jobs).where(
                studio_render_jobs.c.tenant_id==tenant,studio_render_jobs.c.job_id==job_id,
                studio_render_jobs.c.status=='failed',studio_render_jobs.c.attempts<2).values(
                    status='queued',error_code=None,cancel_requested=0))
            if affected.rowcount!=1:raise StudioError('STUDIO_RENDER_RETRY_NOT_ALLOWED',409)
            _event(db,tenant,job_id,'retried',actor)
        return self.get(tenant,job_id)

    def artifact(self,tenant,artifact_id):
        with self.engine.connect() as db:
            row=db.execute(select(studio_render_artifacts.c.data,
                studio_render_artifacts.c.content_sha256,
                studio_render_artifacts.c.job_id).where(
                studio_render_artifacts.c.tenant_id==tenant,
                studio_render_artifacts.c.artifact_id==artifact_id)).first()
            if not row:raise StudioError('STUDIO_RENDER_ARTIFACT_NOT_FOUND',404)
            source=db.execute(select(studio_render_jobs.c.manifest).where(
                studio_render_jobs.c.tenant_id==tenant,
                studio_render_jobs.c.job_id==row[2],
                studio_render_jobs.c.status=='succeeded')).scalar_one_or_none()
            if source is None:raise StudioError('STUDIO_RENDER_ARTIFACT_NOT_FOUND',404)
            manifest=json.loads(source)
            # Safe download requires rights to remain active.
            for frame in manifest['frames'].values():
                digest,_=self._active_rights(db,tenant,frame['asset_id'],'png')
                if digest!=frame['sha256']:
                    raise StudioError('STUDIO_RENDER_ASSET_CHANGED',403)
            if manifest['audio']:
                digest,_=self._active_rights(db,tenant,manifest['audio']['asset_id'],'wav')
                if digest!=manifest['audio']['sha256']:
                    raise StudioError('STUDIO_RENDER_AUDIO_CHANGED',403)
        if sha256(bytes(row[0])).hexdigest()!=row[1]:
            raise StudioError('STUDIO_RENDER_ARTIFACT_CORRUPTED',500)
        return bytes(row[0])

    @staticmethod
    def _encode_frames(frames:list[tuple[bytes,int]],audio:bytes | None)->bytes:
        """Runs a fixed ffmpeg argument list with only validated local byte input."""
        try:
            from PIL import Image, ImageDraw
        except ImportError as exc:
            raise StudioError('STUDIO_LOCAL_RENDER_PILLOW_MISSING',503) from exc
        ffmpeg=shutil.which('ffmpeg')
        if ffmpeg is None:
            raise StudioError('STUDIO_FFMPEG_UNAVAILABLE_OR_FAILED',503)
        with tempfile.TemporaryDirectory(prefix='tapi_render_') as folder:
            root=Path(folder);inputs=[]
            for i,(png,duration) in enumerate(frames):
                # Decoder is downstream from strict PNG metadata validation.
                im=Image.open(io.BytesIO(png)); im.load(); im=im.convert('RGB')
                im.thumbnail((360,640))
                canvas=Image.new('RGB',(360,640),'#111111')
                canvas.paste(im,((360-im.width)//2,(640-im.height)//2))
                draw=ImageDraw.Draw(canvas)
                draw.rectangle((0,609,360,640),fill='#111111')
                draw.text((14,616),'RASCUNHO - NAO PUBLICAR',fill='white')
                path=root/f'frame{i}.png';canvas.save(path,'PNG');inputs.append((path,duration))
            total_ms=sum(d for _,d in frames)
            cmd=[ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y',
                '-threads','1','-filter_threads','1']
            for path,duration in inputs:
                cmd+=['-loop','1','-framerate','8','-t',f'{duration/1000:.3f}',
                      '-i',str(path)]
            if audio is not None:
                wav=root/'audio.wav';wav.write_bytes(audio)
                cmd+=['-i',str(wav)]
            segments=';'.join(f'[{i}:v]fps=8,format=yuv420p[v{i}]' for i in range(len(inputs)))
            concat=''.join(f'[v{i}]' for i in range(len(inputs)))
            filt=f'{segments};{concat}concat=n={len(inputs)}:v=1:a=0[v]'
            cmd+=['-filter_complex',filt,'-map','[v]']
            if audio is None:
                cmd+=['-an']
            else:
                cmd+=['-map',f'{len(inputs)}:a:0','-af','apad',
                      '-c:a','aac','-b:a','64k']
            out=root/'draft.mp4'
            cmd+=['-c:v','libx264','-preset','ultrafast','-crf','34',
                '-r','8','-pix_fmt','yuv420p','-t',f'{total_ms/1000:.3f}',
                '-movflags','+faststart',str(out)]
            try:
                subprocess.run(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,timeout=FFMPEG_TIMEOUT_SECONDS,check=True,cwd=root,
                    env={**{k:os.environ[k] for k in
                            ('PATH','SYSTEMROOT','WINDIR','TMP','TEMP') if k in os.environ},
                         'HOME':str(root)})
            except (subprocess.CalledProcessError,subprocess.TimeoutExpired,FileNotFoundError) as exc:
                raise StudioError('STUDIO_FFMPEG_UNAVAILABLE_OR_FAILED',503) from exc
            if not out.is_file() or out.stat().st_size>MAX_OUTPUT_BYTES:
                raise StudioError('STUDIO_RENDER_OUTPUT_SIZE_INVALID',422)
            return out.read_bytes()

    def process_next(self,tenant,actor='local-worker')->RenderJobInfo | None:
        self._gates()
        with self.engine.begin() as db:
            job=db.execute(select(studio_render_jobs).where(
                studio_render_jobs.c.tenant_id==tenant,
                studio_render_jobs.c.status=='queued').order_by(
                    studio_render_jobs.c.created_at,studio_render_jobs.c.job_id).limit(1)).mappings().first()
            if job is None:return None
            claimed=db.execute(update(studio_render_jobs).where(
                studio_render_jobs.c.tenant_id==tenant,
                studio_render_jobs.c.job_id==job['job_id'],
                studio_render_jobs.c.status=='queued').values(
                    status='running',attempts=job['attempts']+1))
            if claimed.rowcount!=1:return None
            _event(db,tenant,job['job_id'],'running',actor)
        error=None;rendered=None
        try:
            manifest=json.loads(job['manifest'])
            if sha256(job['manifest'].encode()).hexdigest()!=job['manifest_sha256']:
                raise StudioError('STUDIO_RENDER_MANIFEST_CORRUPTED',403)
            story=self.storyboards.get(tenant,job['storyboard_id'],job['storyboard_version'])
            if sum(s.duration_ms for s in story.scenes)!=manifest['duration_ms']:
                raise StudioError('STUDIO_RENDER_STORYBOARD_CHANGED',403)
            with self.engine.connect() as db:
                frames=[]
                for scene in story.scenes:
                    record=manifest['frames'][scene.scene_id]
                    digest,raw=self._active_rights(db,tenant,record['asset_id'],'png')
                    if digest!=record['sha256']:
                        raise StudioError('STUDIO_RENDER_ASSET_CHANGED',403)
                    decode_png(base64.b64encode(raw).decode())
                    frames.append((raw,scene.duration_ms))
                audio=None
                if manifest['audio']:
                    digest,audio=self._active_rights(db,tenant,manifest['audio']['asset_id'],'wav')
                    if digest!=manifest['audio']['sha256']:
                        raise StudioError('STUDIO_RENDER_AUDIO_CHANGED',403)
                    _decode_wav(base64.b64encode(audio).decode())
            rendered=self._encode_frames(frames,audio)
        except StudioError as exc:
            error=exc.code
        except Exception:
            error='STUDIO_RENDER_UNEXPECTED_FAILURE'
        with self.engine.begin() as db:
            current=db.execute(select(studio_render_jobs.c.status).where(
                studio_render_jobs.c.tenant_id==tenant,
                studio_render_jobs.c.job_id==job['job_id'])).scalar_one()
            if current=='canceled':return self.get(tenant,job['job_id'])
            if current!='running':raise StudioError('STUDIO_RENDER_JOB_STATE_CHANGED',409)
            # Revoke/expiry may happen while FFmpeg runs. Never commit a new
            # artifact after either grant changed during the render.
            if rendered is not None:
                try:
                    for record in manifest['frames'].values():
                        digest,_=self._active_rights(db,tenant,record['asset_id'],'png')
                        if digest!=record['sha256']:
                            raise StudioError('STUDIO_RENDER_ASSET_CHANGED',403)
                    if manifest['audio']:
                        digest,_=self._active_rights(db,tenant,manifest['audio']['asset_id'],'wav')
                        if digest!=manifest['audio']['sha256']:
                            raise StudioError('STUDIO_RENDER_AUDIO_CHANGED',403)
                except StudioError as exc:
                    rendered=None;error=exc.code
            if rendered is not None:
                digest=sha256(rendered).hexdigest();artifact_id='video.'+digest[:32]
                existing=db.execute(select(studio_render_artifacts.c.artifact_id).where(
                    studio_render_artifacts.c.tenant_id==tenant,
                    studio_render_artifacts.c.artifact_id==artifact_id)).scalar_one_or_none()
                if existing:artifact_id='video.'+str(uuid.uuid4())
                db.execute(insert(studio_render_artifacts).values(tenant_id=tenant,
                    artifact_id=artifact_id,job_id=job['job_id'],content_sha256=digest,
                    byte_size=len(rendered),duration_ms=manifest['duration_ms'],data=rendered))
                db.execute(update(studio_render_jobs).where(
                    studio_render_jobs.c.tenant_id==tenant,studio_render_jobs.c.job_id==job['job_id']).values(
                    status='succeeded',artifact_id=artifact_id,error_code=None))
                _event(db,tenant,job['job_id'],'succeeded',actor)
            else:
                db.execute(update(studio_render_jobs).where(
                    studio_render_jobs.c.tenant_id==tenant,studio_render_jobs.c.job_id==job['job_id']).values(
                    status='failed',error_code=error or 'STUDIO_RENDER_FAILED'))
                _event(db,tenant,job['job_id'],'failed',actor)
        return self.get(tenant,job['job_id'])
