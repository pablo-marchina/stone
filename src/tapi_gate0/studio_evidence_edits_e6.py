"""Evidence-bound editing: source and snapshot are real persisted tenant data.

This mechanism does not assert scientific validity, copyright, causal impact or
approval. The operator explicitly reviews a deterministic diff before a
transactional versioned write and audit event. No LLM or remote calls.
"""
from __future__ import annotations

from hashlib import sha256
import json
from uuid import uuid4
from datetime import datetime, timezone

from typing import Literal
from pydantic import ConfigDict, Field
from sqlalchemy import Table, Column, String, Integer, ForeignKeyConstraint, select, insert, update

from .domain import Id, ContentItem, Creator, MetricsCreate
from .sa_store import metadata, content_items, creators, metrics_snapshots
from .studio_e1 import StudioError, DesignDocument, StudioStore, studio_documents, studio_versions
from .studio_e4 import ProposedTextEdit, _proposed_patch, studio_etag, assert_etag


class EvidenceEditProposal(ProposedTextEdit):
    model_config=ConfigDict(extra='forbid')
    reference_content_id: Id
    reference_snapshot_id: Id


class ConfirmEvidenceEdit(EvidenceEditProposal):
    preview_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    operator_confirmed: Literal[True]


studio_evidence_edit_events=Table('studio_evidence_edit_events',metadata,
    Column('event_id',String(36),primary_key=True),
    Column('tenant_id',String(128),nullable=False),
    Column('document_id',String(128),nullable=False),
    Column('document_version',Integer,nullable=False),
    Column('content_id',String(128),nullable=False),
    Column('snapshot_id',String(128),nullable=False),
    Column('snapshot_sha256',String(64),nullable=False),
    Column('preview_sha256',String(64),nullable=False),
    Column('operator_id',String(128),nullable=False),
    Column('created_at',String(48),nullable=False),
    ForeignKeyConstraint(['tenant_id','document_id','document_version'],
        ['studio_document_versions.tenant_id','studio_document_versions.document_id','studio_document_versions.version']))


class StudioEvidenceEditService:
    def __init__(self,engine):
        self.engine=engine;self.docs=StudioStore(engine)

    @staticmethod
    def _evidence(db, tenant, doc, proposal):
        """Validate *both* SQL keys and serialized evidence before an edit.

        A tenant-scoped SELECT alone is insufficient: persisted payloads may
        be corrupted, relabeled or inconsistent with their indexed rows.
        Metadata is descriptive evidence, NEVER a creative-use rights grant.
        """
        if proposal.reference_content_id not in doc.reference_content_ids:
            raise StudioError('STUDIO_EVIDENCE_NOT_IN_DOCUMENT_REFERENCES', 403)
        row = db.execute(select(
            content_items.c.creator_id, content_items.c.origin,
            content_items.c.published_at, content_items.c.payload,
        ).where(
            content_items.c.tenant_id == tenant,
            content_items.c.id == proposal.reference_content_id,
        )).one_or_none()
        if row is None:
            raise StudioError('STUDIO_EVIDENCE_CONTENT_NOT_FOUND', 404)
        try:
            content = ContentItem.model_validate_json(row.payload)
            if (content.tenant_id != tenant
                    or content.content_id != proposal.reference_content_id
                    or content.creator_id != row.creator_id
                    or content.origin.value != row.origin
                    or content.published_at != datetime.fromisoformat(row.published_at)):
                raise StudioError('STUDIO_EVIDENCE_CONTENT_BINDING_INVALID', 409)
        except (ValueError, TypeError, AttributeError):
            raise StudioError('STUDIO_EVIDENCE_CONTENT_PAYLOAD_INVALID', 409) from None

        creator_row = db.execute(select(
            creators.c.origin, creators.c.payload,
        ).where(
            creators.c.tenant_id == tenant,
            creators.c.id == content.creator_id,
        )).one_or_none()
        if creator_row is None:
            raise StudioError('STUDIO_EVIDENCE_CREATOR_NOT_FOUND', 409)
        try:
            creator = Creator.model_validate_json(creator_row.payload)
            if (creator.tenant_id != tenant
                    or creator.creator_id != content.creator_id
                    or creator.origin != content.origin
                    or creator.origin.value != creator_row.origin):
                raise StudioError('STUDIO_EVIDENCE_CREATOR_BINDING_INVALID', 409)
        except (ValueError, TypeError, AttributeError):
            raise StudioError('STUDIO_EVIDENCE_CREATOR_PAYLOAD_INVALID', 409) from None

        if content.is_synthetic:
            raise StudioError('STUDIO_EVIDENCE_SYNTHETIC_NOT_ALLOWED', 403)
        snap_row = db.execute(select(
            metrics_snapshots.c.observed_at, metrics_snapshots.c.payload,
        ).where(
            metrics_snapshots.c.tenant_id == tenant,
            metrics_snapshots.c.id == proposal.reference_snapshot_id,
            metrics_snapshots.c.content_id == proposal.reference_content_id,
        )).one_or_none()
        if snap_row is None:
            raise StudioError('STUDIO_EVIDENCE_SNAPSHOT_NOT_FOUND', 404)
        try:
            snap = MetricsCreate.model_validate_json(snap_row.payload)
            if (snap.tenant_id != tenant
                    or snap.content_id != proposal.reference_content_id
                    or snap.snapshot_id != proposal.reference_snapshot_id
                    or snap.observed_at != datetime.fromisoformat(snap_row.observed_at)
                    or snap.observed_at < content.published_at):
                raise StudioError('STUDIO_EVIDENCE_SNAPSHOT_BINDING_INVALID', 409)
        except (ValueError, TypeError, AttributeError):
            raise StudioError('STUDIO_EVIDENCE_SNAPSHOT_PAYLOAD_INVALID', 409) from None
        return {
            'source_url': str(content.source_url) if content.source_url else None,
            'snapshot_observed_at': snap.observed_at.isoformat(),
            'snapshot_sha256': sha256(snap_row.payload.encode()).hexdigest(),
        }

    @staticmethod
    def _digest(doc,proposal,evidence):
        _,patch_digest=_proposed_patch(doc,proposal)
        return sha256(json.dumps({
            'patch_sha256':patch_digest,'snapshot_sha256':evidence['snapshot_sha256'],
            'content_id':proposal.reference_content_id,
            'snapshot_id':proposal.reference_snapshot_id},
            sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def preview(self,tenant,document_id,proposal:EvidenceEditProposal):
        doc=self.docs.get(tenant,document_id)
        with self.engine.connect() as db:
            evidence=self._evidence(db,tenant,doc,proposal)
        candidate,digest=_proposed_patch(doc,proposal)
        from .studio_e4 import _flatten
        before=dict(_flatten(doc.model_dump(mode='json')))
        proposed=dict(_flatten(candidate))
        return {'document_id':doc.document_id,'base_version':doc.version,
            'base_etag':studio_etag(doc),'preview_sha256':self._digest(doc,proposal,evidence),
            'reference_content_id':proposal.reference_content_id,
            'reference_snapshot_id':proposal.reference_snapshot_id,
            'source_url':evidence['source_url'],
            'snapshot_sha256':evidence['snapshot_sha256'],
            'snapshot_observed_at':evidence['snapshot_observed_at'],
            'descriptive_evidence_only':True,'scientifically_validated':False,
            'production_approved':False,'requires_operator_confirmation':True,
            'changes':[{'path':k,'before':before.get(k),'after':proposed.get(k)}
              for k in sorted(before.keys()|proposed.keys()) if before.get(k)!=proposed.get(k)]}

    def apply(self,tenant,actor,document_id,proposal:ConfirmEvidenceEdit,if_match:str|None):
        with self.engine.begin() as db:
            current=db.execute(select(studio_documents.c.current_version).where(
                studio_documents.c.tenant_id==tenant,
                studio_documents.c.document_id==document_id)).scalar_one_or_none()
            if current is None:raise StudioError('STUDIO_DOCUMENT_NOT_FOUND',404)
            raw=db.execute(select(studio_versions.c.payload).where(
                studio_versions.c.tenant_id==tenant,
                studio_versions.c.document_id==document_id,
                studio_versions.c.version==current)).scalar_one()
            doc=DesignDocument.model_validate_json(raw)
            assert_etag(doc,if_match,proposal.expected_version)
            evidence=self._evidence(db,tenant,doc,proposal)
            digest=self._digest(doc,proposal,evidence)
            if digest!=proposal.preview_sha256:
                raise StudioError('STUDIO_EVIDENCE_PREVIEW_CHANGED',409)
            proposed,_=_proposed_patch(doc,proposal)
            new=DesignDocument.model_validate(proposed)
            updated=db.execute(update(studio_documents).where(
                studio_documents.c.tenant_id==tenant,
                studio_documents.c.document_id==document_id,
                studio_documents.c.current_version==current).values(current_version=current+1))
            if updated.rowcount!=1:
                raise StudioError('STUDIO_VERSION_CONFLICT',409)
            StudioStore._insert_version(db,new,actor)
            db.execute(insert(studio_evidence_edit_events).values(event_id=str(uuid4()),
                tenant_id=tenant,document_id=document_id,document_version=new.version,
                content_id=proposal.reference_content_id,
                snapshot_id=proposal.reference_snapshot_id,
                snapshot_sha256=evidence['snapshot_sha256'],preview_sha256=digest,
                operator_id=actor,created_at=datetime.now(timezone.utc).isoformat()))
        return new
