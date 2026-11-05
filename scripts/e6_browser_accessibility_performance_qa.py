"""CAP-023 E6 small, reproducible Chromium keyboard/ARIA + API latency smoke.

No network, no outside browser origin, no production claims. Requires local
Playwright Chromium, Pillow, and the secure app's optional test dependencies.
"""
from __future__ import annotations

import json
from pathlib import Path
import statistics
import tempfile
from time import perf_counter

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

from tapi_gate0.secure_api import create_secure_app

ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'src/tapi_gate0/web'


def run(executable='/usr/bin/chromium'):
    with tempfile.TemporaryDirectory() as temp:
        app=create_secure_app(f'sqlite:///{temp}/a11y.sqlite',initialize_schema=True,allow_http_local=True)
        app.state.identity_store.bootstrap('tenant.demo','Demo','founder','local-test-pass-12345')
        with TestClient(app) as backend, sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path=executable,args=['--no-sandbox'])
            context=browser.new_context()
            page=context.new_page()
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            def backend_call(source,path,request):
                response=backend.request(request.get('method','GET'),path,
                    data=request.get('body'),headers=request.get('headers',{}))
                return {'status':response.status_code,
                    'headers':{'content-type':response.headers.get('content-type','application/json'),
                               'etag':response.headers.get('etag','')},
                    'body':response.content.decode('utf-8')}
            page.expose_binding('testApiRequest',backend_call)
            html=(STATIC/'studio.html').read_text().replace('<link rel="stylesheet" href="./studio.css">','').replace('<script defer src="./studio_export_e4.js"></script>','').replace('<script type="module" src="./studio.mjs"></script>','')
            page.set_content(html)
            page.evaluate('''() => { window.fetch=async (path,opts={})=>{
                const r=await window.testApiRequest(path,{method:opts.method||'GET',
                    headers:opts.headers||{},body:opts.body});
                return new Response(r.body,{status:r.status,headers:r.headers});
            }; }''')
            page.add_script_tag(content=(STATIC/'studio_export_e4.js').read_text())
            page.evaluate("() => {let n=1;Object.defineProperty(window.crypto,'randomUUID',{value:()=>(String(n++).padStart(6,'0')+'e6dummy0000000000000000000')});}")
            page.add_script_tag(content=(STATIC/'studio.mjs').read_text())
            assert page.locator('html').get_attribute('lang')=='pt-BR'
            assert page.locator('#status').get_attribute('aria-live')=='polite'
            assert page.locator('#canvas').get_attribute('tabindex')=='0'
            page.locator('#password').fill('local-test-pass-12345')
            page.locator('#login').click()
            page.get_by_text('Autenticado como admin').wait_for()
            page.locator('#document-id').fill('design.a11y')
            page.locator('#create').click()
            page.get_by_text('Rascunho criado e persistido. Versão 1.').wait_for(timeout=5000)
            assert page.locator('#layer-nav button').count()==3
            page.locator('#layer-nav button').first.focus()
            page.keyboard.press('Enter')
            assert page.locator('#selected').text_content().startswith('headline')
            assert page.locator('#canvas').evaluate('(el)=>document.activeElement===el')
            initial_x=70
            page.keyboard.press('ArrowRight')
            page.get_by_text('Camada movida por teclado. Versão 2').wait_for(timeout=5000)
            assert page.locator('#geom-x').input_value()==str(initial_x+10)
            page.keyboard.press('Shift+ArrowRight')
            page.get_by_text('Camada movida por teclado. Versão 3').wait_for(timeout=5000)
            assert page.locator('#geom-x').input_value()==str(initial_x+11)
            # Minimal latency smoke, not a platform-wide load/capacity claim.
            # Credentials are only inside the intercepted test session. Use a
            # separate authenticated test client request rather than console.
            session=backend.post('/v1/auth/sessions',json={
                'username':'founder','password':'local-test-pass-12345','tenant_id':'tenant.demo'})
            h={'Authorization':'Bearer '+session.json()['access_token']}
            timings=[]
            for _ in range(40):
                start=perf_counter();resp=backend.get('/v1/studio/documents/design.a11y',headers=h)
                timings.append((perf_counter()-start)*1000)
                assert resp.status_code==200
            ms=sorted(timings);p95=ms[int(len(ms)*0.95)-1]
            assert p95<1500, f'single-user local p95 exceeded smoke limit: {p95:.1f}ms'
            assert not errors,errors
            browser.close()
            print(json.dumps({'accessibility_smoke':'PASS',
                'keyboard_move':['+10px','+1px'],'browser_errors':0,
                'api_get_samples':len(ms),'api_p95_ms':round(p95,2),
                'scope':'single-process isolated SQLite, not production load'},ensure_ascii=False))


if __name__=='__main__':run()
