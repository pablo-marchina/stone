"""CAP-023: tenant-scoped draft library with historical provenance summary."""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select, and_
from .domain import Id
from .studio_e1 import DesignDocument, StudioError, studio_documents, studio_versions
from .sa_store import domain_events, outbox


class DraftSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: Id
    version: int = Field(ge=1)
    title: str = Field(max_length=120)
    pages: int = Field(ge=1, le=10)
    platform_intent: Literal["instagram_feed", "instagram_carousel"]
    approval_status: Literal["draft"] = "draft"
    reference_status: Literal["unverified"] = "unverified"
    rights_status: Literal["pending_review"] = "pending_review"
    historical_provenance: Literal["not_recorded", "recorded", "invalid"]
    historical_reference_count: int | None = Field(default=None, ge=0, le=30)
    hypothesis: Literal["vendas"] | None = None
    current_source_scope_verified: Literal[False] = False
    scientifically_validated: Literal[False] = False
    publication_approved: Literal[False] = False


class DraftLibraryPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["studio-draft-library.v1"] = "studio-draft-library.v1"
    items: list[DraftSummary] = Field(max_length=50)
    next_after: Id | None = None


def _historical(db, tenant, doc):
    # A historical receipt is not a current grant or a scientific review.
    from .discovery_studio_handoff import AGG, EVENT, VERSION
    from .discovery_caption_research import digest
    rows = db.execute(select(domain_events.c.payload, domain_events.c.event_type,
                             domain_events.c.aggregate_version, outbox.c.seq)
                      .outerjoin(outbox, outbox.c.seq == domain_events.c.seq)
                      .where(domain_events.c.tenant_id == tenant,
                             domain_events.c.aggregate_type == AGG,
                             domain_events.c.aggregate_id == doc.document_id)).mappings().all()
    if not rows:
        return ("invalid" if doc.document_id.startswith("draft.exploratory.") else "not_recorded", None, None)
    if len(rows) != 1:
        return "invalid", None, None
    try:
        row = rows[0]
        p = json.loads(row["payload"])
        refs = [r["content_id"] for r in p["references"]]
        initial_blob = db.execute(select(studio_versions.c.payload).where(
            studio_versions.c.tenant_id == tenant,
            studio_versions.c.document_id == doc.document_id,
            studio_versions.c.version == 1)).scalar_one_or_none()
        initial = DesignDocument.model_validate_json(initial_blob)
        if (row["event_type"] != EVENT or row["aggregate_version"] != 1 or row["seq"] is None
                or p["policy_version"] != VERSION or p["scientifically_validated"] is not False
                or p["publication_approved"] is not False or p["authored_template"] is not True
                or p["hypothesis"] != {"field":"topic","value":"vendas"}
                or doc.document_id != "draft.exploratory."+digest(p)[:32]
                or initial.document_id != doc.document_id or initial.tenant_id != tenant
                or initial.reference_content_ids != refs or doc.reference_content_ids != refs
                or not refs or len(refs) != len(set(refs))):
            return "invalid", None, None
        return "recorded", len(refs), "vendas"
    except (ValueError, TypeError, KeyError, ValidationError):
        return "invalid", None, None


def list_drafts(engine, tenant: str, *, limit: int = 20, after: str | None = None) -> DraftLibraryPage:
    if not 1 <= limit <= 50:
        raise StudioError("STUDIO_LIBRARY_INVALID_LIMIT",422)
    join = studio_documents.outerjoin(studio_versions, and_(
        studio_versions.c.tenant_id == studio_documents.c.tenant_id,
        studio_versions.c.document_id == studio_documents.c.document_id,
        studio_versions.c.version == studio_documents.c.current_version))
    stmt = select(studio_documents.c.document_id, studio_documents.c.current_version,
                  studio_versions.c.payload).select_from(join).where(studio_documents.c.tenant_id == tenant)
    if after is not None:
        stmt = stmt.where(studio_documents.c.document_id > after)
    with engine.connect() as db:
        rows = db.execute(stmt.order_by(studio_documents.c.document_id).limit(limit+1)).mappings().all()
        items = []
        for row in rows[:limit]:
            try:
                doc = DesignDocument.model_validate_json(row["payload"])
            except (ValueError, TypeError, ValidationError) as exc:
                raise StudioError("STUDIO_LIBRARY_INVALID_REVISION",409) from exc
            if doc.tenant_id != tenant or doc.document_id != row["document_id"] or doc.version != row["current_version"]:
                raise StudioError("STUDIO_LIBRARY_INVALID_REVISION",409)
            state, count, hypothesis = _historical(db,tenant,doc)
            layers = [layer for layer in doc.pages[0].layers if layer.kind=="text"]
            title = next((layer.text for layer in layers if layer.id in ("headline","main")),
                         layers[0].text if layers else doc.document_id)
            items.append(DraftSummary(document_id=doc.document_id,version=doc.version,
                                      title=title[:120],pages=len(doc.pages),platform_intent=doc.platform_intent,
                                      historical_provenance=state,historical_reference_count=count,
                                      hypothesis=hypothesis))
    return DraftLibraryPage(items=items,next_after=items[-1].document_id if len(rows)>limit else None)
