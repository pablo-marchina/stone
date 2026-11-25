from scripts.demo_experiment_pairs import previews, persist
from tapi_gate0.studio_e1 import TextStyle, StudioStore
from tapi_gate0.secure_api import create_secure_app
from test_demo_presentation_polish import snapshot


def test_legacy_style_serialization_and_social_persistence(tmp_path):
    assert TextStyle().model_dump() == {'font_family':'sans-serif','font_size':64,'color':'#171717'}
    source=snapshot()
    classic=previews(source,'stone-demo','instagram_carousel')[0]
    row=previews(source,'stone-demo','instagram_carousel','social')[0]
    assert classic['preview_sha256']!=row['preview_sha256']
    assert row['pair']['aesthetic_evidence']=='provisional_design_candidate_not_corpus_validated'
    a,b=row['previews']
    assert a['pages'][:2]==b['pages'][:2]
    diffs=[(pa['id'],la['id']) for pa,pb in zip(a['pages'],b['pages']) for la,lb in zip(pa['layers'],pb['layers']) if la!=lb]
    assert diffs==[('page.3','cta')]
    assert a['pages'][0]['layers'][1]['style']['box_fill']=='#C9F36B'
    app=create_secure_app('sqlite:///'+(tmp_path/'demo.sqlite').as_posix(),initialize_schema=True,allow_http_local=True)
    try:
        engine=app.state.identity_store.engine
        app.state.identity_store.bootstrap('stone-demo','Demo','demo','fixture-only-password')
        saved=persist(engine,source,'stone-demo','fixture.actor',row['preview_sha256'])
        for expected,actual in zip(row['previews'],saved['documents']):
            assert actual=={**expected,'document_id':actual['document_id']}
            assert StudioStore(engine).get('stone-demo',actual['document_id']).model_dump(mode='json')==actual
    finally:
        app.state.identity_store.engine.dispose()
