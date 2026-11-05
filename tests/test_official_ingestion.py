"""Contract tests: provider APIs mocked; no real network, credentials, or charge."""
import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.ingestion import IngestionStore, GrantCreate, IngestionRequest, ingestion_records, ingestion_runs
from tapi_gate0.connectors import (OfficialHttp, InstagramOfficial, YouTubeOfficial,
                                  ConnectorError, Platform)
from tapi_gate0.classification import classify_metadata_caption
from tapi_gate0.domain import EvidenceStatus, RankingRequest
from tapi_gate0.sa_store import domain_events, outbox

PASS="correct-horse-battery-admin-42-safe"
TENANT="project-research"
FUTURE=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat()


def setup(tmp_path):
    app=create_secure_app(f"sqlite:///{tmp_path/'data.sqlite3'}",initialize_schema=True,allow_http_local=True)
    app.state.identity_store.bootstrap(TENANT,"Test Organization","admin",PASS)
    return app


def bearer(client):
    resp=client.post('/v1/auth/sessions',json={'username':'admin','password':PASS,'tenant_id':TENANT})
    assert resp.status_code==200, resp.text
    return {"Authorization":"Bearer "+resp.json()['access_token']}


def ig_responder(request):
    assert request.url.host=="graph.facebook.com"
    assert request.headers.get('authorization')=="Bearer mocked-credentials-that-never-log"
    if request.url.path.endswith('/178900'):
        return httpx.Response(200,json={'id':'178900','username':'authorized_professional','followers_count':1200})
    if request.url.path.endswith('/178900/media'):
        return httpx.Response(200,json={'data':[{'id':'179001','media_type':'VIDEO',
            'media_product_type':'REELS','permalink':'https://www.instagram.com/reel/C123/',
            'timestamp':'2024-01-14T12:00:00Z','caption':'Dicas para vendas: comente aqui',
            'like_count':120,'comments_count':12},{'id':'179002','media_type':'VIDEO',
            'media_product_type':'VIDEO','permalink':'https://www.instagram.com/p/D123/',
            'timestamp':'2024-01-14T12:00:00Z'}]})
    return httpx.Response(404,json={'error':'unexpected'})


def yt_responder(request):
    assert request.url.host=="www.googleapis.com"
    if request.url.path.endswith('/channels'):
        return httpx.Response(200,json={'items':[{'id':'UC123456789',
          'snippet':{'title':'My channel'},'statistics':{'subscriberCount':'12300'}}]})
    if request.url.path.endswith('/videos'):
        return httpx.Response(200,json={'items':[{'id':'AZabcdef123',
          'snippet':{'channelId':'UC123456789','title':'Marketing local',
                     'description':'Salve para depois','publishedAt':'2024-01-16T13:00:00Z'},
          'statistics':{'likeCount':'700','viewCount':'32000'}}]})
    return httpx.Response(404)


def mock_http(fn):
    return OfficialHttp(httpx.Client(transport=httpx.MockTransport(fn)))


def grant(client,headers,platform,account):
    return client.post('/v1/ingestion/grants',headers=headers,json={
        'platform':platform,'source_account_id':account,
        'approval_reference':'APPROVED internal rights scope documented in project record',
        'expires_at':FUTURE})


def test_default_deny_and_admin_auth(tmp_path,monkeypatch):
    monkeypatch.delenv('TAPI_OFFICIAL_METADATA_READS',raising=False)
    monkeypatch.delenv('TAPI_INSTAGRAM_ACCESS_TOKEN',raising=False)
    app=setup(tmp_path)
    with TestClient(app) as c:
        h=bearer(c)
        request={'platform':'instagram','source_account_id':'178900','run_key':'run-default-off', 'limit':2}
        assert c.post('/v1/ingestion/runs',json=request,headers=h).status_code==403
        assert c.post('/v1/ingestion/grants',json={"platform":"instagram"}).status_code==401
        r=grant(c,h,'instagram','178900');assert r.status_code==201,r.text
        assert r.json()['technical_verified'] is False
        state=c.get('/v1/ingestion/connections/instagram/178900',headers=h)
        assert state.status_code==200 and not state.json()['can_attempt_validation']
        assert c.post('/v1/ingestion/runs',json=request,headers=h).json()['code']=='OFFICIAL_READS_DISABLED'
        assert c.post('/v1/collections',headers=h,json={'tenant_id':TENANT,'source':'instagram','request_id':'x'}).status_code==403


def test_instagram_official_normalization_and_multimodal_abstention(tmp_path,monkeypatch):
    app=setup(tmp_path)
    monkeypatch.setenv('TAPI_OFFICIAL_METADATA_READS','1')
    monkeypatch.setenv('TAPI_ZERO_BILLING_CONFIRMED','1')
    monkeypatch.setenv('TAPI_INSTAGRAM_ACCESS_TOKEN','mocked-credentials-that-never-log')
    store=app.state.ingestion_store
    with TestClient(app) as client:
        hdr=bearer(client)
        assert grant(client,hdr,'instagram','178900').status_code==201
        req=IngestionRequest(platform='instagram',source_account_id='178900',run_key='ingest-first',limit=3)
        result=store.run(TENANT,req,http=mock_http(ig_responder))
        assert result.new_records==1 and result.duplicate_records==0
        # Idempotency across distinct job keys: content must not duplicate or emit events.
        next_result=store.run(TENANT,req.model_copy(update={'run_key':'ingest-second'}),http=mock_http(ig_responder))
        assert next_result.new_records==0 and next_result.duplicate_records==1
        r=client.get('/v1/ingestion/runs',headers=hdr);assert r.status_code==200
        assert len(r.json()['items'])==2
        with store.engine.connect() as db:
            row=db.execute(select(ingestion_records)).mappings().one()
            assert row['denominator_quality']=='observed_current_only'
            assert db.execute(select(func.count()).select_from(domain_events)).scalar_one()==2
            assert db.execute(select(func.count()).select_from(outbox)).scalar_one()==2
        cid=row['content_id']
        assessment=client.get(f'/v1/content/{cid}/assessments/latest',headers=hdr)
        assert assessment.status_code==200,assessment.text
        a=assessment.json()
        assert a['values']['tipo_post']=='reels'
        assert a['values']['tema_principal']=='vendas'
        assert a['values']['tem_cta'] is True
        assert a['values']['tipo_cta']=='comentar'
        for x in ['tem_rosto','hook_primeiros_3s','ritmo_cortes_0a10','texto_na_tela']:
            assert a['values'][x] is None and a['field_evidence'][x]['status']=='not_observable'
        rank=client.post('/v1/analyses/rankings',headers=hdr,
          json={'tenant_id':TENANT,'origin':'instagram','min_age_days':14,
                'as_of':datetime.now(timezone.utc).isoformat()})
        # The old local domain HTTP contract still forbids external ranking; intentional.
        assert rank.status_code==403
        calculated=app.state.local_domain_store.ranking(RankingRequest(tenant_id=TENANT,origin='instagram',
            min_age_days=14,as_of=datetime.now(timezone.utc)))
        assert calculated.n_posts==1 and calculated.rows[0].likes==120


def test_youtube_missing_stats_are_unknown_and_not_zero(tmp_path,monkeypatch):
    monkeypatch.setenv('TAPI_OFFICIAL_METADATA_READS','1')
    monkeypatch.setenv('TAPI_ZERO_BILLING_CONFIRMED','1')
    monkeypatch.setenv('TAPI_YOUTUBE_ACCESS_TOKEN','mocked-credentials-that-never-log')
    app=setup(tmp_path)
    with TestClient(app) as client:
        h=bearer(client)
        assert grant(client,h,'youtube','UC123456789').status_code==201
        req=IngestionRequest(platform='youtube',source_account_id='UC123456789',run_key='youtube-run-1',
              video_ids=['AZabcdef123'],shorts_evidence_reference='Owner attests these IDs are Shorts')
        result=app.state.ingestion_store.run(TENANT,req,http=mock_http(yt_responder))
        assert result.new_records==1
        content=client.get('/v1/ingestion/runs',headers=h)
        assert content.status_code==200
        with app.state.ingestion_store.engine.connect() as db:
            row=db.execute(select(ingestion_records)).mappings().one()
            assert row['denominator_quality']=='youtube_rounded_estimate'
            # YouTube omitted commentCount: do not persist fictional zero and rank.
            from tapi_gate0.sa_store import metrics_snapshots
            assert db.execute(select(func.count()).select_from(metrics_snapshots)).scalar_one()==0


def test_provider_mismatch_prevents_all_writes(tmp_path,monkeypatch):
    monkeypatch.setenv('TAPI_OFFICIAL_METADATA_READS','1')
    monkeypatch.setenv('TAPI_ZERO_BILLING_CONFIRMED','1')
    monkeypatch.setenv('TAPI_INSTAGRAM_ACCESS_TOKEN','mocked-credentials-that-never-log')
    app=setup(tmp_path)
    def wrong(_request):return httpx.Response(200,json={'id':'wrong','username':'hijack','followers_count':30})
    with TestClient(app) as client:
        h=bearer(client);grant(client,h,'instagram','178900')
        with pytest.raises(ConnectorError) as err:
            app.state.ingestion_store.run(TENANT,IngestionRequest(
                platform='instagram',source_account_id='178900',run_key='mismatched-token'),http=mock_http(wrong))
        assert err.value.code=='PROVIDER_ACCOUNT_MISMATCH'
        with app.state.ingestion_store.engine.connect() as db:
            assert db.execute(select(func.count()).select_from(ingestion_records)).scalar_one()==0
            assert db.execute(select(ingestion_runs.c.status)).scalar_one()=='failed'


def test_grants_lease_and_secret_gates(tmp_path,monkeypatch):
    monkeypatch.setenv('TAPI_OFFICIAL_METADATA_READS','1')
    monkeypatch.setenv('TAPI_ZERO_BILLING_CONFIRMED','1')
    monkeypatch.delenv('TAPI_INSTAGRAM_ACCESS_TOKEN',raising=False)
    app=setup(tmp_path)
    with TestClient(app) as client:
        h=bearer(client)
        payload=IngestionRequest(platform='instagram',source_account_id='178900',run_key='run-auth-missing')
        with pytest.raises(ConnectorError) as missing:
            app.state.ingestion_store.run(TENANT,payload,http=mock_http(ig_responder))
        assert missing.value.code=='VALID_SOURCE_GRANT_REQUIRED'
        grant(client,h,'instagram','178900')
        with pytest.raises(ConnectorError) as missing:
            app.state.ingestion_store.run(TENANT,payload,http=mock_http(ig_responder))
        assert missing.value.code=='CREDENTIAL_MISSING'
        with app.state.ingestion_store.engine.connect() as db:
            assert db.execute(select(func.count()).select_from(ingestion_runs)).scalar_one()==0


def test_security_no_untrusted_host_or_redirects():
    adapter=InstagramOfficial(mock_http(lambda req:httpx.Response(302,headers={'Location':'http://127.0.0.1/private'})))
    with pytest.raises(ConnectorError) as exc:
        adapter.verify('178900','mocked-credentials-that-never-log')
    assert exc.value.code=='PROVIDER_REDIRECT_DENIED'
    with pytest.raises(ConnectorError) as exc:
        adapter.http.get(Platform.YOUTUBE,'../metadata',{},'mocked-credentials-that-never-log')
    assert exc.value.code=='UNSAFE_PROVIDER_PATH'


def test_rbac_for_grants(tmp_path):
    app=setup(tmp_path)
    with TestClient(app) as c:
        h=bearer(c)
        created=c.post('/v1/admin/members',headers=h,json={
            'user_id':'reader','username':'reader','password':'correct-password-user-42','role':'viewer'})
        assert created.status_code==201
        viewer=c.post('/v1/auth/sessions',json={'username':'reader','password':'correct-password-user-42',
            'tenant_id':TENANT}).json()['access_token']
        read={'Authorization':'Bearer '+viewer}
        assert grant(c,read,'instagram','178900').status_code==403
        assert c.post('/v1/ingestion/runs',headers=read,json={
            'platform':'instagram','source_account_id':'178900','run_key':'no-viewer-access'}).status_code==403


def test_official_routes_are_in_contract(tmp_path):
    app=setup(tmp_path)
    spec=app.openapi()
    assert '/v1/ingestion/grants' in spec['paths']
    assert '/v1/ingestion/runs' in spec['paths']


def test_billing_guard_fails_before_network(tmp_path,monkeypatch):
    monkeypatch.setenv('TAPI_OFFICIAL_METADATA_READS','1')
    monkeypatch.delenv('TAPI_ZERO_BILLING_CONFIRMED',raising=False)
    app=setup(tmp_path)
    with TestClient(app) as client:
        h=bearer(client);grant(client,h,'instagram','178900')
        r=client.post('/v1/ingestion/runs',json={'platform':'instagram',
             'source_account_id':'178900','run_key':'requires-zero-bill'},headers=h)
        assert r.status_code==403
        assert r.json()['code']=='PROVIDER_ZERO_BILLING_NOT_CONFIRMED'
        with app.state.ingestion_store.engine.connect() as db:
            assert db.execute(select(func.count()).select_from(ingestion_runs)).scalar_one()==0


def test_authenticated_http_run_with_mock_provider(tmp_path,monkeypatch):
    """Real API route -> grant gate -> provider adapter -> SQL commit -> UI event."""
    import tapi_gate0.ingestion as ing
    monkeypatch.setenv('TAPI_OFFICIAL_METADATA_READS','1')
    monkeypatch.setenv('TAPI_ZERO_BILLING_CONFIRMED','1')
    monkeypatch.setenv('TAPI_INSTAGRAM_ACCESS_TOKEN','mocked-credentials-that-never-log')
    monkeypatch.setattr(ing,'OfficialHttp',lambda:mock_http(ig_responder))
    app=setup(tmp_path)
    with TestClient(app) as c:
        h=bearer(c)
        assert grant(c,h,'instagram','178900').status_code==201
        posted=c.post('/v1/ingestion/runs',headers=h,json={
            'platform':'instagram','source_account_id':'178900',
            'run_key':'route-test-001','limit':3})
        assert posted.status_code==200,posted.text
        assert posted.json()['new_records']==1
        overview=c.get('/v1/ui/overview',headers=h)
        assert overview.status_code==200
        assert overview.json()['counts']['posts']==1
        assert overview.json()['recent_posts'][0]['origin']=='instagram'
        assert overview.json()['data_scope']=='authorized_metadata_and_synthetic'
        events=c.get('/v1/events',headers=h).json()['events']
        assert events[-1]['event_type']=='ingestion.content_processed'
