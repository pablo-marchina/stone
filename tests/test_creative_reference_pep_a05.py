"""A05 operational-shape PEP tests with disposable, fictitious signed grants.

Every signature, source, approval digest, role and identifier below is a LOCAL
TEST FIXTURE. These checks do not establish rights to actual third-party media.
No external services, provisioning or publication.
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update, insert

from test_creative_reference_registry_a05 import (
    registry, provision, TENANT, PASSWORD,
)
from tapi_gate0.creative_reference_rights_a05 import ReferenceOperation
from tapi_gate0.creative_reference_pep_a05 import (
    CreativeReferencePEP, CreativeReferencePermissionDenied,
)
from tapi_gate0.identity import memberships
from tapi_gate0.ingestion import source_grants
from tapi_gate0.sa_store import domain_events, outbox, content_items, creators
from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.studio_e1 import StudioStore, studio_documents


def signed_fixture(r, operations=None):
    provision(r)
    opts = operations or (
        ReferenceOperation.CREATIVE_SPEC_REFERENCE,
        ReferenceOperation.STUDIO_DRAFT_REFERENCE,
    )
    assert r["svc"].register(
        r["anchor"], r["grant"](operations=opts),
        verified_approval_digest="a" * 64,
    )
    return CreativeReferencePEP(
        r["engine"], {(TENANT, "instagram"): r["anchor"]},
    )


def grant_ids(r):
    return {r["content_id"]: "a054-fixture-grant"}


def spec_body(r, doc="draft.with-signed-ref"):
    return {
        "document_id": doc,
        "brief": {
            "spec_id": "spec.signed.fixture",
            "objective": "Criar exemplo educativo local e editável",
            "headline": "Organize o caixa",
            "body": "Exemplo elaborado com referências fictícias de teste.",
            "cta": "Revise o material",
            "platform_intent": "instagram_feed",
            "reference_content_ids": [r["content_id"]],
        },
        "reference_grant_ids": grant_ids(r),
    }


def app_for(r, *, authorities=True):
    return create_secure_app(
        str(r["engine"].url), initialize_schema=False,
        allow_http_local=True,
        creative_reference_authorities=(
            {(TENANT, "instagram"): r["anchor"]} if authorities else None
        ),
    )


def headers(client):
    login = client.post("/v1/auth/sessions", json={
        "username": "localadmin", "password": PASSWORD, "tenant_id": TENANT,
    })
    assert login.status_code == 200, login.text
    return {"Authorization": "Bearer " + login.json()["access_token"]}


def test_signed_grants_require_both_creative_operations(registry):
    r = registry
    pep = signed_fixture(r)
    with r["engine"].begin() as con:
        pep.require_for_atomic_draft(
            con, token=r["token"], tenant=TENANT, actor="founder",
            document_id="local.test", grant_ids=grant_ids(r),
        )
    with r["engine"].connect() as con:
        events = con.execute(select(domain_events).where(
            domain_events.c.aggregate_type == "creative_reference_use",
        )).mappings().all()
        assert len(events) == 1
        assert r["content_id"] not in events[0]["payload"]
        assert r["token"] not in events[0]["payload"]
        assert con.execute(select(outbox.c.seq).where(
            outbox.c.seq == events[0]["seq"],
        )).scalar_one() == events[0]["seq"]


def test_one_signed_operation_cannot_grant_agent_to_studio(registry):
    r = registry
    pep = signed_fixture(r, (
        ReferenceOperation.CREATIVE_SPEC_REFERENCE,
    ))
    with r["engine"].begin() as con:
        with pytest.raises(CreativeReferencePermissionDenied):
            pep.require_for_atomic_draft(
                con, token=r["token"], tenant=TENANT, actor="founder",
                document_id="local.test", grant_ids=grant_ids(r),
            )


def test_pep_denies_revoked_session_and_downgraded_role(registry):
    r = registry
    pep = signed_fixture(r)
    principal = r["identity"].resolve(r["token"])
    r["identity"].revoke(r["token"], principal)
    with r["engine"].begin() as con:
        with pytest.raises(CreativeReferencePermissionDenied):
            pep.require_for_atomic_draft(
                con, token=r["token"], tenant=TENANT, actor="founder",
                document_id="local.test", grant_ids=grant_ids(r),
            )


def test_pep_denies_revoked_source_grant(registry):
    r = registry
    pep = signed_fixture(r)
    with r["engine"].begin() as con:
        con.execute(update(source_grants).where(
            source_grants.c.tenant_id == TENANT,
        ).values(enabled=0))
    with r["engine"].begin() as con:
        with pytest.raises(CreativeReferencePermissionDenied):
            pep.require_for_atomic_draft(
                con, token=r["token"], tenant=TENANT, actor="founder",
                document_id="local.test", grant_ids=grant_ids(r),
            )


def test_runtime_endpoint_default_denies_even_registered_signed_grant(registry):
    r = registry
    signed_fixture(r)
    app = app_for(r, authorities=False)
    with TestClient(app) as client:
        h = headers(client)
        response = client.post("/v1/agent/creative-drafts",
                               headers=h, json=spec_body(r))
        assert response.status_code == 422
        assert response.json()["detail"] == "CREATIVE_REFERENCE_NOT_VERIFIED"
        assert client.get(
            "/v1/studio/documents/draft.with-signed-ref", headers=h,
        ).status_code == 404


def test_signed_references_create_only_unapproved_draft_when_host_pinned(registry):
    r = registry
    signed_fixture(r)
    app = app_for(r)
    with TestClient(app) as client:
        h = headers(client)
        created = client.post(
            "/v1/agent/creative-drafts", headers=h, json=spec_body(r),
        )
        assert created.status_code == 201, created.text
        doc = created.json()
        assert doc["reference_content_ids"] == [r["content_id"]]
        assert doc["rights_status"] == "pending_review"
        assert doc["approval_status"] == "draft"
        assert doc["reference_status"] == "unverified"
        assert doc["version"] == 1
        assert created.headers["cache-control"] == "private, no-store"
        assert "fixture" not in created.headers.get("etag", "").lower()


def test_signed_reference_recheck_failure_blocks_document(registry):
    r = registry
    signed_fixture(r)
    with r["engine"].begin() as con:
        con.execute(update(source_grants).where(
            source_grants.c.tenant_id == TENANT,
        ).values(enabled=0))
    app = app_for(r)
    with TestClient(app) as client:
        h = headers(client)
        denied = client.post(
            "/v1/agent/creative-drafts", headers=h, json=spec_body(r),
        )
        assert denied.status_code == 422
        assert client.get(
            "/v1/studio/documents/draft.with-signed-ref", headers=h,
        ).status_code == 404


def test_version_insert_failure_rolls_back_rights_audit_too(registry, monkeypatch):
    r = registry
    signed_fixture(r)
    app = app_for(r)
    def fail_version(_connection, _doc, _actor):
        raise RuntimeError("fixture transaction failure")
    monkeypatch.setattr(StudioStore, "_insert_version", staticmethod(fail_version))
    with TestClient(app) as client:
        h = headers(client)
        with pytest.raises(RuntimeError, match="fixture transaction failure"):
            client.post(
                "/v1/agent/creative-drafts", headers=h, json=spec_body(r),
            )
    with r["engine"].connect() as con:
        assert con.execute(select(studio_documents.c.document_id).where(
            studio_documents.c.tenant_id == TENANT,
        )).scalars().all() == []
        assert con.execute(select(domain_events.c.seq).where(
            domain_events.c.aggregate_type == "creative_reference_use",
        )).scalars().all() == []


def test_wrong_tenant_actor_and_grant_are_never_authorized(registry):
    r = registry
    pep = signed_fixture(r)
    for tenant, actor, gids in [
        (TENANT, "another-user", grant_ids(r)),
        ("another-tenant", "founder", grant_ids(r)),
        (TENANT, "founder", {r["content_id"]: "wrong-grant"}),
    ]:
        with r["engine"].begin() as con:
            with pytest.raises(CreativeReferencePermissionDenied):
                pep.require_for_atomic_draft(
                    con, token=r["token"], tenant=tenant, actor=actor,
                    document_id="local.test", grant_ids=gids,
                )


def test_server_supplied_trust_cannot_be_forged_from_json(registry):
    r = registry
    signed_fixture(r)
    app = app_for(r, authorities=False)
    with TestClient(app) as client:
        h = headers(client)
        body = spec_body(r)
        body["creative_reference_authorities"] = {"instagram": "forged"}
        denied = client.post("/v1/agent/creative-drafts", headers=h, json=body)
        assert denied.status_code == 422


def test_pep_checks_revocation_head_against_independent_pin(registry):
    r = registry
    stale_pep = signed_fixture(r)
    next_state = r["state"](
        revision=2, revoked_grant_ids=("a054-fixture-grant",),
    )
    assert r["svc"].advance(r["anchor"], TENANT, "instagram", next_state)
    # Previous host pin cannot silently follow a changed DB head.
    with r["engine"].begin() as con:
        with pytest.raises(CreativeReferencePermissionDenied):
            stale_pep.require_for_atomic_draft(
                con, token=r["token"], tenant=TENANT, actor="founder",
                document_id="draft.test", grant_ids=grant_ids(r),
            )
    # An independently refreshed host pin also enforces the revocation.
    active_pep = CreativeReferencePEP(
        r["engine"], {(TENANT, "instagram"): r["pin"](next_state)},
    )
    with r["engine"].begin() as con:
        with pytest.raises(CreativeReferencePermissionDenied):
            active_pep.require_for_atomic_draft(
                con, token=r["token"], tenant=TENANT, actor="founder",
                document_id="draft.test", grant_ids=grant_ids(r),
            )


def test_pep_denies_role_downgrade_before_creative_write(registry):
    r = registry
    pep = signed_fixture(r)
    with r["engine"].begin() as con:
        con.execute(update(memberships).where(
            memberships.c.tenant_id == TENANT,
        ).values(role="viewer"))
    with r["engine"].begin() as con:
        with pytest.raises(CreativeReferencePermissionDenied):
            pep.require_for_atomic_draft(
                con, token=r["token"], tenant=TENANT, actor="founder",
                document_id="draft.test", grant_ids=grant_ids(r),
            )


def test_pep_rejects_corrupted_signed_grant_payload(registry):
    from tapi_gate0.creative_reference_registry_a05 import grants
    r = registry
    pep = signed_fixture(r)
    with r["engine"].begin() as con:
        con.execute(update(grants).where(
            grants.c.tenant_id == TENANT,
        ).values(payload='{"token":"must_not_leak"'))
    with r["engine"].begin() as con:
        with pytest.raises(CreativeReferencePermissionDenied) as exc:
            pep.require_for_atomic_draft(
                con, token=r["token"], tenant=TENANT, actor="founder",
                document_id="draft.test", grant_ids=grant_ids(r),
            )
    assert "must_not_leak" not in str(exc.value)


# A05 reference lifecycle: persisted grant IDs and current rights must match.
from tapi_gate0.studio_reference_bindings_a05 import studio_reference_bindings
from tapi_gate0.studio_e1 import CreativeSpec


def test_signed_draft_persists_grants_and_rechecks_current_state(registry):
    r = registry
    signed_fixture(r)
    app = app_for(r)
    with TestClient(app) as client:
        h = headers(client)
        created = client.post("/v1/agent/creative-drafts",
                              headers=h, json=spec_body(r))
        assert created.status_code == 201, created.text
        with r["engine"].connect() as db:
            saved = db.execute(select(studio_reference_bindings).where(
                studio_reference_bindings.c.tenant_id == TENANT,
                studio_reference_bindings.c.document_id == "draft.with-signed-ref",
            )).mappings().all()
        assert len(saved) == 1
        assert saved[0]["content_id"] == r["content_id"]
        assert saved[0]["grant_id"] == "a054-fixture-grant"
        reply = client.post(
            "/v1/agent/creative-drafts/draft.with-signed-ref/reference-recheck",
            headers=h,
        )
        assert reply.status_code == 200, reply.text
        data = reply.json()
        assert data["status"] == "SIGNED_REFERENCES_CURRENT_FOR_DRAFT_REVIEW_ONLY"
        assert data["verified_external_reference_count"] == 1
        assert data["publication_allowed"] is False
        assert data["production_approved"] is False
    with r["engine"].connect() as db:
        events = db.execute(select(domain_events.c.event_type).where(
            domain_events.c.tenant_id == TENANT,
            domain_events.c.aggregate_type == "creative_reference_use",
        )).scalars().all()
    assert "creative_reference.checked_for_draft" in events
    assert "creative_reference.rechecked_for_draft" in events


def test_recheck_denied_after_source_revocation_no_new_audit(registry):
    r = registry
    signed_fixture(r)
    app = app_for(r)
    with TestClient(app) as client:
        h = headers(client)
        assert client.post("/v1/agent/creative-drafts",
                           headers=h, json=spec_body(r)).status_code == 201
        with r["engine"].begin() as db:
            db.execute(update(source_grants).where(
                source_grants.c.tenant_id == TENANT,
            ).values(enabled=0))
        denied = client.post(
            "/v1/agent/creative-drafts/draft.with-signed-ref/reference-recheck",
            headers=h,
        )
        assert denied.status_code == 422
        assert denied.json()["detail"] == "CREATIVE_REFERENCE_NOT_VERIFIED"
    with r["engine"].connect() as db:
        assert db.execute(select(domain_events.c.seq).where(
            domain_events.c.event_type == "creative_reference.rechecked_for_draft",
        )).all() == []
        assert db.execute(select(studio_documents.c.current_version).where(
            studio_documents.c.tenant_id == TENANT,
            studio_documents.c.document_id == "draft.with-signed-ref",
        )).scalar_one() == 1


def test_tampered_reference_set_digest_denies_recheck(registry):
    r = registry
    signed_fixture(r)
    app = app_for(r)
    with TestClient(app) as client:
        h = headers(client)
        assert client.post("/v1/agent/creative-drafts",
                           headers=h, json=spec_body(r)).status_code == 201
        with r["engine"].begin() as db:
            db.execute(update(studio_reference_bindings).where(
                studio_reference_bindings.c.tenant_id == TENANT,
            ).values(reference_set_sha256="0" * 64))
        denied = client.post(
            "/v1/agent/creative-drafts/draft.with-signed-ref/reference-recheck",
            headers=h,
        )
        assert denied.status_code == 422


def test_existing_signed_draft_recheck_requires_host_pinned_pep(registry):
    r = registry
    signed_fixture(r)
    with TestClient(app_for(r)) as client:
        h = headers(client)
        assert client.post("/v1/agent/creative-drafts",
                           headers=h, json=spec_body(r)).status_code == 201
    with TestClient(app_for(r, authorities=False)) as client:
        h = headers(client)
        denied = client.post(
            "/v1/agent/creative-drafts/draft.with-signed-ref/reference-recheck",
            headers=h,
        )
        assert denied.status_code == 422


def test_manually_created_external_reference_has_no_inferred_grant(registry):
    r = registry
    signed_fixture(r)
    doc_id = "manual.no-signed-binding"
    StudioStore(r["engine"]).create(
        TENANT, "founder",
        CreativeSpec(
            spec_id="spec.manual.unverified", tenant_id=TENANT,
            objective="Rascunho descritivo para revisão humana",
            headline="Uso não autorizado", body="Metadados não dão licença",
            cta="Revisar material", reference_content_ids=[r["content_id"]],
        ), doc_id,
    )
    with TestClient(app_for(r)) as client:
        h = headers(client)
        denied = client.post(
            f"/v1/agent/creative-drafts/{doc_id}/reference-recheck",
            headers=h,
        )
        assert denied.status_code == 422


def test_signed_draft_text_edit_rechecks_rights_in_same_transaction(registry):
    r = registry
    signed_fixture(r)
    with TestClient(app_for(r)) as client:
        h = headers(client)
        created = client.post("/v1/agent/creative-drafts",
                              headers=h, json=spec_body(r))
        assert created.status_code == 201, created.text
        before = created.headers["etag"]
        amended = client.post(
            "/v1/agent/creative-drafts/draft.with-signed-ref/text-patches",
            headers={**h, "If-Match": before},
            json={"expected_version": 1, "page_id": "page.1",
                  "layer_id": "headline", "text": "Revisão humana do rascunho"},
        )
        assert amended.status_code == 200, amended.text
        doc = amended.json()
        assert doc["version"] == 2
        assert doc["rights_status"] == "pending_review"
        assert doc["approval_status"] == "draft"
        assert amended.headers["etag"] != before
        with r["engine"].connect() as db:
            kinds = db.execute(select(domain_events.c.event_type).where(
                domain_events.c.aggregate_type == "creative_reference_use",
            )).scalars().all()
        assert kinds.count("creative_reference.rechecked_for_draft") == 1


def test_revoked_signed_reference_blocks_text_edit_and_rolls_back_audit(registry):
    r = registry
    signed_fixture(r)
    with TestClient(app_for(r)) as client:
        h = headers(client)
        created = client.post("/v1/agent/creative-drafts",
                              headers=h, json=spec_body(r))
        assert created.status_code == 201
        with r["engine"].begin() as db:
            db.execute(update(source_grants).where(
                source_grants.c.tenant_id == TENANT,
            ).values(enabled=0))
        denied = client.post(
            "/v1/agent/creative-drafts/draft.with-signed-ref/text-patches",
            headers={**h, "If-Match": created.headers["etag"]},
            json={"expected_version": 1, "page_id": "page.1",
                  "layer_id": "headline", "text": "Não aplicar"},
        )
        assert denied.status_code == 422
        assert client.get(
            "/v1/studio/documents/draft.with-signed-ref", headers=h,
        ).json()["version"] == 1
    with r["engine"].connect() as db:
        assert db.execute(select(domain_events.c.seq).where(
            domain_events.c.event_type == "creative_reference.rechecked_for_draft",
        )).all() == []


def test_legacy_studio_text_edit_denied_for_signed_external_draft(registry):
    r = registry
    signed_fixture(r)
    with TestClient(app_for(r)) as client:
        h = headers(client)
        made = client.post("/v1/agent/creative-drafts",
                           headers=h, json=spec_body(r))
        assert made.status_code == 201
        denied = client.post(
            "/v1/studio/documents/draft.with-signed-ref/text-patches",
            headers={**h, "If-Match": made.headers["etag"]},
            json={"expected_version": 1, "page_id": "page.1",
                  "layer_id": "headline", "text": "Não autorizado"},
        )
        assert denied.status_code == 403
        assert denied.json()["detail"] == (
            "STUDIO_SIGNED_REFERENCE_ACTION_RECHECK_REQUIRED"
        )
        assert client.get(
            "/v1/studio/documents/draft.with-signed-ref", headers=h,
        ).json()["version"] == 1


def test_signed_edit_requires_if_match_and_unchanged_version(registry):
    r = registry
    signed_fixture(r)
    with TestClient(app_for(r)) as client:
        h = headers(client)
        made = client.post("/v1/agent/creative-drafts",
                           headers=h, json=spec_body(r))
        assert made.status_code == 201
        path = "/v1/agent/creative-drafts/draft.with-signed-ref/text-patches"
        patch = {"expected_version": 1, "page_id": "page.1",
                 "layer_id": "headline", "text": "Sem condição"}
        missing = client.post(path, headers=h, json=patch)
        assert missing.status_code == 428
        invalid = client.post(path, headers={**h, "If-Match": '"wrong"'},
                              json=patch)
        assert invalid.status_code == 412
        assert client.get(
            "/v1/studio/documents/draft.with-signed-ref", headers=h,
        ).json()["version"] == 1


def test_without_runtime_pep_signed_edit_is_denied(registry):
    r = registry
    signed_fixture(r)
    with TestClient(app_for(r)) as client:
        h = headers(client)
        made = client.post("/v1/agent/creative-drafts",
                           headers=h, json=spec_body(r))
        assert made.status_code == 201
    with TestClient(app_for(r, authorities=False)) as client:
        h = headers(client)
        denied = client.post(
            "/v1/agent/creative-drafts/draft.with-signed-ref/text-patches",
            headers={**h, "If-Match": made.headers["etag"]},
            json={"expected_version": 1, "page_id": "page.1",
                  "layer_id": "headline", "text": "Falha fechada"},
        )
        assert denied.status_code == 422


def test_failed_signed_edit_rolls_back_recheck_audit(registry):
    r = registry
    signed_fixture(r)
    with TestClient(app_for(r)) as client:
        h = headers(client)
        created = client.post("/v1/agent/creative-drafts",
                              headers=h, json=spec_body(r))
        assert created.status_code == 201
        failed = client.post(
            "/v1/agent/creative-drafts/draft.with-signed-ref/text-patches",
            headers={**h, "If-Match": created.headers["etag"]},
            json={"expected_version": 1, "page_id": "page.1",
                  "layer_id": "no-such-layer", "text": "Não aplicar"},
        )
        assert failed.status_code == 404
        assert client.get(
            "/v1/studio/documents/draft.with-signed-ref", headers=h,
        ).json()["version"] == 1
    with r["engine"].connect() as db:
        assert db.execute(select(domain_events.c.seq).where(
            domain_events.c.event_type == "creative_reference.rechecked_for_draft",
        )).all() == []


def test_old_studio_page_mutation_denied_for_signed_draft(registry):
    r = registry
    signed_fixture(r)
    with TestClient(app_for(r)) as client:
        h = headers(client)
        created = client.post("/v1/agent/creative-drafts",
                              headers=h, json=spec_body(r))
        assert created.status_code == 201
        # The router-level deny applies to every legacy POST carrying a
        # document_id, before route handler side effects.
        denied = client.post(
            "/v1/studio/documents/draft.with-signed-ref/pages/duplicate",
            headers={**h, "If-Match": created.headers["etag"]},
            json={"expected_version": 1, "page_id": "page.1"},
        )
        assert denied.status_code == 403
        assert denied.json()["detail"] == (
            "STUDIO_SIGNED_REFERENCE_ACTION_RECHECK_REQUIRED"
        )


def test_signed_draft_geometry_edit_revalidates_rights_and_versions(registry):
    r = registry
    signed_fixture(r)
    with TestClient(app_for(r)) as client:
        h = headers(client)
        made = client.post("/v1/agent/creative-drafts", headers=h, json=spec_body(r))
        assert made.status_code == 201, made.text
        moved = client.post(
            "/v1/agent/creative-drafts/draft.with-signed-ref/geometry",
            headers={**h, "If-Match": made.headers["etag"]},
            json={"expected_version": 1, "page_id": "page.1",
                  "layer_id": "headline", "x": 30},
        )
        assert moved.status_code == 200, moved.text
        doc = moved.json()
        assert doc["version"] == 2
        assert doc["pages"][0]["layers"][0]["x"] == 30
        assert moved.headers["etag"] != made.headers["etag"]
        assert doc["rights_status"] == "pending_review"
        assert doc["approval_status"] == "draft"
    with r["engine"].connect() as db:
        kinds = db.execute(select(domain_events.c.event_type).where(
            domain_events.c.aggregate_type == "creative_reference_use",
        )).scalars().all()
    assert kinds.count("creative_reference.rechecked_for_draft") == 1


def test_signed_geometry_fails_closed_after_source_revocation(registry):
    r = registry
    signed_fixture(r)
    with TestClient(app_for(r)) as client:
        h = headers(client)
        made = client.post("/v1/agent/creative-drafts", headers=h, json=spec_body(r))
        assert made.status_code == 201
        with r["engine"].begin() as db:
            db.execute(update(source_grants).where(
                source_grants.c.tenant_id == TENANT,
            ).values(enabled=0))
        denied = client.post(
            "/v1/agent/creative-drafts/draft.with-signed-ref/geometry",
            headers={**h, "If-Match": made.headers["etag"]},
            json={"expected_version": 1, "page_id": "page.1",
                  "layer_id": "headline", "y": 15},
        )
        assert denied.status_code == 422
        assert client.get(
            "/v1/studio/documents/draft.with-signed-ref", headers=h,
        ).json()["version"] == 1
    with r["engine"].connect() as db:
        assert db.execute(select(domain_events.c.seq).where(
            domain_events.c.event_type == "creative_reference.rechecked_for_draft",
        )).all() == []


def test_signed_geometry_requires_if_match_and_exact_etag(registry):
    r = registry
    signed_fixture(r)
    with TestClient(app_for(r)) as client:
        h = headers(client)
        made = client.post("/v1/agent/creative-drafts", headers=h, json=spec_body(r))
        assert made.status_code == 201
        url = "/v1/agent/creative-drafts/draft.with-signed-ref/geometry"
        patch = {"expected_version": 1, "page_id": "page.1",
                 "layer_id": "headline", "x": 25}
        assert client.post(url, headers=h, json=patch).status_code == 428
        assert client.post(url, headers={**h, "If-Match": '"wrong"'},
                           json=patch).status_code == 412
        assert client.get(
            "/v1/studio/documents/draft.with-signed-ref", headers=h,
        ).json()["version"] == 1


def test_signed_geometry_rolls_back_audit_when_layer_missing(registry):
    r = registry
    signed_fixture(r)
    with TestClient(app_for(r)) as client:
        h = headers(client)
        made = client.post("/v1/agent/creative-drafts", headers=h, json=spec_body(r))
        assert made.status_code == 201
        result = client.post(
            "/v1/agent/creative-drafts/draft.with-signed-ref/geometry",
            headers={**h, "If-Match": made.headers["etag"]},
            json={"expected_version": 1, "page_id": "page.1",
                  "layer_id": "absent.layer", "x": 25},
        )
        assert result.status_code == 404
    with r["engine"].connect() as db:
        assert db.execute(select(domain_events.c.seq).where(
            domain_events.c.event_type == "creative_reference.rechecked_for_draft",
        )).all() == []


def test_direct_canvas_mutation_cannot_skip_pep_on_signed_draft(registry):
    from tapi_gate0.studio_canvas_c2 import StudioCanvasStore, MoveLayer
    from tapi_gate0.studio_e1 import StudioError
    r = registry
    signed_fixture(r)
    with TestClient(app_for(r)) as client:
        h = headers(client)
        made = client.post("/v1/agent/creative-drafts", headers=h, json=spec_body(r))
        assert made.status_code == 201
    with pytest.raises(StudioError, match="STUDIO_SIGNED_REFERENCE_RECHECK_REQUIRED"):
        StudioCanvasStore(r["engine"]).move(
            TENANT, "founder", "draft.with-signed-ref",
            MoveLayer(expected_version=1, page_id="page.1",
                      layer_id="headline", x=40),
        )


def test_signed_pep_requires_caller_owned_active_transaction(registry):
    # A read-only connection without a begun transaction must not approve
    # creative-reference reuse or leave an audit/outbox event.
    r = registry
    pep = signed_fixture(r)
    with r["engine"].connect() as db:
        assert not db.in_transaction()
        with pytest.raises(CreativeReferencePermissionDenied):
            pep.require_for_atomic_draft(
                db, token=r["token"], tenant=TENANT, actor="founder",
                document_id="fixture.no.transaction", grant_ids=grant_ids(r),
            )
    with r["engine"].connect() as db:
        assert db.execute(select(domain_events.c.seq).where(
            domain_events.c.aggregate_type == "creative_reference_use",
        )).all() == []


def test_pep_denies_indexed_publication_date_drift_not_covered_by_signature(registry):
    # The signed content payload remains intact, but the SQL indexed date
    # silently diverges. The standalone PEP must not accept this corruption.
    r = registry
    pep = signed_fixture(r)
    with r["engine"].begin() as db:
        db.execute(update(content_items).where(
            content_items.c.tenant_id == TENANT,
            content_items.c.id == r["content_id"],
        ).values(published_at="2000-01-01T00:00:00+00:00"))
    with pytest.raises(CreativeReferencePermissionDenied):
        with r["engine"].begin() as db:
            pep.require_for_atomic_draft(
                db, token=r["token"], tenant=TENANT, actor="founder",
                document_id="fixture.indexed.published.at",
                grant_ids=grant_ids(r),
            )
    with r["engine"].connect() as db:
        assert db.execute(select(domain_events.c.seq).where(
            domain_events.c.aggregate_type == "creative_reference_use",
        )).all() == []


def test_pep_denies_indexed_creator_id_drift_even_if_payload_is_unchanged(registry):
    # Construct a valid foreign-key target with an intentionally wrong SQL
    # index while copying the original signed creator's serialized payload.
    # The previous source-bound logic joined it and compared only payload IDs.
    r = registry
    pep = signed_fixture(r)
    with r["engine"].begin() as db:
        original = db.execute(select(creators).where(
            creators.c.tenant_id == TENANT,
        )).mappings().one()
        db.execute(insert(creators).values(
            **(dict(original) | {"id": "shadow.creator"}),
        ))
        db.execute(update(content_items).where(
            content_items.c.tenant_id == TENANT,
            content_items.c.id == r["content_id"],
        ).values(creator_id="shadow.creator"))
    with pytest.raises(CreativeReferencePermissionDenied):
        with r["engine"].begin() as db:
            pep.require_for_atomic_draft(
                db, token=r["token"], tenant=TENANT, actor="founder",
                document_id="fixture.indexed.creator.id",
                grant_ids=grant_ids(r),
            )
    with r["engine"].connect() as db:
        assert db.execute(select(domain_events.c.seq).where(
            domain_events.c.aggregate_type == "creative_reference_use",
        )).all() == []
