"""A5 private historical checkpoint, bounded scheduling and recovery tests (no network)."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select

from tapi_gate0.connectors import ConnectorError, OfficialHttp
from tapi_gate0.discovery_batch import BatchLimits
from tapi_gate0.discovery_continuous import execute_cycle, plan_cycle, tenant_coverage
from tapi_gate0.discovery_history import cycle_lease, read_checkpoint
from tapi_gate0.discovery_technical import TechnicalDiscoveryRequest, TechnicalDiscoveryService
from tapi_gate0.ingestion import ingestion_runs
from tapi_gate0.sa_store import engine_for
from test_discovery_batch_a4 import db, manifest, SOURCES, TENANT, VIEWER, TOKEN


@pytest.fixture(autouse=True)
def switches(monkeypatch):
    for key in ("TAPI_BD_CONTINUOUS_ENABLED", "TAPI_BD_TECHNICAL_INGEST",
                "TAPI_OFFICIAL_METADATA_READS", "TAPI_ZERO_BILLING_CONFIRMED"):
        monkeypatch.setenv(key, "1")


def limits(sources=1):
    return BatchLimits(max_sources=sources, page_limit=2, max_pages=1, persist_limit=2)


def provider(*, fail=False, loop=False, recent=False):
    calls = []
    def callback(req):
        fields = req.url.params["fields"]
        calls.append(fields)
        assert req.url.host == "graph.facebook.com" and req.url.path == "/v26.0/" + VIEWER
        assert req.headers["Authorization"] == "Bearer " + TOKEN
        assert "access_token" not in str(req.url)
        if fail:
            return httpx.Response(429, json={"error":{"code":4}})
        name, ident, _ = next(s for s in SOURCES if f"username({s[0]})" in fields)
        base = 18000000000000000 + SOURCES.index((name, ident, _)) * 100
        start = 0 if ".after(" not in fields else 2 if ".after(CURSOR_ONE)" in fields else 4
        n = 2 if start < 4 else 1
        rows = [{"id": str(base+start+i), "media_type":"CAROUSEL_ALBUM", "media_product_type":"FEED",
                 "timestamp": (datetime.now(timezone.utc) - timedelta(days=1 if recent else 40)).isoformat(),
                 "like_count":10, "comments_count":1, "caption":"Negócios locais",
                 "permalink":f"https://www.instagram.com/p/Fixture{base+start+i}/"} for i in range(n)]
        cursor = "CURSOR_ONE" if start == 0 or loop else "CURSOR_TWO" if start == 2 else None
        paging = {"cursors":{"after":cursor}} if cursor else {}
        return httpx.Response(200,json={"id":VIEWER,"business_discovery":{
            "id":ident,"username":name,"followers_count":100,"media_count":5,
            "media":{"data":rows,"paging":paging}}})
    client = httpx.Client(transport=httpx.MockTransport(callback))
    return OfficialHttp(client=client, instagram_version="v26.0"), calls, client


def cycle(store, transport, *, mode="history", approved=1, budget=80):
    return execute_cycle(store,TENANT,manifest(approved=approved),VIEWER,
        mode=mode,limits=limits(),daily_request_budget=budget,token=TOKEN,http=transport)


def checkpoint(engine):
    with engine.connect() as conn:
        return read_checkpoint(conn,TENANT,SOURCES[0][1])


def test_history_resumes_full_pages_and_refresh_does_not_move_checkpoint(tmp_path):
    engine,store=db(tmp_path)
    transport,calls,client=provider()
    try:
        first=cycle(store,transport)
        assert first["batch"]["counts"]["new_records"]==2
        assert checkpoint(engine)["next_cursor"]=="CURSOR_ONE"
        assert "CURSOR_ONE" not in json.dumps(first)
        second=cycle(store,transport)
        assert second["batch"]["counts"]["new_records"]==2
        assert ".after(CURSOR_ONE)" in calls[-1]
        assert checkpoint(engine)["next_cursor"]=="CURSOR_TWO"
        prior=checkpoint(engine)
        refreshed=cycle(store,transport,mode="refresh")
        assert refreshed["batch"]["counts"]["new_records"]==0
        assert ".after(" not in calls[-1]
        assert checkpoint(engine)==prior
        third=cycle(store,transport)
        assert third["batch"]["counts"]["new_records"]==1
        assert checkpoint(engine)["status"]=="frontier_unconfirmed"
        assert checkpoint(engine)["next_cursor"] is None
        assert checkpoint(engine)["pages_examined"]==3
        assert tenant_coverage(store,TENANT)["unique_media_ids"]==5
        fourth=cycle(store,transport)
        assert fourth["status"]=="NO_DUE_AUTHORIZED_SOURCES"
        assert len(calls)==4
        assert fourth["plan"]["deferred"][0]["reason"]=="BD_HISTORY_FRONTIER_UNCONFIRMED"
        assert cycle(store,transport,mode="refresh")["status"]=="NO_DUE_AUTHORIZED_SOURCES"
    finally:
        client.close();engine.dispose()


def test_failure_preserves_checkpoint_and_stops_automatic_retries(tmp_path):
    engine,store=db(tmp_path)
    ok,calls,client=provider(); bad,bad_calls,bad_client=provider(fail=True)
    try:
        cycle(store,ok); prior=checkpoint(engine)
        report=cycle(store,bad)
        assert report["status"]=="BATCH_STOPPED_ON_SOURCE_FAILURE"
        assert checkpoint(engine)==prior
        assert len(bad_calls)==1
        assert cycle(store,ok)["status"]=="NO_DUE_AUTHORIZED_SOURCES"
        assert len(calls)==1
    finally:
        client.close();bad_client.close();engine.dispose()


def test_cursor_cycle_is_blocked_without_checkpoint_advance(tmp_path):
    engine,store=db(tmp_path)
    ok,calls,client=provider(); bad,bad_calls,bad_client=provider(loop=True)
    try:
        cycle(store,ok); prior=checkpoint(engine)
        report=cycle(store,bad)
        assert report["status"]=="BATCH_STOPPED_ON_SOURCE_FAILURE"
        assert report["batch"]["failure_code"]=="BD_PAGINATION_STALLED"
        assert checkpoint(engine)==prior
        assert "CURSOR_ONE" not in json.dumps(report)
    finally:
        client.close();bad_client.close();engine.dispose()


def test_empty_eligible_page_advances_without_fabricating_posts(tmp_path):
    engine,store=db(tmp_path)
    transport,calls,client=provider(recent=True)
    try:
        report=cycle(store,transport)
        assert report["status"]=="BATCH_NO_ELIGIBLE_OBSERVATIONS"
        assert report["batch"]["counts"]["new_records"]==0
        assert checkpoint(engine)["next_cursor"]=="CURSOR_ONE"
        assert tenant_coverage(store,TENANT)["unique_media_ids"]==0
    finally:
        client.close();engine.dispose()


def test_history_audit_failure_does_not_advance_checkpoint(tmp_path,monkeypatch):
    engine,store=db(tmp_path)
    transport,calls,client=provider()
    try:
        monkeypatch.setattr("tapi_gate0.discovery_technical.audit_run",lambda *a,**kw:{"all_traces_valid":False})
        report=cycle(store,transport)
        assert report["status"]=="BATCH_STOPPED_ON_SOURCE_FAILURE"
        assert report["batch"]["failure_code"]=="BD_HISTORY_AUDIT_FAILED"
        assert checkpoint(engine) is None
        with engine.connect() as conn:
            assert conn.execute(select(ingestion_runs.c.status)).scalar_one()=="failed"
    finally:
        client.close();engine.dispose()


def test_plan_fairness_budget_candidate_and_lease(tmp_path):
    engine,store=db(tmp_path)
    transport,calls,client=provider()
    try:
        plan,selected=plan_cycle(store,TENANT,manifest(),VIEWER,mode="history",limits=limits())
        assert len(selected)==1 and plan["external_data_accessed"] is False
        assert calls==[] and checkpoint(engine) is None
        first=cycle(store,transport,approved=2)
        second=cycle(store,transport,approved=2)
        assert first["plan"]["selected_sources"]!=second["plan"]["selected_sources"]
        blocked=cycle(store,transport,approved=2,budget=8)
        assert blocked["status"]=="NO_DUE_AUTHORIZED_SOURCES" and len(calls)==2
        with cycle_lease(engine,TENANT,"fixture-lease"):
            with pytest.raises(ConnectorError,match="BD_CYCLE_LEASE_UNAVAILABLE"):
                cycle(store,transport)
        assert len(calls)==2
        plan,_=plan_cycle(store,TENANT,manifest(approved=1),VIEWER,mode="history",limits=limits())
        assert any(s["reason"]=="SOURCE_NOT_APPROVED" for s in plan["deferred"])
    finally:
        client.close();engine.dispose()


def test_history_rejects_truncating_page_before_provider(tmp_path):
    engine,store=db(tmp_path)
    transport,calls,client=provider()
    try:
        req=TechnicalDiscoveryRequest(username=SOURCES[0][0],expected_ig_id=SOURCES[0][1],
            viewer_ig_id=VIEWER,run_key="a5bad-limit",page_limit=2,max_pages=1,persist_limit=1)
        with pytest.raises(ConnectorError,match="BD_HISTORY_FULL_PAGE_BUDGET_REQUIRED"):
            TechnicalDiscoveryService(store).execute(TENANT,req,token=TOKEN,http=transport,history=True)
        assert not calls
    finally:
        client.close();engine.dispose()


def test_migration_preserves_existing_ingestion_tables(tmp_path,monkeypatch):
    path=tmp_path/"migrate.sqlite"
    monkeypatch.setenv("TAPI_DATABASE_URL",f"sqlite:///{path}")
    root=Path(__file__).resolve().parents[1]
    config=Config(str(root/"alembic.ini"));config.set_main_option("script_location",str(root/"migrations"))
    command.upgrade(config,"0011_studio_source_audio_hq_e8")
    engine=engine_for(f"sqlite:///{path}")
    try:
        assert not inspect(engine).has_table("bd_history_checkpoints")
        command.upgrade(config,"head")
        assert inspect(engine).has_table("bd_history_checkpoints")
        assert inspect(engine).has_table("bd_cycle_leases")
        command.downgrade(config,"0011_studio_source_audio_hq_e8")
        assert not inspect(engine).has_table("bd_history_checkpoints")
        assert inspect(engine).has_table("ingestion_records")
    finally:
        engine.dispose()


def test_candidate_intake_preserves_existing_approvals_and_never_promotes():
    from scripts.a5_expand_source_frame import merge_candidates
    from tapi_gate0.discovery_batch import BatchManifest
    base=manifest(approved=1)
    public=BatchManifest.model_validate_json((Path(__file__).resolve().parents[1]/
        "evidence/acquisition/bd_a5_candidate_expansion_20261112.json").read_text(encoding="utf-8"))
    merged=merge_candidates(base,public)
    assert len(merged.sources)==len(base.sources)+6
    assert merged.sources[:len(base.sources)]==base.sources
    assert sum(s.status=="approved" for s in merged.sources)==1
    assert all(s.status=="candidate" and not s.allowed_operations for s in public.sources)
    with pytest.raises(ValueError,match="CANDIDATE_FRAME_CANNOT_CONTAIN_APPROVALS"):
        merge_candidates(base,manifest())


def test_a5_plan_cli_needs_no_token_and_never_writes(tmp_path,monkeypatch,capsys):
    from scripts.a5_business_discovery_cycle import main
    engine,store=db(tmp_path)
    try:
        monkeypatch.setenv("TAPI_DATABASE_URL",str(engine.url))
        monkeypatch.setenv("TAPI_TENANT_ID",TENANT)
        monkeypatch.setenv("TAPI_META_IG_ID",VIEWER)
        monkeypatch.delenv("TAPI_INSTAGRAM_ACCESS_TOKEN",raising=False)
        path=tmp_path/"manifest.json";path.write_text(manifest(approved=1).model_dump_json(), encoding="utf-8")
        assert main(["--manifest",str(path),"--mode","history"])==0
        result=json.loads(capsys.readouterr().out)
        assert result["status"]=="PLAN_ONLY_NO_EXTERNAL_READ"
        assert result["selected_sources"]==[SOURCES[0][0]]
        assert checkpoint(engine) is None
        with engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(ingestion_runs)).scalar_one()==0
    finally:
        engine.dispose()


def test_a5_missing_database_is_blocked_without_creating_file(tmp_path, monkeypatch, capsys):
    from scripts.a5_business_discovery_cycle import main
    from scripts.a5_recover_business_discovery import main as recover
    missing = tmp_path / "missing db.sqlite"
    monkeypatch.setenv("TAPI_DATABASE_URL", "sqlite:///" + missing.as_posix())
    monkeypatch.setenv("TAPI_TENANT_ID", TENANT)
    monkeypatch.setenv("TAPI_META_IG_ID", VIEWER)
    path = tmp_path / "manifest.json"
    path.write_text(manifest(approved=1).model_dump_json(), encoding="utf-8")
    assert main(["--manifest", str(path), "--mode", "history"]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "A5_DATABASE_INVALID_OR_MISSING"
    assert recover([]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "EXISTING_DATABASE_AND_TENANT_REQUIRED"
    assert not missing.exists()


def test_coverage_plan_observes_only_due_approved_sources_and_is_read_only(tmp_path):
    engine, store = db(tmp_path)
    try:
        plan, selected = plan_cycle(store, TENANT, manifest(approved=1), VIEWER,
            mode="history", limits=limits(sources=2), priority_policy="coverage")
        assert [s.username for s in selected] == [SOURCES[0][0]]
        assert plan["priority_comparison"]["coverage_policy"]["sources_without_observations"] == 1
        assert plan["priority_comparison"]["recency_baseline"]["selected_sources"] == plan["selected_sources"]
        assert plan["external_data_accessed"] is False
        assert any(s["reason"] == "SOURCE_NOT_APPROVED" for s in plan["deferred"])
        with engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(ingestion_runs)).scalar_one() == 0
        blocked, selected = plan_cycle(store, TENANT, manifest(approved=1, expired=True), VIEWER,
            mode="history", limits=limits(), priority_policy="coverage")
        assert not selected and not blocked["priority_comparison"]["inputs"]
    finally:
        engine.dispose()


def test_coverage_execution_counts_existing_inventory_without_touching_refresh_policy(tmp_path):
    engine, store = db(tmp_path)
    transport, calls, client = provider()
    try:
        first = execute_cycle(store, TENANT, manifest(approved=2), VIEWER,
            mode="history", limits=limits(), priority_policy="coverage", token=TOKEN, http=transport)
        assert first["status"] == "BATCH_COMPLETED"
        prior_calls = len(calls)
        plan, selected = plan_cycle(store, TENANT, manifest(approved=2), VIEWER,
            mode="history", limits=limits(sources=2), priority_policy="coverage")
        coverage = {c["username"]: c["technical_posts"] for c in plan["priority_comparison"]["inputs"]}
        assert sorted(coverage.values()) == [0, 2]
        assert len(calls) == prior_calls and len(selected) == 2
        with pytest.raises(ConnectorError, match="BD_PRIORITY_INVALID_POLICY"):
            plan_cycle(store, TENANT, manifest(), VIEWER, mode="refresh", limits=limits(), priority_policy="coverage")
        default, _ = plan_cycle(store, TENANT, manifest(), VIEWER, mode="refresh", limits=limits())
        assert default["priority_policy"] == "recency" and default["priority_comparison"] is None
    finally:
        client.close()
        engine.dispose()


def test_coverage_cli_preview_matches_selected_policy(tmp_path, monkeypatch, capsys):
    from scripts.a5_business_discovery_cycle import main
    engine, store = db(tmp_path)
    try:
        monkeypatch.setenv("TAPI_DATABASE_URL", str(engine.url))
        monkeypatch.setenv("TAPI_TENANT_ID", TENANT)
        monkeypatch.setenv("TAPI_META_IG_ID", VIEWER)
        monkeypatch.delenv("TAPI_INSTAGRAM_ACCESS_TOKEN", raising=False)
        path = tmp_path / "manifest.json"
        path.write_text(manifest().model_dump_json(), encoding="utf-8")
        assert main(["--manifest", str(path), "--mode", "history", "--priority-policy", "coverage"]) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["priority_comparison"]["coverage_policy"]["selected_sources"] == result["selected_sources"]
        assert result["external_data_accessed"] is False
    finally:
        engine.dispose()


def test_scheduler_real_a5_cycle_and_replay(tmp_path, monkeypatch):
    from tapi_gate0 import discovery_scheduler as scheduler
    from tapi_gate0.sa_store import domain_events
    engine, store = db(tmp_path)
    transport, calls, client = provider()
    try:
        now = datetime.now(timezone.utc).replace(hour=10)
        monkeypatch.setattr(scheduler, "now_utc", lambda: now)
        monkeypatch.setenv("TAPI_BD_SCHEDULER_ENABLED", "1")
        monkeypatch.setenv("TAPI_META_REQUIRE_TOKEN_EXPIRY", "1")
        monkeypatch.setenv("TAPI_META_TOKEN_EXPIRES_AT", (datetime.now(timezone.utc)+timedelta(days=30)).isoformat())
        monkeypatch.delenv("TAPI_META_DATA_ACCESS_EXPIRES_AT", raising=False)
        frame = manifest(approved=1)
        plan = scheduler.preview_tick(store, TENANT, frame, VIEWER, max_sources=1)
        assert plan["proposed_mode"] == "history" and not plan["execution_blockers"]
        assert not calls
        result = scheduler.execute_tick(store, TENANT, frame, VIEWER, max_sources=1, token=TOKEN, http=transport)
        assert result["status"] == "SCHEDULER_COMPLETED"
        assert result["cycle"]["plan"]["priority_policy"] == "coverage"
        assert result["cycle"]["batch"]["counts"]["new_records"] > 0
        assert checkpoint(engine) is not None
        before = len(calls)
        with pytest.raises(ConnectorError, match="BD_SCHEDULER_SLOT_ALREADY_CONSUMED"):
            scheduler.execute_tick(store, TENANT, frame, VIEWER, max_sources=1, token=TOKEN, http=transport)
        assert len(calls) == before
        with engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(domain_events).where(
                domain_events.c.aggregate_type == scheduler.AGGREGATE)).scalar_one() == 2
    finally:
        client.close()
        engine.dispose()


def test_scheduler_cli_preview_requires_no_token_and_does_not_write(tmp_path, monkeypatch, capsys):
    from scripts.a6_supervised_scheduler import main
    from tapi_gate0 import discovery_scheduler as scheduler
    from tapi_gate0.sa_store import domain_events
    engine, store = db(tmp_path)
    try:
        monkeypatch.setenv("TAPI_DATABASE_URL", str(engine.url))
        monkeypatch.setenv("TAPI_TENANT_ID", TENANT)
        monkeypatch.setenv("TAPI_META_IG_ID", VIEWER)
        monkeypatch.setenv("TAPI_BD_SCHEDULER_ENABLED", "0")
        monkeypatch.setenv("TAPI_META_REQUIRE_TOKEN_EXPIRY", "0")
        for key in ("TAPI_INSTAGRAM_ACCESS_TOKEN", "TAPI_META_TOKEN_EXPIRES_AT", "TAPI_META_DATA_ACCESS_EXPIRES_AT"):
            monkeypatch.delenv(key, raising=False)
        path = tmp_path / "manifest.json"
        path.write_text(manifest(approved=1).model_dump_json(), encoding="utf-8")
        assert main(["--manifest", str(path)]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["status"] == "SCHEDULER_PLAN_ONLY"
        assert "BD_SCHEDULER_TOKEN_EXPIRY_REQUIRED" in report["execution_blockers"]
        assert report["external_data_accessed"] is False
        with engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(ingestion_runs)).scalar_one() == 0
            assert conn.execute(select(func.count()).select_from(domain_events).where(
                domain_events.c.aggregate_type == scheduler.AGGREGATE)).scalar_one() == 0
    finally:
        engine.dispose()


def test_readiness_reports_caption_without_scientific_admission(tmp_path, monkeypatch, capsys):
    # Register corpus tables before the A4 fixture creates metadata.
    from tapi_gate0 import corpus  # noqa: F401
    from tapi_gate0.discovery_corpus_readiness import readiness_report
    from tapi_gate0.sa_store import domain_events
    from tapi_gate0.ingestion import source_grants
    from sqlalchemy import update
    from scripts.a6_corpus_readiness import main
    engine, store = db(tmp_path)
    transport, calls, client = provider()
    try:
        cycle(store, transport)
        frame = manifest(approved=1)
        before = len(calls)
        with engine.connect() as conn:
            event_count = conn.execute(select(func.count()).select_from(domain_events)).scalar_one()
        report = readiness_report(engine, TENANT, frame, VIEWER)
        assert report["technical_inventory"]["records"] == 2
        assert report["first_blocking_stage"]["CAPTION_AVAILABLE_FOR_ASSESSMENT"] == 2
        assert report["canonical_corpus_card"]["observed"]["scientifically_eligible_instagram_posts"] == 0
        assert report["new_scientific_admissions"] == 0
        assert "Negócios locais" not in json.dumps(report, ensure_ascii=False)
        assert len(calls) == before
        monkeypatch.setenv("TAPI_DATABASE_URL", str(engine.url))
        monkeypatch.setenv("TAPI_TENANT_ID", TENANT)
        monkeypatch.setenv("TAPI_META_IG_ID", VIEWER)
        monkeypatch.delenv("TAPI_INSTAGRAM_ACCESS_TOKEN", raising=False)
        path = tmp_path / "manifest.json"
        path.write_text(frame.model_dump_json(), encoding="utf-8")
        assert main(["--manifest", str(path)]) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "CORPUS_READINESS_PLANNED"
        with engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(domain_events)).scalar_one() == event_count
        with engine.begin() as conn:
            conn.execute(update(source_grants).where(source_grants.c.tenant_id == TENANT,
                source_grants.c.source_account_id == SOURCES[0][1]).values(enabled=0))
        revoked = readiness_report(engine, TENANT, frame, VIEWER)
        assert revoked["first_blocking_stage"]["SOURCE_NOT_ELIGIBLE"] == 2
        assert revoked["first_blocking_stage"]["CAPTION_AVAILABLE_FOR_ASSESSMENT"] == 0
    finally:
        client.close()
        engine.dispose()
