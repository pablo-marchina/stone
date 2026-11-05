"""E7: video source trims, multitrack audio, keyframe positions, fades, safe leases."""
import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import io
import json
import shutil
import struct
import subprocess
import wave

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update

from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.sa_store import tenants
from tapi_gate0.studio_advanced_e7 import (AdvancedStudioRenderer, UploadVideoSource,
    advanced_jobs, advanced_events, video_sources, _interpolate, _mix_wavs)
from tapi_gate0.studio_e1 import StudioError
from tapi_gate0.studio_video_e5 import (StoryboardStore, StoryScene, TimelineClip,
    UpdateStoryboard, OverlayKeyframe, TextOverlay)

PASSWORD="secure-studio-e7-testing-password"


def setup(tmp_path):
    app=create_secure_app(f"sqlite:///{tmp_path / 'e7.sqlite'}",initialize_schema=True,
                          allow_http_local=True)
    app.state.identity_store.bootstrap("tenantA","Tenant A","founder",PASSWORD)
    client=TestClient(app);client.__enter__()
    login=client.post("/v1/auth/sessions",json={
        "username":"founder","password":PASSWORD,"tenant_id":"tenantA"})
    assert login.status_code==200,login.text
    headers={"Authorization":"Bearer "+login.json()["access_token"]}
    draft=client.post("/v1/studio/documents",headers=headers,json={
        "document_id":"design.e7","spec":{
            "spec_id":"spec.e7","tenant_id":"tenantA","objective":"Conteúdo educativo",
            "headline":"Organize seu caixa","body":"Planeje suas despesas",
            "cta":"Aprenda a planejar","platform_intent":"instagram_feed"}})
    assert draft.status_code==201,draft.text
    storyboard=client.post("/v1/studio/storyboards",headers=headers,json={
        "storyboard_id":"story.e7","source_document_id":"design.e7",
        "platform_intent":"instagram_reel"})
    assert storyboard.status_code==201,storyboard.text
    return app,client,headers


def expiry():
    return (datetime.now(timezone.utc)+timedelta(days=7)).isoformat()


def to_story_two(app):
    store=StoryboardStore(app.state.identity_store.engine)
    text=TextOverlay(text="Vendas",start_ms=0,end_ms=1100,
                     keyframes=[OverlayKeyframe(at_ms=0,x=50,y=150,opacity=20),
                                OverlayKeyframe(at_ms=1100,x=350,y=150,opacity=100)])
    scenes=[StoryScene(scene_id="scene.1",duration_ms=1200,narration="Abertura",
                       overlays=[text]),
            StoryScene(scene_id="scene.2",duration_ms=1200,narration="Conselho",
                       overlays=[TextOverlay(text="Planeje!",end_ms=1100)])]
    clips=[TimelineClip(scene_id="scene.1",start_ms=0,duration_ms=1200,
                        transition="crossfade",transition_ms=300),
           TimelineClip(scene_id="scene.2",start_ms=1200,duration_ms=1200)]
    return store.update("tenantA","founder","story.e7",UpdateStoryboard(
        expected_version=1,scenes=scenes,clips=clips))


def wav(value):
    data=io.BytesIO()
    samples=b"".join(struct.pack("<h",value) for _ in range(16000))
    with wave.open(data,"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000)
        f.writeframes(samples)
    return base64.b64encode(data.getvalue()).decode()


def image_png():
    from PIL import Image
    b=io.BytesIO();Image.new("RGB",(100,180),"#17aabb").save(b,"PNG")
    return base64.b64encode(b.getvalue()).decode()


def mp4_bytes(tmp_path):
    path=tmp_path/"silent.mp4"
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
        "-f","lavfi","-i","color=c=red:s=180x320:r=12",
        "-t","2.8","-an","-c:v","libx264","-pix_fmt","yuv420p",
        "-movflags","+faststart",str(path)],check=True,timeout=20)
    return path.read_bytes()


def attest_audio(c,h,value):
    r=c.post("/v1/studio/audio/wav",headers=h,json={
        "data_base64":wav(value),"evidence_reference":"local-author-voice-source-record",
        "expires_at":expiry(),"rights_attested":True})
    assert r.status_code==201,r.text
    return r.json()["asset_id"]


def attest_png(c,h):
    r=c.post("/v1/studio/assets/png",headers=h,json={
        "data_base64":image_png(),"rights_attested":True})
    assert r.status_code==201,r.text
    asset=r.json()["asset_id"]
    r=c.post("/v1/studio/assets/draft-render-rights",headers=h,json={
        "asset_id":asset,"evidence_reference":"local-author-image-source-2026",
        "expires_at":expiry(),"rights_attested":True})
    assert r.status_code==200,r.text
    return asset


def gate(monkeypatch):
    monkeypatch.setenv("TAPI_LOCAL_RENDER_ENABLED","1")
    monkeypatch.setenv("TAPI_ZERO_BILLING_CONFIRMED","1")
    monkeypatch.setenv("TAPI_E7_VIDEO_RENDER_ENABLED","1")


def test_interpolated_keyframes_and_multitrack_pcm_mix():
    points=[OverlayKeyframe(at_ms=0,x=0,y=0,opacity=0),
            OverlayKeyframe(at_ms=1000,x=1000,y=500,opacity=100)]
    assert _interpolate(points,500)==(500,250,50)
    first=base64.b64decode(wav(1200));second=base64.b64decode(wav(800))
    combined=_mix_wavs([(first,0,100),(second,200,50)],1200)
    with wave.open(io.BytesIO(combined),"rb") as f:
        samples=f.readframes(f.getnframes())
        assert struct.unpack_from("<h",samples,100*32)[0]==1200
        assert struct.unpack_from("<h",samples,250*32)[0]==1600
        assert struct.unpack_from("<h",samples,1100*32)[0]==400


def test_storyboard_rejects_invalid_crossfade(tmp_path):
    app,client,h=setup(tmp_path)
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TimelineClip(scene_id="scene.1",start_ms=0,duration_ms=1200,
                     transition="crossfade",transition_ms=0)
    with pytest.raises(ValidationError):
        TimelineClip(scene_id="scene.1",start_ms=0,duration_ms=1200,
                     transition="cut",transition_ms=300)
    client.__exit__(None,None,None)


def test_gates_rights_tenant_and_expired_lease_recovery(tmp_path,monkeypatch):
    app,c,h=setup(tmp_path);to_story_two(app)
    service=AdvancedStudioRenderer(app.state.identity_store.engine)
    denied=c.post("/v1/studio/video-sources/mp4",headers=h,json={
        "data_base64":base64.b64encode(b"not video"*25).decode(),
        "evidence_reference":"local-authorized-video-2026",
        "expires_at":expiry(),"rights_attested":True})
    assert denied.status_code==403
    gate(monkeypatch)
    denied=c.post("/v1/studio/video-sources/mp4",headers=h,json={
        "data_base64":base64.b64encode(b"not video"*25).decode(),
        "evidence_reference":"local-authorized-video-2026",
        "expires_at":expiry(),"rights_attested":True})
    assert denied.status_code==422
    png=attest_png(c,h)
    request={"job_id":"e7.lease","storyboard_id":"story.e7","storyboard_version":2,
        "scenes":[{"scene_id":"scene.1","image_asset_id":png},
                  {"scene_id":"scene.2","image_asset_id":png}]}
    queued=c.post("/v1/studio/advanced-render-jobs",headers=h,json=request)
    assert queued.status_code==201,queued.text
    with app.state.identity_store.engine.begin() as db:
        db.execute(update(advanced_jobs).where(advanced_jobs.c.tenant_id=="tenantA",
            advanced_jobs.c.job_id=="e7.lease").values(status="running",attempts=1,
            lease_token="oldworker",lease_until="2025-01-01T00:00:00+00:00"))
    assert service.recover_stale("tenantA")==1
    assert service.get("tenantA","e7.lease").status=="queued"
    assert c.post("/v1/studio/advanced-render-jobs/e7.lease/cancel",headers=h).status_code==200
    assert service.process_next("tenantA") is None
    assert c.get("/v1/studio/advanced-render-jobs/e7.lease",headers=h).json()["status"]=="canceled"
    assert c.get("/v1/studio/advanced-render-jobs/e7.lease").status_code==401
    with app.state.identity_store.engine.begin() as db:
        db.execute(insert(tenants).values(tenant_id="tenantB",name="B"))
    assert service.get("tenantA","e7.lease").status=="canceled"
    with pytest.raises(StudioError,match="STUDIO_E7_JOB_NOT_FOUND"):
        service.get("tenantB","e7.lease")
    c.__exit__(None,None,None)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),reason="FFmpeg local missing")
def test_real_video_trim_tracks_transitions_and_revocation(tmp_path,monkeypatch):
    gate(monkeypatch)
    app,c,h=setup(tmp_path);to_story_two(app)
    visual=mp4_bytes(tmp_path)
    source=c.post("/v1/studio/video-sources/mp4",headers=h,json={
        "data_base64":base64.b64encode(visual).decode(),
        "evidence_reference":"owned-local-video-record-2026",
        "expires_at":expiry(),"rights_attested":True})
    assert source.status_code==201,source.text
    source_id=source.json()["asset_id"]
    png=attest_png(c,h)
    audio1=attest_audio(c,h,1000)
    audio2=attest_audio(c,h,500)
    queued=c.post("/v1/studio/advanced-render-jobs",headers=h,json={
        "job_id":"e7.video1","storyboard_id":"story.e7","storyboard_version":2,
        "scenes":[{"scene_id":"scene.1","video_asset_id":source_id,"trim_start_ms":300},
                  {"scene_id":"scene.2","image_asset_id":png}],
        "audio_tracks":[{"asset_id":audio1,"start_ms":0,"gain_percent":75},
                        {"asset_id":audio2,"start_ms":450,"gain_percent":50}]})
    assert queued.status_code==201,queued.text
    worker=AdvancedStudioRenderer(app.state.identity_store.engine)
    result=worker.process_next("tenantA")
    assert result.status=="succeeded",(result.error_code,result.model_dump())
    assert result.artifact_sha256
    downloaded=c.get("/v1/studio/advanced-render-artifacts/"+result.artifact_id,headers=h)
    assert downloaded.status_code==200,downloaded.text[:100]
    assert sha256(downloaded.content).hexdigest()==result.artifact_sha256
    video=tmp_path/"out.mp4";video.write_bytes(downloaded.content)
    probed=subprocess.run(["ffprobe","-v","error","-show_entries",
        "format=duration:stream=codec_type,width,height,r_frame_rate", "-of","json",str(video)],
        text=True,capture_output=True,timeout=20,check=True)
    details=json.loads(probed.stdout)
    assert 2.1<=float(details["format"]["duration"])<=2.55
    assert any(s.get("codec_type")=="video" and s.get("width")==540 and s.get("height")==960
               for s in details["streams"])
    assert any(s.get("codec_type")=="audio" for s in details["streams"])
    revocation=c.post("/v1/studio/video-sources/"+source_id+"/revoke",headers=h)
    assert revocation.status_code==200
    assert c.get("/v1/studio/advanced-render-artifacts/"+result.artifact_id,headers=h).status_code==403
    with app.state.identity_store.engine.connect() as db:
        actions=db.execute(select(advanced_events.c.action).where(
            advanced_events.c.tenant_id=="tenantA")).scalars().all()
    assert {"video_attested","queued","running","succeeded","video_revoked"} <= set(actions)
    c.__exit__(None,None,None)


def test_cancellation_wins_worker_completion(tmp_path,monkeypatch):
    gate(monkeypatch)
    app,c,h=setup(tmp_path);to_story_two(app)
    png=attest_png(c,h)
    request={"job_id":"e7.race","storyboard_id":"story.e7","storyboard_version":2,
        "scenes":[{"scene_id":"scene.1","image_asset_id":png},
                  {"scene_id":"scene.2","image_asset_id":png}]}
    assert c.post("/v1/studio/advanced-render-jobs",headers=h,json=request).status_code==201
    worker=AdvancedStudioRenderer(app.state.identity_store.engine)
    def canceled_during_render(*args,**kwargs):
        assert worker.cancel("tenantA","founder","e7.race").status=="canceled"
        return b"fake mp4"
    monkeypatch.setattr(worker,"_render",canceled_during_render)
    result=worker.process_next("tenantA")
    assert result.status=="canceled" and result.artifact_id is None
    c.__exit__(None,None,None)


def test_recovery_exhaustion_and_stale_token_cannot_finalize(tmp_path,monkeypatch):
    gate(monkeypatch)
    app,c,h=setup(tmp_path);to_story_two(app)
    png=attest_png(c,h)
    job={"job_id":"e7.exhaust","storyboard_id":"story.e7","storyboard_version":2,
         "scenes":[{"scene_id":"scene.1","image_asset_id":png},
                   {"scene_id":"scene.2","image_asset_id":png}]}
    assert c.post("/v1/studio/advanced-render-jobs",headers=h,json=job).status_code==201
    worker=AdvancedStudioRenderer(app.state.identity_store.engine)
    with app.state.identity_store.engine.begin() as db:
        db.execute(update(advanced_jobs).where(advanced_jobs.c.tenant_id=="tenantA",
            advanced_jobs.c.job_id=="e7.exhaust").values(
            status="running",attempts=3,lease_token="expiredworker",
            lease_until="2025-01-01T00:00:00+00:00"))
    assert worker.recover_stale("tenantA")==1
    failed=worker.get("tenantA","e7.exhaust")
    assert failed.status=="failed" and failed.error_code=="STUDIO_E7_LEASE_EXHAUSTED"
    assert c.post("/v1/studio/advanced-render-jobs/e7.exhaust/retry",headers=h).status_code==409
    assert worker.process_next("tenantA") is None
    c.__exit__(None,None,None)


def test_render_rejects_rights_revoked_while_encoding(tmp_path,monkeypatch):
    gate(monkeypatch)
    app,c,h=setup(tmp_path);to_story_two(app)
    png=attest_png(c,h)
    request={"job_id":"e7.rights-race","storyboard_id":"story.e7","storyboard_version":2,
         "scenes":[{"scene_id":"scene.1","image_asset_id":png},
                   {"scene_id":"scene.2","image_asset_id":png}]}
    assert c.post("/v1/studio/advanced-render-jobs",headers=h,json=request).status_code==201
    worker=AdvancedStudioRenderer(app.state.identity_store.engine)
    def revoke_after_render(*args,**kwargs):
        response=c.post("/v1/studio/assets/"+png+"/draft-render-rights/revoke",headers=h)
        assert response.status_code==200
        return b"fake mp4"
    monkeypatch.setattr(worker,"_render",revoke_after_render)
    result=worker.process_next("tenantA")
    assert result.status=="failed" and result.error_code=="STUDIO_RENDER_RIGHTS_NOT_ACTIVE"
    assert result.artifact_id is None
    c.__exit__(None,None,None)


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='FFmpeg local missing')
def test_rejects_trim_beyond_video_and_embedded_audio(tmp_path,monkeypatch):
    gate(monkeypatch)
    app,c,h=setup(tmp_path);to_story_two(app)
    raw=mp4_bytes(tmp_path)
    uploaded=c.post('/v1/studio/video-sources/mp4',headers=h,json={
        'data_base64':base64.b64encode(raw).decode(),
        'evidence_reference':'locally-authored-video-2026','expires_at':expiry(),
        'rights_attested':True})
    assert uploaded.status_code==201
    asset=uploaded.json()['asset_id']
    static=attest_png(c,h)
    outcome=c.post('/v1/studio/advanced-render-jobs',headers=h,json={
        'job_id':'e7.badtrim','storyboard_id':'story.e7','storyboard_version':2,
        'scenes':[{'scene_id':'scene.1','video_asset_id':asset,'trim_start_ms':2500},
                  {'scene_id':'scene.2','image_asset_id':static}]})
    assert outcome.status_code==422 and outcome.json()['detail']=='STUDIO_E7_TRIM_OUT_OF_BOUNDS'
    invalid=tmp_path/'withaudio.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',
        '-f','lavfi','-i','color=c=blue:s=180x320:r=12',
        '-f','lavfi','-i','anullsrc=r=16000:cl=mono',
        '-t','1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(invalid)],
        check=True,timeout=20)
    rejected=c.post('/v1/studio/video-sources/mp4',headers=h,json={
        'data_base64':base64.b64encode(invalid.read_bytes()).decode(),
        'evidence_reference':'locally-authored-embedded-audio-2026',
        'expires_at':expiry(),'rights_attested':True})
    assert rejected.status_code==422 and rejected.json()['detail']=='STUDIO_E7_VIDEO_ONLY_REQUIRED'
    c.__exit__(None,None,None)


def test_stale_worker_token_cannot_commit_an_artifact(tmp_path,monkeypatch):
    gate(monkeypatch)
    app,c,h=setup(tmp_path);to_story_two(app)
    png=attest_png(c,h)
    request={"job_id":"e7.token-race","storyboard_id":"story.e7","storyboard_version":2,
         "scenes":[{"scene_id":"scene.1","image_asset_id":png},
                   {"scene_id":"scene.2","image_asset_id":png}]}
    assert c.post("/v1/studio/advanced-render-jobs",headers=h,json=request).status_code==201
    worker=AdvancedStudioRenderer(app.state.identity_store.engine)
    def stolen_lease(*args,**kwargs):
        with app.state.identity_store.engine.begin() as db:
            db.execute(update(advanced_jobs).where(advanced_jobs.c.tenant_id=="tenantA",
                advanced_jobs.c.job_id=="e7.token-race").values(lease_token="new-worker-token"))
        return b"fake mp4"
    monkeypatch.setattr(worker,"_render",stolen_lease)
    outcome=worker.process_next("tenantA")
    assert outcome.status=="running" and outcome.artifact_id is None
    with app.state.identity_store.engine.connect() as db:
        row=db.execute(select(advanced_jobs.c.lease_token).where(
            advanced_jobs.c.tenant_id=="tenantA",
            advanced_jobs.c.job_id=="e7.token-race")).scalar_one()
    assert row=="new-worker-token"
    c.__exit__(None,None,None)
