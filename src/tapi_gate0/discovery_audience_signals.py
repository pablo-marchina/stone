"""Conservative local lexical evidence triage, never a scientific admission."""
from __future__ import annotations

import hashlib
import re

POLICY = "bd-caption-audience-signals.v1"
AUDIENCE = r"(?:MEIs?|microempreendedor(?:es|a|as)?(?:\s+individua(?:l|is))?|microempresas?|pequen[oa]s?\s+(?:empreendedor(?:es|a|as)?|negócios?|negocios?|empresas?))"
RULES = (
    ("direct_address", re.compile(r"\b(?:atenção|atencao|olá|ola|ei|você\s*,|voce\s*,)\s*[,!:]?\s*" + AUDIENCE + r"\b", re.I)),
    ("conditional_address", re.compile(r"\bse\s+voc[êe]\s+[ée]\s+(?:(?:um|uma)\s+)?" + AUDIENCE + r"\b", re.I)),
    ("dedicated_audience", re.compile(r"\b(?:para|destinad[oa]s?\s+a|voltad[oa]s?\s+a)\s+(?:(?:os|as)\s+)?" + AUDIENCE + r"\b", re.I)),
    ("possessive_business", re.compile(r"\b(?:seu\s+pequeno\s+neg[óo]cio|sua\s+microempresa|sua\s+pequena\s+empresa)\b", re.I)),
)
MENTION = re.compile(r"\b" + AUDIENCE + r"\b", re.I)


def assess_caption(caption: str) -> dict:
    """Return codepoint spans and hash only; no excerpt, confidence or admission."""
    if not isinstance(caption, str) or not caption.strip() or len(caption) > 10000:
        raise ValueError("BD_CAPTION_INVALID")
    evidence = sorted({(m.start(), m.end(), rule) for rule, pattern in RULES
                       for m in pattern.finditer(caption)})
    mentions = list(MENTION.finditer(caption))
    if evidence:
        status = "EXPLICIT_AUDIENCE_SIGNAL"
    elif mentions:
        status = "MENTION_ONLY_UNCERTAIN"
        evidence = [(m.start(), m.end(), "audience_mention") for m in mentions]
    else:
        status = "NO_EXPLICIT_SIGNAL_ABSTAIN"
    return {"policy_version": POLICY, "signal_status": status,
            "caption_sha256": hashlib.sha256(caption.encode("utf-8")).hexdigest(),
            "evidence_spans": [{"start": start, "end": end, "rule": rule}
                               for start, end, rule in evidence[:20]],
            "evidence_truncated": len(evidence) > 20,
            "targeting_decision": "not_assessed", "human_review": False,
            "scientific_admission": False}


SECTORS = {
    "foodservice_association_regional": "food",
    "beauty_industry_association": "beauty",
    "ecommerce_education": "commerce",
    "accounting_mpe": "services",
    "business_financial_management": "services",
    "financial_services_mpe": "services",
    "merchant_payments_mpe": "services",
    # V9/V10: broad sampling categories; cross-sector remains other.
    "digital_marketing_education": "services",
    "beauty_entrepreneurship_education": "beauty",
    "foodservice_platform_education": "food",
    "fashion_microenterprise_inclusion": "commerce",
    "ecommerce_logistics": "commerce",
    "artisan_market_access": "commerce",
    "pet_retail_education": "commerce",
    "retail_digital_training": "commerce",
    # V11/V12: broad documentary strata, not post labels.
    "travel_agency_business_education": "services",
    "franchise_business_education": "other",
    "food_safety_consulting": "food",
    "fashion_sector_entrepreneurship": "commerce",
    "erp_consulting": "services",
    "natural_cosmetics_microbusiness_training": "beauty",
    "entrepreneurship_growth": "other",
    "circular_fashion_enterprise_inclusion": "commerce",
}


def sampling_sector(stratum: str) -> str:
    """Operator sampling label, not a determination of legal business size."""
    return SECTORS.get(stratum, "other")
