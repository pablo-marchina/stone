"""Authenticated API/SQLite tests of local generated proposal preview and acceptance."""
import json
from hashlib import sha256

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from tapi_gate0 import agent_creative_proposals_local as proposals
from tapi_gate0.sa_store import content_items, domain_events, outbox
from test_architecture_vertical_synthetic import local_system, _trace, NOW, PASSWORD
from test_agent_trace_draft_handoff import counts

PREFIX = '/v1/agent/local-graph/'
PREVIEW = PREFIX + 'creative-proposals'
ACCEPT = PREFIX + 'creative-proposal-draft'
RUN = 'proposal.run'


def request():
    return {'run_id': RUN, 'plan': {'mode':'recomendar', 'content_id':'fixture.post',
            'as_of':NOW.isoformat(), 'min_age_days':14}}


def ready(client, headers):
    assert _trace(client, headers, 'recomendar', RUN)['status'] == 'TRACE_RECORDED'
    response = client.post(PREVIEW, headers=headers, json=request())
    assert response.status_code == 200, response.text
    return response.json()


def acceptance(preview, index=0):
    return {**request(), 'document_id':'generated.draft',
            'proposal_sha256':preview['proposals'][index]['proposal_sha256']}


def test_five_original_proposals_deterministic_sql_citations_no_writes(local_system):
    app, client, headers = local_system
    first = ready(client, headers)
    before = counts(app)
    second = client.post(PREVIEW, headers=headers, json=request())
    assert second.status_code == 200 and second.json() == first
    assert second.headers['cache-control'] == 'private, no-store'
    assert counts(app) == before
    rows = first['proposals']
    assert len(rows) == len({p['proposal_sha256'] for p in rows}) == 5
    assert len({p['proposal']['brief']['headline'] for p in rows}) == 5
    for row in rows:
        p = row['proposal']
        assert p['citation']['snapshot_id'] == 'fixture.metrics'
        assert float(p['citation']['engagement_rate']) == .25
        assert p['brief']['reference_content_ids'] == ['fixture.post']
        assert p['script'] == [p['brief'][k] for k in ('headline','body','cta')]
        assert p['caption'] and p['hypothesis'] and p['brand_profile'] == 'unbranded_synthetic'
        assert p['uncertainty'] == 'exploratory_not_scientifically_validated'
    assert 'Ignore previous instructions' not in json.dumps(first)
    assert first['model_calls_performed'] == 0
    assert all(first[k] is False for k in ('scientifically_validated','studio_write_allowed','publication_allowed','production_approved'))


@pytest.mark.parametrize('index', range(5))
def test_explicit_selection_creates_matching_draft_and_provenance(local_system, index):
    app, client, headers = local_system
    preview = ready(client, headers)
    before = counts(app)
    req = acceptance(preview, index)
    res = client.post(ACCEPT, headers=headers, json=req)
    assert res.status_code == 201, res.text
    doc = res.json()
    assert doc['version'] == 1 and doc['approval_status'] == 'draft'
    assert doc['rights_status'] == 'pending_review'
    assert doc['pages'][0]['layers'][0]['text'] == preview['proposals'][index]['proposal']['brief']['headline']
    assert res.headers['etag'] and counts(app) == tuple(a+b for a,b in zip(before,(1,1,1,1,0)))
    with app.state.identity_store.engine.connect() as db:
        event = db.execute(select(domain_events).where(domain_events.c.aggregate_type==proposals.AGGREGATE)).mappings().one()
        proof = json.loads(event['payload'])
        assert proof['operator_authored_brief'] is False and proof['operator_selected_proposal'] is True
        assert proof['proposal_sha256'] == req['proposal_sha256']
        assert proof['trace_chain_sha256'] == preview['trace_chain_sha256']
        assert proof['publication_allowed'] is False and proof['scientifically_validated'] is False
        assert db.scalar(select(outbox.c.seq).where(outbox.c.seq==event['seq'])) == event['seq']
    assert client.post(ACCEPT,headers=headers,json=req).status_code == 409
    assert counts(app) == tuple(a+b for a,b in zip(before,(1,1,1,1,0)))


@pytest.mark.parametrize('kind',['hash','plan','run','extra','drift','policy_change'])
def test_stale_or_tampered_acceptance_denied(local_system, monkeypatch, kind):
    app, client, headers = local_system
    req = acceptance(ready(client,headers))
    if kind == 'hash': req['proposal_sha256']='0'*64
    if kind == 'plan': req['plan']['min_age_days']=15
    if kind == 'run': req['run_id']='wrong.run'
    if kind == 'extra': req['brief']={'headline':'injected'}
    if kind == 'drift':
        with app.state.identity_store.engine.begin() as db:
            data=json.loads(db.scalar(select(content_items.c.payload)))
            data['caption']='changed source'
            db.execute(update(content_items).values(payload=json.dumps(data)))
    if kind == 'policy_change': monkeypatch.setattr(proposals,'VERSION','tapi-local-creative-proposals.v2')
    before=counts(app)
    assert client.post(ACCEPT,headers=headers,json=req).status_code == (422 if kind=='extra' else 409)
    assert counts(app)==before


def test_no_open_trace_or_unauthenticated_preview(local_system):
    app,client,headers=local_system
    before=counts(app)
    assert client.post(PREVIEW,json=request()).status_code==401
    assert client.post(PREVIEW,headers=headers,json=request()).status_code==409
    assert counts(app)==before
    assert client.post(PREFIX+'step',headers=headers,json=request()).status_code==200
    before=counts(app)
    assert client.post(PREVIEW,headers=headers,json=request()).status_code==409
    assert counts(app)==before


def test_outbox_error_rolls_back_selected_draft(local_system, monkeypatch):
    app,client,headers=local_system
    req=acceptance(ready(client,headers)); before=counts(app)
    original=proposals.insert
    def fail(table):
        if table is outbox: raise SQLAlchemyError('fixture')
        return original(table)
    monkeypatch.setattr(proposals,'insert',fail)
    res=client.post(ACCEPT,headers=headers,json=req)
    assert res.status_code==409 and res.json()['detail']=='LOCAL_PROPOSAL_TRANSACTION_ABORTED'
    assert counts(app)==before


def test_editor_actor_binding_and_remote_denial(local_system):
    from fastapi.testclient import TestClient
    app,client,headers=local_system
    req=acceptance(ready(client,headers)); before=counts(app)
    for role,status in [('researcher',403),('editor',409)]:
        assert client.post('/v1/admin/members',headers=headers,json={
            'user_id':role,'username':role,'password':PASSWORD,'role':role}).status_code==201
        login=client.post('/v1/auth/sessions',json={'username':role,'tenant_id':'tenantA','password':PASSWORD})
        other={'Authorization':'Bearer '+login.json()['access_token']}
        assert client.post(PREVIEW,headers=other,json=request()).status_code==status
        assert client.post(ACCEPT,headers=other,json=req).status_code==status
    with TestClient(app,base_url='https://stone.example',client=('203.0.113.25',5001)) as remote:
        assert remote.post(PREVIEW,headers={**headers,'X-Forwarded-For':'127.0.0.1'},json=request()).status_code==403
        assert remote.post(ACCEPT,headers=headers,json=req).status_code==403
    assert counts(app)[:2]==before[:2] and counts(app)[4]==before[4]


def test_concurrent_selection_creates_once(local_system):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    app,client,headers=local_system
    req=acceptance(ready(client,headers)); before=counts(app)
    barrier=Barrier(2)
    def submit():
        with TestClient(app) as peer:
            barrier.wait(timeout=5)
            return peer.post(ACCEPT,headers=headers,json=req).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        a,b=pool.submit(submit),pool.submit(submit)
        assert sorted([a.result(timeout=20),b.result(timeout=20)])==[201,409]
    assert counts(app)==tuple(a+b for a,b in zip(before,(1,1,1,1,0)))
