"""Offline report audit against persisted mock-transport observations."""
import copy
import pytest
from scripts.a6_audit_history_reports import consolidate
from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_technical import TechnicalDiscoveryService, audit_run
from test_discovery_technical_a3 import setup, request as make_request, transport, RECENT, TENANT, VIEWER, TARGET, TOKEN

CYCLE = "a5history-20261113021012-0b5d54d6"


@pytest.fixture(params=[False, True])
def audited_report(tmp_path, monkeypatch, request):
    for flag in ("TAPI_BD_TECHNICAL_INGEST", "TAPI_OFFICIAL_METADATA_READS", "TAPI_ZERO_BILLING_CONFIRMED"):
        monkeypatch.setenv(flag,"1")
    engine,store=setup(tmp_path)
    http,_,client=transport(pages=[RECENT] if request.param else None)
    key=CYCLE+"-01"
    try:
        result=TechnicalDiscoveryService(store).execute(TENANT,make_request(key,pages=1 if request.param else 2),token=TOKEN,http=http)
        audit=audit_run(engine,TENANT,key)
        counters=result["sample"]["counts"]
        row={"username":"sebrae","run_key":key,"source_account_id":TARGET,
             "provider_counts":counters,"new_records":audit["new_records"],"refreshed_records":audit["refreshed_records"],
             "unchanged_duplicate_records":audit["duplicate_records"],"pages_examined":result["sample"]["pages_examined"],
             "audit_observations":audit["observations"],"audit_all_traces_valid":True,
             "history_checkpoint_status":"continuation_available",
             "evidence":[{k:i[k] for k in ("source_item_id","content_id","snapshot_id","metadata_sha256")} for i in audit["items"]]}
        counts={k:row[k] for k in ("new_records","refreshed_records","unchanged_duplicate_records","pages_examined")}
        counts.update(returned=counters["returned"],eligible_observations=counters["accepted"],provider_duplicate_items=counters["duplicate_in_page"],too_recent=counters["too_recent"])
        status="BATCH_NO_ELIGIBLE_OBSERVATIONS" if request.param else "BATCH_COMPLETED"
        report={"cycle_key":CYCLE,"mode":"history","schema_version":"tapi-bd-continuous-cycle.v1","status":status,
                "plan":{"selected_sources":["sebrae"]},"batch":{"batch_key":CYCLE,"status":status,"sources":[row],"counts":counts}}
        yield engine,report
    finally:
        client.close();engine.dispose()


def test_reaudit(audited_report):
    engine,report=audited_report
    result=consolidate(engine,TENANT,VIEWER,[report])
    assert result["status"]=="HISTORY_REPORTS_REAUDITED"
    assert result["totals"]["observations"]==report["batch"]["counts"]["eligible_observations"]
    assert result["database_written"] is False
    assert result["external_data_accessed"] is False


@pytest.mark.parametrize("change",["counts","duplicate","scope","exclusions"])
def test_rejects_mismatch(audited_report,change):
    engine,report=audited_report
    report=copy.deepcopy(report)
    if change=="counts":report["batch"]["counts"]["new_records"]+=1
    if change=="scope":report["batch"]["sources"][0]["source_account_id"]="17841499999999999"
    if change=="exclusions":report["batch"]["sources"][0]["provider_counts"]["missing_metrics"]+=1
    with pytest.raises(ConnectorError):
        consolidate(engine,TENANT,VIEWER,[report,report] if change=="duplicate" else [report])
