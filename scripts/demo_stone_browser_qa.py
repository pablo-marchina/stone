"""Optional local Chromium QA with in-process FastAPI, no outbound network."""
from __future__ import annotations

import argparse
import base64
import os
import subprocess
import hashlib
import shutil
import json
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from scripts.demo_stone import build_demo
from scripts.demo_av_report import read_report
from tapi_gate0.agent_graph_checkpoints import agent_graph_events
from tapi_gate0.sa_store import domain_events
from tapi_gate0.studio_e1 import studio_versions

ROOT = Path(__file__).resolve().parents[1]


def run(browser_path, output, *, video=False, av_report=None):
    from playwright.sync_api import sync_playwright
    static = ROOT / 'src/tapi_gate0/web'
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='stone-demo-qa-') as directory:
        app = build_demo(Path(directory) / 'demo.sqlite', 'fixture-only-not-real-password', video_enabled=video, av_report=av_report)
        try:
            with TestClient(app) as backend, sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path=browser_path, args=['--no-sandbox'])
                try:
                    page = browser.new_page(viewport={'width':1440,'height':1050}, accept_downloads=True)
                    errors = []
                    page.on('pageerror', lambda exc: errors.append(str(exc)))
                    def backend_call(source, path, request):
                        r = backend.request(request.get('method','GET'), path, content=request.get('body'), headers=request.get('headers',{}))
                        if r.headers.get('content-type','').startswith('video/mp4'):
                            return {'status':r.status_code,'headers':{'content-type':'video/mp4'},'binary':base64.b64encode(r.content).decode('ascii')}
                        return {'status':r.status_code,'headers':{'content-type':r.headers.get('content-type','application/json'),'etag':r.headers.get('etag','')},'body':r.text}
                    page.expose_binding('testApiRequest', backend_call)
                    html = (static/'demo.html').read_text(encoding='utf-8').replace('<link rel="stylesheet" href="demo.css">','').replace('<script defer src="studio_export_e4.js"></script>','').replace('<script type="module" src="demo.mjs"></script>','')
                    page.set_content(html)
                    page.add_style_tag(content=(static/'demo.css').read_text(encoding='utf-8'))
                    # Browser uses the in-process API bridge, not a network connection.
                    page.evaluate("""() => { window.fetch=async (path,opts={})=>{const r=await window.testApiRequest(path,{method:opts.method||'GET',headers:opts.headers||{},body:opts.body});return new Response(r.status===204?null:r.binary?Uint8Array.from(atob(r.binary),c=>c.charCodeAt(0)):r.body,{status:r.status,headers:r.headers});}; let n=0;Object.defineProperty(window.crypto,'randomUUID',{value:()=> '00000000-0000-4000-8000-'+String(++n).padStart(12,'0')}); }""")
                    page.add_script_tag(content=(static/'studio_export_e4.js').read_text(encoding='utf-8'))
                    page.add_script_tag(content=(static/'demo.mjs').read_text(encoding='utf-8'))
                    page.locator('#password').fill('fixture-only-not-real-password')
                    page.get_by_role('button',name='Entrar e calcular ranking').click()
                    page.wait_for_function("document.querySelectorAll('#ranking tr').length===20 && document.querySelector('#status').textContent.includes('Ranking e análise')")
                    assert page.locator('#chart progress').count()==10
                    assert page.locator('#evidence').inner_text().startswith('Snapshot: demo.snapshot.01')
                    assert page.locator('#rubric-fields article').count()==20
                    page.locator('.rubric-panel').filter(has=page.locator('#rubric-fields')).screenshot(path=output/'stone_demo_rubrica.png')
                    page.screenshot(path=output/'stone_demo_ranking.png')
                    if av_report:
                        assert page.locator('#av-case option').count()==9
                        assert page.locator('#av-fields tr.suppressed').count()==1
                        page.locator('#av-panel').screenshot(path=output/'stone_demo_multimodal.png')
                        page.locator('#av-case').select_option('audio_insufficient')
                        assert 'ABSTAINED' in page.locator('#av-ledger').inner_text()
                        page.locator('#av-panel').screenshot(path=output/'stone_demo_abstencao.png')
                        with page.expect_download() as download:
                            page.locator('#av-download').click()
                        saved=output/'stone_demo_av_report.json'
                        download.value.save_as(saved)
                        assert json.loads(saved.read_bytes())==av_report
                    page.locator('#search-form button').click()
                    page.wait_for_function("document.querySelectorAll('#search-results article').length===5")
                    page.locator('#search-results article button').first.click()
                    page.wait_for_function("document.querySelector('#evidence').textContent.includes('demo.snapshot.01')")
                    page.locator('#search-form').locator('..').screenshot(path=output/'stone_demo_busca.png')
                    page.locator('#run').click()
                    page.wait_for_function("document.querySelectorAll('#proposals article').length===5")
                    assert page.locator('#trace li').count()==6
                    assert page.locator('#proposals canvas').count()==5
                    page.locator('#proposal-panel').screenshot(path=output/'stone_demo_propostas.png')
                    page.get_by_role('button',name='Selecionar rascunho').first.click()
                    page.wait_for_selector('#editor:visible')
                    page.locator('#headline').fill('Organize seu estoque hoje')
                    page.locator('#save').click()
                    page.wait_for_function("document.querySelector('#document-meta').textContent.includes('versão 2')")
                    page.locator('#editor').screenshot(path=output/'stone_demo_studio.png')
                    for button, filename in [('#export','stone_demo_criativo.svg'),('#export-png','stone_demo_criativo.png')]:
                        with page.expect_download() as download:
                            page.locator(button).click()
                        download.value.save_as(output/filename)
                        data = (output/filename).read_bytes()
                        page.wait_for_function("document.querySelector('#export-proof').textContent.includes('SHA-256')")
                        assert hashlib.sha256(data).hexdigest() in page.locator('#export-proof').inner_text()
                    assert b'RASCUNHO' in (output/'stone_demo_criativo.svg').read_bytes()
                    assert (output/'stone_demo_criativo.png').read_bytes().startswith(b'\x89PNG')
                    page.get_by_role('button',name='Selecionar rascunho').nth(4).click()
                    page.wait_for_function("document.querySelectorAll('#page-select option').length===3")
                    page.locator('#page-select').select_option('page.2')
                    page.locator('#headline').fill('Priorize sua semana')
                    page.locator('#save').click()
                    page.wait_for_function("document.querySelector('#document-meta').textContent.includes('versão 2')")
                    page.locator('#editor').screenshot(path=output/'stone_demo_carrossel.png')
                    with page.expect_download() as download:
                        page.locator('#export-zip').click()
                    archive=output/'stone_demo_carrossel.zip'
                    download.value.save_as(archive)
                    page.wait_for_function("document.querySelector('#export-proof').textContent.includes('SHA-256')")
                    assert hashlib.sha256(archive.read_bytes()).hexdigest() in page.locator('#export-proof').inner_text()
                    with zipfile.ZipFile(archive) as z:
                        manifest=json.loads(z.read('manifest.json'))
                        assert len(manifest['pages'])==3 and manifest['version']==2
                        assert all(hashlib.sha256(z.read(p['file'])).hexdigest()==p['sha256'] for p in manifest['pages'])
                    if video:
                        assert page.locator('#video-panel').is_visible()
                        page.locator('#video-rights').check()
                        page.locator('#render-video').click()
                        page.wait_for_function("!document.querySelector('#download-video').hidden", timeout=60000)
                        assert page.locator('#video-trace li').count()==4
                        page.locator('#video-panel').screenshot(path=output/'stone_demo_video.png')
                        with page.expect_download() as download:
                            page.locator('#download-video').click()
                        mp4=output/'stone_demo_video.mp4'
                        download.value.save_as(mp4)
                        assert hashlib.sha256(mp4.read_bytes()).hexdigest() in page.locator('#video-proof').inner_text()
                        if shutil.which('ffprobe'):
                            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(mp4)],text=True))
                            assert len(probe['streams'])==1 and probe['streams'][0]['codec_name']=='h264'
                            assert (probe['streams'][0]['width'],probe['streams'][0]['height'])==(360,640)
                            assert float(probe['format']['duration'])==15.0
                            (output/'stone_demo_video_probe.json').write_text(json.dumps(probe,indent=2))
                    page.locator('#session-panel').screenshot(path=output/'stone_demo_resultados.png')
                    with page.expect_download() as download:
                        page.locator('#session-download').click()
                    report=output/'stone_demo_resultados.json'
                    download.value.save_as(report)
                    counters=json.loads(report.read_bytes())['synthetic_counters']
                    assert counters['document_versions']==4
                    assert counters['storyboards']==counters['rendered_videos']==int(video)
                    with app.state.identity_store.engine.connect() as db:
                        assert db.scalar(select(func.count()).select_from(agent_graph_events))==6
                        assert db.scalar(select(func.count()).select_from(studio_versions))==4
                        assert db.scalar(select(func.count()).select_from(domain_events).where(domain_events.c.aggregate_type=='agent_generated_draft'))==2
                    page.locator('#logout').click()
                    page.wait_for_selector('#login:visible')
                    assert page.locator('#workspace').is_hidden() and not errors, errors
                finally:
                    browser.close()
        finally:
            app.state.identity_store.engine.dispose()
    print('PASS — Chromium + FastAPI em processo: ranking 20/4/2, seis checkpoints, cinco propostas, quatro versões, busca FTS5, carrossel ZIP e resumo JSON, hashes e logout.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', default=shutil.which('chromium') or shutil.which('chrome'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--video', action='store_true')
    parser.add_argument('--av-report', type=Path)
    args = parser.parse_args()
    if not args.browser:
        parser.error('indique o executável Chromium/Chrome com --browser')
    if args.video:
        os.environ["TAPI_LOCAL_RENDER_ENABLED"]="1"
        os.environ["TAPI_ZERO_BILLING_CONFIRMED"]="1"
    run(args.browser,args.output,video=args.video, av_report=read_report(args.av_report) if args.av_report else None)


if __name__=='__main__':
    main()
