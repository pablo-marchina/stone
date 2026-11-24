"""Historical report projection: no private identities, no implicit revalidation."""
import json
import pytest
from fastapi.testclient import TestClient
from scripts.demo_stone import build_demo, TENANT, USERNAME
from scripts.demo_technical_snapshot import project_report
from tapi_gate0.discovery_audience_exploratory import summarize
from tapi_gate0.discovery_rubric_coverage import rubric_coverage


def report():
    rows = [{"content_id":f"private.post.{i}", "username":"private.profile", "tier":"unresolved",
             "likes":i+10,"comments":2,"followers":1000,"format":"reels",
             "caption_chars":20,"topic":None,"cta":None} for i in range(20)]
    return {**summarize(rows),"private_rows":rows,"status":"EXPLORATORY_EDITORIAL_COMPLETED",
            "as_of":"2026-11-19T12:00:00+00:00","manifest_sha256":"a"*64,
            "production_approved":False,"rubric_coverage":rubric_coverage(rows)}


def test_technical_snapshot_is_aggregate_only(tmp_path):
    path=tmp_path/'report.json';path.write_text(json.dumps(report()))
    snapshot=project_report(path)
    assert snapshot['cohorts']['technical_all']['posts']==20
    assert snapshot['cohorts']['technical_all']['top_decile_count']==2
    assert len(snapshot['rubric_fields'])==20
    assert snapshot['historical_report_only'] and not snapshot['current_rights_verified']
    assert 'private.post' not in str(snapshot) and 'private.profile' not in str(snapshot)
    app=build_demo(tmp_path/'demo.sqlite','fixture-only-not-real-password',snapshot)
    try:
        with TestClient(app) as client:
            assert client.get('/v1/demo/technical-snapshot').status_code==401
            login=client.post('/v1/auth/sessions',json={'tenant_id':TENANT,'username':USERNAME,'password':'fixture-only-not-real-password'})
            h={'Authorization':'Bearer '+login.json()['access_token']}
            response=client.get('/v1/demo/technical-snapshot',headers=h)
            assert response.status_code==200 and response.json()=={'available':True,'snapshot':snapshot}
            assert response.headers['cache-control']=='private, no-store'
    finally:
        app.state.identity_store.engine.dispose()


@pytest.mark.parametrize('kind',['summary','coverage','scientific','rights','duplicate','tier'])
def test_inconsistent_report_denied(tmp_path,kind):
    data=report()
    if kind=='summary':data['cohorts']['technical_all']['posts']=21
    if kind=='coverage':data['rubric_coverage']['field_count']=19
    if kind=='scientific':data['scientifically_validated']=True
    if kind=='rights':data['production_approved']=True
    if kind=='duplicate':data['private_rows'][1]['content_id']=data['private_rows'][0]['content_id']
    if kind=='tier':data['private_rows'][0]['tier']='unknown'
    p=tmp_path/'report.json';p.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='DEMO_REPORT_INCONSISTENT_OR_UNSUPPORTED'):
        project_report(p)
