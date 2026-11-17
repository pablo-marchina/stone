"""Reaudit saved grounded report and rank local metadata; no inference or external release."""
import argparse
import getpass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re

from tapi_gate0.discovery_audience_exploratory import evidence_tier, report_rows, summarize
from tapi_gate0.discovery_batch import BatchManifest
from tapi_gate0.discovery_caption_research import require_scoped_research
from tapi_gate0.discovery_corpus_readiness import readiness_report
from tapi_gate0.discovery_local_db import validate_existing_database_url
from tapi_gate0.sa_store import engine_for
from tapi_gate0.connectors import ConnectorError

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--persist-studio-drafts", action="store_true", help="Create authenticated local editable drafts; implies agent preview")
    p.add_argument("--confirm-all-writers-stopped", action="store_true")
    p.add_argument("--admin", help="Existing local admin login; otherwise select unique enabled SQLite admin")
    p.add_argument("--agent-preview", action="store_true", help="Private exploratory agent findings and draft CreativeSpecs; implies editorial")
    p.add_argument("--editorial", action="store_true", help="Compute descriptive editorial coverage and ranking sensitivity")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--input-name", required=True)
    p.add_argument("--report-name", required=True)
    p.add_argument("--confirm-all-ingestion-stopped", action="store_true")
    a = p.parse_args(argv)
    if a.persist_studio_drafts:
        a.agent_preview = True
    if a.agent_preview:
        a.editorial = True
    engine = None
    identity_session_written = False
    studio_write_attempted = False
    try:
        if a.persist_studio_drafts and not a.confirm_all_writers_stopped:
            raise ConnectorError("BD_STUDIO_LOCAL_ADMIN_STOP_REQUIRED",403)
        if not a.confirm_all_ingestion_stopped:
            raise ConnectorError("BD_CORPUS_ADMIN_STOP_REQUIRED", 403)
        private = ROOT / "artifacts" / "private"
        if private.resolve() != private.absolute():
            raise ValueError("BD_EXPLORATORY_PRIVATE_ROOT_REDIRECTED")
        for name in (a.input_name, a.report_name):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json", name):
                raise ValueError("BD_EXPLORATORY_PRIVATE_NAME_REQUIRED")
        source, target = private/a.input_name, private/a.report_name
        if source.is_symlink() or target.is_symlink() or target.exists():
            raise ValueError("BD_EXPLORATORY_PRIVATE_PATH_INVALID")
        if source.stat().st_size > 25_000_000:
            raise ValueError("BD_EXPLORATORY_REPORT_TOO_LARGE")
        raw = source.read_bytes()
        frame = BatchManifest.model_validate_json(a.manifest.read_text(encoding="utf-8"))
        saved = report_rows(json.loads(raw), frame.fingerprint())
        tenant, viewer = os.environ["TAPI_TENANT_ID"], os.environ["TAPI_META_IG_ID"]
        engine = engine_for(validate_existing_database_url(os.environ["TAPI_DATABASE_URL"]))
        require_scoped_research(engine, tenant, frame, viewer)
        rows = []
        seen = set()
        if a.editorial:
            from tapi_gate0.classification import TOPICS, CTA
            from tapi_gate0.discovery_audience_signals import sampling_sector
            from tapi_gate0.discovery_editorial_descriptive import caption_features, age_band, analyze_editorial
        def observe(source, post, metric):
            cid = post.content_id
            if cid in seen or cid not in saved or saved[cid]["username"] != source.username:
                raise ValueError("BD_EXPLORATORY_REPORT_PARTITION_MISMATCH")
            seen.add(cid)
            tier = evidence_tier(post.caption, saved[cid])
            row = {"content_id": cid, "username": source.username, "tier": tier,
                         "likes": metric.likes, "comments": metric.comments,
                         "followers": metric.follower_count, "snapshot_id": metric.snapshot_id,
                         "observed_at": metric.observed_at.isoformat(),
                         "followers_measured_at": metric.followers_measured_at.isoformat(),
                         "caption_sha256": saved[cid]["caption_sha256"]}
            if a.editorial:
                row.update(format=post.media_type.value, published_at=post.published_at.isoformat(),
                           sector=sampling_sector(source.sampling_stratum), caption_chars=len(post.caption),
                           **caption_features(post.caption, TOPICS, CTA))
            rows.append(row)
        ready = readiness_report(engine, tenant, frame, viewer, _record_observer=observe)
        if seen != set(saved) or len(seen) != ready["first_blocking_stage"]["CAPTION_AVAILABLE_FOR_ASSESSMENT"]:
            raise ValueError("BD_EXPLORATORY_REPORT_PARTITION_MISMATCH")
        require_scoped_research(engine, tenant, frame, viewer)
        if a.editorial:
            as_of = datetime.fromisoformat(ready["as_of"])
            for row in rows:
                row["age_band"] = age_band((as_of-datetime.fromisoformat(row["published_at"])).days)
        result = summarize(rows)
        top = result.pop("top_ids_private")
        result.update(status="EXPLORATORY_RANKING_COMPLETED", as_of=ready["as_of"],
                      manifest_sha256=frame.fingerprint(), input_sha256=hashlib.sha256(raw).hexdigest(),
                      model_predictions_reexecuted=False, model_predictions_independently_verified=False,
                      external_data_accessed=False, database_mutated=False, production_approved=False,
                      caveats=["No cohort is independently validated MPE content.",
                               "ER uses latest observed likes/comments/followers, not historical publication-time denominator.",
                               "Sampling and age differences confound comparisons; no causal or editorial recommendation.",
                               "Saved model predictions are local operator evidence, not independently attested.",
                               "Top 10% uses ceil(n/10) and content ID tie-break; small strata are descriptive only."])
        editorial_private = {}
        if a.editorial:
            editorial = analyze_editorial(rows)
            editorial_private = editorial.pop("private_rankings")
            result["editorial"] = editorial
            from tapi_gate0.discovery_rubric_coverage import rubric_coverage
            result["rubric_coverage"] = rubric_coverage(rows)
            result["status"] = "EXPLORATORY_EDITORIAL_COMPLETED"
        agent_private = {}
        if a.agent_preview:
            from tapi_gate0.discovery_editorial_agent import build_agent_preview
            agent_private = build_agent_preview(rows, tenant=tenant, as_of=ready["as_of"], manifest_sha256=frame.fingerprint())
            result["agent_preview"] = {k:v for k,v in agent_private.items() if k not in ("findings","reference_posts","creatives")}
            result["agent_preview"].update(findings_count=len(agent_private["findings"]),
                reference_posts_count=len(agent_private["reference_posts"]), creatives_count=len(agent_private["creatives"]),
                hypotheses=[{k:v for k,v in f.items() if k != "reference_content_ids"} for f in agent_private["findings"]])
            result["status"] = "EXPLORATORY_AGENT_PREVIEW_COMPLETED"
        require_scoped_research(engine, tenant, frame, viewer)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            studio_private = {}
            if a.persist_studio_drafts:
                from tapi_gate0.discovery_studio_handoff import prepare_drafts, persist_drafts
                from tapi_gate0.identity import IdentityStore
                from tapi_gate0.local_admin_selection import select_admin_login
                if engine.dialect.name != "sqlite":
                    raise ConnectorError("BD_STUDIO_LOCAL_ADMIN_STOP_REQUIRED",403)
                drafts = prepare_drafts(agent_private, tenant)
                receipts = []
                if drafts:
                    try:
                        from scripts.a6_corpus_bridge import inspect_local_admins
                    except ModuleNotFoundError as exc:
                        if exc.name not in ("scripts", "scripts.a6_corpus_bridge"):
                            raise
                        from a6_corpus_bridge import inspect_local_admins
                    login = a.admin or select_admin_login(inspect_local_admins(engine,tenant)["admins"])
                    identity = IdentityStore(engine)
                    identity_session_written = True  # failed auth can also mutate lock state
                    session = identity.login(login,getpass.getpass("Admin password: "),tenant)
                    principal = identity.resolve(session.access_token)
                    try:
                        studio_write_attempted = True
                        receipts = persist_drafts(engine,principal,frame,viewer,drafts,stopped=True)
                    finally:
                        identity.revoke(session.access_token,principal)
                created = sum(r["action"]=="CREATED" for r in receipts)
                studio_private = {"receipts":receipts,"drafts":[{"document":doc.model_dump(mode="json"),"provenance":provenance} for doc,provenance in drafts]}
                result.update(status="EXPLORATORY_STUDIO_DRAFTS_COMPLETED",
                    studio_drafts_created=created,studio_drafts_reused=len(receipts)-created,
                    studio_documents=[r["document_id"] for r in receipts],
                    studio_mutated=bool(created),identity_session_written=identity_session_written,
                    database_mutated=identity_session_written,publication_approved=False)
            json.dump({**result, "private_rows": rows, "top_ids_private": top, **({"editorial_private_rankings": editorial_private} if a.editorial else {}), **({"agent_preview_private": agent_private} if a.agent_preview else {}), **({"studio_handoff_private":studio_private} if a.persist_studio_drafts else {})}, stream, indent=2)
        print(json.dumps({**result, "report_name": a.report_name}))
        return 0
    except ConnectorError as exc:
        code = exc.code
    except Exception as exc:
        from tapi_gate0.identity import IdentityFailure
        code = exc.code if isinstance(exc,IdentityFailure) else "BD_EXPLORATORY_LOCAL_ERROR"
        if isinstance(exc,ValueError) and exc.args and isinstance(exc.args[0],str) and re.fullmatch(r"BD_(?:EXPLORATORY|STUDIO)_[A-Z_]+",exc.args[0]):
            code = exc.args[0]
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps({"status":"BLOCKED", "code":code, "database_mutated":identity_session_written, "studio_write_attempted":studio_write_attempted,
                      "external_data_accessed":False, "scientific_admissions":0}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
