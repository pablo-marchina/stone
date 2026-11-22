"""CAP-023 / E6 — SQL-to-payload trust boundary for evidence-bound edits.

All records are disposable local fixtures. The source is an artificial external
metadata entry, NOT an authorized third-party creative asset or production gold.
"""
from datetime import datetime, timezone
import json

import pytest
from sqlalchemy import insert, select, update

from tapi_gate0.domain import ContentItem, Creator, MediaType, MetricsCreate, Origin
from tapi_gate0.sa_store import (
    SqlDomainStore, engine_for, tenants, creators, content_items, metrics_snapshots,
)
from tapi_gate0.studio_e1 import CreativeSpec, StudioError, StudioStore
from tapi_gate0.studio_evidence_edits_e6 import (
    EvidenceEditProposal, ConfirmEvidenceEdit, StudioEvidenceEditService,
)

PUBLISHED = datetime(2026, 10, 1, tzinfo=timezone.utc)
OBSERVED = datetime(2026, 11, 5, tzinfo=timezone.utc)
CREATE = datetime(2026, 11, 5, tzinfo=timezone.utc)


@pytest.fixture
def scenario(tmp_path):
    engine = engine_for(f"sqlite:///{tmp_path / 'studio-evidence-integrity.sqlite'}")
    SqlDomainStore(engine).initialize()
    creator = Creator(
        tenant_id="tenantA", creator_id="creator.real", origin=Origin.INSTAGRAM,
        handle="source", created_at=CREATE,
    )
    content = ContentItem(
        tenant_id="tenantA", content_id="content.real",
        creator_id=creator.creator_id, origin=Origin.INSTAGRAM,
        media_type=MediaType.REELS, published_at=PUBLISHED,
        source_url="https://www.instagram.com/reel/Example123/",
        caption="Fonte de metadados para o teste local", is_synthetic=False,
        created_at=CREATE,
    )
    metrics = MetricsCreate(
        tenant_id="tenantA", content_id=content.content_id,
        snapshot_id="snapshot.real", observed_at=OBSERVED,
        followers_measured_at=OBSERVED, likes=10, comments=2,
        follower_count=500,
    )
    with engine.begin() as db:
        db.execute(insert(tenants).values(tenant_id="tenantA", name="Test Tenant"))
        db.execute(insert(creators).values(
            tenant_id="tenantA", id=creator.creator_id,
            origin=creator.origin.value, payload=creator.model_dump_json(),
        ))
        db.execute(insert(content_items).values(
            tenant_id="tenantA", id=content.content_id, creator_id=creator.creator_id,
            origin=content.origin.value, published_at=content.published_at.isoformat(),
            payload=content.model_dump_json(),
        ))
        db.execute(insert(metrics_snapshots).values(
            tenant_id="tenantA", id=metrics.snapshot_id, content_id=metrics.content_id,
            observed_at=metrics.observed_at.isoformat(), payload=metrics.model_dump_json(),
        ))
    studio = StudioStore(engine)
    studio.create("tenantA", "operator", CreativeSpec(
        spec_id="spec.test", tenant_id="tenantA",
        objective="Revisar material educativo apenas como rascunho",
        headline="Organize o caixa", body="Uma referência para análise",
        cta="Revise o exemplo", reference_content_ids=["content.real"],
    ), "document.test")
    proposal = EvidenceEditProposal(
        expected_version=1, page_id="page.1", layer_id="headline",
        text="Proposta revisada pelo operador", origin="operator",
        reference_content_id="content.real", reference_snapshot_id="snapshot.real",
    )
    try:
        yield engine, StudioEvidenceEditService(engine), proposal
    finally:
        engine.dispose()


def _payload_change(engine, table, record_id, edits):
    with engine.begin() as db:
        row = db.execute(select(table.c.payload).where(
            table.c.tenant_id == "tenantA", table.c.id == record_id,
        )).scalar_one()
        value = json.loads(row)
        value.update(edits)
        db.execute(update(table).where(
            table.c.tenant_id == "tenantA", table.c.id == record_id,
        ).values(payload=json.dumps(value)))


@pytest.mark.parametrize("table,record_id,edits,reason", [
    (content_items, "content.real", {"tenant_id": "tenantB"}, "CONTENT_BINDING_INVALID"),
    (content_items, "content.real", {"content_id": "content.other"}, "CONTENT_BINDING_INVALID"),
    (content_items, "content.real", {"creator_id": "creator.other"}, "CONTENT_BINDING_INVALID"),
    (content_items, "content.real", {"published_at": "2026-10-03T00:00:00+00:00"}, "CONTENT_BINDING_INVALID"),
    (creators, "creator.real", {"tenant_id": "tenantB"}, "CREATOR_BINDING_INVALID"),
    (creators, "creator.real", {"creator_id": "creator.other"}, "CREATOR_BINDING_INVALID"),
    (creators, "creator.real", {"origin": "youtube"}, "CREATOR_BINDING_INVALID"),
    (metrics_snapshots, "snapshot.real", {"tenant_id": "tenantB"}, "SNAPSHOT_BINDING_INVALID"),
    (metrics_snapshots, "snapshot.real", {"content_id": "content.other"}, "SNAPSHOT_BINDING_INVALID"),
    (metrics_snapshots, "snapshot.real", {"snapshot_id": "snapshot.other"}, "SNAPSHOT_BINDING_INVALID"),
    (metrics_snapshots, "snapshot.real", {"observed_at": "2026-11-07T00:00:00+00:00"}, "SNAPSHOT_BINDING_INVALID"),
])
def test_corrupt_serialized_binding_blocks_preview(scenario, table, record_id, edits, reason):
    engine, service, proposal = scenario
    _payload_change(engine, table, record_id, edits)
    with pytest.raises(StudioError, match=reason):
        service.preview("tenantA", "document.test", proposal)
    assert service.docs.get("tenantA", "document.test").version == 1


@pytest.mark.parametrize("table,record_id,reason", [
    (content_items, "content.real", "CONTENT_PAYLOAD_INVALID"),
    (creators, "creator.real", "CREATOR_PAYLOAD_INVALID"),
    (metrics_snapshots, "snapshot.real", "SNAPSHOT_PAYLOAD_INVALID"),
])
def test_invalid_json_fails_closed_without_leaking_payload(scenario, table, record_id, reason):
    engine, service, proposal = scenario
    with engine.begin() as db:
        db.execute(update(table).where(
            table.c.tenant_id == "tenantA", table.c.id == record_id,
        ).values(payload='{"token": "never_echo_secret",'))
    with pytest.raises(StudioError, match=reason) as exc:
        service.preview("tenantA", "document.test", proposal)
    assert "never_echo_secret" not in str(exc.value)


@pytest.mark.parametrize("table,record_id,column,new_value,reason", [
    (content_items, "content.real", "origin", "youtube", "CONTENT_BINDING_INVALID"),
    (content_items, "content.real", "published_at", "2026-10-02T00:00:00+00:00", "CONTENT_BINDING_INVALID"),
    (creators, "creator.real", "origin", "youtube", "CREATOR_BINDING_INVALID"),
    (metrics_snapshots, "snapshot.real", "observed_at", "2026-11-07T00:00:00+00:00", "SNAPSHOT_BINDING_INVALID"),
])
def test_corrupt_indexed_identity_blocks_preview(scenario, table, record_id, column, new_value, reason):
    engine, service, proposal = scenario
    with engine.begin() as db:
        db.execute(update(table).where(
            table.c.tenant_id == "tenantA", table.c.id == record_id,
        ).values({column: new_value}))
    with pytest.raises(StudioError, match=reason):
        service.preview("tenantA", "document.test", proposal)


def test_snapshot_before_publication_denied_even_if_index_and_payload_agree(scenario):
    engine, service, proposal = scenario
    older = "2026-09-01T00:00:00+00:00"
    _payload_change(engine, metrics_snapshots, "snapshot.real", {"observed_at": older})
    with engine.begin() as db:
        db.execute(update(metrics_snapshots).where(
            metrics_snapshots.c.tenant_id == "tenantA",
            metrics_snapshots.c.id == "snapshot.real",
        ).values(observed_at=older))
    with pytest.raises(StudioError, match="SNAPSHOT_BINDING_INVALID"):
        service.preview("tenantA", "document.test", proposal)


def test_valid_evidence_preview_remains_descriptive_and_draft(scenario):
    _engine, service, proposal = scenario
    preview = service.preview("tenantA", "document.test", proposal)
    assert preview["reference_content_id"] == "content.real"
    assert preview["reference_snapshot_id"] == "snapshot.real"
    assert preview["descriptive_evidence_only"] is True
    assert preview["production_approved"] is False
    assert preview["requires_operator_confirmation"] is True
    assert service.docs.get("tenantA", "document.test").version == 1


def test_invalid_evidence_at_apply_leaves_document_unmodified(scenario):
    engine, service, proposal = scenario
    preview = service.preview("tenantA", "document.test", proposal)
    _payload_change(engine, metrics_snapshots, "snapshot.real", {
        "tenant_id": "tenantB",
    })
    confirmed = ConfirmEvidenceEdit(
        **proposal.model_dump(), preview_sha256=preview["preview_sha256"],
        operator_confirmed=True,
    )
    with pytest.raises(StudioError, match="SNAPSHOT_BINDING_INVALID"):
        service.apply("tenantA", "operator", "document.test", confirmed,
                      preview["base_etag"])
    assert service.docs.get("tenantA", "document.test").version == 1


@pytest.mark.parametrize("table,record_id,change", [
    (content_items, "content.real", {
        "caption": "Fonte alterada depois da prévia",
    }),
    (creators, "creator.real", {"handle": "changed_author_after_preview"}),
])
def test_content_or_creator_drift_invalidates_operator_confirmation(
        scenario, table, record_id, change):
    engine, service, proposal = scenario
    preview = service.preview("tenantA", "document.test", proposal)
    _payload_change(engine, table, record_id, change)
    confirmed = ConfirmEvidenceEdit(
        **proposal.model_dump(),
        preview_sha256=preview["preview_sha256"],
        operator_confirmed=True,
    )
    with pytest.raises(StudioError, match="STUDIO_EVIDENCE_PREVIEW_CHANGED"):
        service.apply("tenantA", "operator", "document.test", confirmed,
                      preview["base_etag"])
    assert service.docs.get("tenantA", "document.test").version == 1
