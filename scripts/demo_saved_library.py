"""Read only the local demo's editable textual drafts and saved pair receipts."""
import json
from sqlalchemy import select, and_
from tapi_gate0.studio_e1 import studio_documents, studio_versions, DesignDocument
from tapi_gate0.sa_store import domain_events


def saved_library(engine, tenant, report_sha256=None):
    d, v = studio_documents, studio_versions
    with engine.connect() as db:
        rows = db.execute(select(v.c.payload).select_from(d.join(v, and_(
            d.c.tenant_id == v.c.tenant_id, d.c.document_id == v.c.document_id,
            d.c.current_version == v.c.version))).where(d.c.tenant_id == tenant,
            d.c.document_id.like('demo.%')).order_by(v.c.created_at.desc(), d.c.document_id).limit(100)).scalars().all()
        documents = []
        for raw in rows:
            doc = DesignDocument.model_validate_json(raw)
            if (doc.approval_status != 'draft' or not doc.pages or
                    any(any(layer.kind != 'text' for layer in page.layers) or
                        not any(layer.id == 'headline' for layer in page.layers) for page in doc.pages)):
                continue
            documents.append(dict(document_id=doc.document_id, version=doc.version,
                headline=next(layer.text for layer in doc.pages[0].layers if layer.id == 'headline'),
                pages=len(doc.pages), platform_intent=doc.platform_intent))
        ids = {d['document_id'] for d in documents}
        pairs = []
        for raw in db.execute(select(domain_events.c.payload).where(
                domain_events.c.tenant_id == tenant,
                domain_events.c.aggregate_type == 'demo_editorial_experiment',
                domain_events.c.event_type == 'demo.editorial_experiment.created').order_by(domain_events.c.seq.desc()).limit(50)).scalars():
            proof = json.loads(raw)
            if (proof.get('report_sha256') == report_sha256 and report_sha256 is not None
                    and proof.get('publication_allowed') is False
                    and all(item['document_id'] in ids for item in proof['documents'])):
                pairs.append(proof)
    return {'documents': documents, 'pairs': pairs, 'publication_allowed': False}
