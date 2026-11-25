"""Motion v2 retains rights and a versioned three-scene timeline."""
import base64
import io
import json
import shutil
import subprocess
from hashlib import sha256
from PIL import Image, ImageDraw
import pytest
from sqlalchemy import select
from tapi_gate0.studio_render_e6 import LocalDraftRenderer, studio_render_jobs
from test_studio_e6 import setup, create_storyboard, asset, attest


def timeline(c,h):
    scenes=[{'scene_id':f'scene.{i+1}','duration_ms':d,'narration':'Rascunho original'} for i,d in enumerate((3000,7000,5000))]
    clips=[{'scene_id':s['scene_id'],'duration_ms':s['duration_ms'],'start_ms':sum(x['duration_ms'] for x in scenes[:i])} for i,s in enumerate(scenes)]
    r=c.post('/v1/studio/storyboards/story.one/timeline',headers=h,json={'expected_version':1,'scenes':scenes,'clips':clips})
    assert r.status_code==200,r.text
    return r.json()


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='requires local ffmpeg/ffprobe')
def test_motion_queue_timeline_rights_and_actual_video(tmp_path,monkeypatch):
    monkeypatch.setenv('TAPI_LOCAL_RENDER_ENABLED','1');monkeypatch.setenv('TAPI_ZERO_BILLING_CONFIRMED','1')
    app,c,h=setup(tmp_path)
    try:
        create_storyboard(c,h);story=timeline(c,h)
        assert story['version']==2 and [s['duration_ms'] for s in story['scenes']]==[3000,7000,5000]
        def queue(aid):
            return c.post('/v1/studio/render-jobs',headers=h,json={'job_id':'job.motion','storyboard_id':'story.one','storyboard_version':2,'frames':[{'scene_id':s['scene_id'],'asset_id':aid} for s in story['scenes']],'render_profile':'social_motion_v2'})
        wrong=asset(c,h);assert queue(wrong).status_code==403
        assert attest(c,h,wrong).status_code==200
        assert queue(wrong).json()['detail']=='STUDIO_SOCIAL_VERTICAL_FRAME_REQUIRED'
        im=Image.new('RGB',(1080,1920),'#102D22');ImageDraw.Draw(im).rectangle((80,1010,999,1509),fill='#C9F36B')
        buf=io.BytesIO();im.save(buf,'PNG')
        r=c.post('/v1/studio/assets/png',headers=h,json={'data_base64':base64.b64encode(buf.getvalue()).decode(),'rights_attested':True})
        assert r.status_code==201,r.text
        aid=r.json()['asset_id'];assert attest(c,h,aid).status_code==200
        r=queue(aid);assert r.status_code==201,r.text
        with app.state.identity_store.engine.connect() as db:
            raw=db.execute(select(studio_render_jobs.c.manifest).where(studio_render_jobs.c.job_id=='job.motion')).scalar_one()
            assert json.loads(raw)['render_profile']=='social_motion_v2'
        job=LocalDraftRenderer(app.state.identity_store.engine).process_next('tenantA')
        assert job.status=='succeeded',job
        r=c.get('/v1/studio/render-artifacts/'+job.artifact_id,headers=h);assert r.status_code==200
        assert sha256(r.content).hexdigest()==job.sha256
        path=tmp_path/'motion.mp4';path.write_bytes(r.content)
        data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=width,height,r_frame_rate,nb_frames:format=duration','-of','json',str(path)]))
        assert data['streams']==[{'width':1080,'height':1920,'r_frame_rate':'30/1','nb_frames':'450'}]
        assert abs(float(data['format']['duration'])-15)<0.04
    finally:
        c.__exit__(None,None,None);app.state.identity_store.engine.dispose()
