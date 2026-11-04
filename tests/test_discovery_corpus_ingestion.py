"""Curated Business Discovery write: only offline mocks, never real API or billing."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import httpx
import pytest
from sqlalchemy import (Table, Column, String, ForeignKeyConstraint,
                        insert, select, func)

from tapi_gate0.connectors import ConnectorError, OfficialHttp, Platform
from tapi_gate0.mpe_sources import SourceEntry, ResearchSourceEntry
from tapi_gate0.scientific_corpus import (source_research_contexts, SourceResearchContextCreate,
                                          register_research_source_context, PostScientificReviewCreate,
                                          record_scientific_post_review)
from tapi_gate0.discovery_ingestion import (
    DiscoveryCorpusRequest, DiscoveryCorpusService, business_discovery_provenance)
from tapi_gate0.ingestion import (
    IngestionStore, GrantCreate, source_grants, ingestion_records, ingestion_runs)
from tapi_gate0.sa_store import metadata, engine_for, tenants, metrics_snapshots, content_items
from tapi_gate0 import identity  # noqa: F401

NOW = datetime.now(timezone.utc)
TENANT = "pilot-tenant"
TARGET = "17841400011122233"
VIEWER = "17841459971757521"
TOKEN = "test-meta-credential-never-print"


def source(tmp_path, *, approved=True, write_scope=True, username="first_mpe_test", creator_type="mpe_business", sector_context="food"):
    doc_dir = tmp_path / "proofs"
    doc_dir.mkdir(exist_ok=True)
    proof = b"test fixture operator approval proof, not real-world authorization"
    (doc_dir / "source.txt").write_bytes(proof)
    data = {
        "username": username,
        "creator_type": creator_type,
        "business_size_class": "micro" if creator_type == "mpe_business" else "not_applicable",
        "business_size_evidence_reference": "reviewed-local-size-source" if creator_type == "mpe_business" else None,
        "sector_context": sector_context,
        "sampling_stratum": "food_micro" if sector_context == "food" else "finance_fintech",
        "audience_intent": "mpe_targeted",
        "audience_rationale_reference": "reviewed-source-MPE-audience-hypothesis",
        "source_evidence_reference": "reviewed-local-profile-source",
        "status": "approved" if approved else "candidate",
    }
    if approved:
        data.update({
            "approval_reference": "approval-specific-corpus-use",
            "approved_by": "review_admin",
            "approved_at": NOW - timedelta(days=1),
            "expires_at": NOW + timedelta(days=60),
            "allowed_operations": [
                "business_discovery_metadata_read", "local_research_metadata_export"
            ] + (["corpus_metadata_ingest"] if write_scope else []),
            "approval_proof_file": "source.txt",
            "approval_proof_sha256": sha256(proof).hexdigest(),
        })
    return ResearchSourceEntry(**data), doc_dir


def setup_store(tmp_path, *, grant=True, registry=True, context=True, creator_type="mpe_business", sector_context="food"):
    if "corpus_profiles" not in metadata.tables:
        Table("corpus_profiles", metadata,
              Column("tenant_id", String(128), primary_key=True),
              Column("platform", String(32), primary_key=True),
              Column("source_account_id", String(128), primary_key=True),
              Column("sector", String(24), nullable=False),
              Column("sampling_stratum", String(80), nullable=False),
              Column("evidence_reference", String(512), nullable=False),
              Column("registered_at", String(40), nullable=False),
              ForeignKeyConstraint(["tenant_id", "platform", "source_account_id"],
                                   ["ingestion_source_grants.tenant_id",
                                    "ingestion_source_grants.platform",
                                    "ingestion_source_grants.source_account_id"]))
    engine = engine_for("sqlite:///" + str(tmp_path / "pilot.sqlite3"))
    metadata.create_all(engine)
    store = IngestionStore(engine)
    with engine.begin() as db:
        db.execute(insert(tenants).values(tenant_id=TENANT, name="Pilot tenant"))
    if grant:
        store.grant(TENANT, "admin", GrantCreate(
            platform=Platform.INSTAGRAM, source_account_id=TARGET,
            approval_reference="approval-specific-corpus-use",
            expires_at=NOW + timedelta(days=60)))
    if registry:
        with engine.begin() as db:
            db.execute(insert(metadata.tables["corpus_profiles"]).values(
                tenant_id=TENANT, platform="instagram", source_account_id=TARGET,
                sector="food" if sector_context == "food" else "other",
                sampling_stratum="food_micro" if sector_context == "food" else "finance_fintech",
                evidence_reference="reviewed-local-profile-source",
                registered_at=NOW.isoformat()))
        if context:
            register_research_source_context(engine, TENANT, "research_admin",
                SourceResearchContextCreate(
                    platform=Platform.INSTAGRAM, source_account_id=TARGET,
                    creator_type=creator_type,
                    business_size_class="micro" if creator_type == "mpe_business" else "not_applicable",
                    business_size_evidence_reference="reviewed-local-size-source" if creator_type == "mpe_business" else None,
                    sector_context=sector_context,
                    audience_intent="mpe_targeted",
                    audience_rationale_reference="reviewed-source-MPE-audience-hypothesis"))
    return store


def graph(state, calls):
    def responder(req):
        calls.append(req)
        assert req.url.host == "graph.facebook.com"
        assert req.url.path == "/v23.0/" + VIEWER
        assert req.headers["Authorization"] == "Bearer " + TOKEN
        assert "access_token" not in req.url.params
        assert "business_discovery.username(first_mpe_test)" in req.url.params["fields"]
        return httpx.Response(200, json={
            "id": VIEWER,
            "business_discovery": {
                "id": state.get("account_id", TARGET),
                "username": "first_mpe_test",
                "followers_count": state.get("followers", 100),
                "media_count": 4,
                "media": {"data": [
                    {"id": "17900000000011111", "media_type": "VIDEO",
                     "media_product_type": "REELS", "like_count": state["likes"],
                     "comments_count": 5, "timestamp": "2026-09-01T12:00:00+0000",
                     "permalink": "https://www.instagram.com/reel/valid1/"},
                    {"id": "17900000000022222", "media_type": "CAROUSEL_ALBUM",
                     "like_count": 10, "comments_count": 2,
                     "timestamp": "2026-11-02T12:00:00+0000",
                     "permalink": "https://www.instagram.com/p/recent1/"}
                ]},
            },
        })
    return responder


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setenv("TAPI_MPE_PERSISTENCE_ENABLED", "1")
    monkeypatch.setenv("TAPI_OFFICIAL_METADATA_READS", "1")
    monkeypatch.setenv("TAPI_ZERO_BILLING_CONFIRMED", "1")
    monkeypatch.setenv("TAPI_INSTAGRAM_ACCESS_TOKEN", TOKEN)


def request(key="pilot-0001", account=TARGET):
    return DiscoveryCorpusRequest(username="first_mpe_test", expected_ig_id=account,
                                  run_key=key, limit=5, max_pages=1)


def invoke(store, s, proof_dir, state, key="pilot-0001"):
    calls = []
    with httpx.Client(transport=httpx.MockTransport(graph(state, calls))) as c:
        outcome = DiscoveryCorpusService(store).ingest(
            TENANT, s, proof_dir, request(key), http=OfficialHttp(c), token=TOKEN)
    return outcome, calls


def test_persist_idempotent_snapshot_refresh_and_provenance(tmp_path):
    store = setup_store(tmp_path)
    s, doc = source(tmp_path)
    state = {"likes": 20}
    first, calls = invoke(store, s, doc, state)
    assert len(calls) == 1 and first["new_records"] == 1
    assert first["status"] == "DISCOVERY_TECHNICAL_METADATA_COMMITTED"
    assert first["scientifically_eligible_posts_created"] == 0
    assert first["excluded_items"]["too_recent"] == 1
    with store.engine.connect() as db:
        assert db.execute(select(func.count()).select_from(ingestion_records)).scalar_one() == 1
        assert db.execute(select(func.count()).select_from(metrics_snapshots)).scalar_one() == 1
        assert db.execute(select(func.count()).select_from(content_items)).scalar_one() == 1
        assert db.execute(select(source_grants.c.technical_verified_at)).scalar_one()
    repeated, _ = invoke(store, s, doc, state, "pilot-0002")
    assert repeated["new_records"] == 0 and repeated["duplicate_records"] == 1
    state["likes"] = 25
    refreshed, _ = invoke(store, s, doc, state, "pilot-0003")
    assert refreshed["refreshed_records"] == 1
    with store.engine.connect() as db:
        assert db.execute(select(func.count()).select_from(ingestion_records)).scalar_one() == 1
        assert db.execute(select(func.count()).select_from(content_items)).scalar_one() == 1
        assert db.execute(select(func.count()).select_from(metrics_snapshots)).scalar_one() == 2
        assert db.execute(select(func.count()).select_from(ingestion_runs)).scalar_one() == 3
        rows = db.execute(select(business_discovery_provenance)).mappings().all()
        assert len(rows) == 3
        assert {r["approval_reference"] for r in rows} == {"approval-specific-corpus-use"}
        assert all(r["acquisition_method"] == "graph_business_discovery" for r in rows)
        assert all(len(r["media_integrity_sha256"]) == 64 for r in rows)


def test_unapproved_or_write_scope_missing_cannot_call_meta(tmp_path):
    store = setup_store(tmp_path)
    calls = []
    for approved, write in [(False, False), (True, False)]:
        s, doc = source(tmp_path, approved=approved, write_scope=write)
        with httpx.Client(transport=httpx.MockTransport(graph({"likes": 1}, calls))) as c:
            with pytest.raises(ConnectorError):
                DiscoveryCorpusService(store).ingest(
                    TENANT, s, doc, request(), http=OfficialHttp(c), token=TOKEN)
    assert calls == []


def test_missing_grant_blocks_before_network(tmp_path):
    store = setup_store(tmp_path, grant=False, registry=False)
    s, doc = source(tmp_path)
    calls = []
    with httpx.Client(transport=httpx.MockTransport(graph({"likes": 1}, calls))) as c:
        with pytest.raises(ConnectorError) as err:
            DiscoveryCorpusService(store).ingest(
                TENANT, s, doc, request(), http=OfficialHttp(c), token=TOKEN)
    assert err.value.code == "VALID_SOURCE_GRANT_REQUIRED"
    assert calls == []


def test_discovered_ig_mismatch_marks_run_failed_and_persists_nothing(tmp_path):
    store = setup_store(tmp_path)
    s, doc = source(tmp_path)
    calls = []
    with httpx.Client(transport=httpx.MockTransport(
            graph({"likes": 1, "account_id": "17841400011122299"}, calls))) as c:
        with pytest.raises(ConnectorError) as err:
            DiscoveryCorpusService(store).ingest(
                TENANT, s, doc, request(), http=OfficialHttp(c), token=TOKEN)
    assert err.value.code == "DISCOVERY_ACCOUNT_MISMATCH"
    assert len(calls) == 1
    with store.engine.connect() as db:
        assert db.execute(select(func.count()).select_from(ingestion_records)).scalar_one() == 0
        assert db.execute(select(ingestion_runs.c.status)).scalar_one() == "failed"


def test_instagram_test_account_cannot_be_promoted_to_corpus(tmp_path):
    store = setup_store(tmp_path)
    s, doc = source(tmp_path, username="instagram")
    with pytest.raises(ConnectorError) as err:
        DiscoveryCorpusService(store).ingest(
            TENANT, s, doc,
            request().model_copy(update={"username": "instagram"}), token=TOKEN)
    assert err.value.code == "TEST_ACCOUNT_EXCLUDED_FROM_CORPUS"


def test_off_by_default_persistence_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("TAPI_MPE_PERSISTENCE_ENABLED")
    store = setup_store(tmp_path)
    s, doc = source(tmp_path)
    with pytest.raises(ConnectorError) as err:
        DiscoveryCorpusService(store).ingest(TENANT, s, doc, request(), token=TOKEN)
    assert err.value.code == "MPE_PERSISTENCE_DISABLED"


def test_existing_corpus_data_card_counts_only_valid_ingested_mpe(tmp_path):
    # The production data-card code is the source of truth for research KPIs.
    from tapi_gate0.corpus import corpus_data_card
    store = setup_store(tmp_path)
    s, doc = source(tmp_path)
    result, _ = invoke(store, s, doc, {"likes": 20})
    assert result["new_records"] == 1
    card = corpus_data_card(store.engine, TENANT)
    assert card["observed"]["technically_eligible_instagram_posts"] == 1
    assert card["observed"]["technically_eligible_instagram_profiles"] == 1
    assert card["observed"]["eligible_instagram_posts"] == 0
    assert card["observed"]["scientifically_eligible_instagram_posts"] == 0
    assert card["observed"]["excluded_unreviewed_content"] == 1
    assert card["observed"]["excluded_too_recent"] == 0
    assert card["instagram_technical_posts_by_operator_sector"]["food"] == 1
    assert card["deficit"] == {"profiles": 30, "posts": 2000}
    assert card["target_reached"] is False


def test_provenance_failure_rolls_back_item_and_snapshot(tmp_path):
    from tapi_gate0.connectors import NormalizedItem
    from tapi_gate0.domain import MediaType
    store = setup_store(tmp_path)
    item = NormalizedItem(
        platform=Platform.INSTAGRAM,
        source_account_id=TARGET,
        source_item_id="17900000000044444",
        creator_handle="first_mpe_test",
        media_type=MediaType.REELS,
        source_url="https://www.instagram.com/reel/roll-back/",
        published_at=NOW - timedelta(days=25),
        likes=15, comments=2, follower_count=250,
        denominator_quality="observed_current_only",
    )

    def failing_evidence_write(db, content_id):
        raise RuntimeError("simulated provenance ledger failure")

    with pytest.raises(RuntimeError, match="simulated provenance"):
        store._persist_item(TENANT, item, provenance_writer=failing_evidence_write)
    with store.engine.connect() as db:
        assert db.execute(select(func.count()).select_from(content_items)).scalar_one() == 0
        assert db.execute(select(func.count()).select_from(ingestion_records)).scalar_one() == 0
        assert db.execute(select(func.count()).select_from(metrics_snapshots)).scalar_one() == 0
        assert db.execute(select(func.count()).select_from(business_discovery_provenance)).scalar_one() == 0


def test_v1_source_is_rejected_before_network(tmp_path):
    store = setup_store(tmp_path)
    legacy = SourceEntry(
        username="first_mpe_test", sector="food", size_band="micro",
        sampling_stratum="food_micro", size_evidence_reference="legacy-evidence",
        source_evidence_reference="reviewed-local-profile-source",
        status="candidate")
    calls = []
    with httpx.Client(transport=httpx.MockTransport(graph({"likes": 3}, calls))) as c:
        with pytest.raises(ConnectorError) as err:
            DiscoveryCorpusService(store).ingest(
                TENANT, legacy, tmp_path, request(), http=OfficialHttp(c), token=TOKEN)
    assert err.value.code == "SOURCE_FRAME_V2_REQUIRED"
    assert not calls


def test_missing_scientific_source_context_blocks_before_network(tmp_path):
    store = setup_store(tmp_path, context=False)
    src, proof_dir = source(tmp_path)
    calls = []
    with httpx.Client(transport=httpx.MockTransport(graph({"likes": 3}, calls))) as c:
        with pytest.raises(ConnectorError) as err:
            DiscoveryCorpusService(store).ingest(
                TENANT, src, proof_dir, request(), http=OfficialHttp(c), token=TOKEN)
    assert err.value.code == "SOURCE_RESEARCH_CONTEXT_REQUIRED"
    assert not calls


def test_fintech_source_can_be_ingested_technically_not_scientifically(tmp_path):
    store = setup_store(tmp_path, creator_type="fintech", sector_context="finance")
    src, proof_dir = source(tmp_path, creator_type="fintech", sector_context="finance")
    result, calls = invoke(store, src, proof_dir, {"likes": 20})
    assert len(calls) == 1
    assert result["new_records"] == 1
    from tapi_gate0.corpus import corpus_data_card
    card = corpus_data_card(store.engine, TENANT)
    assert card["observed"]["technically_eligible_instagram_posts"] == 1
    assert card["observed"]["scientifically_eligible_instagram_posts"] == 0
    assert card["observed"]["excluded_unreviewed_content"] == 1


def test_separate_manual_review_makes_existing_technical_post_scientific(tmp_path):
    store = setup_store(tmp_path)
    src, proof_dir = source(tmp_path)
    result, calls = invoke(store, src, proof_dir, {"likes": 20})
    assert result["new_records"] == 1
    with store.engine.connect() as db:
        item_id = db.execute(select(ingestion_records.c.content_id)).scalar_one()
    # This is a synthetic reviewer fixture, not a caption obtained from Graph
    # Business Discovery. The source evidence is assumed to exist independently.
    record_scientific_post_review(store.engine, TENANT, "test_reviewer",
        PostScientificReviewCreate(
            content_id=item_id, targeting_status="mpe_targeted",
            evidence_quality="sufficient",
            evidence_reference="privately-observed-content-fixture",
            evidence_sha256=sha256(b"privately-reviewed-fixture-caption").hexdigest(),
            observed_modalities=["caption"], rubric_observability="partial"))
    from tapi_gate0.corpus import corpus_data_card
    card = corpus_data_card(store.engine, TENANT)
    assert card["observed"]["technically_eligible_instagram_posts"] == 1
    assert card["observed"]["scientifically_eligible_instagram_posts"] == 1
    assert card["observed"]["eligible_instagram_posts"] == 1


def test_source_frame_v2_context_mismatch_fails_before_network(tmp_path):
    # A fintech cannot reuse a previously registered MPE producer context
    # merely because it has the same Instagram user ID and a read grant.
    store = setup_store(tmp_path)
    src, proof_dir = source(tmp_path, creator_type="fintech", sector_context="finance")
    calls = []
    with httpx.Client(transport=httpx.MockTransport(graph({"likes": 3}, calls))) as c:
        with pytest.raises(ConnectorError) as err:
            DiscoveryCorpusService(store).ingest(
                TENANT, src, proof_dir, request(), http=OfficialHttp(c), token=TOKEN)
    assert err.value.code == "CORPUS_REGISTRATION_MISMATCH"
    assert calls == []


def test_source_context_audience_mismatch_fails_before_network(tmp_path):
    from sqlalchemy import update
    store = setup_store(tmp_path)
    src, proof_dir = source(tmp_path)
    with store.engine.begin() as db:
        db.execute(update(source_research_contexts).values(audience_intent="uncertain"))
    calls = []
    with httpx.Client(transport=httpx.MockTransport(graph({"likes": 3}, calls))) as c:
        with pytest.raises(ConnectorError) as err:
            DiscoveryCorpusService(store).ingest(
                TENANT, src, proof_dir, request(), http=OfficialHttp(c), token=TOKEN)
    assert err.value.code == "SOURCE_RESEARCH_CONTEXT_MISMATCH"
    assert calls == []


def test_admin_route_requires_session_and_private_source_frame(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from tapi_gate0.secure_api import create_secure_app

    monkeypatch.delenv("TAPI_MPE_APPROVED_FRAME_PATH", raising=False)
    monkeypatch.delenv("TAPI_MPE_APPROVAL_PROOFS_DIR", raising=False)
    app = create_secure_app(
        "sqlite:///" + str(tmp_path / "api-rbac.sqlite3"),
        initialize_schema=True, allow_http_local=True)
    app.state.identity_store.bootstrap(
        "tenant-rbac", "Org for tests", "admin",
        "long-mock-password-no-provider-2026")
    request_body = {
        "username": "first_mpe_test",
        "expected_ig_id": TARGET,
        "run_key": "rbac-local-no-meta-001",
        "limit": 5, "max_pages": 1,
    }
    with TestClient(app) as client:
        denied = client.post("/v1/ingestion/business-discovery/runs",
                             json=request_body)
        assert denied.status_code == 401
        signed_in = client.post("/v1/auth/sessions", json={
            "tenant_id": "tenant-rbac", "username": "admin",
            "password": "long-mock-password-no-provider-2026"})
        assert signed_in.status_code == 200, signed_in.text
        allowed_to_check = client.post(
            "/v1/ingestion/business-discovery/runs",
            headers={"Authorization": "Bearer " + signed_in.json()["access_token"]},
            json=request_body)
        assert allowed_to_check.status_code == 403
        assert allowed_to_check.json()["code"] == "APPROVED_SOURCE_FRAME_NOT_CONFIGURED"
