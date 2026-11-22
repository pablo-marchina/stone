"""A05 operational-shape PEP tests with disposable, fictitious signed grants.

Every signature, source, approval digest, role and identifier below is a LOCAL
TEST FIXTURE. These checks do not establish rights to actual third-party media.
No external services, provisioning or publication.
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from test_creative_reference_registry_a05 import (
    registry, provision, TENANT, PASSWORD,
)
from tapi_gate0.creative_reference_rights_a05 import ReferenceOperation
from tapi_gate0.creative_reference_pep_a05 import (
    CreativeReferencePEP, CreativeReferencePermissionDenied,
)
from tapi_gate0.identity import memberships
from tapi_gate0.ingestion import source_grants
from tapi_gate0.sa_store import domain_events, outbox
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
