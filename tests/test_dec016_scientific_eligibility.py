"""DEC-016: source provenance, per-post scientific targeting and research card.

All provider responses are MockTransport; no real API, scraping or cost.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, func

from tapi_gate0.connectors import OfficialHttp
from tapi_gate0.mpe_sources import (ResearchSourceEntry, ResearchSourceFrame, SourceGateError,
                                    load_frame, audit_source_frame, authorized_source)
from tapi_gate0.ingestion import IngestionRequest, ingestion_records
from tapi_gate0.scientific_corpus import post_scientific_reviews
from tapi_gate0.secure_api import create_secure_app

TENANT = "dec016-tenant"
PASSWORD = "a-very-long-admin-password-for-tests-2026"
ACCOUNT = "17841400000000001"


def test_v2_creator_type_is_not_mpe_size(tmp_path):
    proof = tmp_path / "approval.txt"
    proof.write_bytes(b"synthetic research agreement fixture")
    data = dict(
        username="finance_expert",
        creator_type="financial_institution",
        business_size_class="not_applicable",
        sector_context="finance",
        sampling_stratum="finance_educators",
        audience_intent="mpe_targeted",
        audience_rationale_reference="content-aimed-at-small-businesses",
        source_evidence_reference="https://example.org/organization",
        status="approved",
        approval_reference="research-approval-ref-2026",
        approved_by="review-admin",
        approved_at=datetime.now(timezone.utc)-timedelta(days=1),
        expires_at=datetime.now(timezone.utc)+timedelta(days=30),
        allowed_operations=["business_discovery_metadata_read","local_research_metadata_export"],
        approval_proof_file=proof.name,
        approval_proof_sha256=sha256(proof.read_bytes()).hexdigest(),
    )
    entry = ResearchSourceEntry(**data)
    frame = ResearchSourceFrame(sources=[entry])
    saved = tmp_path / "frame.json"
    saved.write_text(frame.model_dump_json(), encoding="utf-8")
    restored = load_frame(saved)
    assert isinstance(restored, ResearchSourceFrame)
    assert authorized_source(restored.sources[0], tmp_path)["creator_type"] == "financial_institution"
    report = audit_source_frame(restored)
    assert report["counts_by_creator_type"]["financial_institution"] == 1
    assert report["actual_eligible_posts"] == 0
    with pytest.raises(ValueError, match="MPE_SIZE_EVIDENCE_REQUIRED"):
        ResearchSourceEntry(**{**data, "creator_type":"mpe_business"})
    with pytest.raises(ValueError, match="RESEARCH_SOURCE_UNSUITABLE"):
        ResearchSourceEntry(**{**data, "audience_intent":"not_mpe_targeted"})
    with pytest.raises(ValueError, match="RESEARCH_SOURCE_UNSUITABLE"):
        ResearchSourceEntry(**{**data, "creator_type":"unverified"})
    with pytest.raises(ValueError):
        ResearchSourceFrame(sources=[entry, entry])


def _app(tmp_path):
    app = create_secure_app("sqlite:///" + str(tmp_path / "science.db"),
                            initialize_schema=True, allow_http_local=True)
    app.state.identity_store.bootstrap(TENANT, "Research tenant", "admin", PASSWORD)
    return app


def _auth(client):
    r = client.post("/v1/auth/sessions", json={
        "tenant_id": TENANT, "username": "admin", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def _granted(client, headers):
    assert client.post("/v1/ingestion/grants", headers=headers, json={
        "platform": "instagram", "source_account_id": ACCOUNT,
        "approval_reference": "synthetic researched contract",
        "expires_at": (datetime.now(timezone.utc)+timedelta(days=10)).isoformat(),
    }).status_code == 201
    assert client.post("/v1/corpus/profiles", headers=headers, json={
        "platform": "instagram", "source_account_id": ACCOUNT,
        "sector": "other", "sampling_stratum": "finance_education",
        "evidence_reference": "profile sampling frame v2 research",
    }).status_code == 201


def _context(client, headers):
    return client.post("/v1/corpus/source-contexts", headers=headers, json={
        "platform": "instagram", "source_account_id": ACCOUNT,
        "creator_type": "fintech", "business_size_class": "not_applicable",
        "sector_context": "finance", "audience_intent": "uncertain",
        "audience_rationale_reference": "manual source-context review 2026",
    })


def _ingest(app, monkeypatch):
    monkeypatch.setenv("TAPI_OFFICIAL_METADATA_READS", "1")
    monkeypatch.setenv("TAPI_ZERO_BILLING_CONFIRMED", "1")
    monkeypatch.setenv("TAPI_INSTAGRAM_ACCESS_TOKEN", "unit-test-never-real-token")
    def response(req):
        if req.url.path.endswith("/" + ACCOUNT):
            return httpx.Response(200, json={
                "id": ACCOUNT, "username": "fintech_fixture", "followers_count": 200})
        assert req.url.path.endswith("/" + ACCOUNT + "/media")
        return httpx.Response(200, json={"data":[{
            "id":"17941400000000001", "media_type":"VIDEO",
            "media_product_type":"REELS", "permalink":"https://www.instagram.com/reel/fixture/",
            "caption":"Precificacao para pequenos negocios",
            "timestamp":"2024-09-01T12:00:00Z", "like_count":23,"comments_count":2
        }]})
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        res = app.state.ingestion_store.run(
            TENANT, IngestionRequest(platform="instagram", source_account_id=ACCOUNT,
                                     run_key="scientific-run-001", limit=1),
            http=OfficialHttp(client))
        assert res.new_records == 1
    with app.state.ingestion_store.engine.connect() as db:
        return db.execute(select(ingestion_records.c.content_id)).scalar_one()


def _review(client, headers, content_id, targeting="mpe_targeted", quality="sufficient", modes=None):
    if modes is None:
        modes = ["caption"]
    return client.post("/v1/corpus/content-reviews",headers=headers,json={
        "content_id":content_id,"targeting_status":targeting,
        "evidence_quality":quality, "evidence_reference":"reviewed-official-caption-2026",
        "evidence_sha256":sha256(b"observed caption fixture for item").hexdigest(),
        "observed_modalities":modes, "rubric_observability":"partial",
    })


def test_scientific_card_requires_post_review_not_producer_type(tmp_path, monkeypatch):
    app=_app(tmp_path)
    with TestClient(app) as c:
        headers=_auth(c)
        _granted(c,headers)
        content_id=_ingest(app, monkeypatch)
        no_context=c.get("/v1/corpus/data-card",headers=headers).json()
        assert no_context["observed"]["technically_eligible_instagram_posts"] == 1
        assert no_context["observed"]["eligible_instagram_posts"] == 0
        assert no_context["observed"]["excluded_source_context_missing"] == 1
        assert no_context["deficit"]["posts"] == 2000

        assert _context(c,headers).status_code == 201
        no_review=c.get("/v1/corpus/data-card",headers=headers).json()
        assert no_review["observed"]["excluded_unreviewed_content"] == 1
        assert no_review["observed"]["eligible_instagram_posts"] == 0

        bad=_review(c,headers,content_id,quality="partial")
        assert bad.status_code == 422
        bad2=_review(c,headers,content_id,modes=[])
        assert bad2.status_code == 422
        missing_hash=c.post("/v1/corpus/content-reviews",headers=headers,json={
            "content_id": content_id, "targeting_status": "mpe_targeted",
            "evidence_quality": "sufficient",
            "evidence_reference": "observed-caption-document",
            "observed_modalities": ["caption"]})
        assert missing_hash.status_code == 422
        assert _review(c,headers,content_id).status_code == 201
        accepted=c.get("/v1/corpus/data-card",headers=headers).json()
        assert accepted["schema_version"] == "tapi-corpus-data-card.v2"
        assert accepted["observed"]["scientifically_eligible_instagram_posts"] == 1
        assert accepted["observed"]["eligible_instagram_posts"] == 1
        assert accepted["observed"]["eligible_instagram_profiles"] == 1
        assert accepted["instagram_scientific_posts_by_creator_type"]["fintech"] == 1
        assert accepted["deficit"] == {"profiles":29,"posts":1999}
        assert not accepted["target_reached"]

        # Append-only review supersedes the older assessment; no deletion of history.
        r=_review(c,headers,content_id,targeting="not_mpe_targeted")
        assert r.status_code == 201
        rejected=c.get("/v1/corpus/data-card",headers=headers).json()
        assert rejected["observed"]["technically_eligible_instagram_posts"] == 1
        assert rejected["observed"]["scientifically_eligible_instagram_posts"] == 0
        assert rejected["observed"]["excluded_not_mpe_targeted"] == 1
        with app.state.ingestion_store.engine.connect() as db:
            assert db.execute(select(func.count()).select_from(post_scientific_reviews)).scalar_one() == 2


def test_cannot_review_unregistered_or_cross_tenant(tmp_path):
    app=_app(tmp_path)
    with TestClient(app) as c:
        headers=_auth(c)
        response=_review(c,headers,"content.nonexistent.000000")
        assert response.status_code == 403
        assert response.json()["code"] == "INGESTED_CONTENT_REQUIRED"
        response=_context(c,headers)
        assert response.status_code == 403
        assert response.json()["code"] == "CORPUS_PROFILE_REQUIRED"


def test_scientific_0005_migration_upgrade_downgrade(tmp_path, monkeypatch):
    root=__import__("pathlib").Path(__file__).resolve().parents[1]
    uri="sqlite:///" + str(tmp_path / "migration.db")
    monkeypatch.setenv("TAPI_DATABASE_URL",uri)
    config=Config(str(root / "alembic.ini"))
    config.set_main_option("script_location",str(root/"migrations"))
    command.upgrade(config,"head")
    engine=create_engine(uri)
    insp=inspect(engine)
    assert insp.has_table("corpus_source_research_contexts")
    assert insp.has_table("corpus_post_scientific_reviews")
    assert "evidence_sha256" in {c["name"] for c in insp.get_columns("corpus_post_scientific_reviews")}
    command.downgrade(config,"0004_corpus_profiles")
    assert not inspect(engine).has_table("corpus_source_research_contexts")
    assert not inspect(engine).has_table("corpus_post_scientific_reviews")
    command.upgrade(config,"head")
    assert inspect(engine).has_table("corpus_post_scientific_reviews")
    engine.dispose()
