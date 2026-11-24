from scripts.demo_experiment_pairs import previews, persist, CAROUSEL_LAYOUT_VERSION
from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.studio_e1 import StudioStore
from test_demo_presentation_polish import snapshot
import pytest


def test_carousel_cta_isolated_and_persisted(tmp_path):
    app=create_secure_app('sqlite:///'+(tmp_path/'demo.sqlite').as_posix(),initialize_schema=True,allow_http_local=True)
    try:
        engine=app.state.identity_store.engine
        app.state.identity_store.bootstrap('stone-demo','Demo','demo','fixture-only-password')
        source=snapshot()
        feed=previews(source,'stone-demo')[0]
        row=previews(source,'stone-demo','instagram_carousel')[0]
        assert row['preview_sha256']!=feed['preview_sha256']
        assert row['pair']['layout_version']==CAROUSEL_LAYOUT_VERSION
        a,b=row['previews']
        assert a['platform_intent']==b['platform_intent']=='instagram_carousel'
        assert len(a['pages'])==len(b['pages'])==3
        assert a['pages'][:2]==b['pages'][:2]
        assert [l for l in a['pages'][2]['layers'] if l['id']!='cta']==[l for l in b['pages'][2]['layers'] if l['id']!='cta']
        assert a['pages'][2]['layers'][2]['text']!=b['pages'][2]['layers'][2]['text']
        r=persist(engine,source,'stone-demo','fixture.actor',row['preview_sha256'])
        assert r['proof']['platform_intent']=='instagram_carousel'
        for expected,actual in zip(row['previews'],r['documents']):
            assert actual=={**expected,'document_id':actual['document_id']}
            assert StudioStore(engine).get('stone-demo',actual['document_id']).model_dump(mode='json')==actual
        with pytest.raises(ValueError,match='FORMAT_INVALID'):
            previews(source,'stone-demo','reels')
    finally:
        app.state.identity_store.engine.dispose()


def test_carousel_theme_only_changes_headline_and_guidance():
    source=snapshot();h={'field':'topic','value':'marketing','difference_pp':10}
    source['editorial_hypotheses']['hypotheses']=[h]
    source['editorial_contrast']['fields']={'topic':{'comparisons':[{'value':'atendimento','rest_count':4}]}}
    a,b=previews(source,'stone-demo','instagram_carousel')[0]['previews']
    assert a['canvas']==b['canvas']
    differences=[]
    for pa,pb in zip(a['pages'],b['pages']):
        for la,lb in zip(pa['layers'],pb['layers']):
            if la!=lb:
                assert {k:v for k,v in la.items() if k!='text'}=={k:v for k,v in lb.items() if k!='text'}
                differences.append((pa['id'],la['id']))
    assert differences==[('page.1','headline'),('page.2','body')]
