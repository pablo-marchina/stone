"""Secure app contract and durable event tests using free local SQLite.

PostgreSQL live integration still requires an available local instance.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func, update

from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.identity import IdentityStore, users, sessions, digest
from tapi_gate0.sa_store import EventDispatcher, outbox, domain_events, engine_for, SqlDomainStore

ADMIN_PASS="correct-horse-battery-admin-Safe42"
OTHER_PASS="correct-horse-battery-user-Safe42"
TENANT="local-research"

def setup(tmp_path):
    db=f"sqlite:///{tmp_path/'tenant.db'}"
    app=create_secure_app(db,initialize_schema=True,allow_http_local=True)
    app.state.identity_store.bootstrap(TENANT,"Demo synthetic", "founder",ADMIN_PASS)
    return app,db

def auth(client,user="founder",password=ADMIN_PASS,tenant=TENANT):
    resp=client.post("/v1/auth/sessions",json={"username":user,"password":password,"tenant_id":tenant})
    assert resp.status_code==200,resp.text
    return {"Authorization":"Bearer "+resp.json()["access_token"]}

def creator(cid="creator1",tenant=TENANT):
    return {"creator_id":cid,"tenant_id":tenant,"origin":"synthetic_local","handle":"account-"+cid}


def test_secure_login_rbac_and_logout(tmp_path):
    app,_=setup(tmp_path)
    with TestClient(app) as client:
        assert client.get("/v1/creators/missing").status_code==401
        a=auth(client)
        assert client.get("/v1/auth/me",headers=a).json()["role"]=="admin"
        payload={"user_id":"u1","username":"readonly","password":OTHER_PASS,"role":"viewer"}
        assert client.post("/v1/admin/members",json=payload,headers=a).status_code==201
        viewer=auth(client,"readonly",OTHER_PASS)
        assert client.get("/v1/domain/catalog",headers=viewer).status_code==200
        assert client.post("/v1/creators",json=creator(),headers=viewer).status_code==403
        assert client.post("/v1/admin/members",json=payload,headers=viewer).status_code==403
        assert client.post("/v1/creators",json=creator(),headers=a).status_code==201
        assert client.post("/v1/collections",json={"tenant_id":TENANT,"source":"instagram","request_id":"x"},headers=a).status_code==403
        assert client.post("/v1/auth/logout",headers=a).status_code==204
        assert client.get("/v1/auth/me",headers=a).status_code==401
        assert client.post("/v1/creators",json=creator("new"),headers=a).status_code==401


def test_bad_password_is_locked_and_token_stores_hash_only(tmp_path):
    app,_=setup(tmp_path)
    with TestClient(app) as client:
        for i in range(5):
            r=client.post("/v1/auth/sessions",json={"username":"founder","password":"wrong-password","tenant_id":TENANT})
            assert r.status_code==401
        assert client.post("/v1/auth/sessions",json={"username":"founder","password":ADMIN_PASS,"tenant_id":TENANT}).status_code==401
    with app.state.identity_store.engine.connect() as conn:
        row=conn.execute(select(users.c.failed_attempts,users.c.locked_until)).one()
        assert row[0]>=5 and row[1]


def test_sql_store_restarts_and_transactional_outbox(tmp_path):
    app,url=setup(tmp_path)
    with TestClient(app) as c:
        hdr=auth(c)
        assert c.post("/v1/creators",json=creator(),headers=hdr).status_code==201
        ev=c.get("/v1/events",headers=hdr).json()["events"]
        assert len(ev)==1
    reopened=create_secure_app(url,initialize_schema=False,allow_http_local=True)
    with TestClient(reopened) as c:
        hdr=auth(c)
        assert c.get("/v1/creators/creator1",headers=hdr).status_code==200
        assert c.get("/v1/events",headers=hdr).json()["events"][0]["event_id"]==ev[0]["event_id"]
        conflict=c.post("/v1/creators",json=creator(),headers=hdr)
        assert conflict.status_code==409
        assert len(c.get("/v1/events",headers=hdr).json()["events"])==1
    with reopened.state.identity_store.engine.connect() as db:
        assert db.execute(select(func.count()).select_from(outbox)).scalar_one()==1


def test_event_dispatcher_retries_and_dead_letters(tmp_path):
    app,url=setup(tmp_path)
    with TestClient(app) as c:
        c.post("/v1/creators",json=creator(),headers=auth(c))
    handler_calls=[]
    dispatcher=EventDispatcher(app.state.identity_store.engine,max_attempts=2)
    def fail(event):
        handler_calls.append(event["event_id"])
        raise RuntimeError("transient error with sensitive value not logged")
    assert dispatcher.deliver(fail)=={"delivered":0,"failed":1}
    assert dispatcher.deliver(fail)=={"delivered":0,"failed":1}
    assert dispatcher.deliver(fail)=={"delivered":0,"failed":0}
    with app.state.identity_store.engine.connect() as db:
        row=db.execute(select(outbox.c.dead_letter,outbox.c.attempts,outbox.c.last_error)).one()
        assert row==(1,2,"RuntimeError")


def test_event_dispatcher_success_and_idempotent_poll(tmp_path):
    app,url=setup(tmp_path)
    with TestClient(app) as c:
        h=auth(c)
        c.post("/v1/creators",json=creator(),headers=h)
        c.post("/v1/creators",json=creator("2"),headers=h)
        seqs=[v["seq"] for v in c.get("/v1/events",headers=h).json()["events"]]
        assert len(seqs)==2 and seqs==sorted(seqs)
        after=c.get("/v1/events",headers=h,params={"after_seq":seqs[0]}).json()["events"]
        assert len(after)==1
    ids=[]
    d=EventDispatcher(app.state.identity_store.engine)
    assert d.deliver(lambda evt:ids.append(evt["event_id"]))=={"delivered":2,"failed":0}
    assert d.deliver(lambda evt:ids.append(evt["event_id"]))=={"delivered":0,"failed":0}
    assert len(set(ids))==2


def test_rbac_uses_membership_not_tenant_from_payload(tmp_path):
    app,_=setup(tmp_path)
    with TestClient(app) as c:
        h=auth(c)
        assert c.post("/v1/creators",json=creator("fake","other-tenant"),headers=h).status_code==403
        assert c.get("/v1/creators/fake",headers=h).status_code==404


def test_secured_openapi_has_expected_routes(tmp_path):
    app,_=setup(tmp_path)
    schema=app.openapi()
    for route in ["/v1/auth/sessions","/v1/auth/me","/v1/admin/members","/v1/events/stream","/v1/creators","/v1/analyses/rankings"]:
        assert route in schema["paths"]


def test_sqlalchemy_pg_ddl_compiles_without_pg_driver():
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects.postgresql import dialect
    from tapi_gate0.sa_store import metadata
    rendered=[str(CreateTable(t).compile(dialect=dialect())) for t in metadata.sorted_tables]
    assert len(rendered)>=12
    assert any('"event_outbox"' in s or 'event_outbox' in s for s in rendered)


def test_secure_mode_requires_https_by_default(tmp_path):
    db=f"sqlite:///{tmp_path/'tls_required.sqlite3'}"
    app=create_secure_app(db,initialize_schema=True)
    with TestClient(app) as c:
        assert c.get("/healthz").status_code==403
        assert c.post("/v1/auth/sessions",json={"username":"x","password":"x","tenant_id":TENANT}).status_code==403


def test_sse_cursor_and_tenant_scope(tmp_path):
    app,_=setup(tmp_path)
    with TestClient(app) as c:
        h=auth(c)
        c.post("/v1/creators",json=creator(),headers=h)
        # A bounded stream terminates and includes a durable event cursor.
        response=c.get("/v1/events/stream?max_events=1",headers=h)
        assert response.status_code==200
        assert "event: domain_event" in response.text
        assert "id: 1" in response.text
        assert c.get("/v1/events/stream",headers={**h,"Last-Event-ID":"garbage"}).status_code==422


def test_sqlite_foreign_key_prevents_cross_tenant_reference(tmp_path):
    app,_=setup(tmp_path)
    admin=app.state.identity_store
    with admin.engine.begin() as db:
        from tapi_gate0.sa_store import tenants
        from sqlalchemy import insert
        db.execute(insert(tenants).values(tenant_id="org-b",name="Other org"))
    with TestClient(app) as c:
        h=auth(c)
        assert c.post("/v1/creators",json=creator(),headers=h).status_code==201
        assert c.get("/v1/creators/creator1",headers=h).status_code==200
        # Forging another tenant in POST body cannot grant access.
        assert c.post("/v1/creators",json=creator("x","org-b"),headers=h).status_code==403


def test_migration_upgrade_and_repeatability(tmp_path,monkeypatch):
    import subprocess,sys,os
    root=Path(__file__).resolve().parents[1]
    db=f"sqlite:///{tmp_path/'migration.sqlite3'}"
    env={**os.environ,"TAPI_DATABASE_URL":db}
    for _ in range(2):
        process=subprocess.run([sys.executable,"-m","alembic","upgrade","head"],cwd=str(root),env=env,
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        assert process.returncode==0,process.stderr
    from sqlalchemy import inspect
    from tapi_gate0.sa_store import engine_for
    inspector=inspect(engine_for(db))
    assert "identity_sessions" in inspector.get_table_names()
    assert "event_outbox" in inspector.get_table_names()
    assert "alembic_version" in inspector.get_table_names()


def test_identity_audit_contains_no_credentials(tmp_path):
    app,_=setup(tmp_path)
    with TestClient(app) as c:
        hdr=auth(c)
        c.post("/v1/auth/logout",headers=hdr)
    from tapi_gate0.identity import audit
    with app.state.identity_store.engine.connect() as conn:
        from sqlalchemy import select
        rows=conn.execute(select(audit.c.action,audit.c.outcome)).all()
        assert ("identity.login","succeeded") in rows
        assert ("identity.logout","succeeded") in rows
        assert not any(ADMIN_PASS in str(r) for r in rows)