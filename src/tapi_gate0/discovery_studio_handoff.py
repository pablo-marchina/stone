"""CAP-023: authenticated local draft handoff, not rights or publication approval."""
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import select, insert, update
from .connectors import ConnectorError
from .domain import ContentItem, MetricsCreate
from .discovery_caption_research import _idle, _rows, digest
from .discovery_history import lock_tenant
from .ingestion import source_grants
from .sa_store import content_items, metrics_snapshots, domain_events, outbox
from .storage import now_utc
from .studio_e1 import (CreativeSpec, DesignDocument, Canvas, DesignPage, TextLayer,
                        TextStyle, StudioStore, studio_documents, studio_versions)

VERSION = "bd-exploratory-studio-handoff.v1"
AGG = "bd_exploratory_studio_draft"
EVENT = "studio.exploratory_draft_created"


def prepare_drafts(preview, tenant):
    """Transform only internally regenerated agent preview, not arbitrary report text."""
    if (preview["confidence_flag"] != "EXPLORATORY_NOT_INDEPENDENTLY_VALIDATED"
            or preview["scientifically_validated"] is not False
            or preview["publication_approved"] is not False
            or preview["scientific_admissions"] != 0):
        raise ValueError("BD_STUDIO_PREVIEW_SCOPE_MISMATCH")
    refs = {r["content_id"]:r for r in preview["reference_posts"]}
    if len(refs) != len(preview["reference_posts"]):
        raise ValueError("BD_STUDIO_DUPLICATE_REFERENCE")
    drafts = []
    for creative in preview["creatives"]:
        spec = CreativeSpec.model_validate(creative["creative_spec"])
        if (spec.tenant_id != tenant or spec.platform_intent != "instagram_carousel"
                or creative["status"] != "draft_hypothesis_not_approved"
                or creative["format_and_cta_are_design_choices"] is not True
                or (creative["hypothesis_field"], creative["hypothesis_value"]) != ("topic","vendas")
                or not spec.reference_content_ids or not set(spec.reference_content_ids).issubset(refs)):
            raise ValueError("BD_STUDIO_SPEC_SCOPE_MISMATCH")
        finding = next((f for f in preview["findings"] if f["field"] == "topic"
                        and f["value"] == "vendas"), None)
        if not finding or finding["reference_content_ids"] != spec.reference_content_ids:
            raise ValueError("BD_STUDIO_HYPOTHESIS_MISMATCH")
        evidence = [refs[cid] for cid in spec.reference_content_ids]
        provenance = {"policy_version":VERSION,"manifest_sha256":preview["manifest_sha256"],
                      "creative_spec_sha256":digest(spec.model_dump(mode="json")),
                      "hypothesis":{"field":"topic","value":"vendas"},
                      "references":evidence,"scientifically_validated":False,
                      "publication_approved":False,"authored_template":True,
                      "format_and_cta_are_design_choices":True}
        document_id = "draft.exploratory."+digest(provenance)[:32]
        def page(num, text, size, y, h):
            return DesignPage(id="page."+str(num),layers=[
                TextLayer(id="eyebrow",x=80,y=85,w=920,h=100,text="EDUCAÇÃO EMPREENDEDORA",
                          style=TextStyle(font_size=32,color="#146C50")),
                TextLayer(id="main",x=80,y=y,w=920,h=h,text=text,
                          style=TextStyle(font_size=size,color="#172B25")),
                TextLayer(id="footer",x=80,y=1200,w=920,h=65,text=f"RASCUNHO  •  {num}/3",
                          style=TextStyle(font_size=25,color="#49645A")),
            ])
        document = DesignDocument(document_id=document_id,tenant_id=tenant,
            spec_id=spec.spec_id,version=1,canvas=Canvas(background="#F6FAF7"),
            platform_intent=spec.platform_intent,
            pages=[page(1,spec.headline,72,320,650),page(2,spec.body,54,270,780),
                   page(3,spec.cta,64,350,600)],reference_content_ids=spec.reference_content_ids)
        drafts.append((document,provenance))
    if len(drafts) > 5 or len({d.document_id for d,_ in drafts}) != len(drafts):
        raise ValueError("BD_STUDIO_DRAFT_PARTITION_MISMATCH")
    return drafts


def _scope_in_transaction(db, tenant, manifest, viewer):
    lock_tenant(db, tenant)
    _idle(db, tenant)
    rows = _rows(db, tenant, manifest, viewer, now_utc())
    if not rows or any(a != "ALREADY_PROVISIONED" for _,a,_ in rows):
        raise ConnectorError("BD_CONTEXTUAL_CLASSIFICATION_SCOPE_BLOCKED",403)
    for s,_,_ in sorted(rows,key=lambda x:x[0].expected_ig_id):
        result = db.execute(update(source_grants).where(
            source_grants.c.tenant_id==tenant, source_grants.c.platform=="instagram",
            source_grants.c.source_account_id==s.expected_ig_id).values(enabled=source_grants.c.enabled))
        if result.rowcount != 1:
            raise ConnectorError("BD_STUDIO_GRANT_CHANGED",409)
    if any(a != "ALREADY_PROVISIONED" for _,a,_ in _rows(db,tenant,manifest,viewer,now_utc())):
        raise ConnectorError("BD_CONTEXTUAL_CLASSIFICATION_SCOPE_BLOCKED",403)


def _validate_refs(db, tenant, drafts):
    for _, provenance in drafts:
        for r in provenance["references"]:
            cid, sid = r["content_id"],r["snapshot_id"]
            blob = db.execute(select(content_items.c.payload).where(
                content_items.c.tenant_id==tenant,content_items.c.id==cid)).scalar_one_or_none()
            snap = db.execute(select(metrics_snapshots.c.payload).where(
                metrics_snapshots.c.tenant_id==tenant,metrics_snapshots.c.content_id==cid,
                metrics_snapshots.c.id==sid)).scalar_one_or_none()
            if blob is None or snap is None:
                raise ConnectorError("BD_STUDIO_REFERENCE_CHANGED",409)
            post,metric = ContentItem.model_validate_json(blob),MetricsCreate.model_validate_json(snap)
            from fractions import Fraction
            if (post.tenant_id!=tenant or post.content_id!=cid or post.is_synthetic
                    or post.origin!="instagram" or not post.caption
                    or sha256(post.caption.encode()).hexdigest()!=r["caption_sha256"]
                    or metric.tenant_id!=tenant or metric.content_id!=cid or metric.snapshot_id!=sid
                    or metric.follower_count<=0 or str(Fraction(metric.likes+metric.comments,metric.follower_count))!=r["er_fraction"]):
                raise ConnectorError("BD_STUDIO_REFERENCE_CHANGED",409)


def persist_drafts(engine, principal, manifest, viewer, drafts, *, stopped):
    """Single SQLite transaction; preserve current edits, verify initial revision."""
    if principal.role!="admin" or not stopped or engine.dialect.name!="sqlite":
        raise ConnectorError("BD_STUDIO_LOCAL_ADMIN_STOP_REQUIRED",403)
    tenant=principal.tenant_id
    if any(d.tenant_id!=tenant or p["manifest_sha256"]!=manifest.fingerprint() for d,p in drafts):
        raise ConnectorError("BD_STUDIO_TENANT_SCOPE_MISMATCH",403)
    receipts=[]
    if not drafts:
        return receipts
    with engine.begin() as db:
        _scope_in_transaction(db,tenant,manifest,viewer)
        _validate_refs(db,tenant,drafts)
        for doc,provenance in drafts:
            key=(studio_documents.c.tenant_id==tenant,studio_documents.c.document_id==doc.document_id)
            current=db.execute(select(studio_documents.c.current_version).where(*key)).scalar_one_or_none()
            event_key=(domain_events.c.tenant_id==tenant,domain_events.c.aggregate_type==AGG,
                       domain_events.c.aggregate_id==doc.document_id)
            prior=db.execute(select(domain_events.c.payload,domain_events.c.event_type,domain_events.c.aggregate_version,
                                     outbox.c.seq).outerjoin(outbox,outbox.c.seq==domain_events.c.seq)
                             .where(*event_key)).mappings().all()
            if current is not None:
                initial=db.execute(select(studio_versions.c.payload).where(
                    studio_versions.c.tenant_id==tenant,studio_versions.c.document_id==doc.document_id,
                    studio_versions.c.version==1)).scalar_one_or_none()
                if (not initial or DesignDocument.model_validate_json(initial)!=doc or len(prior)!=1
                        or prior[0]["event_type"]!=EVENT or prior[0]["aggregate_version"]!=1
                        or prior[0]["seq"] is None or json.loads(prior[0]["payload"])!=provenance):
                    raise ConnectorError("BD_STUDIO_EXISTING_DRAFT_CONFLICT",409)
                receipts.append({"document_id":doc.document_id,"current_version":current,"action":"REUSED","pages":len(doc.pages)})
                continue
            if prior:
                raise ConnectorError("BD_STUDIO_EXISTING_DRAFT_CONFLICT",409)
            db.execute(insert(studio_documents).values(tenant_id=tenant,document_id=doc.document_id,
                                                       spec_id=doc.spec_id,current_version=1))
            StudioStore._insert_version(db,doc,principal.actor_id)
            seq=db.execute(insert(domain_events).values(event_id=str(uuid4()),tenant_id=tenant,
                aggregate_type=AGG,aggregate_id=doc.document_id,aggregate_version=1,
                event_type=EVENT,occurred_at=now_utc().isoformat(),
                payload=json.dumps(provenance,sort_keys=True,ensure_ascii=False))).inserted_primary_key[0]
            db.execute(insert(outbox).values(seq=seq,attempts=0,dead_letter=0))
            receipts.append({"document_id":doc.document_id,"current_version":1,"action":"CREATED","pages":len(doc.pages)})
    return receipts
