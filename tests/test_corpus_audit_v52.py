"""IMP-167/170: permissions, corpus counts, eligibility and Alembic 0004 tests.

Mocks only; never connects to Meta, YouTube, or a paid provider.
"""
from datetime import datetime, timedelta, timezone

import httpx
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, update

from tapi_gate0.connectors import OfficialHttp
from tapi_gate0.corpus import corpus_data_card
from tapi_gate0.ingestion import IngestionRequest, source_grants
from tapi_gate0.secure_api import create_secure_app

TENANT = 'corpus-tenant'
PASSWORD = 'correct-horse-battery-admin-42-safe'
ACCOUNT = '178900'


def setup(tmp_path):
    app = create_secure_app(f"sqlite:///{tmp_path/'corpus.sqlite'}",
                            initialize_schema=True,allow_http_local=True)
    app.state.identity_store.bootstrap(TENANT,'Test Organization','admin',PASSWORD)
    return app


def logged_in(client):
    r=client.post('/v1/auth/sessions',json={'username':'admin','password':PASSWORD,'tenant_id':TENANT})
    assert r.status_code==200
    return {'Authorization':'Bearer '+r.json()['access_token']}


def reg(client,headers):
    return client.post('/v1/corpus/profiles',headers=headers,json={
        'platform':'instagram','source_account_id':ACCOUNT,
        'sector':'commerce','sampling_stratum':'retail_micro_south',
        'evidence_reference':'research sampling frame v1'})


def grant(client,headers):
    return client.post('/v1/ingestion/grants',headers=headers,json={
        'platform':'instagram','source_account_id':ACCOUNT,
        'approval_reference':'approved mocked source research grant',
        'expires_at':(datetime.now(timezone.utc)+timedelta(days=10)).isoformat()})


def test_empty_card_and_no_auto_grants(tmp_path):
    app=setup(tmp_path)
    with TestClient(app) as client:
        assert client.get('/v1/corpus/data-card').status_code==401
        headers=logged_in(client)
        d=client.get('/v1/corpus/data-card',headers=headers)
        assert d.status_code==200,d.text
        info=d.json()
        assert info['sampling_frame']['registered_profiles']==0
        assert info['observed']['eligible_instagram_posts']==0
        assert info['deficit']=={'profiles':30,'posts':2000}
        assert not info['target_reached']
        assert info['external_requests_performed']==0
        assert reg(client,headers).status_code==403
        assert grant(client,headers).status_code==201
        r=reg(client,headers)
        assert r.status_code==201,r.text
        assert r.json()['access_verified'] is False
        assert reg(client,headers).status_code==409
        pending=client.get('/v1/corpus/data-card',headers=headers).json()
        assert pending['sampling_frame']=={
            'registered_profiles':1,'with_current_administrative_grant':1,
            'with_prior_technical_verification':0}
        assert not pending['target_reached']


def test_authorized_mock_ingest_counts_only_mature_instagram(tmp_path,monkeypatch):
    app=setup(tmp_path)
    monkeypatch.setenv('TAPI_OFFICIAL_METADATA_READS','1')
    monkeypatch.setenv('TAPI_ZERO_BILLING_CONFIRMED','1')
    monkeypatch.setenv('TAPI_INSTAGRAM_ACCESS_TOKEN','mocked-credentials-no-network')
    def responder(req):
        assert req.url.host=='graph.facebook.com'
        if req.url.path.endswith('/178900'):
            return httpx.Response(200,json={'id':ACCOUNT,'username':'verified','followers_count':125})
        assert req.url.path.endswith('/178900/media')
        return httpx.Response(200,json={'data':[
            {'id':'179001','media_type':'VIDEO','media_product_type':'REELS',
             'permalink':'https://www.instagram.com/reel/ok/',
             'timestamp':'2024-01-01T00:00:00Z','caption':'Vendas',
             'like_count':20,'comments_count':2},
            {'id':'179002','media_type':'VIDEO','media_product_type':'REELS',
             'permalink':'https://www.instagram.com/reel/new/',
             'timestamp':datetime.now(timezone.utc).isoformat(),
             'like_count':14,'comments_count':1},
            {'id':'179003','media_type':'IMAGE',
             'permalink':'https://www.instagram.com/p/photo/',
             'timestamp':'2024-01-01T00:00:00Z',
             'like_count':30,'comments_count':3}]})
    http=OfficialHttp(httpx.Client(transport=httpx.MockTransport(responder)))
    with TestClient(app) as client:
        headers=logged_in(client)
        assert grant(client,headers).status_code==201
        assert reg(client,headers).status_code==201
        result=app.state.ingestion_store.run(TENANT,IngestionRequest(
            platform='instagram',source_account_id=ACCOUNT,run_key='corpus-run-0001',limit=3),http=http)
        assert result.new_records==2 and result.excluded_too_recent==1
        data=client.get('/v1/corpus/data-card',headers=headers).json()
        assert data['sampling_frame']['with_prior_technical_verification']==1
        assert data['observed']['eligible_instagram_posts']==1
        assert data['observed']['excluded_nonprimary_instagram_format']==1
        assert data['observed']['eligible_instagram_profiles']==1
        assert data['instagram_posts_by_operator_sector']['commerce']==1
        assert data['instagram_sampling_strata']['retail_micro_south']=={
            'registered_profiles':1, 'eligible_profiles':1, 'eligible_posts':1}
        assert data['deficit']=={'profiles':29,'posts':1999}
        assert not data['target_reached']
        with app.state.ingestion_store.engine.begin() as db:
            db.execute(update(source_grants).where(source_grants.c.tenant_id==TENANT)
                       .values(enabled=0))
        blocked=client.get('/v1/corpus/data-card',headers=headers).json()
        assert blocked['observed']['eligible_instagram_posts']==0
        assert blocked['observed']['excluded_grant_or_technical']==2
        assert blocked['deficit']['posts']==2000
        # An expired grant also excludes historical posts from current sampling.
        with app.state.ingestion_store.engine.begin() as db:
            db.execute(update(source_grants).where(source_grants.c.tenant_id==TENANT)
                       .values(enabled=1, expires_at='2020-01-01T00:00:00+00:00'))
        expired=client.get('/v1/corpus/data-card',headers=headers).json()
        assert expired['observed']['eligible_instagram_posts']==0
        assert expired['observed']['excluded_grant_or_technical']==2
        assert corpus_data_card(app.state.ingestion_store.engine,'unknown-tenant')['observed']['eligible_instagram_posts']==0


def test_corpus_0004_upgrade_and_downgrade(tmp_path,monkeypatch):
    from pathlib import Path
    project=Path(__file__).resolve().parents[1]
    path=tmp_path/'migrations.sqlite'
    monkeypatch.setenv('TAPI_DATABASE_URL',f'sqlite:///{path}')
    cfg=Config(str(project/'alembic.ini'))
    cfg.set_main_option('script_location',str(project/'migrations'))
    command.upgrade(cfg,'0003_ingestion_page_checkpoints')
    engine=create_engine(f'sqlite:///{path}')
    assert not inspect(engine).has_table('corpus_profiles')
    command.upgrade(cfg,'head')
    assert inspect(engine).has_table('corpus_profiles')
    command.downgrade(cfg,'0003_ingestion_page_checkpoints')
    assert not inspect(engine).has_table('corpus_profiles')
    command.upgrade(cfg,'head')
    assert inspect(engine).has_table('corpus_profiles')
    engine.dispose()


def test_youtube_remains_supplemental_not_part_of_instagram_target(tmp_path,monkeypatch):
    app=setup(tmp_path)
    channel='UC123456789'
    monkeypatch.setenv('TAPI_OFFICIAL_METADATA_READS','1')
    monkeypatch.setenv('TAPI_ZERO_BILLING_CONFIRMED','1')
    monkeypatch.setenv('TAPI_YOUTUBE_ACCESS_TOKEN','mocked-credentials-no-network')
    def responder(req):
        assert req.url.host=='www.googleapis.com'
        if req.url.path.endswith('/channels'):
            return httpx.Response(200,json={'items':[{
                'id':channel,'snippet':{'title':'Authorized channel'},
                'statistics':{'subscriberCount':'1200'}}]})
        assert req.url.path.endswith('/videos')
        return httpx.Response(200,json={'items':[{
            'id':'AZabcdef123',
            'snippet':{'channelId':channel,'title':'Store tips',
                       'publishedAt':'2024-01-01T00:00:00Z'},
            'statistics':{'likeCount':'20','commentCount':'2','viewCount':'1000'}}]})
    provider=OfficialHttp(httpx.Client(transport=httpx.MockTransport(responder)))
    with TestClient(app) as client:
        headers=logged_in(client)
        assert client.post('/v1/ingestion/grants',headers=headers,json={
            'platform':'youtube','source_account_id':channel,
            'approval_reference':'approved mocked YouTube research grant',
            'expires_at':(datetime.now(timezone.utc)+timedelta(days=10)).isoformat(),
        }).status_code==201
        assert client.post('/v1/corpus/profiles',headers=headers,json={
            'platform':'youtube','source_account_id':channel,'sector':'services',
            'sampling_stratum':'service_south',
            'evidence_reference':'mock youtube sampling ref',
        }).status_code==201
        result=app.state.ingestion_store.run(TENANT,IngestionRequest(
            platform='youtube',source_account_id=channel,run_key='youtube-corpus-1',
            video_ids=['AZabcdef123'],
            shorts_evidence_reference='human attests authorized shorts'),http=provider)
        assert result.new_records==1
        d=client.get('/v1/corpus/data-card',headers=headers).json()
        assert d['observed']['eligible_instagram_posts']==0
        assert d['observed']['eligible_instagram_profiles']==0
        assert d['observed']['eligible_youtube_supplementary_posts']==1
        assert d['deficit']=={'profiles':30,'posts':2000}
        assert not d['target_reached']
