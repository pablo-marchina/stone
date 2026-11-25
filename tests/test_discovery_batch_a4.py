"""CAP-001/A4 tests. No network or actual Meta tokens are used."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import insert, select, func

from tapi_gate0.connectors import ConnectorError, OfficialHttp, Platform
from tapi_gate0.discovery_batch import (
    BatchLimits, BatchManifest, TechnicalDiscoveryBatch, selection_plan,
)
from tapi_gate0.ingestion import IngestionStore, GrantCreate, ingestion_records
from tapi_gate0.sa_store import metadata, tenants, engine_for, content_items, metrics_snapshots, domain_events

VIEWER = "17841459971757521"
SOURCES = [
    ("sebrae", "17841403133066329", "cross_sector_institution"),
    ("mpe_example", "17841411111111111", "commerce_research_sample"),
]
TENANT = "local-research"
TOKEN = "fictional-fixture-token-not-real"


@pytest.fixture(autouse=True)
def switches(monkeypatch):
    monkeypatch.setenv("TAPI_BD_TECHNICAL_INGEST", "1")
    monkeypatch.setenv("TAPI_OFFICIAL_METADATA_READS", "1")
    monkeypatch.setenv("TAPI_ZERO_BILLING_CONFIRMED", "1")


def manifest(*, approved=2, expired=False) -> BatchManifest:
    now = datetime.now(timezone.utc)
    rows = []
    for i, (username, ident, stratum) in enumerate(SOURCES):
        is_approved = i < approved
        row = {
            "username": username, "expected_ig_id": ident,
            "sampling_stratum": stratum,
            "audience_intent": "mpe_targeted",
            "source_evidence_reference": "docs/test-authorized-metadata-reference",
            "status": "approved" if is_approved else "candidate",
        }
        if is_approved:
            row.update(audience_rationale_reference="docs/recorded-research-target-rationale",
                       approval_reference="operator-evidence-" + ident,
                       expires_at=(now - timedelta(days=1) if expired else now + timedelta(days=30)),
                       allowed_operations=["business_discovery_metadata_read"])
        rows.append(row)
    return BatchManifest(schema_version="tapi-bd-technical-batch.v1", sources=rows)


def db(tmp_path, grants=2):
    engine = engine_for("sqlite:///" + (tmp_path / "a4.sqlite").as_posix())
    metadata.create_all(engine)
    with engine.begin() as c:
        c.execute(insert(tenants).values(tenant_id=TENANT, name="A4 test tenant"))
    store = IngestionStore(engine)
    for _, ident, _ in SOURCES[:grants]:
        store.grant(TENANT, "admin", GrantCreate(
            platform=Platform.INSTAGRAM, source_account_id=ident,
            approval_reference="operator-evidence-" + ident,
            expires_at=datetime.now(timezone.utc)+timedelta(days=30)))
    return engine, store


def fake_http(*, likes_offset=0, items=2, same_ids_across_sources=False):
    calls = []
    def callback(req):
        calls.append(req)
        assert req.url.host == "graph.facebook.com"
        assert req.url.path == "/v26.0/" + VIEWER
        assert req.headers["Authorization"] == "Bearer " + TOKEN
        assert "access_token" not in str(req.url)
        fields = req.url.params["fields"]
        found = next((s for s in SOURCES if f"username({s[0]})" in fields), None)
        assert found is not None
        index = SOURCES.index(found)
        source_id = found[1]
        data = [{
            "id": str(18000000000000000+(0 if same_ids_across_sources else index*1000)+j),
            "media_type": "CAROUSEL_ALBUM",
            "media_product_type": "FEED",
            "permalink": f"https://www.instagram.com/p/Fixture{index}a{j}/",
            "timestamp": "2026-10-01T12:00:00+0000",
            "like_count": 100 + likes_offset * int(index==0 and j==0),
            "comments_count": 2,
            "caption": "Contexto de negocios locais",
        } for j in range(items)]
        return httpx.Response(200, json={
            "id":VIEWER,
            "business_discovery": {
                "id": source_id, "username": found[0],
                "followers_count": 1234, "media_count": 123,
                "media": {"data":data,"paging":{"cursors":{}}},
            },
        })
    client = httpx.Client(transport=httpx.MockTransport(callback))
    return OfficialHttp(client=client, instagram_version="v26.0"), calls, client


def batch_limits(persist=12):
    return BatchLimits(max_sources=3,page_limit=10,max_pages=4,persist_limit=persist)


def test_plan_does_not_access_any_source():
    m = manifest(approved=1)
    plan = selection_plan(m, batch_limits())
    assert plan["status"] == "PLAN_ONLY_NO_EXTERNAL_READ"
    assert plan["profiles_in_manifest"] == 2
    assert plan["profiles_marked_approved_unverified"] == 1
    assert plan["source_approvals_verified"] is False
    assert plan["max_official_requests"] == 4
    assert plan["scientific_corpus_accepted"] is False
    assert plan["manifest_sha256"] == m.fingerprint()


def test_manifest_rejects_duplicates_and_unsuitable_sources():
    m = manifest()
    with pytest.raises(ValidationError,match="BD_BATCH_DUPLICATE_SOURCE"):
        BatchManifest(schema_version=m.schema_version, sources=[m.sources[0], m.sources[0]])
    bad = m.sources[0].model_dump()
    bad["audience_intent"]="not_mpe_targeted"
    with pytest.raises(ValidationError,match="BD_BATCH_NOT_MPE_TARGETED"):
        BatchManifest(schema_version=m.schema_version, sources=[bad])
    bad["audience_intent"]="mpe_targeted"
    bad["username"]="academy_fellow_stone"
    with pytest.raises(ValidationError,match="BD_BATCH_INVALID_SOURCE"):
        BatchManifest(schema_version=m.schema_version, sources=[bad])
    with pytest.raises(ValidationError,match="BD_BATCH_PERSIST_EXCEEDS_REQUEST_BUDGET"):
        BatchLimits(page_limit=2,max_pages=2,persist_limit=12)


def test_preflights_all_grants_before_first_network_request(tmp_path):
    engine,store = db(tmp_path, grants=1)
    transport,calls,client = fake_http()
    with pytest.raises(ConnectorError,match="VALID_SOURCE_GRANT_REQUIRED"):
        TechnicalDiscoveryBatch(store).execute(TENANT,manifest(),batch_limits(),VIEWER,
                                           batch_key="bdbatch-pending",token=TOKEN,http=transport)
    assert calls == []
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(content_items)).scalar_one() == 0
    client.close();engine.dispose()


def test_expired_manifest_blocks_even_with_active_grant(tmp_path):
    engine,store = db(tmp_path)
    transport,calls,client = fake_http()
    with pytest.raises(ConnectorError,match="BD_BATCH_MANIFEST_APPROVAL_EXPIRED"):
        TechnicalDiscoveryBatch(store).execute(TENANT,manifest(expired=True),batch_limits(),VIEWER,
                                           batch_key="bdbatch-expired",token=TOKEN,http=transport)
    assert calls == []
    client.close();engine.dispose()


def test_flags_block_before_request(tmp_path,monkeypatch):
    engine,store = db(tmp_path)
    transport,calls,client = fake_http()
    monkeypatch.setenv("TAPI_ZERO_BILLING_CONFIRMED", "0")
    with pytest.raises(ConnectorError,match="BD_BATCH_FLAGS_REQUIRED"):
        TechnicalDiscoveryBatch(store).execute(TENANT,manifest(),batch_limits(),VIEWER,
                                           batch_key="bdbatch-no-cost-flag",token=TOKEN,http=transport)
    assert calls == []
    client.close();engine.dispose()


def test_two_source_batch_idempotency_snapshot_reuse_and_provenance(tmp_path):
    engine,store = db(tmp_path)
    first_http,calls,client = fake_http()
    first = TechnicalDiscoveryBatch(store).execute(TENANT,manifest(),batch_limits(),VIEWER,
                                            batch_key="bdbatch-first01",token=TOKEN,http=first_http)
    assert first["status"] == "BATCH_COMPLETED"
    assert len(calls) == 2 and first["counts"]["new_records"] == 4
    assert first["selection"]["attempted"] == 2
    assert first["coverage"]["unique_technical_posts_after"] == 4
    assert first["coverage"]["profiles_with_persisted_technical_posts"] == 2
    assert all(x["audit_all_traces_valid"] and x["audit_observations"] == 2 for x in first["sources"])
    assert first["scientific_admissions_from_batch"] == 0
    assert all(len(s["evidence"]) == 2 for s in first["sources"])
    assert TOKEN not in json.dumps(first)
    assert first["coverage"]["scientific_reference_comparable"] is False
    again_http,calls2,client2 = fake_http(likes_offset=10)
    second = TechnicalDiscoveryBatch(store).execute(TENANT,manifest(),batch_limits(),VIEWER,
                                              batch_key="bdbatch-again02",token=TOKEN,http=again_http)
    assert len(calls2) == 2
    assert second["counts"]["new_records"] == 0
    assert second["counts"]["refreshed_records"] == 1
    assert second["counts"]["unchanged_duplicate_records"] == 3
    assert second["coverage"]["unique_technical_posts_after"] == 4
    assert second["coverage"]["unique_technical_posts_added"] == 0
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(content_items)).scalar_one() == 4
        assert c.execute(select(func.count()).select_from(ingestion_records)).scalar_one() == 4
        assert c.execute(select(func.count()).select_from(metrics_snapshots)).scalar_one() == 5
        assert c.execute(select(func.count()).select_from(domain_events).where(
            domain_events.c.event_type == "business_discovery.metadata_observed")).scalar_one() == 8
    # Same key must fail before network, not duplicate a prior run.
    third_http,calls3,client3 = fake_http()
    with pytest.raises(ConnectorError,match="BD_BATCH_RUN_KEY_ALREADY_USED"):
        TechnicalDiscoveryBatch(store).execute(TENANT,manifest(),batch_limits(),VIEWER,
                                           batch_key="bdbatch-first01",token=TOKEN,http=third_http)
    assert calls3 == []
    for c in (client,client2,client3):c.close()
    engine.dispose()


def test_bounded_expansion_persists_five_not_just_three(tmp_path):
    engine,store = db(tmp_path,grants=1)
    transport,calls,client = fake_http(items=5)
    limits=BatchLimits(max_sources=1,page_limit=10,max_pages=1,persist_limit=5)
    result=TechnicalDiscoveryBatch(store).execute(TENANT,manifest(approved=1),limits,VIEWER,
                                               batch_key="bdbatch-five-items",token=TOKEN,http=transport)
    assert len(calls)==1
    assert result["counts"]["new_records"]==5
    assert result["coverage"]["unique_technical_posts_after"]==5
    assert result["sources"][0]["audit_observations"]==5
    client.close();engine.dispose()


def test_failure_stops_subsequent_sources_without_crediting_progress(tmp_path):
    engine,store = db(tmp_path)
    requests=[]
    def mismatch(req):
        requests.append(req)
        return httpx.Response(200,json={"id":VIEWER,"business_discovery":{
            "id":"17841499999999999","username":"sebrae","followers_count":42,
            "media":{"data":[],"paging":{}}}})
    client=httpx.Client(transport=httpx.MockTransport(mismatch))
    transport=OfficialHttp(client=client,instagram_version="v26.0")
    result=TechnicalDiscoveryBatch(store).execute(TENANT,manifest(),batch_limits(),VIEWER,
                                             batch_key="bdbatch-wrong-target",token=TOKEN,http=transport)
    assert result["status"]=="BATCH_STOPPED_ON_SOURCE_FAILURE"
    assert result["failure_code"]=="BD_TARGET_ACCOUNT_MISMATCH"
    assert result["selection"]["attempted"]==1
    assert len(requests)==1
    assert result["counts"]["new_records"]==0
    client.close();engine.dispose()


def test_grant_reference_mismatch_blocks_all_sources_before_network(tmp_path):
    engine,store=db(tmp_path)
    target=manifest()
    incompatible=target.sources[1].model_dump()
    incompatible["approval_reference"]="an-unrelated-approval-reference"
    amended=BatchManifest(schema_version=target.schema_version,
                          sources=[target.sources[0], incompatible])
    transport,calls,client=fake_http()
    with pytest.raises(ConnectorError,match="BD_BATCH_GRANT_REFERENCE_MISMATCH"):
        TechnicalDiscoveryBatch(store).execute(TENANT,amended,batch_limits(),VIEWER,
                                           batch_key="bdbatch-grant-mismatch",token=TOKEN,http=transport)
    assert not calls
    client.close();engine.dispose()


def test_all_candidates_do_not_invoke_network_even_with_valid_db_grants(tmp_path):
    engine,store=db(tmp_path)
    transport,calls,client=fake_http()
    with pytest.raises(ConnectorError,match="BD_BATCH_NO_APPROVED_SOURCES"):
        TechnicalDiscoveryBatch(store).execute(TENANT,manifest(approved=0),batch_limits(),VIEWER,
                                           batch_key="bdbatch-candidates",token=TOKEN,http=transport)
    assert calls == []
    client.close();engine.dispose()


def test_empty_provider_data_does_not_create_synthetic_observations(tmp_path):
    engine,store=db(tmp_path,grants=1)
    transport,calls,client=fake_http(items=0)
    result=TechnicalDiscoveryBatch(store).execute(TENANT,manifest(approved=1),batch_limits(),VIEWER,
                                           batch_key="bdbatch-empty-source",token=TOKEN,http=transport)
    assert result["status"]=="BATCH_NO_ELIGIBLE_OBSERVATIONS"
    assert result["counts"]["new_records"]==0
    assert result["sources"][0]["audit_all_traces_valid"]
    assert result["coverage"]["unique_technical_posts_after"]==0
    assert len(calls)==1
    client.close();engine.dispose()


def test_cross_source_media_id_collision_stops_without_double_count(tmp_path):
    engine, store = db(tmp_path)
    transport, calls, client = fake_http(same_ids_across_sources=True)
    result = TechnicalDiscoveryBatch(store).execute(TENANT, manifest(), batch_limits(), VIEWER,
        batch_key="bdbatch-cross-source", token=TOKEN, http=transport)
    assert len(calls) == 2
    assert result["status"] == "BATCH_STOPPED_ON_SOURCE_FAILURE"
    assert result["failure_code"] == "BD_CROSS_SOURCE_MEDIA_ID_CONFLICT"
    assert result["counts"]["new_records"] == 2
    assert result["coverage"]["unique_technical_posts_after"] == 2
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(content_items)).scalar_one() == 2
        assert c.execute(select(func.count()).select_from(ingestion_records)).scalar_one() == 2
    client.close();engine.dispose()


def test_concurrent_cross_source_collision_is_serialized(tmp_path):
    """Exercise the storage invariant independently of the acquisition gate."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from tapi_gate0.connectors import NormalizedItem
    from tapi_gate0.domain import MediaType
    engine, store = db(tmp_path)
    barrier = Barrier(2)
    def persist(source):
        name, ident, _ = source
        item = NormalizedItem(platform=Platform.INSTAGRAM, source_account_id=ident,
            source_item_id="18000000000000000", creator_handle=name,
            media_type=MediaType.CAROUSEL, source_url="https://www.instagram.com/p/FixtureCollision/",
            published_at=datetime.now(timezone.utc)-timedelta(days=40),
            likes=100, comments=2, follower_count=1234, metadata_only=True)
        # Deliberately test the lower-level storage guard, not a second
        # acquisition reservation. No provider request is involved.
        barrier.wait(timeout=10)
        try:
            return store._persist_item(TENANT, item)
        except ConnectorError as exc:
            return exc.code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(persist, SOURCES))
        assert sorted(outcomes) == ["BD_CROSS_SOURCE_MEDIA_ID_CONFLICT", "created"]
        with engine.connect() as c:
            for table in (ingestion_records, content_items, metrics_snapshots):
                assert c.execute(select(func.count()).select_from(table)).scalar_one() == 1
    finally:
        engine.dispose()


def test_concurrent_technical_runs_are_blocked_before_network(tmp_path, monkeypatch):
    """The new acquisition gate prevents overlap; a later collision still fails."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from tapi_gate0.discovery_technical import TechnicalDiscoveryRequest, TechnicalDiscoveryService, audit_run
    from tapi_gate0.ingestion import ingestion_runs
    engine, store = db(tmp_path)
    transport, calls, client = fake_http(items=1, same_ids_across_sources=True)
    entered, release = Event(), Event()
    original = IngestionStore._persist_item
    def hold_first(self, tenant, item, **kwargs):
        entered.set()
        if not release.wait(timeout=15):
            raise AssertionError("test did not release the first acquisition")
        return original(self, tenant, item, **kwargs)
    monkeypatch.setattr(IngestionStore, "_persist_item", hold_first)
    def run(source):
        name, ident, _ = source
        return TechnicalDiscoveryService(store).execute(TENANT,
            TechnicalDiscoveryRequest(username=name, expected_ig_id=ident,
                viewer_ig_id=VIEWER, run_key="concurrent-bd-"+name, persist_limit=1),
            token=TOKEN, http=transport)
    first_key = "concurrent-bd-"+SOURCES[0][0]
    second_key = "concurrent-bd-"+SOURCES[1][0]
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run, SOURCES[0])
            try:
                assert entered.wait(timeout=15), "first run did not reach persistence"
                with pytest.raises(ConnectorError, match="ACCOUNT_INGESTION_IN_PROGRESS"):
                    run(SOURCES[1])
                assert len(calls) == 1
                with engine.connect() as c:
                    assert c.execute(select(ingestion_runs.c.run_key).where(
                        ingestion_runs.c.run_key == second_key)).first() is None
            finally:
                release.set()
            assert future.result(timeout=15)["status"] == "BD_TECHNICAL_METADATA_COMMITTED"
        # The blocked attempt did not reserve a run or make a provider call.
        # After the first run finishes, the same media ID from another source
        # must still fail, even though the second reservation is now allowed.
        with pytest.raises(ConnectorError, match="BD_CROSS_SOURCE_MEDIA_ID_CONFLICT"):
            run(SOURCES[1])
        assert len(calls) == 2
        for key, valid in ((first_key, True), (second_key, False)):
            audited = audit_run(engine, TENANT, key)
            assert audited["all_traces_valid"] is valid
            assert audited["observations"] == int(valid)
        with engine.connect() as c:
            for table in (ingestion_records, content_items, metrics_snapshots):
                assert c.execute(select(func.count()).select_from(table)).scalar_one() == 1
    finally:
        release.set()
        client.close(); engine.dispose()
