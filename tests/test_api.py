from fastapi.testclient import TestClient
from tapi_gate0.api import app

client=TestClient(app)

def test_healthz_only_claims_bootstrap():
    assert client.get('/healthz').json() == {'status':'ok','purpose':'local_gate0_bootstrap'}

def test_readiness_never_claims_prod():
    res=client.get('/v1/gate0/status')
    assert res.status_code==200
    data=res.json()
    assert data['is_production_ready'] is False
    assert data['source_operations_enabled'] is False
    assert data['gate0b'].startswith('BLOQUEADO')

def test_no_external_endpoints_exposed():
    paths=set(app.openapi()['paths'])
    assert paths == {'/healthz','/v1/gate0/status'}


def test_readiness_respects_zero_spend_and_user_scope():
    data=client.get('/v1/gate0/status').json()
    assert data['expanded_scope_user_approved'] is True
    assert data['institutional_scope_confirmation'] == 'UNVERIFIED'
    assert data['financial_spend_ceiling_brl'] == 0
    assert data['source_use_grants'] == 'PENDING'
    assert data['remote_repo_created'] is False
