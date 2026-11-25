"""Real local API/SQL handoff: recommendation trace is provenance, not rights."""
import json
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from tapi_gate0 import agent_trace_draft_handoff as handoff
from tapi_gate0.agent_graph_checkpoints import agent_graph_events
from tapi_gate0.identity import memberships
from tapi_gate0.sa_store import content_items, domain_events, outbox, tenants
from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.studio_e1 import studio_documents, studio_versions
from test_architecture_vertical_synthetic import local_system, _trace, _brief, NOW, PASSWORD

PATH = '/v1/agent/local-graph/creative-draft'
RUN = 'trace.draft'


def request():
    return {'run_id': RUN, 'plan': {'mode': 'recomendar', 'content_id': 'fixture.post',
            'origin': 'synthetic_local', 'as_of': NOW.isoformat(), 'min_age_days': 14},
            'draft': _brief()}


def complete(client, headers):
    receipt = _trace(client, headers, 'recomendar', RUN)
    assert receipt['status'] == 'TRACE_RECORDED'
    return receipt


def counts(app):
    with app.state.identity_store.engine.connect() as db:
        return tuple(db.scalar(select(func.count()).select_from(t)) for t in (
            studio_documents, studio_versions, domain_events, outbox, agent_graph_events))


def test_trace_draft_provenance_and_versioned_edit(local_system):
    app, client, headers = local_system
    trace = complete(client, headers)
    before = counts(app)
    response = client.post(PATH, headers=headers, json=request())
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc['version'] == 1 and doc['approval_status'] == 'draft'
    assert doc['rights_status'] == 'pending_review'
    assert response.headers['cache-control'] == 'private, no-store'
    assert counts(app) == tuple(a+b for a,b in zip(before,(1,1,1,1,0)))
    with app.state.identity_store.engine.connect() as db:
        event = db.execute(select(domain_events).where(domain_events.c.aggregate_type == handoff.AGGREGATE)).mappings().one()
        proof = json.loads(event['payload'])
        assert proof['trace_chain_sha256'] == trace['chain_sha256']
        assert proof['trace_revision'] == 6
        raw = db.scalar(select(studio_versions.c.payload))
        assert proof['initial_document_sha256'] == sha256(raw.encode()).hexdigest()
        assert len(proof['operator_brief_sha256']) == 64
        assert proof['operator_authored_brief'] is True
        assert all(proof[k] is False for k in ('scientific_validation','external_rights_verified','publication_allowed','production_approved'))
        assert db.scalar(select(func.count()).select_from(outbox).where(outbox.c.seq == event['seq'])) == 1
        assert 'Organize seu estoque' not in event['payload']
    duplicate = client.post(PATH, headers=headers, json=request())
    assert duplicate.status_code == 409
    assert counts(app) == tuple(a+b for a,b in zip(before,(1,1,1,1,0)))
    amended = client.post('/v1/agent/creative-drafts/design.vertical/text-patches',
        headers={**headers, 'If-Match': response.headers['etag']}, json={
            'expected_version':1,'page_id':'page.1','layer_id':'headline','text':'Revise seu estoque'})
    assert amended.status_code == 200, amended.text
    assert amended.json()['version'] == 2
    assert amended.json()['approval_status'] == 'draft'


def test_missing_and_open_trace_denied_without_writes(local_system):
    app, client, headers = local_system
    req = request()
    before = counts(app)
    assert client.post(PATH, headers=headers, json=req).status_code == 409
    assert counts(app) == before
    step = {k:v for k,v in req.items() if k != 'draft'}
    assert client.post('/v1/agent/local-graph/step', headers=headers, json=step).status_code == 200
    before = counts(app)
    assert client.post(PATH, headers=headers, json=req).status_code == 409
    assert counts(app) == before


def test_source_drift_rejected(local_system):
    app, client, headers = local_system
    complete(client, headers)
    with app.state.identity_store.engine.begin() as db:
        data = json.loads(db.scalar(select(content_items.c.payload)))
        data['caption'] = 'Changed evidence after trace'
        db.execute(update(content_items).values(payload=json.dumps(data)))
    before = counts(app)
    res = client.post(PATH, headers=headers, json=request())
    assert res.status_code == 409 and res.json()['detail'] == 'TRACE_DRAFT_SOURCE_DRIFT_RESTART_REQUIRED'
    assert counts(app) == before


@pytest.mark.parametrize('kind', ['plan','reference','grant','creative_mode'])
def test_mismatched_scope_denied(local_system, kind):
    app, client, headers = local_system
    complete(client, headers)
    req = request()
    if kind == 'plan': req['plan']['min_age_days'] = 15
    if kind == 'reference': req['draft']['brief']['reference_content_ids'] = ['other.post']
    if kind == 'grant': req['draft']['reference_grant_ids'] = {'fixture.post':'grant.fixture'}
    if kind == 'creative_mode': req['plan']['mode'] = 'gerar_criativo'
    before = counts(app)
    assert client.post(PATH, headers=headers, json=req).status_code == 409
    assert counts(app) == before


def test_auth_role_actor_and_tenant_boundaries(local_system):
    app, client, headers = local_system
    complete(client, headers)
    before = counts(app)
    assert client.post(PATH, json=request()).status_code == 401
    for role, status in [('researcher',403),('editor',409)]:
        assert client.post('/v1/admin/members', headers=headers, json={
            'user_id':role,'username':role,'password':PASSWORD,'role':role}).status_code == 201
        login = client.post('/v1/auth/sessions',json={'username':role,'tenant_id':'tenantA','password':PASSWORD})
        other = {'Authorization':'Bearer '+login.json()['access_token']}
        assert client.post(PATH, headers=other, json=request()).status_code == status
    with app.state.identity_store.engine.begin() as db:
        db.execute(insert(tenants).values(tenant_id='tenantB',name='Other fixture'))
        db.execute(insert(memberships).values(user_id='founder',tenant_id='tenantB',role='admin'))
    login = client.post('/v1/auth/sessions',json={'username':'founder','tenant_id':'tenantB','password':PASSWORD})
    other = {'Authorization':'Bearer '+login.json()['access_token']}
    assert client.post(PATH, headers=other, json=request()).status_code == 409
    assert counts(app)[:2] == before[:2]
    assert counts(app)[4] == before[4]


def test_outbox_failure_rolls_back_document_and_event(local_system, monkeypatch):
    app, client, headers = local_system
    complete(client, headers)
    before = counts(app)
    original = handoff.insert
    def fail(table):
        if table is outbox:
            raise SQLAlchemyError('simulated outbox failure')
        return original(table)
    monkeypatch.setattr(handoff, 'insert', fail)
    res = client.post(PATH, headers=headers, json=request())
    assert res.status_code == 409 and res.json()['detail'] == 'TRACE_DRAFT_TRANSACTION_ABORTED'
    assert counts(app) == before


def test_opt_in_and_loopback_only(local_system, tmp_path):
    app, client, headers = local_system
    disabled = create_secure_app(f'sqlite:///{tmp_path / "disabled.sqlite"}',initialize_schema=True,allow_http_local=True)
    try:
        with TestClient(disabled) as c:
            assert c.post(PATH,json=request()).status_code == 404
    finally:
        disabled.state.identity_store.engine.dispose()
    with TestClient(app, base_url='https://stone.example', client=('203.0.113.25',5001)) as remote:
        assert remote.post(PATH, headers={**headers,'X-Forwarded-For':'127.0.0.1'},json=request()).status_code == 403


def test_concurrent_duplicate_draft_keeps_single_document_and_provenance(local_system):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    app, client, headers = local_system
    complete(client, headers)
    before = counts(app)
    barrier = Barrier(2)
    def submit():
        with TestClient(app) as peer:
            barrier.wait(timeout=5)
            return peer.post(PATH, headers=headers, json=request()).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(submit), pool.submit(submit)
        assert sorted([a.result(timeout=20), b.result(timeout=20)]) == [201, 409]
    assert counts(app) == tuple(a+b for a,b in zip(before,(1,1,1,1,0)))


def test_trace_draft_reaches_offline_svg_export(local_system):
    from pathlib import Path
    import shutil
    import subprocess
    node = shutil.which('node')
    if not node:
        pytest.skip('NODE_REQUIRED_FOR_STUDIO_EXPORT_E2E')
    app, client, headers = local_system
    complete(client, headers)
    response = client.post(PATH, headers=headers, json=request())
    assert response.status_code == 201
    edit = client.post('/v1/agent/creative-drafts/design.vertical/text-patches',
        headers={**headers, 'If-Match': response.headers['etag']}, json={
            'expected_version':1,'page_id':'page.1','layer_id':'headline','text':'Revise seu estoque'})
    assert edit.status_code == 200
    result = subprocess.run([node, 'scripts/a11_studio_export_probe.mjs'],
        input=json.dumps(edit.json(), ensure_ascii=False), cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, 'TRACE_DRAFT_SVG_EXPORT_DENIED'
    proof = json.loads(result.stdout)
    assert proof['status'] == 'LOCAL_DRAFT_SVG_BYTES_VERIFIED'
    assert proof['watermark_verified'] is True and proof['version'] == 2
    assert proof['source_immutable'] is True
    assert all(proof[k] is False for k in ('external_rights_verified','publication_allowed','production_approved','gates_released'))
