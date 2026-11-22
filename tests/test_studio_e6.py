"""CAP-023 E6: no-spend local MP4, rights revocation, evidence-bound edits."""
import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import io
import shutil
import subprocess
import wave

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, func

from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.domain import Creator, ContentItem, MetricsCreate, Origin, MediaType
from tapi_gate0.sa_store import tenants, creators, content_items, metrics_snapshots
from tapi_gate0.identity import memberships
from tapi_gate0.studio_render_e6 import (
    LocalDraftRenderer, studio_render_rights_events, studio_render_events,
    studio_render_artifacts, studio_render_jobs)
from tapi_gate0.studio_evidence_edits_e6 import studio_evidence_edit_events, StudioEvidenceEditService

PASSWORD = 'Local-Testing-Password-2026'


def setup(tmp_path):
    app=create_secure_app(f"sqlite:///{tmp_path / 'render.sqlite'}",
                          initialize_schema=True,allow_http_local=True)
    auth=app.state.identity_store
    auth.bootstrap('tenantA','Test Tenant A','founder',PASSWORD)
    client=TestClient(app);client.__enter__()
    login=client.post('/v1/auth/sessions',json={
        'username':'founder','tenant_id':'tenantA','password':PASSWORD})
    assert login.status_code==200,login.text
    h={'Authorization':'Bearer '+login.json()['access_token']}
    return app,client,h


def png():
    from PIL import Image
    out=io.BytesIO();Image.new('RGB',(48,86),'#4b8768').save(out,'PNG')
    return base64.b64encode(out.getvalue()).decode()


def wav():
    out=io.BytesIO()
    with wave.open(out,'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000)
        f.writeframes(b'\0\0'*16000)
    return base64.b64encode(out.getvalue()).decode()


def expiry():
    return (datetime.now(timezone.utc)+timedelta(days=14)).isoformat()


def create_storyboard(client,h,doc_id='design.one',sb_id='story.one',ref_ids=None):
    spec={'spec_id':'spec.one','tenant_id':'tenantA',
          'objective':'Criar um roteiro audiovisual educativo para empresas',
          'headline':'Organize o caixa','body':'Separe receitas e despesas',
          'cta':'Revise os custos.','reference_content_ids':ref_ids or [],
          'platform_intent':'instagram_feed'}
    draft=client.post('/v1/studio/documents',headers=h,
                      json={'document_id':doc_id,'spec':spec})
    assert draft.status_code==201,draft.text
    story=client.post('/v1/studio/storyboards',headers=h,json={
        'storyboard_id':sb_id,'source_document_id':doc_id,
        'platform_intent':'instagram_reel'})
    assert story.status_code==201,story.text
    return story.json()


def asset(client,h):
    uploaded=client.post('/v1/studio/assets/png',headers=h,
                         json={'data_base64':png(),'rights_attested':True})
    assert uploaded.status_code==201,uploaded.text
    return uploaded.json()['asset_id']


def attest(client,h,id_):
    return client.post('/v1/studio/assets/draft-render-rights',headers=h,json={
        'asset_id':id_,
        'evidence_reference':'local-author-asset-rights-2026',
        'expires_at':expiry(),'rights_attested':True})


def queue(client,h,aid,job='job.local',audio=None):
    return client.post('/v1/studio/render-jobs',headers=h,json={
        'job_id':job,'storyboard_id':'story.one','storyboard_version':1,
        'frames':[{'scene_id':'scene.1','asset_id':aid}],
        'audio_asset_id':audio})


def test_local_worker_is_gated_and_attestations_are_revocable(tmp_path,monkeypatch):
    app,c,h=setup(tmp_path)
    create_storyboard(c,h)
    id_=asset(c,h)
    denied=queue(c,h,id_)
    assert denied.status_code==403 and denied.json()['detail']=='STUDIO_RENDER_DISABLED'
    monkeypatch.setenv('TAPI_LOCAL_RENDER_ENABLED','1')
    monkeypatch.setenv('TAPI_ZERO_BILLING_CONFIRMED','1')
    denied=queue(c,h,id_)
    assert denied.status_code==403 and denied.json()['detail']=='STUDIO_RENDER_RIGHTS_NOT_ACTIVE'
    a=attest(c,h,id_)
    assert a.status_code==200,a.text
    queued=queue(c,h,id_)
    assert queued.status_code==201,queued.text
    assert queued.json()['status']=='queued'
    assert queued.json()['draft_only'] and not queued.json()['production_approved']
    revoke=c.post(f'/v1/studio/assets/{id_}/draft-render-rights/revoke',headers=h)
    assert revoke.status_code==200
    worker=LocalDraftRenderer(app.state.identity_store.engine)
    failed=worker.process_next('tenantA')
    assert failed.status=='failed' and failed.error_code=='STUDIO_RENDER_RIGHTS_NOT_ACTIVE'
    assert failed.artifact_id is None and failed.attempts==1
    assert worker.retry('tenantA','founder','job.local').status=='queued'
    assert worker.process_next('tenantA').status=='failed'
    assert c.post('/v1/studio/render-jobs/job.local/retry',headers=h).status_code==409
    with app.state.identity_store.engine.connect() as db:
        states=db.execute(select(studio_render_events.c.action).where(
            studio_render_events.c.tenant_id=='tenantA').order_by(
            studio_render_events.c.at)).scalars().all()
        rights=db.execute(select(studio_render_rights_events.c.action).where(
            studio_render_rights_events.c.tenant_id=='tenantA')).scalars().all()
    assert 'queued' in states and 'failed' in states
    assert rights==['attested','revoked']
    c.__exit__(None,None,None)


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='requires local ffmpeg/ffprobe')
def test_real_mp4_pcm_audio_and_tenant_isolation(tmp_path,monkeypatch):
    app,c,h=setup(tmp_path)
    create_storyboard(c,h)
    png_id=asset(c,h)
    assert attest(c,h,png_id).status_code==200
    recorded=c.post('/v1/studio/audio/wav',headers=h,json={
        'data_base64':wav(),'rights_attested':True,
        'evidence_reference':'original-recording-evidence-2026',
        'expires_at':expiry()})
    assert recorded.status_code==201,recorded.text
    audio_id=recorded.json()['asset_id']
    monkeypatch.setenv('TAPI_LOCAL_RENDER_ENABLED','1')
    monkeypatch.setenv('TAPI_ZERO_BILLING_CONFIRMED','1')
    queued=queue(c,h,png_id,audio=audio_id)
    assert queued.status_code==201,queued.text
    renderer=LocalDraftRenderer(app.state.identity_store.engine)
    outcome=renderer.process_next('tenantA')
    assert outcome.status=='succeeded',outcome.error_code
    assert outcome.artifact_id and outcome.sha256
    response=c.get('/v1/studio/render-artifacts/'+outcome.artifact_id,headers=h)
    assert response.status_code==200,response.text[:100]
    assert response.content[4:8]==b'ftyp'
    assert sha256(response.content).hexdigest()==outcome.sha256
    assert 'attachment' in response.headers['content-disposition']
    assert response.headers['cache-control']=='private, no-store'
    path=tmp_path/'draft.mp4';path.write_bytes(response.content)
    probe=subprocess.run(['ffprobe','-v','error','-show_entries',
        'format=duration:stream=codec_type,width,height','-of','json',str(path)],
        capture_output=True,text=True,check=True,timeout=15)
    import json
    data=json.loads(probe.stdout)
    assert 4.5<=float(data['format']['duration'])<=5.5
    assert any(x.get('codec_type')=='video' and x.get('width')==360 and x.get('height')==640
               for x in data['streams'])
    assert any(x.get('codec_type')=='audio' for x in data['streams'])
    with app.state.identity_store.engine.begin() as db:
        db.execute(insert(tenants).values(tenant_id='tenantB',name='Tenant B'))
        db.execute(insert(memberships).values(user_id='founder',tenant_id='tenantB',role='admin'))
    other=c.post('/v1/auth/sessions',json={'username':'founder','password':PASSWORD,'tenant_id':'tenantB'})
    assert other.status_code==200
    hb={'Authorization':'Bearer '+other.json()['access_token']}
    assert c.get('/v1/studio/render-jobs/job.local',headers=hb).status_code==404
    assert c.get('/v1/studio/render-artifacts/'+outcome.artifact_id,headers=hb).status_code==404
    assert c.post('/v1/studio/assets/'+png_id+'/draft-render-rights/revoke',headers=hb).status_code==404
    assert c.get('/v1/studio/render-artifacts/'+outcome.artifact_id).status_code==401
    # Rights revocation also blocks subsequent retrieval of an already-created
    # local draft artifact, without deleting its immutable audit record.
    revoked=c.post('/v1/studio/assets/'+png_id+'/draft-render-rights/revoke',headers=h)
    assert revoked.status_code==200
    assert c.get('/v1/studio/render-artifacts/'+outcome.artifact_id,headers=h).status_code==403
    c.__exit__(None,None,None)


def test_canceled_job_cannot_run_and_audio_rejects_bad_data(tmp_path,monkeypatch):
    app,c,h=setup(tmp_path)
    create_storyboard(c,h)
    png_id=asset(c,h)
    assert attest(c,h,png_id).status_code==200
    monkeypatch.setenv('TAPI_LOCAL_RENDER_ENABLED','1')
    monkeypatch.setenv('TAPI_ZERO_BILLING_CONFIRMED','1')
    assert queue(c,h,png_id).status_code==201
    canceled=c.post('/v1/studio/render-jobs/job.local/cancel',headers=h)
    assert canceled.status_code==200 and canceled.json()['status']=='canceled'
    assert LocalDraftRenderer(app.state.identity_store.engine).process_next('tenantA') is None
    bad=c.post('/v1/studio/audio/wav',headers=h,json={
        'data_base64':base64.b64encode(b'bad wav data').decode(),
        'rights_attested':True,'evidence_reference':'bad-audio-local-test',
        'expires_at':expiry()})
    assert bad.status_code==422
    c.__exit__(None,None,None)


def test_evidence_bound_edit_requires_persisted_snapshot_and_explicit_confirmation(tmp_path, monkeypatch):
    # E6 edit-flow unit test: mock the independent metadata policy only here.
    # It must NOT be interpreted as an operational source grant.
    monkeypatch.setattr(StudioEvidenceEditService, "_metadata_source_scope",
                        staticmethod(lambda *_: "f" * 64))
    app,c,h=setup(tmp_path)
    auth=app.state.identity_store
    published=datetime(2026,10,1,tzinfo=timezone.utc)
    now=datetime(2026,11,5,tzinfo=timezone.utc)
    creator=Creator(tenant_id='tenantA',creator_id='creator.real',origin=Origin.INSTAGRAM,
                    handle='publicsource',created_at=now)
    post=ContentItem(tenant_id='tenantA',content_id='content.real',creator_id=creator.creator_id,
                     origin=Origin.INSTAGRAM,media_type=MediaType.REELS,
                     published_at=published,source_url='https://www.instagram.com/reel/Example123/',
                     caption='Marketing real da fonte externa',is_synthetic=False,created_at=now)
    snap=MetricsCreate(tenant_id='tenantA',content_id=post.content_id,
                       snapshot_id='metric.real',observed_at=now,
                       followers_measured_at=now,likes=10,comments=5,follower_count=2000)
    with auth.engine.begin() as db:
        db.execute(insert(creators).values(tenant_id='tenantA',id=creator.creator_id,
            origin=creator.origin.value,payload=creator.model_dump_json()))
        db.execute(insert(content_items).values(tenant_id='tenantA',id=post.content_id,
            creator_id=creator.creator_id,origin=post.origin.value,
            published_at=post.published_at.isoformat(),payload=post.model_dump_json()))
        db.execute(insert(metrics_snapshots).values(tenant_id='tenantA',id=snap.snapshot_id,
            content_id=post.content_id,observed_at=snap.observed_at.isoformat(),
            payload=snap.model_dump_json()))
    create_storyboard(c,h,ref_ids=['content.real'])
    original=c.get('/v1/studio/documents/design.one',headers=h)
    proposal={'expected_version':1,'page_id':'page.1','layer_id':'headline',
       'text':'Texto editado pelo operador','origin':'untrusted_model',
       'reference_content_id':'content.real','reference_snapshot_id':'metric.real'}
    pre=c.post('/v1/studio/documents/design.one/evidence-edits/preview',headers=h,json=proposal)
    assert pre.status_code==200,pre.text
    assert pre.json()['requires_operator_confirmation']
    assert not pre.json()['scientifically_validated']
    assert pre.json()['reference_snapshot_id']=='metric.real'
    assert c.get('/v1/studio/documents/design.one',headers=h).json()['version']==1
    confirm={**proposal,'operator_confirmed':True,
             'preview_sha256':pre.json()['preview_sha256']}
    forged=c.post('/v1/studio/documents/design.one/evidence-edits/apply',headers=h,
       json={**confirm,'preview_sha256':'a'*64})
    assert forged.status_code==409
    wrong=c.post('/v1/studio/documents/design.one/evidence-edits/preview',headers=h,
       json={**proposal,'reference_snapshot_id':'metric.other'})
    assert wrong.status_code==404
    done=c.post('/v1/studio/documents/design.one/evidence-edits/apply',
       headers={**h,'If-Match':original.headers['etag']},json=confirm)
    assert done.status_code==200,done.text
    assert done.json()['version']==2
    assert done.json()['approval_status']=='draft'
    stale=c.post('/v1/studio/documents/design.one/evidence-edits/apply',headers=h,json=confirm)
    assert stale.status_code==409
    with auth.engine.connect() as db:
        events=db.execute(select(studio_evidence_edit_events).where(
            studio_evidence_edit_events.c.tenant_id=='tenantA')).mappings().all()
    assert len(events)==1
    assert events[0]['content_id']=='content.real' and events[0]['snapshot_id']=='metric.real'
    assert events[0]['document_version']==2
    assert len(events[0]['snapshot_sha256'])==64
    c.__exit__(None,None,None)
