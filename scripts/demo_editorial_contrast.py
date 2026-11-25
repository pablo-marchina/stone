"""Anonymous descriptive top/rest contrast; no content identifiers or free text."""
from math import ceil

from tapi_gate0.classification import CTA, TOPICS
from tapi_gate0.discovery_editorial_descriptive import _distribution, er
from tapi_gate0.domain import MediaType

ALLOWED = {
    "format": frozenset(x.value for x in MediaType),
    "topic": frozenset(TOPICS),
    "cta": frozenset(CTA),
    "age_band": frozenset(("14-29", "30-89", "90-364", "365+")),
}


def contrast(rows):
    """Shares use only observed values; unknowns are counted separately.

    Unrecognized labels are withheld (never displayed). Selection uses exact
    ER and the existing deterministic ID tie-break, not rounded percentages.
    """
    normalized = [{**r, **{k: r.get(k) if isinstance(r.get(k), str) and r[k] in allowed else None
                           for k, allowed in ALLOWED.items()}} for r in rows]
    ordered = sorted(normalized, key=lambda r: (-er(r), r["content_id"]))
    ids = {r["content_id"] for r in ordered[:ceil(len(ordered)/10)]}
    return {"top_posts": len(ids), "rest_posts": len(rows)-len(ids),
            "fields": {k: _distribution(normalized, ids, k) for k in ALLOWED},
            "descriptive_only": True, "causal_claims": False}
