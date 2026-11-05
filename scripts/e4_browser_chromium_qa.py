"""Real Chromium drag/drop and exports against intercepted, in-process FastAPI.
No outbound network and no Meta token. Uses secure localhost origin with real DOM.
"""
from __future__ import annotations
import base64, io, tempfile, zipfile, json
from pathlib import Path
from urllib.parse import urlsplit
from PIL import Image
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from tapi_gate0.secure_api import create_secure_app

ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'src/tapi_gate0/web'
with tempfile.TemporaryDirectory() as temp:
    app=create_secure_app(f'sqlite:///{temp}/studio_qa.sqlite',initialize_schema=True,allow_http_local=True)
    app.state.identity_store.bootstrap('tenant.demo','Demo','founder','local-test-pass-12345')
    with TestClient(app) as backend, sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(accept_downloads=True)
        page=context.new_page()
        errors=[]
        page.on('pageerror',lambda error: errors.append(str(error)))
        def backend_call(source,path,request):
            method=request.get('method','GET')
            headers=request.get('headers',{})
            data=request.get('body')
            response=backend.request(method,path,data=data,headers=headers)
            return {'status':response.status_code,
                    'headers': {'content-type':response.headers.get('content-type','application/json'),
                                'etag':response.headers.get('etag','')},
                    'body':response.content.decode('utf-8')}
        page.expose_binding('testApiRequest',backend_call)
        html=(STATIC/'studio.html').read_text().replace('<link rel="stylesheet" href="./studio.css">','').replace('<script defer src="./studio_export_e4.js"></script>','').replace('<script type="module" src="./studio.mjs"></script>','')
        page.set_content(html)
        page.evaluate('''() => { window.fetch=async function(path,opts={}){
            const r=await window.testApiRequest(path,{method:opts.method||'GET',headers:opts.headers||{},body:opts.body});
            return new Response(r.body,{status:r.status,headers:r.headers});
        }; }''')
        page.add_script_tag(content=(STATIC/'studio_export_e4.js').read_text())
        page.evaluate("() => {let n=1;Object.defineProperty(window.crypto,'randomUUID',{value:()=>(String(n++).padStart(6,'0')+'e4dummy0000000000000000000')});}")
        page.add_script_tag(content=(STATIC/'studio.mjs').read_text())
        page.locator('#password').fill('local-test-pass-12345')
        page.locator('#login').click()
        page.get_by_text('Autenticado como admin').wait_for()
        page.locator('#format').select_option('instagram_carousel')
        page.locator('#document-id').fill('design.e4')
        page.locator('#create').click()
        page.get_by_text('Rascunho criado e persistido. Versão 1.').wait_for()
        page.locator('#duplicate-page').click()
        page.get_by_text('Página duplicada. Versão 2').wait_for()
        page.locator('#duplicate-page').click()
        page.get_by_text('Página duplicada. Versão 3').wait_for()
        assert page.locator('.page-chip').count()==3
        # Real Chromium HTML5 drag-and-drop rather than invoking DOM callbacks.
        page.locator('.page-chip').nth(0).drag_to(page.locator('.page-chip').nth(2))
        page.get_by_text('Ordem das páginas salva. Versão 4').wait_for(timeout=5000)
        assert page.locator('.page-chip').count()==3
        # Capture actual preview's pixels before export for bytewise pixel comparison.
        data_url=page.locator('#canvas').evaluate('(c) => c.toDataURL("image/png")')
        canvas_png=base64.b64decode(data_url.split(',')[1])
        with page.expect_download() as download_info: page.locator('#export').click()
        png=download_info.value.path().read_bytes()
        assert png.startswith(b'\x89PNG')
        left,right=Image.open(io.BytesIO(canvas_png)).convert('RGBA'),Image.open(io.BytesIO(png)).convert('RGBA')
        assert left.size==right.size and left.tobytes()==right.tobytes(), 'preview PNG parity failed'
        page.locator('#export-format').select_option('jpeg')
        with page.expect_download() as d:page.locator('#export').click()
        assert Image.open(d.value.path()).format=='JPEG'
        page.locator('#export-format').select_option('svg')
        with page.expect_download() as d:page.locator('#export').click()
        svg=d.value.path().read_bytes()
        assert b'<svg' in svg and b'<text' in svg and b'<script' not in svg
        page.locator('#export-format').select_option('png')
        with page.expect_download() as d:page.locator('#export-zip').click()
        zipdata=d.value.path().read_bytes()
        with zipfile.ZipFile(io.BytesIO(zipdata)) as z:
            assert z.testzip() is None
            names=z.namelist();assert names==['page-01.png','page-02.png','page-03.png','manifest.json'],names
            manifest=json.loads(z.read('manifest.json'))
            assert manifest['version']==4 and len(manifest['pages'])==3
            assert manifest['approval_status']=='draft'
            import hashlib
            for entry in manifest['pages']:
                raw=z.read(entry['file']);assert entry['sha256']==hashlib.sha256(raw).hexdigest()
                assert Image.open(io.BytesIO(raw)).size==(1080,1350)
        # Storyboard bootstrap is a separate, versioned data contract, not a rendered MP4.
        page.locator('#storyboard-create').click()
        page.get_by_text('Storyboard textual versionado salvo. Render de vídeo não disponível.').wait_for(timeout=5000)
        assert 'story.' in (page.locator('#storyboard-preview').text_content() or '')
        # Proposal UI: a text patch must be previewed and explicitly confirmed.
        rect=page.locator('#canvas').bounding_box()
        page.locator('#canvas').click(position={'x':rect['width']*140/1080,'y':rect['height']*170/1350})
        print('SELECT:',page.locator('#selected').text_content(),'CANVAS=',rect)
        assert page.locator('#preview-proposal').is_enabled()
        page.locator('#proposal-text').fill('Novo título com aprovação humana explícita')
        page.locator('#preview-proposal').click()
        page.get_by_text('Proposta em prévia. Nenhuma edição foi aplicada.').wait_for(timeout=5000)
        assert page.locator('#apply-proposal').is_disabled()
        page.locator('#confirm-proposal').check()
        page.locator('#apply-proposal').click()
        page.get_by_text('Patch confirmado e salvo na versão 5').wait_for(timeout=5000)
        assert not errors,errors
        print('CHROMIUM_OK: drag_to real; preview-vs-PNG pixels equal; JPEG/SVG/ZIP; SHA256; storyboard and operator-confirmed patch')
        browser.close()
