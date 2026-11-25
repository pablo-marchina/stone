"""Consolidated read-only audit of completed, private A5/A6 history reports."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_local_db import validate_existing_database_url
from tapi_gate0.discovery_technical import audit_run
from tapi_gate0.ingestion import ingestion_runs
from tapi_gate0.sa_store import engine_for

CYCLE = re.compile(r"a5history-[0-9]{14}-[a-f0-9]{8}\Z")
EXCLUSIONS = ("too_recent", "unsupported_format", "missing_metrics", "invalid_metadata", "duplicate_in_page")
COUNTERS = ("returned", "accepted", *EXCLUSIONS)


def require(ok):
    if not ok:
        raise ConnectorError("BD_REPORT_AUDIT_MISMATCH", 409)


def number(value):
    require(type(value) is int and value >= 0)
    return value


def consolidate(engine, tenant, viewer, reports):
    require(1 <= len(reports) <= 20 and bool(re.fullmatch(r"[0-9]{5,32}", viewer)))
    seen = set()
    rows = []
    totals = dict.fromkeys((*COUNTERS, "observations", "new_records", "refreshed_records", "unchanged_duplicate_records", "pages_examined"), 0)
    with engine.connect() as db:
        for report in reports:
            cycle = report["cycle_key"]
            require(bool(CYCLE.fullmatch(cycle)) and report["mode"] == "history"
                    and report["schema_version"] == "tapi-bd-continuous-cycle.v1"
                    and report["status"] in {"BATCH_COMPLETED", "BATCH_NO_ELIGIBLE_OBSERVATIONS"})
            batch = report["batch"]
            sources = batch["sources"]
            require(1 <= len(sources) <= 5 and batch["batch_key"] == cycle
                    and batch["status"] == report["status"]
                    and report["plan"]["selected_sources"] == [s["username"] for s in sources])
            subtotal = dict.fromkeys(totals, 0)
            for index, source in enumerate(sources, 1):
                run_key = source["run_key"]
                require(run_key == f"{cycle}-{index:02d}" and run_key not in seen)
                seen.add(run_key)
                ledger = db.execute(select(ingestion_runs).where(ingestion_runs.c.tenant_id == tenant,
                    ingestion_runs.c.run_key == run_key)).mappings().one_or_none()
                require(ledger is not None and ledger["platform"] == "instagram"
                        and ledger["source_account_id"] == source["source_account_id"]
                        and ledger["status"] == "completed")
                audit = audit_run(engine, tenant, run_key)
                require(audit["all_traces_valid"] is True and source["audit_all_traces_valid"] is True)
                counters = {k: number(source["provider_counts"][k]) for k in COUNTERS}
                counts = {"new_records":number(source["new_records"]),
                    "refreshed_records":number(source["refreshed_records"]),
                    "unchanged_duplicate_records":number(source["unchanged_duplicate_records"]),
                    "observations":number(audit["observations"]), "pages_examined":number(source["pages_examined"])}
                require(counters["returned"] == counters["accepted"] + sum(counters[k] for k in EXCLUSIONS)
                        and counters["accepted"] == counts["observations"] == source["audit_observations"]
                        and counts["observations"] == sum(counts[k] for k in ("new_records", "refreshed_records", "unchanged_duplicate_records"))
                        and counts["new_records"] == audit["new_records"]
                        and counts["refreshed_records"] == audit["refreshed_records"]
                        and counts["unchanged_duplicate_records"] == audit["duplicate_records"]
                        and 1 <= counts["pages_examined"] <= 4
                        and audit["has_persisted_observations"] == bool(counts["observations"]))
                evidence_keys = ("source_item_id", "content_id", "snapshot_id", "metadata_sha256")
                require(all(item["viewer_ig_id"] == viewer and item["source_account_id"] == source["source_account_id"]
                            and item["acquisition_method"] == "graph_business_discovery"
                            and item["scientific_eligibility"] == "NOT_ASSESSED" for item in audit["items"]))
                require([tuple(item[k] for k in evidence_keys) for item in source["evidence"]] ==
                        [tuple(item[k] for k in evidence_keys) for item in audit["items"]])
                require(source["history_checkpoint_status"] in {"continuation_available", "frontier_unconfirmed"})
                combined = {**counters, **counts}
                for k, v in combined.items():
                    subtotal[k] += v
                rows.append({"username":source["username"], "run_key":run_key, **combined,
                             "checkpoint_at_run":source["history_checkpoint_status"], "audit_valid":True})
            aliases = {"eligible_observations":"accepted", "provider_duplicate_items":"duplicate_in_page"}
            for key in ("returned", "eligible_observations", "provider_duplicate_items", "too_recent", "new_records",
                        "refreshed_records", "unchanged_duplicate_records", "pages_examined"):
                require(number(batch["counts"][key]) == subtotal[aliases.get(key,key)])
            for k, v in subtotal.items():
                totals[k] += v
    return {"status":"HISTORY_REPORTS_REAUDITED", "reports":len(reports), "runs":len(rows),
            "totals":totals, "sources":rows, "external_data_accessed":False,
            "scientific_admissions":0, "database_written":False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", type=Path, required=True)
    args = parser.parse_args(argv)
    engine = None
    try:
        root = (Path(__file__).resolve().parents[1] / "artifacts" / "private").resolve()
        require(1 <= len(args.report) <= 20 and all(p.resolve().is_relative_to(root) and p.suffix.lower()==".json" for p in args.report))
        url = validate_existing_database_url(os.environ["TAPI_DATABASE_URL"])
        require(url.startswith("sqlite:///"))
        engine = engine_for(url)
        reports = [json.loads(p.read_text(encoding="utf-8")) for p in args.report]
        print(json.dumps(consolidate(engine, os.environ["TAPI_TENANT_ID"], os.environ["TAPI_META_IG_ID"], reports), ensure_ascii=False))
        return 0
    except ConnectorError as exc:
        print(json.dumps({"status":"BLOCKED", "code":exc.code, "external_data_accessed":False}))
        return 3
    except (OSError, SQLAlchemyError, ValueError, KeyError, TypeError, AttributeError):
        print(json.dumps({"status":"BLOCKED", "code":"BD_REPORT_INVALID_INPUT_OR_DATABASE", "external_data_accessed":False}))
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
