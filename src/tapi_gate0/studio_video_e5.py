"""CAP-023 / IMP-187/188: durable, text-only Reel/Short storyboard and timeline.

No video/audio asset processing, renderer, publication, external URLs, model
inference or source download. The document source, tenant and revision are
verified at creation; every later change creates an immutable version.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from sqlalchemy import Table, Column, String, Integer, Text, ForeignKeyConstraint, select, insert, update
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, ConfigDict, Field, model_validator, ValidationError

from .domain import Id
from .sa_store import metadata
from .studio_e1 import StudioError, StudioStore, studio_documents


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OverlayKeyframe(Model):
    at_ms: int = Field(ge=0, le=180_000)
    x: int = Field(default=100, ge=0, le=1000)
    y: int = Field(default=100, ge=0, le=1000)
    opacity: int = Field(default=100, ge=0, le=100)


class TextOverlay(Model):
    text: str = Field(min_length=1, max_length=500)
    start_ms: int = Field(default=0, ge=0)
    end_ms: int = Field(default=2000, ge=1)
    keyframes: list[OverlayKeyframe] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def valid_timing(self):
        if self.start_ms >= self.end_ms:
            raise ValueError("STORYBOARD_OVERLAY_TIME_INVALID")
        positions=[key.at_ms for key in self.keyframes]
        if positions!=sorted(set(positions)) or any(x<self.start_ms or x>self.end_ms for x in positions):
            raise ValueError("STORYBOARD_KEYFRAMES_INVALID")
        return self


class StoryScene(Model):
    scene_id: Id
    duration_ms: int = Field(default=5000, ge=500, le=30_000)
    narration: str = Field(min_length=1, max_length=1000)
    overlays: list[TextOverlay] = Field(default_factory=list, max_length=12)
    visual_note: str = Field(default="Storyboard textual. Sem mídia autorizada vinculada.",max_length=500)

    @model_validator(mode="after")
    def overlays_inside_scene(self):
        if any(item.end_ms>self.duration_ms for item in self.overlays):
            raise ValueError("STORYBOARD_OVERLAY_BEYOND_SCENE")
        return self


class TimelineClip(Model):
    scene_id: Id
    start_ms: int = Field(ge=0, le=180_000)
    duration_ms: int = Field(ge=500, le=30_000)
    transition: Literal["cut"] = "cut"


class StoryboardDocument(Model):
    schema_version: Literal["studio-storyboard.v1"] = "studio-storyboard.v1"
    storyboard_id: Id
    tenant_id: Id
    source_document_id: Id
    source_document_version: int = Field(ge=1)
    version: int = Field(ge=1)
    platform_intent: Literal["instagram_reel", "youtube_short"]
    canvas_width: Literal[1080] = 1080
    canvas_height: Literal[1920] = 1920
    scenes: list[StoryScene] = Field(min_length=1, max_length=12)
    clips: list[TimelineClip] = Field(min_length=1, max_length=12)
    audio_status: Literal["not_implemented"] = "not_implemented"
    render_status: Literal["not_implemented"] = "not_implemented"
    rights_status: Literal["pending_review"] = "pending_review"
    approval_status: Literal["draft"] = "draft"

    @model_validator(mode="after")
    def enforce_timeline(self):
        names=[s.scene_id for s in self.scenes]
        if len(names)!=len(set(names)):
            raise ValueError("STORYBOARD_DUPLICATE_SCENE")
        clips=[c.scene_id for c in self.clips]
        if len(clips)!=len(set(clips)) or set(clips)!=set(names):
            raise ValueError("STORYBOARD_TIMELINE_MUST_COVER_SCENES")
        durations={s.scene_id:s.duration_ms for s in self.scenes}
        elapsed=0
        for clip in self.clips:
            if clip.start_ms!=elapsed or clip.duration_ms!=durations[clip.scene_id]:
                raise ValueError("STORYBOARD_TIMELINE_GAP_OVERLAP_OR_DURATION")
            elapsed+=clip.duration_ms
        if elapsed>180_000:
            raise ValueError("STORYBOARD_MAX_DURATION_EXCEEDED")
        return self


class CreateStoryboard(Model):
    storyboard_id: Id
    source_document_id: Id
    platform_intent: Literal["instagram_reel", "youtube_short"]


class UpdateStoryboard(Model):
    expected_version: int = Field(ge=1)
    scenes: list[StoryScene] = Field(min_length=1,max_length=12)
    clips: list[TimelineClip] = Field(min_length=1,max_length=12)


storyboards=Table("studio_storyboards",metadata,
    Column("tenant_id",String(128),primary_key=True),
    Column("storyboard_id",String(128),primary_key=True),
    Column("source_document_id",String(128),nullable=False),
    Column("current_version",Integer,nullable=False),
    ForeignKeyConstraint(["tenant_id","source_document_id"],
        ["studio_documents.tenant_id","studio_documents.document_id"]))
storyboard_versions=Table("studio_storyboard_versions",metadata,
    Column("tenant_id",String(128),primary_key=True),
    Column("storyboard_id",String(128),primary_key=True),
    Column("version",Integer,primary_key=True),
    Column("payload",Text,nullable=False),
    Column("edited_by",String(128),nullable=False),
    Column("created_at",String(48),nullable=False),
    ForeignKeyConstraint(["tenant_id","storyboard_id"],
       ["studio_storyboards.tenant_id","studio_storyboards.storyboard_id"]))


class StoryboardStore:
    def __init__(self,engine):self.engine=engine;self.docs=StudioStore(engine)

    @staticmethod
    def _insert(db,doc,actor):
        db.execute(insert(storyboard_versions).values(
            tenant_id=doc.tenant_id,storyboard_id=doc.storyboard_id,version=doc.version,
            payload=doc.model_dump_json(),edited_by=actor,
            created_at=datetime.now(timezone.utc).isoformat()))

    def create(self,tenant,actor,payload:CreateStoryboard):
        # Source is an existing local draft, never a remote URL or unverified ID.
        source=self.docs.get(tenant,payload.source_document_id)
        scenes=[]
        for i,page in enumerate(source.pages):
            texts=[layer.text for layer in page.layers if layer.kind=='text']
            note=(texts[0] if texts else f'Cena {i+1}')[:1000]
            scenes.append(StoryScene(scene_id=f'scene.{i+1}',narration=note,
                overlays=[TextOverlay(text=note[:500],start_ms=0,end_ms=3000)]))
        clips=[];elapsed=0
        for scene in scenes:
            clips.append(TimelineClip(scene_id=scene.scene_id,start_ms=elapsed,duration_ms=scene.duration_ms))
            elapsed+=scene.duration_ms
        doc=StoryboardDocument(storyboard_id=payload.storyboard_id,tenant_id=tenant,
            source_document_id=source.document_id,source_document_version=source.version,
            version=1,platform_intent=payload.platform_intent,scenes=scenes,clips=clips)
        try:
            with self.engine.begin() as db:
                db.execute(insert(storyboards).values(tenant_id=tenant,
                    storyboard_id=doc.storyboard_id,source_document_id=doc.source_document_id,
                    current_version=1))
                self._insert(db,doc,actor)
        except IntegrityError as exc:
            raise StudioError('STORYBOARD_ALREADY_EXISTS_OR_BAD_SOURCE',409) from exc
        return doc

    def get(self,tenant,storyboard_id,version=None):
        with self.engine.connect() as db:
            if version is None:
                version=db.execute(select(storyboards.c.current_version).where(
                  storyboards.c.tenant_id==tenant,storyboards.c.storyboard_id==storyboard_id)).scalar_one_or_none()
            if version is None:raise StudioError('STORYBOARD_NOT_FOUND',404)
            raw=db.execute(select(storyboard_versions.c.payload).where(
                storyboard_versions.c.tenant_id==tenant,
                storyboard_versions.c.storyboard_id==storyboard_id,
                storyboard_versions.c.version==version)).scalar_one_or_none()
            if raw is None:raise StudioError('STORYBOARD_VERSION_NOT_FOUND',404)
        return StoryboardDocument.model_validate_json(raw)

    def update(self,tenant,actor,storyboard_id,payload:UpdateStoryboard):
        with self.engine.begin() as db:
            current=db.execute(select(storyboards.c.current_version).where(
                storyboards.c.tenant_id==tenant,storyboards.c.storyboard_id==storyboard_id)).scalar_one_or_none()
            if current is None:raise StudioError('STORYBOARD_NOT_FOUND',404)
            if current!=payload.expected_version:raise StudioError('STORYBOARD_VERSION_CONFLICT',409)
            original=db.execute(select(storyboard_versions.c.payload).where(
                storyboard_versions.c.tenant_id==tenant,
                storyboard_versions.c.storyboard_id==storyboard_id,
                storyboard_versions.c.version==current)).scalar_one()
            new=StoryboardDocument.model_validate_json(original).model_copy(update={
                'version':current+1,'scenes':payload.scenes,'clips':payload.clips,
                'approval_status':'draft','rights_status':'pending_review'})
            # Pydantic model_copy bypasses validation; re-validate explicitly.
            try:
                new=StoryboardDocument.model_validate(new.model_dump())
            except ValidationError as exc:
                raise StudioError('STORYBOARD_INVALID_TIMELINE',422) from exc
            changed=db.execute(update(storyboards).where(
                storyboards.c.tenant_id==tenant,storyboards.c.storyboard_id==storyboard_id,
                storyboards.c.current_version==current).values(current_version=current+1))
            if changed.rowcount!=1:raise StudioError('STORYBOARD_VERSION_CONFLICT',409)
            self._insert(db,new,actor)
        return new
