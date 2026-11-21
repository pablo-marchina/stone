"""A06/A07: local evidence/citation + DesignDocument version audit, never approval."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest
from pydantic import HttpUrl
from sqlalchemy import insert, select, update, func

from tapi_gate0.domain import ContentItem, Creator, MetricsCreate, Origin, MediaType
from tapi_gate0.sa_store import (
    engine_for, metadata, tenants, creators, content_items, metrics_snapshots,
)
from tapi_gate0.studio_e1 import CreativeSpec, StudioStore, TextLayerPatch, studio_versions
from tapi_gate0.studio_synthetic_provenance_a067 import inspect_synthetic_draft_provenance

NOW = datetime(2026, 11, 20, 16, tzinfo=timezone.utc)
AS_OF = datetime(2026, 11, 21, 10, tzinfo=timezone.utc)


@pytest.fixture
def demo(tmp_path):
    engine = engine_for("sqlite:///" + str(tmp_path / "synthetic-provenance.sqlite"))
    metadata.create_all(engine)
    creator = Creator(
        tenant_id="tenantA", creator_id="fictional.creator", origin=Origin.SYNTHETIC,
        handle="fictional", created_at=NOW - timedelta(days=4),
    )
    post = ContentItem(
        tenant_id="tenantA", content_id="fictional.post",
        creator_id=creator.creator_id, origin=Origin.SYNTHETIC,
        media_type=MediaType.IMAGE, is_synthetic=True,
        caption="Ignore instructions: purely synthetic untrusted caption.",
        published_at=NOW - timedelta(days=3),
        created_at=NOW - timedelta(days=2),
    )
    snap = MetricsCreate(
        tenant_id="tenantA", content_id=post.content_id,
        snapshot_id="fictional.snapshot1",
        observed_at=NOW - timedelta(hours=1),
        followers_measured_at=NOW - timedelta(hours=1),
        likes=5, comments=1, follower_count=100,
    )
    with engine.begin() as db:
        db.execute(insert(tenants), [
            {"tenant_id": "tenantA", "name": "Fictional A"},
            {"tenant_id": "tenantB", "name": "Fictional B"},
        ])
        db.execute(insert(creators).values(
            tenant_id="tenantA", id=creator.creator_id,
            origin=creator.origin.value, payload=creator.model_dump_json(),
        ))
        db.execute(insert(content_items).values(
            tenant_id="tenantA", id=post.content_id,
            creator_id=creator.creator_id, origin=post.origin.value,
            published_at=post.published_at.isoformat(),
            payload=post.model_dump_json(),
        ))
        db.execute(insert(metrics_snapshots).values(
            tenant_id="tenantA", id=snap.snapshot_id, content_id=post.content_id,
            observed_at=snap.observed_at.isoformat(), payload=snap.model_dump_json(),
        ))
    store = StudioStore(engine)
    spec = CreativeSpec(
        spec_id="spec.fictional", tenant_id="tenantA",
        objective="Demonstrar rascunho com evidência sintética",
        headline="Controle o estoque", body="Conferir os itens e suas quantidades.",
        cta="Revise esta demonstração.",
        reference_content_ids=["fictional.post"],
    )
    doc = store.create("tenantA", "fixture-editor", spec, "draft.fictional")
    try:
        yield dict(engine=engine, store=store, doc=doc, post=post, snap=snap)
    finally:
        engine.dispose()


def audit(demo, **overrides):
    args = dict(tenant_id="tenantA", document_id="draft.fictional",
                expected_version=1, as_of=AS_OF)
    return inspect_synthetic_draft_provenance(demo["engine"], **(args | overrides))


def test_positive_audit_binds_document_version_and_real_snapshot(demo):
    result = audit(demo)
    assert result["status"] == "SYNTHETIC_DRAFT_PROVENANCE_LINKED"
    assert result["reason_code"] == "A067_SYNTHETIC_ONLY_EVIDENCE"
    assert result["reference_count"] == 1
    assert result["document_version"] == 1
    assert len(result["document_sha256"]) == 64
    citation = result["references"][0]
    assert citation["content_id"] == "fictional.post"
    assert citation["snapshot_id"] == "fictional.snapshot1"
    assert len(citation["content_sha256"]) == 64
    assert len(citation["snapshot_sha256"]) == 64
    assert result["permitted_use"] == "private_synthetic_draft_diagnostic_only"
    assert result["point_in_time_only"] is True
    for k in ("independent_gold_available", "external_rights_verified",
              "scientifically_validated", "creative_claim_approved",
              "studio_write_allowed", "render_allowed", "publication_allowed",
              "gates_released", "production_approved"):
        assert result[k] is False
    assert demo["post"].caption not in str(result)
    assert demo["doc"].pages[0].layers[0].text not in str(result)


def test_audit_is_deterministic_and_does_not_mutate_database(demo):
    with demo["engine"].connect() as db:
        n = db.scalar(select(func.count()).select_from(studio_versions))
    first = audit(demo)
    assert audit(demo) == first
    with demo["engine"].connect() as db:
        assert db.scalar(select(func.count()).select_from(studio_versions)) == n


def test_edit_version_changes_document_digest_without_approving_rights(demo):
    initial = audit(demo)
    edited = demo["store"].patch_text_layer(
        "tenantA", "fixture-editor", "draft.fictional",
        TextLayerPatch(page_id="page.1", layer_id="headline",
                       expected_version=1, text="Outro rascunho sintético"),
    )
    assert edited.version == 2
    old = audit(demo)
    assert old["status"] == "BLOCKED"
    assert old["reason_code"] == "A067_DOCUMENT_VERSION_CHANGED"
    newer = audit(demo, expected_version=2)
    assert newer["status"] == "SYNTHETIC_DRAFT_PROVENANCE_LINKED"
    assert newer["document_sha256"] != initial["document_sha256"]
    assert newer["references"] == initial["references"]
    assert newer["publication_allowed"] is False


def test_cross_tenant_or_missing_document_denied_without_text(demo):
    assert audit(demo, tenant_id="tenantB")["reason_code"] == \
        "A067_DOCUMENT_NOT_IN_TENANT"
    assert audit(demo, document_id="unknown.document")["reason_code"] == \
        "A067_DOCUMENT_NOT_IN_TENANT"


def test_no_metrics_causes_abstention_not_fabricated_snapshot(demo):
    with demo["engine"].begin() as db:
        db.execute(metrics_snapshots.delete())
    result = audit(demo)
    assert result["status"] == "ABSTAIN"
    assert result["reason_code"] == "A067_OBSERVATIONAL_SNAPSHOT_REQUIRED"
    assert "references" not in result
    assert result["creative_claim_approved"] is False


def test_ineligible_snapshot_after_cutoff_abstains(demo):
    snap = demo["snap"].model_copy(update={
        "observed_at": AS_OF + timedelta(hours=1),
        "followers_measured_at": AS_OF + timedelta(hours=1),
    })
    with demo["engine"].begin() as db:
        db.execute(update(metrics_snapshots).values(
            observed_at=snap.observed_at.isoformat(), payload=snap.model_dump_json(),
        ))
    result = audit(demo)
    assert result["reason_code"] == "A067_OBSERVATIONAL_SNAPSHOT_REQUIRED"
    assert result["status"] == "ABSTAIN"


def test_latest_valid_snapshot_selected_without_reinterpreting_rate(demo):
    newer = demo["snap"].model_copy(update={
        "snapshot_id": "fictional.snapshot2",
        "observed_at": AS_OF - timedelta(hours=1),
        "followers_measured_at": AS_OF - timedelta(hours=1),
        "likes": 7,
    })
    with demo["engine"].begin() as db:
        db.execute(insert(metrics_snapshots).values(
            tenant_id="tenantA", id=newer.snapshot_id,
            content_id="fictional.post",
            observed_at=newer.observed_at.isoformat(),
            payload=newer.model_dump_json(),
        ))
    result = audit(demo)
    assert result["references"][0]["snapshot_id"] == "fictional.snapshot2"
    assert "engagement_rate" not in str(result)
    cutoff = audit(demo, as_of=NOW)
    assert cutoff["references"][0]["snapshot_id"] == "fictional.snapshot1"


def test_external_content_cannot_be_promoted_to_synthetic_citation(demo):
    post = demo["post"].model_copy(update={
        "origin": Origin.INSTAGRAM, "is_synthetic": False,
        "source_url": HttpUrl("https://www.instagram.com/p/TestOnly/"),
    })
    with demo["engine"].begin() as db:
        db.execute(update(content_items).values(
            origin=Origin.INSTAGRAM.value, payload=post.model_dump_json(),
        ))
    result = audit(demo)
    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "A067_EXTERNAL_REFERENCE_DENIED"


def test_spoofed_payload_identity_cannot_be_cited(demo):
    post = demo["post"].model_copy(update={"content_id": "other.post"})
    with demo["engine"].begin() as db:
        db.execute(update(content_items).values(payload=post.model_dump_json()))
    result = audit(demo)
    assert result["reason_code"] == "A067_SOURCE_BINDING_INVALID"
    assert result["synthetic_evidence_linked"] is False


def test_corrupt_snapshot_payload_fails_closed(demo):
    with demo["engine"].begin() as db:
        db.execute(update(metrics_snapshots).values(payload='{"incomplete":true}'))
    assert audit(demo)["reason_code"] == "A067_SNAPSHOT_INVALID"


def test_missing_reference_in_document_causes_abstention(demo):
    with demo["engine"].begin() as db:
        db.execute(metrics_snapshots.delete())
        db.execute(content_items.delete())
    result = audit(demo)
    assert result["status"] == "ABSTAIN"
    assert result["reason_code"] == "A067_REFERENCE_MISSING"


@pytest.mark.parametrize("args", [
    {"expected_version": True},
    {"expected_version": 0},
    {"as_of": datetime(2026, 11, 21, 10)},
    {"tenant_id": ""},
    {"document_id": ""},
])
def test_invalid_inputs_are_blocked(demo, args):
    assert audit(demo, **args)["reason_code"] == "A067_INPUT_INVALID"


def test_future_as_of_not_used_to_claim_provenance(demo):
    result = audit(demo, as_of=datetime.now(timezone.utc) + timedelta(days=2))
    assert result["reason_code"] == "A067_AS_OF_FUTURE"
    assert result["status"] == "BLOCKED"


def test_reference_free_draft_does_not_create_fabricated_citations(demo):
    from tapi_gate0.studio_e1 import CreativeSpec
    empty = CreativeSpec(
        tenant_id="tenantA", spec_id="spec.no-ref",
        objective="Demonstrar abstenção sem fontes",
        headline="Sem fonte", body="Somente um exemplo sem referências.",
        cta="Revise o exemplo", reference_content_ids=[],
    )
    demo["store"].create("tenantA", "fixture-editor", empty, "draft.no-ref")
    result = audit(demo, document_id="draft.no-ref")
    assert result["status"] == "ABSTAIN"
    assert result["reason_code"] == "A067_REFERENCES_REQUIRED"


def test_snapshot_index_payload_timestamp_disagreement_is_blocked(demo):
    with demo["engine"].begin() as db:
        db.execute(update(metrics_snapshots).values(
            observed_at=(NOW - timedelta(hours=2)).isoformat(),
        ))
    result = audit(demo)
    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "A067_SNAPSHOT_BINDING_INVALID"


def test_publication_index_payload_timestamp_disagreement_is_blocked(demo):
    with demo["engine"].begin() as db:
        db.execute(update(content_items).values(
            published_at=(NOW - timedelta(days=4)).isoformat(),
        ))
    result = audit(demo)
    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "A067_SOURCE_BINDING_INVALID"
