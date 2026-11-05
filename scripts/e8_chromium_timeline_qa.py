"""E8 browser test: authenticated visual timeline, DnD, keyboard, versioning, draft queue.

Uses FastAPI in-process through Playwright interception; no external network.
"""
from __future__ import annotations

import base64
from datetime import datetime,timedelta,timezone
import io,json,re,tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from PIL import Image

from tapi_gate0.secure_api import create_secure_app

ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'src/tapi_gate0/web'


def run(executable=None):
    if executable is None and Path('/usr/bin/chromium').is_file():
        executable='/usr/bin/chromium'
    with tempfile.TemporaryDirectory() as temp:
        app=create_secure_app(f'sqlite:///{temp}/studio_e8.sqlite',initialize_schema=True,
                              allow_http_local=True)
        app.state.identity_store.bootstrap('tenant.demo','Demo','founder','pass-secret-1234567')
        with TestClient(app) as backend,sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path=executable,
                                       args=['--no-sandbox'] if executable else [])
            page=browser.new_page(accept_downloads=True)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            def call(_source,path,opts):
                response=backend.request(opts.get('method','GET'),path,
                      data=opts.get('body'),headers=opts.get('headers',{}))
                return {'status':response.status_code,
                        'headers':{'content-type':response.headers.get('content-type','application/json'),
                                   'etag':response.headers.get('etag','')},
                        'body':response.content.decode('utf-8')}
            page.expose_binding('stoneTestBackend',call)
            html=(STATIC/'studio.html').read_text()
            html=re.sub(r'<script[^>]*\s+src="[^"]+"[^>]*></script>','',html)
            html=html.replace('<link rel="stylesheet" href="./studio.css">','')
            page.set_content(html)
            page.evaluate('''() => {window.fetch=async (path,opts={})=>{
                const response=await window.stoneTestBackend(path,{method:opts.method||'GET',
                    headers:opts.headers||{},body:opts.body});
                return new Response(response.body,{status:response.status,headers:response.headers});
              };}''')
            # about:blank is not a secure origin; inject a deterministic test UUID only here.
            page.evaluate("() => {let i=0;Object.defineProperty(window.crypto,'randomUUID',{value:()=>('e8'+String(++i).padStart(30,'0'))});}")
            page.add_script_tag(content=(STATIC/'studio_export_e4.js').read_text())
            page.add_script_tag(content=(STATIC/'studio_timeline_e8.js').read_text())
            page.add_script_tag(content=(STATIC/'studio.mjs').read_text())
            page.locator('#tenant').fill('tenant.demo')
            page.locator('#password').fill('pass-secret-1234567')
            page.locator('#login').click()
            page.get_by_text('Autenticado como admin').wait_for(timeout=7000)
            page.locator('#document-id').fill('design.e8.chromium')
            page.locator('#format').select_option('instagram_carousel')
            page.locator('#create').click()
            page.get_by_text('Rascunho criado e persistido. Versão 1.').wait_for(timeout=7000)
            page.locator('#duplicate-page').click()
            page.get_by_text('Página duplicada. Versão 2').wait_for(timeout=7000)
            page.locator('#storyboard-create').click()
            page.get_by_text('Storyboard versionado criado').wait_for(timeout=7000)
            assert page.locator('.timeline-scene').count()==2
            first=page.locator('.timeline-scene').first
            first.click()
            page.locator('#timeline-duration').fill('1200')
            page.locator('#timeline-overlay').fill('Plano financeiro')
            page.locator('#timeline-kf-x0').fill('100')
            page.locator('#timeline-kf-x1').fill('400')
            page.locator('#timeline-transition').select_option('crossfade')
            page.locator('#timeline-crossfade').fill('200')
            page.locator('#timeline-save').click()
            page.get_by_text('Timeline salva na versão 2').wait_for(timeout=7000)
            second=page.locator('.timeline-scene').nth(1)
            second.click()
            page.locator('#timeline-duration').fill('1200')
            page.locator('#timeline-save').click()
            page.get_by_text('Timeline salva na versão 3').wait_for(timeout=7000)
            target=page.locator('.timeline-scene').first
            moving=page.locator('.timeline-scene').nth(1)
            moving.drag_to(target)
            page.get_by_text('Timeline salva na versão 4').wait_for(timeout=8000)
            assert page.locator('.timeline-scene').first.get_attribute('data-scene-id')=='scene.2'
            # Prepare owned PNG via in-process backend. The UI explicitly attests rights and binds each scene.
            session=backend.post('/v1/auth/sessions',json={
                'username':'founder','password':'pass-secret-1234567','tenant_id':'tenant.demo'})
            auth={'Authorization':'Bearer '+session.json()['access_token']}
            image=io.BytesIO();Image.new('RGB',(80,140),'#4d8d61').save(image,format='PNG')
            uploaded=backend.post('/v1/studio/assets/png',headers=auth,json={
                'data_base64':base64.b64encode(image.getvalue()).decode(),'rights_attested':True})
            assert uploaded.status_code==201,uploaded.text
            asset=uploaded.json()['asset_id']
            page.locator('#timeline-rights-ref').fill('owned-local-visual-test-2026')
            page.locator('#timeline-expiry').fill((datetime.now(timezone.utc)+timedelta(days=4)).date().isoformat())
            page.locator('#timeline-video-rights').check()
            page.locator('#timeline-image-id').fill(asset)
            page.locator('#timeline-attest-image').click()
            page.get_by_text('Direitos locais de PNG atestados').wait_for(timeout=8000)
            for i in range(2):
                page.locator('.timeline-scene').nth(i).click()
                page.locator('#timeline-image-id').fill(asset)
                page.locator('#timeline-video-id').fill('')
                page.locator('#timeline-bind-source').click()
                page.get_by_text('Origem da cena preparada').wait_for(timeout=8000)
            page.locator('#timeline-quality').select_option('preview_540p')
            page.locator('#timeline-queue').click()
            page.get_by_text('Job em fila').wait_for(timeout=8000)
            job_id=page.locator('#timeline-job-id').input_value()
            assert job_id.startswith('draft.')
            status=backend.get('/v1/studio/advanced-render-jobs/'+job_id,headers=auth)
            assert status.status_code==200 and status.json()['status']=='queued'
            assert not errors,errors
            browser.close()
            print(json.dumps({'chromium_e8':'PASS','scenes':2,'visual_drag_drop':'PASS',
                'version_after_drag':4,'draft_job_created':True,'js_errors':0},ensure_ascii=False))


if __name__=='__main__':run()
