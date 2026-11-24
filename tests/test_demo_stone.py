"""Demo fixture uses real application routes and a new private local database."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from scripts.demo_stone import AS_OF, TENANT, USERNAME, build_demo
from tapi_gate0.agent_graph_checkpoints import agent_graph_events
from tapi_gate0.sa_store import domain_events
from tapi_gate0.studio_e1 import studio_versions


def test_demo_vertical(tmp_path):
    path = tmp_path / 'demo.sqlite'
    password = 'fixture-only-not-real-password'
    app = build_demo(path, password)
    try:
        with pytest.raises(ValueError, match='DEMO_REQUIRES_NEW_DATABASE'):
            build_demo(path, password)
        with TestClient(app) as client:
            assert client.get('/v1/demo/rubric/demo.post.01').status_code == 401
            assert client.get('/v1/demo/technical-snapshot').status_code == 401
            assert client.get('/v1/demo/search?q=estoque').status_code == 401
            assert client.get('/v1/demo/session-results').status_code == 401
            assert client.get('/app/demo.html').status_code == 200
            assert client.get('/app/demo.mjs').status_code == 200
            assert client.get('/app/demo.css').status_code == 200
            assert client.post('/v1/agent/local-graph/step', json={}).status_code in (401, 422)
            login = client.post('/v1/auth/sessions', json={'tenant_id':TENANT,'username':USERNAME,'password':password})
            headers = {'Authorization':'Bearer '+login.json()['access_token']}
            assert client.get('/v1/demo/technical-snapshot',headers=headers).json()=={'available':False,'snapshot':None}
            rubric=client.get('/v1/demo/rubric/demo.post.01',headers=headers).json()
            assert rubric['field_count']==20 and rubric['canonical'] is False
            assert rubric['fields']['tipo_post']['state']=='metadata_observed'
            assert rubric['fields']['tema_principal']['value']=='gestão'
            assert rubric['fields']['tem_cta']['value'] is True
            assert rubric['fields']['tem_rosto']['value'] is None
            assert rubric['fields']['tem_rosto']['state']=='not_assessed'
            assert client.get('/v1/demo/rubric/unknown',headers=headers).status_code==404
            request = {'tenant_id':TENANT,'origin':'synthetic_local','as_of':AS_OF.isoformat(),'min_age_days':14}
            ranking = client.post('/v1/analyses/rankings', headers=headers, json=request).json()
            assert (ranking['n_posts'],ranking['n_creators'],ranking['top_count']) == (20,4,2)
            assert float(ranking['rows'][0]['engagement_rate']) == .17
            search = client.get('/v1/demo/search?q=estoque', headers=headers).json()
            assert search['hit_count'] == 5 and search['indexed_posts'] == 20
            assert all('estoque' in hit['caption'] for hit in search['hits'])
            assert search['hits'][0]['top'] is True and search['scientifically_validated'] is False
            assert client.get('/v1/demo/search?q=impossivel', headers=headers).json()['hit_count'] == 0
            assert client.get('/v1/demo/search?q=!!!', headers=headers).status_code == 422
            assert client.get('/v1/demo/session-results', headers=headers).json()['synthetic_counters']['editable_drafts'] == 0
            for row in ranking['rows'][:2]:
                assert row['is_top_decile']
                detail = client.get('/v1/agent/evidence/'+row['content_id'],headers=headers).json()
                assert detail['origin']=='synthetic_local' and detail['source_url'] is None
                assert detail['snapshot_id']==row['snapshot_id']
            plan = {'run_id':'demo.test','plan':{'mode':'recomendar','content_id':ranking['rows'][0]['content_id'],'origin':'synthetic_local','as_of':AS_OF.isoformat()}}
            for n in range(1,7):
                response=client.post('/v1/agent/local-graph/step',headers=headers,json=plan)
                assert response.status_code==200 and response.json()['revision']==n
            assert response.json()['status']=='TRACE_RECORDED'
            result=client.post('/v1/agent/local-graph/creative-proposals',headers=headers,json=plan).json()
            assert len(result['proposals'])==5 and result['scientifically_validated'] is False
            assert [len(p['preview_document']['pages']) for p in result['proposals']] == [1,1,1,1,3]
            created=client.post('/v1/agent/local-graph/creative-proposal-draft',headers=headers,json={**plan,'document_id':'demo.test.draft','proposal_sha256':result['proposals'][0]['proposal_sha256']})
            assert created.status_code==201
            edited=client.post('/v1/agent/creative-drafts/demo.test.draft/text-patches',headers={**headers,'If-Match':created.headers['etag']},json={'expected_version':1,'page_id':'page.1','layer_id':'headline','text':'Organize seu estoque hoje'})
            assert edited.status_code==200 and edited.json()['version']==2
            assert edited.json()['approval_status']=='draft' and edited.json()['rights_status']=='pending_review'
            with app.state.identity_store.engine.connect() as db:
                assert db.scalar(select(func.count()).select_from(agent_graph_events))==6
                assert db.scalar(select(func.count()).select_from(studio_versions))==2
                assert db.scalar(select(func.count()).select_from(domain_events).where(domain_events.c.aggregate_type=='agent_generated_draft'))==1
            carousel=client.post('/v1/agent/local-graph/creative-proposal-draft',headers=headers,json={**plan,'document_id':'demo.carousel','proposal_sha256':result['proposals'][4]['proposal_sha256']})
            assert carousel.status_code==201 and len(carousel.json()['pages'])==3
            edited=client.post('/v1/agent/creative-drafts/demo.carousel/text-patches',headers={**headers,'If-Match':carousel.headers['etag']},json={'expected_version':1,'page_id':'page.2','layer_id':'headline','text':'Priorize sua semana'})
            assert edited.status_code==200 and edited.json()['version']==2
            assert edited.json()['pages'][1]['layers'][0]['text']=='Priorize sua semana'
            assert edited.json()['pages'][0]==carousel.json()['pages'][0]
            report=client.get('/v1/demo/session-results',headers=headers).json()
            assert report['synthetic_counters']==dict(eligible_posts=20,profiles=4,top_posts=2,completed_traces=1,checkpoint_events=6,editable_drafts=2,document_versions=4,generated_draft_events=2)
            assert report['historical_technical_snapshot'] is None and report['production_approved'] is False
            assert client.post('/v1/auth/logout',headers=headers).status_code==204
            assert client.get('/v1/auth/me',headers=headers).status_code==401
    finally:
        app.state.identity_store.engine.dispose()
