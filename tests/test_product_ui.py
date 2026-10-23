"""Read-model, multi-tenant, static shell and security regression checks."""
from fastapi.testclient import TestClient
from sqlalchemy import insert
from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.sa_store import tenants

PWD = "local-example-password-12345"


def app_for(tmp_path):
    app = create_secure_app(f"sqlite:///{tmp_path / 'product_ui.db'}", initialize_schema=True, allow_http_local=True)
    app.state.identity_store.bootstrap("org-1", "org-1", "owner", PWD)
    with app.state.identity_store.engine.begin() as conn:
        conn.execute(insert(tenants).values(tenant_id="org-2", name="org-2"))
    return app


def bearer(client):
    r = client.post('/v1/auth/sessions', json={"username":"owner", "password":PWD, "tenant_id":"org-1"})
    assert r.status_code == 200
    return {"Authorization":"Bearer " + r.json()["access_token"]}


def test_ui_shell_is_free_static_and_hardened(tmp_path):
    app = app_for(tmp_path)
    with TestClient(app) as client:
        r = client.get('/app/')
        assert r.status_code == 200
        assert '<title>TAPI Stone' in r.text
        assert "script-src 'self'" in r.headers['content-security-policy']
        assert r.headers['x-content-type-options'] == 'nosniff'
        assert r.headers['cache-control'] == 'no-store'
        assert client.get('/app/main.mjs').status_code == 200
        assert client.get('/app/events.mjs').status_code == 200
        assert client.get('/app/style.css').status_code == 200
        # Static HTML contains no tenant data, credential or artificial KPI number.
        assert PWD not in r.text
        assert client.get('/v1/ui/overview').status_code == 401


def test_ui_overview_counts_only_authenticated_tenant(tmp_path):
    app = app_for(tmp_path)
    with TestClient(app) as client:
        h = bearer(client)
        original = client.get('/v1/ui/overview', headers=h)
        assert original.status_code == 200, original.text
        payload = original.json()
        assert payload['tenant_id'] == 'org-1'
        assert payload['counts']['posts'] == 0
        assert payload['counts']['creators'] == 0
        assert payload['external_actions_enabled'] is False
        assert payload['financial_spend_ceiling_brl'] == 0
        created = client.post('/v1/creators', headers=h, json={
            'creator_id':'creator-x', 'tenant_id':'org-1', 'origin':'synthetic_local', 'handle':'@local'
        })
        assert created.status_code == 201, created.text
        data = client.get('/v1/ui/overview', headers=h).json()
        assert data['counts']['creators'] == 1
        assert data['counts']['events'] == 1
        assert data['recent_events'][0]['aggregate_id'] == 'creator-x'
        assert 'payload' not in data['recent_events'][0]
        assert 'password' not in str(data)
        client.post('/v1/auth/logout', headers=h)
        assert client.get('/v1/ui/overview', headers=h).status_code == 401


def test_ui_other_org_cannot_infer_counts(tmp_path):
    app = app_for(tmp_path)
    with app.state.identity_store.engine.begin() as conn:
        from tapi_gate0.sa_store import creators
        from sqlalchemy import insert
        import json
        conn.execute(insert(creators).values(tenant_id='org-2', id='secret-creator',origin='synthetic_local',payload=json.dumps({'private':'other-tenant'})))
    with TestClient(app) as c:
        data=c.get('/v1/ui/overview',headers=bearer(c)).json()
        assert data['counts']['creators'] == 0
        assert 'secret-creator' not in str(data)


def test_product_ui_in_openapi_and_external_still_denied(tmp_path):
    app=app_for(tmp_path)
    assert '/v1/ui/overview' in app.openapi()['paths']
    assert app.openapi()['paths']['/v1/ui/overview']['get']['security'] == [{'BearerAuth': []}]
    with TestClient(app) as c:
        h=bearer(c)
        denied=c.post('/v1/publications', headers=h, json={'tenant_id':'org-1','source':'instagram','request_id':'x'})
        assert denied.status_code==403
