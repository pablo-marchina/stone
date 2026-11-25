"""CAP-002 descriptive sensitivity and observable editorial features; local only."""
from collections import Counter, defaultdict
from fractions import Fraction
from math import ceil
from statistics import median
import re

VERSION = "bd-editorial-descriptive.v1"
FIELDS = ("format", "topic", "cta", "age_band", "sector")
MIN_PROFILE_POSTS = 10  # engineering coverage floor for within-profile comparison


def caption_features(text, topics, cta):
    """Reuse the existing conservative baseline rules; absence is unknown."""
    topic_hits = [key for key, patterns in topics.items()
                  if any(re.search(pattern, text.casefold()) for pattern in patterns)]
    cta_hits = [key for key, pattern in cta.items() if re.search(pattern, text.casefold())]
    return {"topic": topic_hits[0] if len(topic_hits) == 1 else None,
            "cta": cta_hits[0] if len(cta_hits) == 1 else None}


def age_band(age_days):
    if age_days < 14:
        raise ValueError("BD_EDITORIAL_IMMATURE_POST")
    return "14-29" if age_days < 30 else "30-89" if age_days < 90 else "90-364" if age_days < 365 else "365+"


def er(row):
    if row["followers"] <= 0 or min(row["likes"], row["comments"]) < 0:
        raise ValueError("BD_EDITORIAL_INVALID_METRIC")
    return Fraction(row["likes"] + row["comments"], row["followers"])


def _ordered(rows):
    return sorted(rows, key=lambda r: (-er(r), r["content_id"]))


def _top(rows):
    return _ordered(rows)[:ceil(len(rows)/10)]


def _profile_percentiles(rows):
    """Midrank of tied observations, 0=lowest, 1=highest, exact rational."""
    ordered = sorted(rows, key=er)
    n = len(ordered)
    result = {}
    i = 0
    while i < n:
        j = i + 1
        while j < n and er(ordered[j]) == er(ordered[i]):
            j += 1
        percentile = Fraction(i+j-1, 2*(n-1)) if n > 1 else Fraction(1,2)
        for r in ordered[i:j]:
            result[r["content_id"]] = percentile
        i = j
    return result


def _distribution(rows, top_ids, field):
    top = [r for r in rows if r["content_id"] in top_ids]
    rest = [r for r in rows if r["content_id"] not in top_ids]
    def coverage(group):
        known = [r for r in group if r[field] is not None]
        return {"posts": len(group), "observed": len(known), "unknown": len(group)-len(known),
                "counts": dict(sorted(Counter(r[field] for r in known).items()))}
    a, b = coverage(top), coverage(rest)
    values = sorted(set(a["counts"]) | set(b["counts"]))
    comparisons = []
    for value in values:
        x, y = a["counts"].get(value, 0), b["counts"].get(value, 0)
        # Denominator is observed only; no lift when comparison group has zero observations.
        pt = x/a["observed"] if a["observed"] else None
        pr = y/b["observed"] if b["observed"] else None
        comparisons.append({"value": value, "top_count": x, "rest_count": y,
                            "top_observed_share": round(pt, 6) if pt is not None else None,
                            "rest_observed_share": round(pr, 6) if pr is not None else None,
                            "difference_percentage_points": round((pt-pr)*100,6) if pt is not None and pr is not None else None,
                            "top_profiles": len({r["username"] for r in top if r[field] == value})})
    return {"top": a, "rest": b, "comparisons": comparisons}


def analyze_cohort(rows):
    if not rows:
        return {"posts":0, "profiles":0, "status":"EMPTY_COHORT"}, {}
    ids = {r["content_id"] for r in rows}
    if len(ids) != len(rows):
        raise ValueError("BD_EDITORIAL_DUPLICATE")
    by_source = defaultdict(list)
    for r in rows:
        by_source[r["username"]].append(r)
        er(r)
    global_top = _top(rows)
    global_ids = {r["content_id"] for r in global_top}
    supported = [r for name, group in by_source.items() if len(group) >= MIN_PROFILE_POSTS for r in group]
    supported_ids = {r["content_id"] for r in supported}
    # Equal top fraction per supported profile, not equal total weight.
    within_top = []
    percentiles = {}
    for name, group in sorted(by_source.items()):
        if len(group) >= MIN_PROFILE_POSTS:
            within_top.extend(_top(group))
            percentiles.update(_profile_percentiles(group))
    within_ids = {r["content_id"] for r in within_top}
    same_population_global = {r["content_id"] for r in _top(supported)}
    intersection = within_ids & same_population_global
    union = within_ids | same_population_global
    # Leave-one-profile-out stability: rank remaining rows, compare global top
    # restricted to surviving rows with recomputed top, using Jaccard.
    loo = []
    for name in sorted(by_source):
        remaining = [r for r in rows if r["username"] != name]
        base = global_ids & {r["content_id"] for r in remaining}
        recomputed = {r["content_id"] for r in _top(remaining)}
        u = base | recomputed
        loo.append({"omitted_profile":name, "remaining_posts":len(remaining),
                    "jaccard":round(len(base & recomputed)/len(u),6) if u else None})
    summary = {"posts":len(rows), "profiles":len(by_source),
               "global_top_count":len(global_ids),
               "global_top_profiles":dict(sorted(Counter(r["username"] for r in global_top).items())),
               "within_profile_min_posts":MIN_PROFILE_POSTS,
               "within_profile_supported_posts":len(supported),
               "within_profile_supported_profiles":sum(len(g)>=MIN_PROFILE_POSTS for g in by_source.values()),
               "within_profile_excluded_posts":len(ids-supported_ids),
               "within_profile_top_count":len(within_ids),
               "same_population_global_top_count":len(same_population_global),
               "top_overlap_count":len(intersection),
               "top_jaccard":round(len(intersection)/len(union),6) if union else None,
               "global_top_median_within_profile_percentile":round(float(median([percentiles[c] for c in global_ids if c in percentiles])),6) if global_ids & supported_ids else None,
               "leave_one_profile_out":loo,
               "observables_global":{f:_distribution(rows,global_ids,f) for f in FIELDS},
               "observables_within_profile":{f:_distribution(supported,within_ids,f) for f in FIELDS},
               "descriptive_only":True}
    private = {"global_top":[r["content_id"] for r in global_top],
               "within_profile_top":sorted(within_ids),
               "percentiles":{c:str(v) for c,v in sorted(percentiles.items())}}
    return summary, private


def analyze_editorial(rows):
    cohorts = {"technical_all":rows,
               "semantic_exploratory":[r for r in rows if r["tier"] in ("grounded_positive","semantic_consensus_only")]}
    summaries, private = {}, {}
    for name, group in cohorts.items():
        summaries[name], private[name] = analyze_cohort(group)
    return {"editorial_policy":VERSION, "cohorts":summaries,
            "scientific_admissions":0, "scientifically_validated":False,
            "causal_claims":False, "editorial_recommendations_generated":False,
            "unobserved_modalities":["image","video","audio","transcript"],
            "private_rankings":private}
