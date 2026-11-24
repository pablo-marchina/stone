"""Project a saved private A6 ranking report to anonymous historical aggregates.

No database, provider, media, identifiers or source captions in the response.
Integrity checks detect inconsistent summaries, not forged historical reports.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from datetime import datetime
import re

from tapi_gate0.discovery_audience_exploratory import POLICY, TIERS, summarize
from tapi_gate0.discovery_rubric_coverage import rubric_coverage
from scripts.demo_editorial_contrast import contrast

STATUSES = {"EXPLORATORY_RANKING_COMPLETED", "EXPLORATORY_EDITORIAL_COMPLETED",
            "EXPLORATORY_AGENT_PREVIEW_COMPLETED", "EXPLORATORY_STUDIO_DRAFTS_COMPLETED"}


def project_report(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 25_000_000:
        raise ValueError("DEMO_REPORT_PATH_INVALID")
    raw = path.read_bytes()
    try:
        report = json.loads(raw)
        if (report["status"] not in STATUSES or report["policy_version"] != POLICY
                or report["ranking_kind"] != "local_exploratory_not_mpe_validated"
                or report["scientifically_validated"] is not False or report["scientific_admissions"] != 0
                or report["production_approved"] is not False):
            raise ValueError()
        date = datetime.fromisoformat(report["as_of"])
        if date.tzinfo is None or not re.fullmatch(r"[a-f0-9]{64}", report["manifest_sha256"]):
            raise ValueError()
        rows = report["private_rows"]
        if not isinstance(rows, list) or not 0 < len(rows) <= 100_000:
            raise ValueError()
        for row in rows:
            if (row["tier"] not in TIERS or not all(type(row[k]) is int for k in ("likes", "comments", "followers"))
                    or not all(type(row[k]) is str and row[k] for k in ("content_id", "username"))):
                raise ValueError()
        expected = summarize(rows)
        for key in ("cohorts", "tier_counts", "per_source"):
            if expected[key] != report[key]:
                raise ValueError()
        coverage = None
        if "rubric_coverage" in report:
            coverage = rubric_coverage(rows)
            if coverage != report["rubric_coverage"]:
                raise ValueError()
            coverage = coverage["cohorts"]["technical_all"]["fields"]
        return {"schema_version": "tapi-demo-technical-snapshot.v1",
                "as_of": date.isoformat(), "report_sha256": hashlib.sha256(raw).hexdigest(),
                "manifest_sha256": report["manifest_sha256"], "cohorts": expected["cohorts"],
                "tier_counts": expected["tier_counts"], "rubric_fields": coverage,
                "editorial_contrast": contrast(rows),
                "historical_report_only": True, "current_rights_verified": False,
                "scientifically_validated": False, "scientific_admissions": 0,
                "production_approved": False}
    except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError):
        raise ValueError("DEMO_REPORT_INCONSISTENT_OR_UNSUPPORTED") from None
