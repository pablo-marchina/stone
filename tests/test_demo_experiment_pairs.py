import json
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from scripts.demo_stone import build_demo, TENANT, USERNAME
from scripts.demo_technical_snapshot import project_report
from tapi_gate0.discovery_audience_exploratory import summarize
from tapi_gate0.sa_store import domain_events, outbox
from tapi_gate0.studio_e1 import studio_versions, StudioStore
from scripts.demo_experiment_pairs import previews, persist
import pytest


def fixture_snapshot(tmp_path):
    rows = [dict(content_id=f'private.{i:02}', username=f'private.profile.{i%4}', tier='unresolved',
                 likes=30-i, comments=0, followers=100, format='reels' if i<2 else 'imagem',
                 topic='marketing' if i<2 else 'atendimento', cta='seguir' if i<2 else 'comentar') for i in range(20)]
    report = {**summarize(rows), 'private_rows':rows, 'status':'EXPLORATORY_RANKING_COMPLETED',
              'as_of':'2026-11-19T12:00:00+00:00','manifest_sha256':'a'*64,'production_approved':False}
    path=tmp_path/'report.json';path.write_text(json.dumps(report),encoding='utf-8')
    return project_report(path)


def test_pairs_persist_and_edit(tmp_path):
    snapshot=fixture_snapshot(tmp_path)
    app=build_demo(tmp_path/'demo.sqlite','fixture-only-not-real-password',snapshot)
    try:
        with TestClient(app) as c:
            url='/v1/demo/experiments'
            assert c.get(url).status_code==401
            h={'Authorization':'Bearer '+c.post('/v1/auth/sessions',json={'tenant_id':TENANT,'username':USERNAME,'password':'fixture-only-not-real-password'}).json()['access_token']}
            rows=c.get(url,headers=h).json()['pairs']
            assert {r['pair']['field'] for r in rows}=={'cta','topic'}
            row=next(r for r in rows if r['pair']['field']=='cta')
            assert row['pair']['control']=='comentar' and row['pair']['candidate']=='seguir'
            a,b=row['previews'];assert a['canvas']==b['canvas']
            assert [l for l in a['pages'][0]['layers'] if l['id']!='cta']==[l for l in b['pages'][0]['layers'] if l['id']!='cta']
            assert a['pages'][0]['layers'][2]['text']!=b['pages'][0]['layers'][2]['text']
            assert c.post(url,headers=h,json={'preview_sha256':'a'*64}).status_code==409
            assert c.post(url,headers=h,json={'preview_sha256':row['preview_sha256'],'headline':'tampered'}).status_code==422
            response=c.post(url,headers=h,json={'preview_sha256':row['preview_sha256']});assert response.status_code==201,response.text
            r=response.json();assert r['proof']['report_sha256']==snapshot['report_sha256']
            assert not r['proof']['publication_allowed'] and 'private.' not in str(r)
            for preview,doc in zip(row['previews'],r['documents']):
                assert doc=={**preview,'document_id':doc['document_id']}
                assert not doc['reference_content_ids'] and doc['approval_status']=='draft'
            d=r['documents'][1]
            edited=c.post('/v1/agent/creative-drafts/'+d['document_id']+'/text-patches',headers={**h,'If-Match':r['etags'][1]},json={'expected_version':1,'page_id':'page.1','layer_id':'headline','text':'Revise sua rotina'})
            assert edited.status_code==200,edited.text
            assert edited.json()['version']==2
            assert c.get('/v1/demo/session-results',headers=h).json()['editorial_experiment_pairs']==1
            with app.state.identity_store.engine.connect() as db:
                assert db.scalar(select(func.count()).select_from(studio_versions))==3
                event=db.execute(select(domain_events).where(domain_events.c.aggregate_type=='demo_editorial_experiment')).mappings().one()
                assert json.loads(event['payload'])==r['proof']
                assert db.scalar(select(func.count()).select_from(outbox).where(outbox.c.seq==event['seq']))==1
    finally:
        app.state.identity_store.engine.dispose()


def test_second_document_failure_rolls_back_pair(tmp_path,monkeypatch):
    snapshot=fixture_snapshot(tmp_path)
    app=build_demo(tmp_path/'demo.sqlite','fixture-only-not-real-password',snapshot)
    engine=app.state.identity_store.engine
    original=StudioStore.create
    def create(self,*args,**kwargs):
        if args[3].endswith('.B'):
            raise ValueError('injected second document failure')
        return original(self,*args,**kwargs)
    monkeypatch.setattr(StudioStore,'create',create)
    try:
        with pytest.raises(ValueError,match='injected'):
            persist(engine,snapshot,TENANT,'fixture.actor',previews(snapshot,TENANT)[0]['preview_sha256'])
        with engine.connect() as db:
            assert db.scalar(select(func.count()).select_from(studio_versions))==0
            assert db.scalar(select(func.count()).select_from(domain_events).where(domain_events.c.aggregate_type=='demo_editorial_experiment'))==0
    finally:
        engine.dispose()


def test_persistent_launcher_recovers_pair_and_revision(tmp_path):
    from scripts.demo_workspace import open_workspace
    snapshot=fixture_snapshot(tmp_path)
    root=tmp_path/'presentation'
    with open_workspace(root, snapshot, None) as work:
        app=build_demo(work.path,'fixture-only-not-real-password',snapshot,workspace=work)
        try:
            work.seal()
            with TestClient(app) as c:
                h={'Authorization':'Bearer '+c.post('/v1/auth/sessions',json={'tenant_id':TENANT,'username':USERNAME,'password':'fixture-only-not-real-password'}).json()['access_token']}
                url='/v1/demo/experiments'
                row=next(r for r in c.get(url,headers=h).json()['pairs'] if r['pair']['field']=='cta')
                created=c.post(url,headers=h,json={'preview_sha256':row['preview_sha256']})
                assert created.status_code==201
                r=created.json()
                d=r['documents'][1]
                assert c.post('/v1/agent/creative-drafts/'+d['document_id']+'/text-patches',headers={**h,'If-Match':r['etags'][1]},json={'expected_version':1,'page_id':'page.1','layer_id':'headline','text':'Revise sua rotina'}).status_code==200
        finally:
            app.state.identity_store.engine.dispose()
    with open_workspace(root, snapshot, None) as work:
        assert work.resume
        app=build_demo(work.path,None,snapshot,workspace=work)
        try:
            with TestClient(app) as c:
                assert c.get('/v1/demo/saved-library').status_code==401
                h={'Authorization':'Bearer '+c.post('/v1/auth/sessions',json={'tenant_id':TENANT,'username':USERNAME,'password':'fixture-only-not-real-password'}).json()['access_token']}
                library=c.get('/v1/demo/saved-library',headers=h).json()
                assert library['persistent_workspace'] is True
                assert library['pairs']==[r['proof']]
                assert len(library['documents'])==2
                assert next(x for x in library['documents'] if x['document_id']==d['document_id'])['version']==2
                counters=c.get('/v1/demo/session-results',headers=h).json()
                assert counters['synthetic_counters']['eligible_posts']==20
                assert counters['synthetic_counters']['document_versions']==3
                assert counters['editorial_experiment_pairs']==1
        finally:
            app.state.identity_store.engine.dispose()


def test_carousel_api_preserves_feed_and_persists_selected_format(tmp_path):
    snapshot=fixture_snapshot(tmp_path)
    app=build_demo(tmp_path/'demo.sqlite','fixture-only-not-real-password',snapshot)
    try:
        with TestClient(app) as c:
            h={'Authorization':'Bearer '+c.post('/v1/auth/sessions',json={'tenant_id':TENANT,'username':USERNAME,'password':'fixture-only-not-real-password'}).json()['access_token']}
            url='/v1/demo/experiments'
            assert c.get(url+'?platform_intent=instagram_carousel').status_code==401
            assert c.get(url+'?platform_intent=reels',headers=h).status_code==422
            feed=c.get(url,headers=h).json()['pairs']
            carousels=c.get(url+'?platform_intent=instagram_carousel',headers=h).json()['pairs']
            assert len(feed)==len(carousels)==2
            assert all(len(d['pages'])==1 for row in feed for d in row['previews'])
            assert all(len(d['pages'])==3 for row in carousels for d in row['previews'])
            row=next(r for r in carousels if r['pair']['field']=='cta')
            created=c.post(url,headers=h,json={'preview_sha256':row['preview_sha256']})
            assert created.status_code==201,created.text
            pair=created.json()
            assert pair['proof']['platform_intent']=='instagram_carousel'
            assert all(len(d['pages'])==3 for d in pair['documents'])
            assert c.get('/v1/demo/saved-library',headers=h).json()['pairs']==[pair['proof']]
    finally:
        app.state.identity_store.engine.dispose()
