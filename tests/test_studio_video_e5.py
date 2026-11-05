"""IMP-187/188: versioned storyboard/timeline contract, API security and limits."""
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from sqlalchemy import select

from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.studio_e1 import CreativeSpec
from tapi_gate0.studio_video_e5 import StoryboardDocument, StoryScene, TimelineClip, TextOverlay, OverlayKeyframe, storyboard_versions

PASSWORD='long-local-test-pass-12345'

def test_timeline_creation_revision_and_isolation(tmp_path):
    app=create_secure_app(f"sqlite:///{tmp_path/'video.sqlite'}",initialize_schema=True,allow_http_local=True)
    auth=app.state.identity_store
    auth.bootstrap('tenantA','Tenant A','founder',PASSWORD)
    with TestClient(app) as client:
        def login(tenant='tenantA',user='founder'):
            r=client.post('/v1/auth/sessions',json={'username':user,'password':PASSWORD,'tenant_id':tenant})
            assert r.status_code==200,r.text
            return {'Authorization':'Bearer '+r.json()['access_token']}
        admin=login()
        spec=CreativeSpec(spec_id='spec.one',tenant_id='tenantA',
            objective='Criar um vídeo educativo sobre empreendedorismo',
            headline='Organize o caixa',body='Separe despesas.',cta='Verifique resultados.',
            platform_intent='instagram_carousel')
        draft=client.post('/v1/studio/documents',headers=admin,json={
            'document_id':'design.source','spec':spec.model_dump()})
        assert draft.status_code==201,draft.text
        request={'storyboard_id':'story.one','source_document_id':'design.source',
                 'platform_intent':'instagram_reel'}
        created=client.post('/v1/studio/storyboards',headers=admin,json=request)
        assert created.status_code==201,created.text
        sb=created.json()
        assert sb['schema_version']=='studio-storyboard.v1'
        assert sb['source_document_version']==1
        assert sb['scenes'][0]['narration']=='Organize o caixa'
        assert sb['approval_status']=='draft'
        assert sb['audio_status']=='not_implemented' and sb['render_status']=='not_implemented'
        assert client.post('/v1/studio/storyboards',headers=admin,json=request).status_code==409
        timeline={'expected_version':1,'scenes':[
          {'scene_id':'scene.1','duration_ms':3500,'narration':'Primeiro o problema.',
            'overlays':[{'text':'Caixa positivo','start_ms':0,'end_ms':2500,
              'keyframes':[{'at_ms':0,'x':100,'y':100,'opacity':0},
                           {'at_ms':900,'x':100,'y':100,'opacity':100}]}]},
          {'scene_id':'scene.2','duration_ms':2000,'narration':'Depois a solução.',
            'overlays':[{'text':'Organize despesas','start_ms':0,'end_ms':1800}]}],
          'clips':[{'scene_id':'scene.1','start_ms':0,'duration_ms':3500,'transition':'cut'},
                   {'scene_id':'scene.2','start_ms':3500,'duration_ms':2000,'transition':'cut'}]}
        updated=client.post('/v1/studio/storyboards/story.one/timeline',headers=admin,json=timeline)
        assert updated.status_code==200,updated.text
        assert updated.json()['version']==2 and len(updated.json()['scenes'])==2
        assert updated.json()['clips'][1]['start_ms']==3500
        assert client.post('/v1/studio/storyboards/story.one/timeline',headers=admin,json=timeline).status_code==409
        historical=client.get('/v1/studio/storyboards/story.one/versions/1',headers=admin)
        assert historical.status_code==200 and len(historical.json()['scenes'])==1
        assert client.get('/v1/studio/storyboards/story.one',headers=admin).json()['version']==2
        with auth.engine.connect() as db:
            history=db.execute(select(storyboard_versions.c.version,storyboard_versions.c.edited_by).where(
              storyboard_versions.c.tenant_id=='tenantA',
              storyboard_versions.c.storyboard_id=='story.one').order_by(storyboard_versions.c.version)).all()
        assert history==[(1,'founder'),(2,'founder')]
        overlap={**timeline,'expected_version':2,'clips':[
          timeline['clips'][0],{**timeline['clips'][1],'start_ms':1000}]}
        assert client.post('/v1/studio/storyboards/story.one/timeline',headers=admin,json=overlap).status_code==422
        overrun={**timeline,'expected_version':2,'scenes':[
          {**timeline['scenes'][0],'duration_ms':1000}, timeline['scenes'][1]],
          'clips':[{**timeline['clips'][0],'duration_ms':1000},
                   {**timeline['clips'][1],'start_ms':1000}]}
        assert client.post('/v1/studio/storyboards/story.one/timeline',headers=admin,json=overrun).status_code==422
        assert client.get('/v1/studio/storyboards/story.one',headers=admin).json()['version']==2
        assert client.post('/v1/studio/storyboards',json=request).status_code==401
        # Another tenant cannot read, modify or create from this tenant's design.
        with auth.engine.begin() as db:
            from tapi_gate0.sa_store import tenants
            from tapi_gate0.identity import memberships
            from sqlalchemy import insert
            db.execute(insert(tenants).values(tenant_id='tenantB',name='B'))
            db.execute(insert(memberships).values(user_id='founder',tenant_id='tenantB',role='admin'))
        other=login('tenantB')
        assert client.get('/v1/studio/storyboards/story.one',headers=other).status_code==404
        assert client.post('/v1/studio/storyboards',headers=other,json=request).status_code==404
        assert client.post('/v1/studio/storyboards/story.one/timeline',headers=other,json=timeline).status_code==404


def test_schema_rejects_unbounded_or_inconsistent_timeline():
    with pytest.raises(ValidationError):
        TextOverlay(text='x',start_ms=2000,end_ms=1000)
    with pytest.raises(ValidationError):
        TextOverlay(text='x',start_ms=0,end_ms=1000,
                    keyframes=[OverlayKeyframe(at_ms=500),OverlayKeyframe(at_ms=200)])
    with pytest.raises(ValidationError):
        StoryScene(scene_id='scene.1',duration_ms=1200,narration='a',
            overlays=[TextOverlay(text='x',start_ms=0,end_ms=2000)])
    with pytest.raises(ValidationError):
        StoryboardDocument(storyboard_id='story.one',tenant_id='t',
            source_document_id='design.one',source_document_version=1,version=1,
            platform_intent='instagram_reel',scenes=[StoryScene(scene_id='scene.1',narration='Hello')],
            clips=[TimelineClip(scene_id='scene.1',start_ms=100,duration_ms=5000)])
