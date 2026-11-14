"""Local descriptive ranking of evidence strata, never scientific admission."""
from collections import Counter, defaultdict
from fractions import Fraction
from hashlib import sha256
from statistics import median
import math

from .discovery_audience_grounded import VERSION, grounded_candidate
from .discovery_audience_benchmark import POS, NEG, UNC, LABELS
from .discovery_audience_signals import assess_caption

POLICY = "bd-exploratory-ranking.v1"
TIERS = ("grounded_positive", "semantic_consensus_only", "single_model_or_lexical_signal", "unresolved", "grounded_negative")


def evidence_tier(caption, row):
    """Recompute deterministic evidence and consensus; saved model labels are not attested."""
    lexical = assess_caption(caption)
    semantic = row["semantic_predictions"]
    pt, en = semantic["descriptive_pt"], semantic["descriptive_en"]
    if pt not in LABELS or en not in LABELS or row["v1_status"] not in LABELS:
        raise ValueError("BD_EXPLORATORY_INVALID_LABEL")
    consensus = pt if pt == en else UNC
    if semantic["semantic_consensus"] != consensus:
        raise ValueError("BD_EXPLORATORY_CONSENSUS_MISMATCH")
    grounding = grounded_candidate(caption, consensus)
    if (row["caption_sha256"] != lexical["caption_sha256"]
            or row["lexical_status"] != lexical["signal_status"]
            or row["grounding"] != grounding or row["status"] != grounding["status"]
            or row["human_review"] is not False or row["scientific_admission"] is not False
            or row["targeting_decision"] != "not_assessed"):
        raise ValueError("BD_EXPLORATORY_EVIDENCE_MISMATCH")
    if grounding["status"] == POS:
        return TIERS[0]
    if grounding["status"] == NEG:
        return TIERS[4]
    if consensus == POS:
        return TIERS[1]
    if POS in (pt, en, row["v1_status"]) or lexical["signal_status"] != "NO_EXPLICIT_SIGNAL_ABSTAIN":
        return TIERS[2]
    return TIERS[3]


def report_rows(report, manifest_sha):
    if (report["status"] != "GROUNDED_CONTEXTUAL_CANDIDATES"
            or report["grounding_policy"] != VERSION or report["manifest_sha256"] != manifest_sha
            or report["synthetic_only"] is not False or report["scientifically_validated"] is not False
            or report["scientific_admissions"] != 0 or report["human_reviews"] != 0
            or report["targeting_decisions"] != 0 or report["database_mutated"] is not False
            or report["synthetic_benchmark"]["engineering_gate_passed"] is not True):
        raise ValueError("BD_EXPLORATORY_REPORT_SCOPE_MISMATCH")
    rows = report["private_evidence"]
    by_id = {r["content_id"]: r for r in rows}
    if not rows or len(rows) != len(by_id) or len(rows) != report["assessed_captions"]:
        raise ValueError("BD_EXPLORATORY_REPORT_PARTITION_MISMATCH")
    return by_id


def summarize(rows):
    """Rank exact ER fractions; ceil top 10%, deterministic ID tie-break.
    Small strata are reported descriptively but not interpreted as patterns.
    """
    if not rows or len({r["content_id"] for r in rows}) != len(rows):
        raise ValueError("BD_EXPLORATORY_EMPTY_OR_DUPLICATE")
    def rate(r):
        if r["followers"] <= 0 or min(r["likes"], r["comments"]) < 0:
            raise ValueError("BD_EXPLORATORY_INVALID_METRICS")
        return Fraction(r["likes"]+r["comments"], r["followers"])
    def stats(group):
        ordered = sorted(group, key=lambda r: (-rate(r), r["content_id"]))
        n = len(ordered)
        k = math.ceil(n/10)
        top = ordered[:k]
        return {"posts": n, "profiles": len({r["username"] for r in group}),
                "median_er_percent": round(float(median([rate(r) for r in ordered]))*100, 6) if n else None,
                "top_decile_count": k,
                "top_decile_median_er_percent": round(float(median([rate(r) for r in top]))*100, 6) if k else None,
                "cutoff_tie": bool(0 < k < n and rate(ordered[k-1]) == rate(ordered[k])),
                "descriptive_only": True,
                "top_ids": [r["content_id"] for r in top]}
    groups = {t: [r for r in rows if r["tier"] == t] for t in TIERS}
    cohorts = {"technical_all": rows,
               "semantic_exploratory": groups[TIERS[0]]+groups[TIERS[1]],
               **groups}
    summaries = {name: stats(group) for name, group in cohorts.items()}
    private = {name: facts.pop("top_ids") for name, facts in summaries.items()}
    sources = defaultdict(list)
    for r in rows:
        sources[r["username"]].append(r)
    source_stats = {}
    for name, group in sorted(sources.items()):
        facts = stats(group)
        facts.pop("top_ids")
        facts["tiers"] = {t: sum(r["tier"] == t for r in group) for t in TIERS}
        source_stats[name] = facts
    return {"policy_version": POLICY, "cohorts": summaries, "per_source": source_stats,
            "tier_counts": {t: len(groups[t]) for t in TIERS},
            "scientific_admissions": 0, "scientifically_validated": False,
            "ranking_kind": "local_exploratory_not_mpe_validated",
            "top_ids_private": private}
