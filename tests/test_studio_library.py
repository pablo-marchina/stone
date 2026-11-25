import json
from fastapi.testclient import TestClient
from sqlalchemy import insert, update
from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.sa_store import tenants, domain_events
from tapi_gate0.identity import memberships, Principal
from tapi_gate0 import discovery_studio_handoff as h
def preview():
    return {"confidence_flag":"EXPLORATORY_NOT_INDEPENDENTLY_VALIDATED",
            "scientifically_validated":False,"publication_approved":False,"scientific_admissions":0,
            "manifest_sha256":"a"*64,
            "reference_posts":[{"content_id":"p.1","snapshot_id":"s.1","caption_sha256":"b"*64,
                                "er_fraction":"1/100","tier":"semantic_consensus_only","username":"fixture"}],
            "findings":[{"field":"topic","value":"vendas","reference_content_ids":["p.1"]}],
            "creatives":[{"creative_spec":{"spec_id":f"spec.{i}","tenant_id":"tenant-a",
                           "objective":"Testar uma hipótese editorial","headline":f"Venda {i}",
                           "body":"Organize os pedidos.","cta":"Salve este checklist.",
                           "platform_intent":"instagram_carousel","reference_content_ids":["p.1"]},
                          "status":"draft_hypothesis_not_approved","format_and_cta_are_design_choices":True,
                          "hypothesis_field":"topic","hypothesis_value":"vendas"} for i in range(5)]}

PASSWORD="local-library-password-123456"


def test_library_auth_pagination_historical_and_tenant(tmp_path,monkeypatch):
    from types import SimpleNamespace
    app=create_secure_app("sqlite:///"+(tmp_path/"library.sqlite").as_posix(),
                          initialize_schema=True,allow_http_local=True)
    auth=app.state.identity_store
    auth.bootstrap("tenant-a","A","founder",PASSWORD)
    with auth.engine.begin() as db:
        db.execute(insert(tenants).values(tenant_id="tenant-b",name="B"))
        db.execute(insert(memberships).values(user_id="founder",tenant_id="tenant-b",role="admin"))
    monkeypatch.setattr(h,"_scope_in_transaction",lambda *args:None)
    monkeypatch.setattr(h,"_validate_refs",lambda *args:None)
    principal=Principal(actor_id="founder",tenant_id="tenant-a",role="admin")
    drafts=h.prepare_drafts(preview(),"tenant-a")
    h.persist_drafts(auth.engine,principal,SimpleNamespace(fingerprint=lambda:"a"*64),"12345",drafts,stopped=True)
    with TestClient(app) as client:
        def headers(tenant):
            login=client.post("/v1/auth/sessions",json={"username":"founder","password":PASSWORD,"tenant_id":tenant})
            assert login.status_code==200
            return {"Authorization":"Bearer "+login.json()["access_token"]}
        url="/v1/studio/documents"
        root=client.get("/",follow_redirects=False)
        assert root.status_code==307 and root.headers["location"]=="/app/"
        assert root.headers["Cache-Control"]=="no-store"
        assert client.get("/").status_code==200
        assert client.get("/app/studio.html").status_code==200
        denied=client.get(url)
        assert denied.status_code==401 and denied.headers["Cache-Control"]=="no-store"
        a,b=headers("tenant-a"),headers("tenant-b")
        assert client.get(url,headers=b).json()["items"]==[]
        first=client.get(url+"?limit=2",headers=a)
        assert first.status_code==200 and first.headers["Cache-Control"]=="private, no-store"
        assert first.headers["X-Content-Type-Options"]=="nosniff"
        assert first.headers["X-Frame-Options"]=="DENY"
        data=first.json()
        assert len(data["items"])==2
        assert all(i["historical_provenance"]=="recorded" and i["historical_reference_count"]==1 for i in data["items"])
        assert all(not i["current_source_scope_verified"] and not i["publication_approved"] for i in data["items"])
        assert "caption_sha256" not in first.text and "p.1" not in first.text
        second=client.get(url,params={"after":data["next_after"],"limit":50},headers=a).json()
        assert len(second["items"])==3 and second["next_after"] is None
        assert not ({i["document_id"] for i in data["items"]}&{i["document_id"] for i in second["items"]})
        assert client.get(url+"?limit=51",headers=a).status_code==422
        assert client.get(url+"?after=%20",headers=a).status_code==422
        doc_id=drafts[0][0].document_id
        edit=client.post(url+"/"+doc_id+"/text-patches",headers=a,json={"page_id":"page.1","layer_id":"main","expected_version":1,"text":"Título editado"})
        assert edit.status_code==200
        found=next(x for x in client.get(url,headers=a).json()["items"] if x["document_id"]==doc_id)
        assert found["title"]=="Título editado" and found["version"]==2 and found["historical_provenance"]=="recorded"
        with auth.engine.begin() as db:
            db.execute(update(domain_events).where(domain_events.c.aggregate_id==doc_id,
                       domain_events.c.tenant_id=="tenant-a").values(payload=json.dumps({"bad":True})))
        found=next(x for x in client.get(url,headers=a).json()["items"] if x["document_id"]==doc_id)
        assert found["historical_provenance"]=="invalid" and found["historical_reference_count"] is None
