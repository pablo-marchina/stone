from datetime import timedelta
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update, func

from tapi_gate0.connectors import NormalizedItem, Platform
from tapi_gate0.corpus import CorpusProfileCreate, register_profile
from tapi_gate0.corpus_inventory import InventoryFilter, list_inventory, get_inventory_item
from tapi_gate0.domain import MediaType
from tapi_gate0.identity import memberships
from tapi_gate0.ingestion import GrantCreate, IngestionStore, source_grants, ingestion_records
from tapi_gate0.sa_store import content_items, metrics_snapshots, domain_events, outbox, tenants
from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.storage import now_utc

PASSWORD = "inventory-test-password-2026"
ACCOUNT = "17841400011122233"


def seed(engine, tenant, handle="test_profile"):
    now = now_utc()
    store = IngestionStore(engine)
    store.grant(tenant, "founder", GrantCreate(platform=Platform.INSTAGRAM,
        source_account_id=ACCOUNT, approval_reference="test-fixture-inventory-grant",
        expires_at=now+timedelta(days=30)))
    register_profile(engine, tenant, CorpusProfileCreate(platform=Platform.INSTAGRAM,
        source_account_id=ACCOUNT, sector="food", sampling_stratum="food_fixture",
        evidence_reference="test-fixture-registered-profile"))
    with engine.begin() as db:
        db.execute(update(source_grants).where(source_grants.c.tenant_id==tenant)
            .values(technical_verified_at=now_utc().isoformat()))
    for i, kind in enumerate((MediaType.REELS, MediaType.CAROUSEL, MediaType.IMAGE)):
        item = NormalizedItem(platform=Platform.INSTAGRAM, source_account_id=ACCOUNT,
            source_item_id=str(17900000000011111+i), creator_handle=handle, media_type=kind,
            source_url="https://www.instagram.com/p/Fixture123/",
            published_at=now-timedelta(days=30+i), caption="private fixture caption",
            likes=10+i, comments=2, follower_count=100,
            denominator_quality="observed_current_only", metadata_only=True)
        assert store._persist_item(tenant,item)=="created"
        if i==0:
            assert store._persist_item(tenant,item.model_copy(update={"likes":20}))=="refreshed"
    return store


@pytest.fixture
def app(tmp_path):
    app = create_secure_app("sqlite:///"+str(tmp_path/"inventory.sqlite3"),
        initialize_schema=True,allow_http_local=True)
    identity = app.state.identity_store
    identity.bootstrap("tenantA","A","founder",PASSWORD)
    with identity.engine.begin() as db:
        db.execute(insert(tenants).values(tenant_id="tenantB",name="B"))
        db.execute(insert(memberships).values(user_id="founder",tenant_id="tenantB",role="admin"))
    seed(identity.engine,"tenantA","alpha_fixture")
    seed(identity.engine,"tenantB","beta_fixture")
    yield app
    identity.engine.dispose()


def auth(client,tenant="tenantA",username="founder"):
    r=client.post("/v1/auth/sessions",json={"username":username,"tenant_id":tenant,"password":PASSWORD})
    assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["access_token"]}


def test_inventory_pagination_filters_and_snapshot_history(app):
    engine=app.state.identity_store.engine
    page=list_inventory(engine,"tenantA",InventoryFilter(limit=1))
    assert page["total_filtered"]==3 and page["next_offset"]==1
    assert page["scope"]=="registered_external_metadata_with_current_technical_grant"
    assert not page["scientific_corpus"] and not page["ranking"]
    first=page["items"][0]
    assert first["handle"]=="alpha_fixture" and first["media_type"]=="reels"
    assert first["latest_snapshot"]["likes"]==20 and first["valid_snapshot_count"]==2
    assert first["caption_available"] and not first["caption_text_returned"]
    assert "private fixture caption" not in json.dumps(page)
    assert not first["media_processing_allowed"]
    assert first["scientific_eligibility"]=="NOT_EVALUATED_BY_INVENTORY"
    second=list_inventory(engine,"tenantA",InventoryFilter(offset=1,limit=1))
    assert second["items"][0]["content_id"]!=first["content_id"]
    assert list_inventory(engine,"tenantA",InventoryFilter(media_type="imagem"))["total_filtered"]==1
    assert list_inventory(engine,"tenantA",InventoryFilter(search="BETA"))["total_filtered"]==0
    assert list_inventory(engine,"tenantA",InventoryFilter(search="ALPHA",sector="food"))["total_filtered"]==3
    detail=get_inventory_item(engine,"tenantA",first["content_id"],snapshot_limit=1)
    assert detail["snapshots"][0]["likes"]==20 and detail["next_snapshot_offset"]==1
    older=get_inventory_item(engine,"tenantA",first["content_id"],snapshot_offset=1,snapshot_limit=1)
    assert older["snapshots"][0]["likes"]==10 and older["next_snapshot_offset"] is None


def test_authenticated_scope_no_mutation_and_revocation(app):
    engine=app.state.identity_store.engine
    path="/v1/corpus/inventory"
    with TestClient(app) as client:
        assert client.get(path).status_code==401
        a,b=auth(client),auth(client,"tenantB")
        tables=(content_items,metrics_snapshots,domain_events,outbox)
        with engine.connect() as db:
            before=[db.scalar(select(func.count()).select_from(t)) for t in tables]
        r=client.get(path,headers=a,params={"limit":1})
        assert r.status_code==200,r.text
        assert r.headers["cache-control"]=="private, no-store"
        cid=r.json()["items"][0]["content_id"]
        # Stable external IDs may coincide across tenants; payload never crosses.
        assert client.get(path+"/"+cid,headers=b).json()["item"]["handle"]=="beta_fixture"
        assert client.get(path+"/"+cid,headers=a).json()["item"]["handle"]=="alpha_fixture"
        assert client.get(path,headers=a,params={"tenant_id":"tenantB"}).status_code==422
        assert client.get(path,headers=a,params={"limit":101}).status_code==422
        assert client.get(path+"/not-found",headers=a).status_code==404
        assert client.post(path,headers=a,json={}).status_code==405
        with engine.connect() as db:
            assert [db.scalar(select(func.count()).select_from(t)) for t in tables]==before
        assert client.post("/v1/admin/members",headers=a,json={"user_id":"reader","username":"reader",
            "password":PASSWORD,"role":"viewer"}).status_code==201
        assert client.get(path,headers=auth(client,username="reader")).status_code==403
        IngestionStore(engine).revoke_grant("tenantA","founder",Platform.INSTAGRAM,ACCOUNT)
        assert client.get(path,headers=a).json()["total_filtered"]==0
        assert client.get(path+"/"+cid,headers=a).status_code==404
        assert client.get(path+"/"+cid,headers=b).status_code==200


def test_invalid_snapshot_and_inconsistent_post_identity_not_exposed(app):
    engine=app.state.identity_store.engine
    first=list_inventory(engine,"tenantA",InventoryFilter(limit=1))["items"][0]
    cid=first["content_id"]
    sid=first["latest_snapshot"]["snapshot_id"]
    with engine.begin() as db:
        blob=db.scalar(select(metrics_snapshots.c.payload).where(metrics_snapshots.c.tenant_id=="tenantA",
            metrics_snapshots.c.id==sid))
        payload=json.loads(blob);payload["tenant_id"]="tenantB"
        db.execute(update(metrics_snapshots).where(metrics_snapshots.c.tenant_id=="tenantA",
            metrics_snapshots.c.id==sid).values(payload=json.dumps(payload)))
    assert get_inventory_item(engine,"tenantA",cid)["item"]["latest_snapshot"]["likes"]==10
    with engine.begin() as db:
        blob=db.scalar(select(content_items.c.payload).where(content_items.c.tenant_id=="tenantA",content_items.c.id==cid))
        payload=json.loads(blob);payload["tenant_id"]="tenantB"
        db.execute(update(content_items).where(content_items.c.tenant_id=="tenantA",content_items.c.id==cid)
            .values(payload=json.dumps(payload)))
    from tapi_gate0.connectors import ConnectorError
    with pytest.raises(ConnectorError,match="INVENTORY_CONTENT_NOT_FOUND"):
        get_inventory_item(engine,"tenantA",cid)
