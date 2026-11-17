import json
import hashlib
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, func

from tapi_gate0 import evidence_lab as lab
from tapi_gate0.domain import RUBRIC_FIELD_NAMES
from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.sa_store import tenants, rubric_assessments, content_items, domain_events
from tapi_gate0.identity import memberships

PASSWORD="test-password-with-sufficient-length-123"


def save(root,name,data):
    p=root/"artifacts"/"private"/name
    p.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(data).encode()
    p.write_bytes(raw)
    return lab.ReportRef(name,hashlib.sha256(raw).hexdigest())


def build(tmp_path,monkeypatch):
    source={"cases":[{"case_id":"example","fragments":[{"text":"fixture","modality":"caption"}]}]}
    visual={"synthetic_only":True}
    fields={k:{"state":"not_assessed","canonical":False,"value":None,"supports":[],"vetoes":[],"measurement":None} for k in RUBRIC_FIELD_NAMES}
    fields["tema_principal"].update(state="candidate",value="vendas")
    result={"policy_version":"fixture","cases":[{"case_id":"example","media_sha256":"a"*64,
        "field_evidence":fields,"visual_observations":[],"source_rights":{"scope":"synthetic"}}],
        "field_count":20,"total_field_cells":20,"field_coverage":{},"ablation":{},
        "engineering_gate_passed":True,"upstream_vlm_gate_passed":False,
        "production_approved":False,"real_media_processing_allowed":False,
        "database_mutated":False,"independent_gold":False}
    s=save(tmp_path,"shared.json",source)
    v=save(tmp_path,"visual.json",visual)
    composed={**result,"source_report_sha256":s.digest,"visual_report_sha256":v.digest}
    c=save(tmp_path,"composed.json",composed)
    monkeypatch.setattr(lab.evidence,"run",lambda *_:deepcopy(result))
    return lab.LabConfig("tenantA",s,v,c)


def test_pinned_snapshot_and_mutation(tmp_path,monkeypatch):
    config=build(tmp_path,monkeypatch)
    service=lab.EvidenceLab(config,tmp_path)
    assert service.summary()["report_sha256"]==config.composed.digest
    assert not service.summary()["upstream_vlm_gate_passed"]
    assert service.case("example")["field_evidence"]["tema_principal"]["value"]=="vendas"
    changed=service.case("example")
    changed["field_evidence"]["tema_principal"]["value"]="marketing"
    assert service.case("example")["field_evidence"]["tema_principal"]["value"]=="vendas"
    (tmp_path/"artifacts"/"private"/"composed.json").write_text("{}")
    with pytest.raises(ValueError,match="HASH_MISMATCH"):
        lab.EvidenceLab(config,tmp_path)


def test_recomposition_and_path_refuse(tmp_path,monkeypatch):
    config=build(tmp_path,monkeypatch)
    ref=save(tmp_path,"different.json",{"synthetic_only":True})
    with pytest.raises(ValueError,match="COMPOSITION_MISMATCH"):
        lab.EvidenceLab(lab.LabConfig(config.tenant_id,config.shared,config.visual,ref),tmp_path)
    with pytest.raises(ValueError,match="REF_INVALID"):
        lab.read_pinned(tmp_path,lab.ReportRef("../shared.json",config.shared.digest))
    with pytest.raises(ValueError,match="CONFIG_INCOMPLETE"):
        lab.config_from_env({"TAPI_EVIDENCE_LAB_TENANT":"tenantA"})
    assert lab.config_from_env({}) is None


def login(client,tenant,username="founder"):
    response=client.post("/v1/auth/sessions",json={"tenant_id":tenant,"username":username,"password":PASSWORD})
    assert response.status_code==200
    return {"Authorization":"Bearer "+response.json()["access_token"]}


def test_authenticated_tenant_bound_read_only(tmp_path,monkeypatch):
    service=lab.EvidenceLab(build(tmp_path,monkeypatch),tmp_path)
    app=create_secure_app(f"sqlite:///{tmp_path/'lab.sqlite'}",initialize_schema=True,allow_http_local=True,evidence_lab=service)
    identity=app.state.identity_store
    identity.bootstrap("tenantA","A","founder",PASSWORD)
    with identity.engine.begin() as db:
        db.execute(insert(tenants).values(tenant_id="tenantB",name="B"))
        db.execute(insert(memberships).values(user_id="founder",tenant_id="tenantB",role="viewer"))
    path="/v1/studio/evidence-lab"
    with TestClient(app) as client:
        assert client.get(path).status_code==401
        admin=login(client,"tenantA")
        other=login(client,"tenantB")
        assert client.get(path,headers=other).status_code==404
        assert client.get(path+"/cases/example",headers=other).status_code==404
        response=client.get(path,headers=admin)
        assert response.status_code==200 and response.headers["cache-control"]=="private, no-store"
        assert not response.json()["canonical"]
        assert client.get(path+"/cases/example",headers=admin).json()["synthetic_only"]
        assert client.get(path+"/cases/missing",headers=admin).status_code==404
        assert client.post(path,headers=admin,json={}).status_code==405
        assert client.post("/v1/admin/members",headers=admin,json={"user_id":"reader","username":"reader",
            "password":PASSWORD,"role":"viewer"}).status_code==201
        viewer=login(client,"tenantA","reader")
        assert client.get(path,headers=viewer).status_code==200
        assert client.post("/v1/auth/logout",headers=viewer).status_code==204
        assert client.get(path,headers=viewer).status_code==401
        html=client.get("/app/studio.html")
        assert html.status_code==200 and 'id="evidence-lab"' in html.text
        assert "report_sha256" not in html.text
        with identity.engine.connect() as db:
            assert all(db.scalar(select(func.count()).select_from(table))==0 for table in (rubric_assessments,content_items,domain_events))


def test_disabled_default(tmp_path):
    app=create_secure_app(f"sqlite:///{tmp_path/'disabled.sqlite'}",initialize_schema=True,allow_http_local=True)
    app.state.identity_store.bootstrap("tenantA","A","founder",PASSWORD)
    with TestClient(app) as client:
        assert client.get("/v1/studio/evidence-lab",headers=login(client,"tenantA")).status_code==404


def test_operator_actual_triplet_when_configured():
    import os
    config=lab.config_from_env(os.environ)
    if config is None:
        pytest.skip("explicit local report triplet required")
    service=lab.EvidenceLab(config)
    assert service.summary()["total_field_cells"]==140
    assert len(service.summary()["cases"])==7
    assert not service.summary()["canonical"]
    for row in service.summary()["cases"]:
        assert set(service.case(row["case_id"])["field_evidence"])==set(RUBRIC_FIELD_NAMES)
