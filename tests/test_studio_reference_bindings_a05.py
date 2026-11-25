"""CAP-023 immutable document-to-signed-grant pointers (local SQL only)."""
from sqlalchemy import insert, update
from sqlalchemy.exc import IntegrityError
import pytest

from tapi_gate0.sa_store import (
    engine_for, SqlDomainStore, tenants, creators, content_items,
)
from tapi_gate0.studio_e1 import studio_documents
from tapi_gate0.studio_reference_bindings_a05 import (
    ReferenceBindingDenied, persist_reference_bindings,
    load_reference_bindings, studio_reference_bindings,
)


@pytest.fixture
def sample(tmp_path):
    engine = engine_for(f"sqlite:///{tmp_path / 'binding-test.sqlite'}")
    SqlDomainStore(engine).initialize()
    with engine.begin() as db:
        for tenant in ("tenantA", "tenantB"):
            db.execute(insert(tenants).values(tenant_id=tenant, name=tenant))
            db.execute(insert(creators).values(
                tenant_id=tenant, id="creator", origin="instagram", payload="{}",
            ))
            for content in ("post1", "post2"):
                db.execute(insert(content_items).values(
                    tenant_id=tenant, id=content, creator_id="creator",
                    origin="instagram", published_at="2026-11-01T00:00:00+00:00",
                    payload="{}",
                ))
            db.execute(insert(studio_documents).values(
                tenant_id=tenant, document_id="doc1", spec_id="spec",
                current_version=1,
            ))
    try:
        yield engine
    finally:
        engine.dispose()


def test_binding_persists_exact_grant_and_is_tenant_scoped(sample):
    with sample.begin() as db:
        persist_reference_bindings(
            db, tenant="tenantA", document_id="doc1",
            reference_content_ids=["post1"], external_grant_ids={"post1": "grantA"},
        )
    with sample.connect() as db:
        assert load_reference_bindings(
            db, tenant="tenantA", document_id="doc1",
            reference_content_ids=["post1"],
        ) == {"post1": "grantA"}
        assert load_reference_bindings(
            db, tenant="tenantB", document_id="doc1",
            reference_content_ids=["post1"],
        ) == {}


@pytest.mark.parametrize("invalid", [
    {"post2": "grantA"},
    {"post1": ""},
    {"post1": "grantA", "post2": "grantB"},
])
def test_invalid_scope_is_denied_before_database_write(sample, invalid):
    with sample.begin() as db:
        with pytest.raises(ReferenceBindingDenied):
            persist_reference_bindings(
                db, tenant="tenantA", document_id="doc1",
                reference_content_ids=["post1"], external_grant_ids=invalid,
            )
    with sample.connect() as db:
        assert db.execute(studio_reference_bindings.select()).all() == []


def test_digest_tampering_or_reference_reordering_invalidates_bindings(sample):
    with sample.begin() as db:
        persist_reference_bindings(
            db, tenant="tenantA", document_id="doc1",
            reference_content_ids=["post1", "post2"],
            external_grant_ids={"post1": "grantA"},
        )
    with sample.connect() as db:
        with pytest.raises(ReferenceBindingDenied):
            load_reference_bindings(
                db, tenant="tenantA", document_id="doc1",
                reference_content_ids=["post2", "post1"],
            )
    with sample.begin() as db:
        db.execute(update(studio_reference_bindings).values(
            reference_set_sha256="0" * 64,
        ))
    with sample.connect() as db:
        with pytest.raises(ReferenceBindingDenied):
            load_reference_bindings(
                db, tenant="tenantA", document_id="doc1",
                reference_content_ids=["post1", "post2"],
            )


def test_duplicate_binding_cannot_replace_original_grant(sample):
    with sample.begin() as db:
        persist_reference_bindings(
            db, tenant="tenantA", document_id="doc1",
            reference_content_ids=["post1"], external_grant_ids={"post1": "grantA"},
        )
    with pytest.raises(IntegrityError):
        with sample.begin() as db:
            persist_reference_bindings(
                db, tenant="tenantA", document_id="doc1",
                reference_content_ids=["post1"], external_grant_ids={"post1": "grantB"},
            )
    with sample.connect() as db:
        assert load_reference_bindings(
            db, tenant="tenantA", document_id="doc1",
            reference_content_ids=["post1"],
        ) == {"post1": "grantA"}


def test_absent_binding_is_not_inferred_as_creative_license(sample):
    with sample.connect() as db:
        assert load_reference_bindings(
            db, tenant="tenantA", document_id="doc1",
            reference_content_ids=["post1"],
        ) == {}
