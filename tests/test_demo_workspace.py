from contextlib import closing
import sqlite3

import pytest
from fastapi.testclient import TestClient
from scripts.demo_workspace import open_workspace, WorkspaceError
from scripts.demo_saved_library import saved_library
from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.studio_e1 import CreativeSpec, StudioStore, TextLayerPatch


def test_restart_keeps_identity_document_versions_and_rejects_other_report(tmp_path):
    root = tmp_path / 'presentation'
    snapshot = {'report_sha256': 'a'*64}
    av = {'test_report_sha256': 'b'*64}
    with open_workspace(root, snapshot, av) as work:
        assert not work.resume
        app = create_secure_app('sqlite:///'+work.path.as_posix(), initialize_schema=True, allow_http_local=True, enable_local_graph_diagnostic=True)
        try:
            identity = app.state.identity_store
            identity.bootstrap('stone-demo', 'Demo', 'demo', 'fixture-only-password')
            store = StudioStore(identity.engine)
            spec = CreativeSpec(spec_id='fixture.spec', tenant_id='stone-demo', objective='Demo editorial', headline='Original', body='Example', cta='Read')
            doc = store.create('stone-demo', 'founder', spec, 'demo.design.test')
            store.patch_text_layer('stone-demo', 'founder', doc.document_id, TextLayerPatch(expected_version=1, page_id='page.1', layer_id='headline', text='Edited'))
            work.seal()
            with pytest.raises(WorkspaceError, match='BUSY'):
                with open_workspace(root, snapshot, av):
                    pass
        finally:
            app.state.identity_store.engine.dispose()
    with pytest.raises(WorkspaceError, match='INPUT_MISMATCH'):
        with open_workspace(root, {'report_sha256':'c'*64}, av):
            pass
    with open_workspace(root, snapshot, av) as work:
        assert work.resume
        app = create_secure_app('sqlite:///'+work.path.as_posix(), initialize_schema=True, allow_http_local=True, enable_local_graph_diagnostic=True)
        try:
            with TestClient(app) as client:
                assert client.post('/v1/auth/sessions', json={'tenant_id':'stone-demo','username':'demo','password':'fixture-only-password'}).status_code == 200
            store = StudioStore(app.state.identity_store.engine)
            assert store.get('stone-demo', 'demo.design.test').version == 2
            assert store.get('stone-demo', 'demo.design.test', 1).pages[0].layers[0].text == 'Original'
            assert store.get('stone-demo', 'demo.design.test').pages[0].layers[0].text == 'Edited'
            library = saved_library(app.state.identity_store.engine, 'stone-demo')
            assert library['documents'][0]['headline'] == 'Edited'
            assert library['documents'][0]['version'] == 2
            assert saved_library(app.state.identity_store.engine, 'other')['documents'] == []
        finally:
            app.state.identity_store.engine.dispose()


def test_refuses_existing_unmarked_database_without_modification(tmp_path):
    root = tmp_path/'existing';root.mkdir()
    (root/'presentation.lock').write_bytes(b'0')
    db = root/'demo.sqlite'
    with closing(sqlite3.connect(db)) as con, con:
        con.execute('create table operational_data (value text)')
        con.execute("insert into operational_data values ('untouched')")
    before = db.read_bytes()
    with pytest.raises(WorkspaceError, match='DATABASE_INVALID'):
        with open_workspace(root, None, None):
            pass
    assert db.read_bytes() == before


def test_refuses_unsealed_workspace(tmp_path):
    root=tmp_path/'interrupted'
    with open_workspace(root, None, None):
        pass
    with pytest.raises(WorkspaceError, match='NOT_INITIALIZED'):
        with open_workspace(root, None, None):
            pass
