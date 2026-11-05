"""IMP-182 / 185: ETag, immutable diffs, safe previews, tenant isolation."""
from fastapi.testclient import TestClient
from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.studio_e1 import CreativeSpec, StudioStore
from tapi_gate0.studio_e4 import studio_etag, version_diff

PASSWORD='local-e4-password-here'

def test_etag_diff_and_preview_apply_explicit_confirmation(tmp_path):
    app=create_secure_app(f"sqlite:///{tmp_path/'e4.sqlite'}",initialize_schema=True,allow_http_local=True)
    auth=app.state.identity_store
    auth.bootstrap('tenantA','Tenant A','founder',PASSWORD)
    with TestClient(app) as client:
        def headers(tenant='tenantA'):
            r=client.post('/v1/auth/sessions',json={
                'username':'founder','password':PASSWORD,'tenant_id':tenant})
            assert r.status_code==200, r.text
            return {'Authorization':'Bearer '+r.json()['access_token']}
        h=headers()
        spec=CreativeSpec(spec_id='spec.alpha',tenant_id='tenantA',
                objective='Criar um conteúdo sobre pequenos negócios',
                headline='Título atual',body='Corpo atual',cta='Comece agora.')
        created=client.post('/v1/studio/documents',headers=h,json={
            'document_id':'doc.alpha','spec':spec.model_dump()})
        assert created.status_code==201,created.text
        etag=created.headers['etag'];assert etag.startswith('"') and etag.endswith('"')
        doc=created.json();assert etag==studio_etag(StudioStore(auth.engine).get('tenantA','doc.alpha'))
        get=client.get('/v1/studio/documents/doc.alpha',headers=h)
        assert get.headers['etag']==etag
        assert 'no-store' in get.headers['cache-control']
        proposal={'expected_version':1,'page_id':'page.1','layer_id':'headline',
                  'text':'Texto proposto — revisão humana obrigatória',
                  'origin':'untrusted_model'}
        preview=client.post('/v1/studio/documents/doc.alpha/edit-proposals/preview',
                            headers=h,json=proposal)
        assert preview.status_code==200,preview.text
        assert preview.json()['requires_operator_confirmation'] is True
        assert preview.json()['scientifically_validated'] is False
        assert preview.json()['production_approved'] is False
        assert client.get('/v1/studio/documents/doc.alpha',headers=h).json()['version']==1
        denied=client.post('/v1/studio/documents/doc.alpha/edit-proposals/apply',headers=h,
          json={**proposal,'preview_sha256':preview.json()['preview_sha256'],
                'operator_confirmed':False})
        assert denied.status_code==422
        stale=client.post('/v1/studio/documents/doc.alpha/edit-proposals/apply',
          headers={**h,'If-Match':'"invalid"'},json={**proposal,
            'preview_sha256':preview.json()['preview_sha256'],'operator_confirmed':True})
        assert stale.status_code==412,stale.text
        bad=client.post('/v1/studio/documents/doc.alpha/edit-proposals/apply',
          headers={**h,'If-Match':etag},json={**proposal,'text':'other text',
            'preview_sha256':preview.json()['preview_sha256'],'operator_confirmed':True})
        assert bad.status_code==409,bad.text
        done=client.post('/v1/studio/documents/doc.alpha/edit-proposals/apply',
          headers={**h,'If-Match':etag},json={**proposal,
            'preview_sha256':preview.json()['preview_sha256'],'operator_confirmed':True})
        assert done.status_code==200,done.text
        assert done.json()['version']==2 and done.headers['etag']!=etag
        assert done.json()['approval_status']=='draft'
        assert done.json()['rights_status']=='pending_review'
        old=client.get('/v1/studio/documents/doc.alpha/versions/1',headers=h)
        assert old.json()['pages'][0]['layers'][0]['text']=='Título atual'
        diff=client.get('/v1/studio/documents/doc.alpha/versions/diff?from_version=1&to_version=2',headers=h)
        assert diff.status_code==200,diff.text
        assert any(x['path'].endswith('/text') for x in diff.json()['changes'])
        assert diff.json()['from_etag']==etag
        assert diff.json()['to_etag']==done.headers['etag']
        assert client.post('/v1/studio/documents/doc.alpha/text-patches',headers={**h,'If-Match':etag},json={
          'expected_version':2,'page_id':'page.1','layer_id':'headline','text':'Stale'}).status_code==412
        assert client.post('/v1/studio/documents/doc.alpha/text-patches',headers=h,json={
          'expected_version':1,'page_id':'page.1','layer_id':'headline','text':'Stale'}).status_code==409
        assert client.get('/v1/studio/documents/doc.alpha',headers=h).json()['version']==2
        # A document and historical versions are scoped to the authenticated tenant.
        with auth.engine.begin() as db:
            from sqlalchemy import insert
            from tapi_gate0.sa_store import tenants
            from tapi_gate0.identity import memberships
            db.execute(insert(tenants).values(tenant_id='tenantB',name='B'))
            db.execute(insert(memberships).values(user_id='founder',tenant_id='tenantB',role='admin'))
        other=headers('tenantB')
        assert client.get('/v1/studio/documents/doc.alpha/versions/diff?from_version=1&to_version=2',headers=other).status_code==404
        assert client.post('/v1/studio/documents/doc.alpha/edit-proposals/preview',headers=other,json=proposal).status_code==404
        assert client.get('/v1/studio/documents/doc.alpha',headers=other).status_code==404
