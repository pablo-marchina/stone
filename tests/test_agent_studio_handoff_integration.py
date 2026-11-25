"""B2→C2: a tenant-bound evidence reference survives the editable design handoff.

Metadata fixture only: no Meta API call, scientific approval or production action.
"""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import insert

from tapi_gate0.domain import ContentItem, Creator, MetricsCreate, Origin, MediaType
from tapi_gate0.identity import memberships
from tapi_gate0.sa_store import tenants, creators, content_items, metrics_snapshots
from tapi_gate0.secure_api import create_secure_app

PASSWORD = "local-integration-password-123456"


def test_agent_creative_spec_to_editable_studio_document(tmp_path):
    app = create_secure_app(f"sqlite:///{tmp_path / 'handoff.sqlite'}",
                            initialize_schema=True, allow_http_local=True)
    auth = app.state.identity_store
    auth.bootstrap("orgA", "Organization A", "founder", PASSWORD)
    now = datetime(2026, 11, 4, tzinfo=timezone.utc)
    creator = Creator(tenant_id="orgA", creator_id="sebrae.creator", origin=Origin.INSTAGRAM,
                      handle="sebrae", created_at=now)
    post = ContentItem(tenant_id="orgA", content_id="sebrae.item", creator_id=creator.creator_id,
                       origin=Origin.INSTAGRAM, media_type=MediaType.REELS,
                       published_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
                       source_url="https://www.instagram.com/reel/Example123/",
                       caption="Conteúdo de exemplo dirigido a negócios.",
                       is_synthetic=False, created_at=now)
    snap = MetricsCreate(tenant_id="orgA", content_id=post.content_id,
                         snapshot_id="metric.first", observed_at=now,
                         followers_measured_at=now, likes=50, comments=10, follower_count=10000)
    with auth.engine.begin() as db:
        db.execute(insert(tenants).values(tenant_id="orgB", name="Organization B"))
        db.execute(insert(memberships).values(user_id="founder", tenant_id="orgB", role="admin"))
        db.execute(insert(creators).values(tenant_id="orgA", id=creator.creator_id,
                origin=creator.origin.value, payload=creator.model_dump_json()))
        db.execute(insert(content_items).values(tenant_id="orgA", id=post.content_id,
                creator_id=post.creator_id, origin=post.origin.value,
                published_at=post.published_at.isoformat(), payload=post.model_dump_json()))
        db.execute(insert(metrics_snapshots).values(tenant_id="orgA", id=snap.snapshot_id,
                content_id=post.content_id, observed_at=snap.observed_at.isoformat(),
                payload=snap.model_dump_json()))
    with TestClient(app) as client:
        def headers(tenant):
            session = client.post("/v1/auth/sessions", json={
                "username":"founder", "password":PASSWORD, "tenant_id":tenant})
            assert session.status_code == 200, session.text
            return {"Authorization":"Bearer " + session.json()["access_token"]}
        a, b = headers("orgA"), headers("orgB")
        evidence = client.get("/v1/agent/evidence/sebrae.item", headers=a)
        assert evidence.status_code == 200 and evidence.json()["snapshot_id"] == "metric.first"
        assert evidence.json()["caption_is_untrusted_data"] is True
        assert client.get("/v1/agent/evidence/sebrae.item", headers=b).status_code == 404
        brief = {"spec_id":"spec.handoff", "objective":"Criar uma peça educativa para MPE",
                 "headline":"Cuide do caixa", "body":"Separe custos e receitas.",
                 "cta":"Revise o planejamento", "platform_intent":"instagram_feed",
                 "reference_content_ids":["sebrae.item"]}
        # External metadata remains readable for analysis, but creative
        # reuse requires a distinct signed, operationally enforced grant.
        denied = client.post("/v1/agent/creative-spec", headers=a, json=brief)
        assert denied.status_code == 422
        assert denied.json()["detail"] == "CREATIVE_REFERENCE_NOT_VERIFIED"
        assert client.post("/v1/agent/creative-spec", headers=b, json=brief).status_code == 422

        # Keep B2→Studio editable-draft integration tested using only local
        # source-free synthetic records; this is not publication approval.
        synthetic_creator = Creator(
            tenant_id="orgA", creator_id="fixture.creator",
            origin=Origin.SYNTHETIC, handle="fixture", created_at=now,
        )
        synthetic_post = ContentItem(
            tenant_id="orgA", content_id="fixture.item",
            creator_id="fixture.creator", origin=Origin.SYNTHETIC,
            media_type=MediaType.IMAGE, published_at=now,
            caption="Exemplo sintético local.", is_synthetic=True, created_at=now,
        )
        with auth.engine.begin() as db:
            db.execute(insert(creators).values(
                tenant_id="orgA", id=synthetic_creator.creator_id,
                origin=synthetic_creator.origin.value,
                payload=synthetic_creator.model_dump_json(),
            ))
            db.execute(insert(content_items).values(
                tenant_id="orgA", id=synthetic_post.content_id,
                creator_id=synthetic_post.creator_id, origin=synthetic_post.origin.value,
                published_at=synthetic_post.published_at.isoformat(),
                payload=synthetic_post.model_dump_json(),
            ))
        safe_brief = {**brief, "reference_content_ids": ["fixture.item"]}
        spec_response = client.post("/v1/agent/creative-spec", headers=a, json=safe_brief)
        assert spec_response.status_code == 200, spec_response.text
        drafted = client.post("/v1/studio/documents", headers=a,
                json={"document_id":"design.handoff", "spec":spec_response.json()})
        assert drafted.status_code == 201, drafted.text
        first = drafted.json()
        assert first["reference_content_ids"] == ["fixture.item"]
        assert first["reference_status"] == "unverified"
        assert first["rights_status"] == "pending_review"
        assert first["approval_status"] == "draft"
        edited = client.post("/v1/studio/documents/design.handoff/text-patches", headers=a,
                json={"expected_version":1, "page_id":"page.1",
                      "layer_id":"headline", "text":"Planeje seu caixa"})
        assert edited.status_code == 200 and edited.json()["version"] == 2
        assert client.get("/v1/studio/documents/design.handoff", headers=b).status_code == 404
        old = client.get("/v1/studio/documents/design.handoff/versions/1",headers=a)
        assert old.status_code == 200 and old.json()["pages"][0]["layers"][0]["text"] == "Cuide do caixa"
