from pathlib import Path
from fastapi.testclient import TestClient
from scripts.demo_experiment_pairs import previews, persist, LAYOUT_VERSION
from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.studio_e1 import StudioStore


def snapshot():
    h = {'field':'cta','value':'seguir','difference_pp':10}
    return {'report_sha256':'a'*64,'editorial_hypotheses':{'report_sha256':'a'*64,'hypotheses':[h]},
            'editorial_contrast':{'fields':{'cta':{'comparisons':[{'value':'comentar','rest_count':4}]}}}}


def test_polished_layout_exact_persistence_and_cta_isolation(tmp_path):
    app=create_secure_app('sqlite:///'+(tmp_path/'demo.sqlite').as_posix(),initialize_schema=True,allow_http_local=True)
    try:
        engine=app.state.identity_store.engine
        app.state.identity_store.bootstrap('stone-demo','Demo','demo','fixture-only-password')
        row=previews(snapshot(),'stone-demo')[0]
        a,b=row['previews']
        assert row['pair']['layout_version']==LAYOUT_VERSION
        assert a['canvas']==b['canvas'] and a['canvas']['background']=='#F4F7EC'
        assert len(a['pages'][0]['layers'])==7
        assert [l for l in a['pages'][0]['layers'] if l['id']!='cta']==[l for l in b['pages'][0]['layers'] if l['id']!='cta']
        r=persist(engine,snapshot(),'stone-demo','fixture.actor',row['preview_sha256'])
        assert r['proof']['layout_version']==LAYOUT_VERSION
        for expected,actual in zip(row['previews'],r['documents']):
            assert actual=={**expected,'document_id':actual['document_id']}
            assert StudioStore(engine).get('stone-demo',actual['document_id']).model_dump(mode='json')==actual
            assert actual['approval_status']=='draft'
    finally:
        app.state.identity_store.engine.dispose()


def test_local_demo_media_csp_is_narrow(tmp_path):
    for allowed in (True,False):
        app=create_secure_app('sqlite:///'+(tmp_path/f'{allowed}.sqlite').as_posix(),initialize_schema=True,allow_http_local=allowed)
        try:
            with TestClient(app,base_url='https://testserver') as c:
                demo=c.get('/app/demo.html').headers['content-security-policy']
                other=c.get('/app/studio.html').headers['content-security-policy']
                assert ("media-src blob:" in demo)==allowed
                assert 'media-src' not in other
                assert "script-src 'self'" in demo and "default-src 'none'" in demo
        finally:
            app.state.identity_store.engine.dispose()
