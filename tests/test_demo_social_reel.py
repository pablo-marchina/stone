"""Native Reel profile retains existing local queue rights and exact frame dimensions."""
import base64
from io import BytesIO
import json
import shutil
import subprocess

import pytest
from PIL import Image
from sqlalchemy import select
from tapi_gate0.studio_render_e6 import LocalDraftRenderer, studio_render_jobs
from test_studio_e6 import setup, create_storyboard, asset, attest


def test_social_vertical_profile(tmp_path, monkeypatch):
    monkeypatch.setenv('TAPI_LOCAL_RENDER_ENABLED','1')
    monkeypatch.setenv('TAPI_ZERO_BILLING_CONFIRMED','1')
    app,c,h=setup(tmp_path)
    try:
        create_storyboard(c,h)
        def queue(aid):
            return c.post('/v1/studio/render-jobs',headers=h,json={
                'job_id':'job.social','storyboard_id':'story.one','storyboard_version':1,
                'frames':[{'scene_id':'scene.1','asset_id':aid}], 'render_profile':'social_vertical_v1'})
        wrong=asset(c,h)
        assert queue(wrong).status_code==403
        assert attest(c,h,wrong).status_code==200
        assert queue(wrong).json()['detail']=='STUDIO_SOCIAL_VERTICAL_FRAME_REQUIRED'
        out=BytesIO();Image.new('RGB',(1080,1920),'#C9F36B').save(out,'PNG')
        r=c.post('/v1/studio/assets/png',headers=h,json={'data_base64':base64.b64encode(out.getvalue()).decode(),'rights_attested':True})
        assert r.status_code==201,r.text
        aid=r.json()['asset_id'];assert attest(c,h,aid).status_code==200
        assert queue(aid).status_code==201
        with app.state.identity_store.engine.connect() as db:
            raw=db.execute(select(studio_render_jobs.c.manifest).where(studio_render_jobs.c.job_id=='job.social')).scalar_one()
            assert json.loads(raw)['render_profile']=='social_vertical_v1'
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            pytest.skip('FFmpeg and FFprobe required for native render verification')
        job=LocalDraftRenderer(app.state.identity_store.engine).process_next('tenantA')
        assert job.status=='succeeded',job
        r=c.get('/v1/studio/render-artifacts/'+job.artifact_id,headers=h)
        assert r.status_code==200
        path=tmp_path/'vertical.mp4';path.write_bytes(r.content)
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=width,height,r_frame_rate','-of','json',str(path)]))
        assert probe['streams']==[{'width':1080,'height':1920,'r_frame_rate':'30/1'}]
    finally:
        c.__exit__(None,None,None)
        app.state.identity_store.engine.dispose()
