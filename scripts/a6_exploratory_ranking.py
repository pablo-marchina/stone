"""Reaudit saved grounded report and rank local metadata; no inference or external release."""
import argparse
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
    p.add_argument("--editorial", action="store_true", help="Compute descriptive editorial coverage and ranking sensitivity")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--input-name", required=True)
    p.add_argument("--report-name", required=True)
    p.add_argument("--confirm-all-ingestion-stopped", action="store_true")
    a = p.parse_args(argv)
    engine = None
    try:
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
                           sector=sampling_sector(source.sampling_stratum),
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
            result["status"] = "EXPLORATORY_EDITORIAL_COMPLETED"
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({**result, "private_rows": rows, "top_ids_private": top, **({"editorial_private_rankings": editorial_private} if a.editorial else {})}, stream, indent=2)
        print(json.dumps({**result, "report_name": a.report_name}))
        return 0
    except ConnectorError as exc:
        code = exc.code
    except Exception as exc:
        # Avoid echoing captions, paths or SQL.
        code = "BD_EXPLORATORY_LOCAL_ERROR"
        if isinstance(exc, ValueError) and exc.args and str(exc.args[0]) in {
            "BD_EXPLORATORY_REPORT_SCOPE_MISMATCH", "BD_EXPLORATORY_REPORT_PARTITION_MISMATCH",
            "BD_EXPLORATORY_EVIDENCE_MISMATCH", "BD_EXPLORATORY_CONSENSUS_MISMATCH",
            "BD_EXPLORATORY_INVALID_LABEL", "BD_EXPLORATORY_PRIVATE_PATH_INVALID",
            "BD_EXPLORATORY_PRIVATE_ROOT_REDIRECTED", "BD_EXPLORATORY_PRIVATE_NAME_REQUIRED",
            "BD_EXPLORATORY_REPORT_TOO_LARGE", "BD_EXPLORATORY_INVALID_METRICS",
            "BD_EXPLORATORY_EMPTY_OR_DUPLICATE"}:
            code = str(exc.args[0])
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps({"status":"BLOCKED", "code":code, "database_mutated":False,
                      "external_data_accessed":False, "scientific_admissions":0}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
