"""Contextual model candidate comparison; no admission or human review."""
from __future__ import annotations

from collections import Counter

POLICY = "bd-contextual-audience-candidate.v1"
CANDIDATES = ("MODEL_POSITIVE_CANDIDATE", "MODEL_NEGATIVE_CANDIDATE", "MODEL_ABSTAIN")


def compare_candidate(evidence, answer, lexical):
    """Verify model/evidence linkage. Model negative is not post-wide exclusion."""
    if (evidence.observation is None or lexical["caption_sha256"] != evidence.observation.sha256
            or answer.evidence_fingerprint != evidence.fingerprint() or answer.is_scientific_review is not False):
        raise ValueError("BD_CONTEXTUAL_EVIDENCE_MISMATCH")
    if len(answer.decisions) != 1 or answer.decisions[0].field_id != "mpe_targeted":
        raise ValueError("BD_CONTEXTUAL_FIELD_MISMATCH")
    decision = answer.decisions[0]
    if decision.abstained:
        status = CANDIDATES[2]
    else:
        if (evidence.observation is None or decision.modality != "caption" or
                decision.locator != evidence.observation.locator or type(decision.value) is not bool):
            raise ValueError("BD_CONTEXTUAL_DECISION_MISMATCH")
        status = CANDIDATES[0] if decision.value else CANDIDATES[1]
    return {"status": status, "lexical_status": lexical["signal_status"],
            "caption_sha256": lexical["caption_sha256"],
            "evidence_fingerprint": answer.evidence_fingerprint,
            "model_id": answer.model_id, "model_version": answer.model_version,
            "duration_ms": answer.duration_ms, "human_review": False,
            "scientific_admission": False, "targeting_decision": "not_assessed"}


def paired_counts(results):
    counts = Counter((r["lexical_status"], r["status"]) for r in results)
    lexical = ("EXPLICIT_AUDIENCE_SIGNAL", "MENTION_ONLY_UNCERTAIN", "NO_EXPLICIT_SIGNAL_ABSTAIN")
    if any(a not in lexical or b not in CANDIDATES for a,b in counts):
        raise ValueError("BD_CONTEXTUAL_UNKNOWN_STATUS")
    return {a: {b: counts[a,b] for b in CANDIDATES} for a in lexical}


def require_caption_classification():
    """Institutional DEC-018 does not supersede actual operation-specific policy."""
    from .policy import decide, Operation
    decision = decide("instagram_metadata", Operation.CLASSIFY.value)
    if not decision.permitted:
        from .connectors import ConnectorError
        raise ConnectorError("BD_CONTEXTUAL_CLASSIFICATION_SCOPE_BLOCKED", 403)
    return decision.code
