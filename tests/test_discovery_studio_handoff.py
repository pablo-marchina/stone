import pytest
from types import SimpleNamespace
from sqlalchemy import insert, select
from tapi_gate0 import discovery_studio_handoff as h
from tapi_gate0.identity import Principal
from tapi_gate0.sa_store import engine_for, metadata, tenants, domain_events
from tapi_gate0.studio_e1 import StudioStore, TextLayerPatch, studio_documents


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


def test_prepare_three_editable_pages_and_preserve_draft():
    drafts=h.prepare_drafts(preview(),"tenant-a")
    assert len(drafts)==5
    assert len({d.document_id for d,p in drafts})==5
    for doc,p in drafts:
        assert len(doc.pages)==3
        assert doc.pages[1].layers[1].text=="Organize os pedidos."
        assert doc.reference_content_ids==["p.1"]
        assert doc.approval_status=="draft" and doc.rights_status=="pending_review"
        assert doc.reference_status=="unverified" and not p["scientifically_validated"]
    assert h.prepare_drafts(preview(),"tenant-a")==drafts
    with pytest.raises(ValueError,match="SCOPE_MISMATCH"):
        h.prepare_drafts(preview(),"tenant-b")


def test_reject_wrong_reference():
    p=preview()
    p["creatives"][0]["creative_spec"]["reference_content_ids"]=["other"]
    with pytest.raises(ValueError,match="SPEC_SCOPE_MISMATCH"):
        h.prepare_drafts(p,"tenant-a")


def test_atomic_store_reuses_edited_draft_and_rejects_conflict(tmp_path,monkeypatch):
    engine=engine_for("sqlite:///"+(tmp_path/"handoff.sqlite").as_posix())
    metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(insert(tenants).values(tenant_id="tenant-a",name="Fixture"))
    # Real transaction and Studio store; scope and reference checks are simulated here.
    monkeypatch.setattr(h,"_scope_in_transaction",lambda *args:None)
    monkeypatch.setattr(h,"_validate_refs",lambda *args:None)
    principal=Principal(actor_id="actor",tenant_id="tenant-a",role="admin")
    frame=SimpleNamespace(fingerprint=lambda:"a"*64)
    drafts=h.prepare_drafts(preview(),"tenant-a")
    try:
        out=h.persist_drafts(engine,principal,frame,"12345",drafts,stopped=True)
        assert len(out)==5 and all(r["action"]=="CREATED" for r in out)
        store=StudioStore(engine)
        cid=drafts[0][0].document_id
        store.patch_text_layer("tenant-a","actor",cid,TextLayerPatch(page_id="page.1",layer_id="main",
                               expected_version=1,text="Versão editada"))
        repeat=h.persist_drafts(engine,principal,frame,"12345",drafts,stopped=True)
        assert all(r["action"]=="REUSED" for r in repeat)
        assert repeat[0]["current_version"]==2
        assert store.get("tenant-a",cid).pages[0].layers[1].text=="Versão editada"
        with engine.connect() as db:
            assert len(db.execute(select(domain_events.c.seq).where(domain_events.c.aggregate_type==h.AGG)).all())==5
        bad=preview()
        bad["creatives"][0]["creative_spec"]["headline"]="Outra versão"
        new=h.prepare_drafts(bad,"tenant-a")[0]
        conflict=(drafts[1][0],{**drafts[1][1],"authored_template":False})
        with pytest.raises(h.ConnectorError,match="BD_STUDIO_EXISTING_DRAFT_CONFLICT"):
            h.persist_drafts(engine,principal,frame,"12345",[new,conflict],stopped=True)
        with engine.connect() as db:
            assert len(db.execute(select(studio_documents.c.document_id)).all())==5
        with pytest.raises(h.ConnectorError,match="LOCAL_ADMIN_STOP_REQUIRED"):
            h.persist_drafts(engine,principal,frame,"12345",drafts,stopped=False)
    finally:
        engine.dispose()
