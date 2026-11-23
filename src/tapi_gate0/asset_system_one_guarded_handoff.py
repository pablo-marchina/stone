"""A02.7 -> Stone-S1 guarded candidate handoff, without E1 authorization.

Only a *fresh*, rights-rechecked protected evaluation may enter the public
entrypoint. Output is typed label metadata, never text evidence, gold or grant.
No network, persistence, model calls, implicit authority or external media.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re

VERSION = "tapi-a027-s1-guarded-handoff.v1"
PROCESSORS = ("asr_vad", "ocr", "temporal", "vlm")
FIELDS = ("tema_principal", "tipo_cta", "tem_cta", "texto_na_tela")
_ARTIFACT = re.compile(r"artifact\.[0-9a-f]{64}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class GuardedHandoffDenied(ValueError):
    """Fixed denial codes: never reflect captions, media, paths or tokens."""


def _deny(code: str):
    raise GuardedHandoffDenied("A027_S1_HANDOFF_" + code)


def _digest(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _project_guarded(guard: dict) -> dict:
    """Private pure projection of an already trusted fusion result; no rights."""
    if type(guard) is not dict or guard.get("schema_version") != "shared-av-coverage-guard.v1":
        _deny("GUARD_REQUIRED")
    if any(guard.get(key) is not False for key in (
        "inference_reexecuted", "canonical_rubric", "scientific_evidence", "policy_promoted"
    )):
        _deny("AUTHORITY_INVALID")
    baseline, guarded = guard.get("baseline"), guard.get("guarded")
    fingerprint = guard.get("source_fingerprint")
    if (type(fingerprint) is not str or not _SHA.fullmatch(fingerprint)
            or baseline is None or guarded is None
            or getattr(baseline, "evidence_fingerprint", None) != fingerprint
            or getattr(guarded, "evidence_fingerprint", None) != fingerprint
            or getattr(guarded, "scientific_evidence", None) is not False
            or getattr(guarded, "canonical_rubric", None) is not False):
        _deny("FINGERPRINT_OR_AUTHORITY_MISMATCH")
    coverage = guard.get("coverage")
    details = guard.get("coverage_details")
    if (type(coverage) is not dict or set(coverage) != set(PROCESSORS)
            or type(details) is not dict or set(details) != set(PROCESSORS)):
        _deny("COMPLETE_COVERAGE_REQUIRED")
    for processor in PROCESSORS:
        state = coverage[processor]
        if (state not in ("observed", "abstained")
                or type(details[processor]) is not dict
                or details[processor].get("state") != state):
            _deny("COMPLETE_COVERAGE_REQUIRED")
    rejections = guard.get("quality_rejections")
    if type(rejections) is not dict or set(rejections) - {"asr_vad"}:
        _deny("QUALITY_REJECTION_INVALID")
    if rejections and (coverage["asr_vad"] != "abstained"
                       or details["asr_vad"].get("reason") != "fixture_quality_rejected"):
        _deny("QUALITY_REJECTION_INVALID")
    suppressed = guard.get("suppressed_fields")
    if (type(suppressed) not in (tuple, list) or len(set(suppressed)) != len(suppressed)
            or set(suppressed)-set(FIELDS)):
        _deny("SUPPRESSION_INVALID")
    fields = getattr(guarded, "fields", None)
    baseline_fields = getattr(baseline, "fields", None)
    if (not isinstance(fields, (tuple, list)) or len(fields) != 20
            or not isinstance(baseline_fields, (tuple, list)) or len(baseline_fields) != 20):
        _deny("FIELD_PARTITION_INVALID")
    by = {getattr(field, "field_id", None): field for field in fields}
    before = {getattr(field, "field_id", None): field for field in baseline_fields}
    if len(by) != 20 or len(before) != 20 or set(by) != set(before) or not set(FIELDS)<=set(by):
        _deny("FIELD_PARTITION_INVALID")
    for field_id, after in by.items():
        original = before[field_id]
        if field_id not in suppressed:
            if after != original:
                _deny("GUARD_DECISION_CHANGED")
        elif (getattr(original, "state", None) != "candidate"
              or getattr(after, "state", None) != "abstained"
              or getattr(after, "value", None) is not None
              or getattr(after, "supports", None) != getattr(original, "supports", None)
              or getattr(after, "vetoes", None) != getattr(original, "vetoes", None)):
            _deny("SUPPRESSION_INVALID")
    if getattr(baseline, "tenant_id", None) != getattr(guarded, "tenant_id", None) or any(
        getattr(baseline, attr, None) != getattr(guarded, attr, None)
        for attr in ("content_id", "object_id", "purpose")
    ):
        _deny("SOURCE_SCOPE_MISMATCH")
    output = []
    for key in FIELDS:
        field = by[key]
        state = getattr(field, "state", None)
        value = getattr(field, "value", None)
        if state not in ("candidate", "abstained") or (
            state == "candidate" and value is None
        ) or (state == "abstained" and value is not None):
            _deny("FIELD_VALUE_INVALID")
        if key in suppressed and state != "abstained":
            _deny("SUPPRESSION_INVALID")
        supports = getattr(field, "supports", ())
        vetoes = getattr(field, "vetoes", ())
        if type(supports) is not tuple or type(vetoes) is not tuple:
            _deny("SUPPORT_INVALID")

        def projection(s):
            # Digest only typed locator fields; not transcript/OCR words, raw
            # model output or source paths.
            return {name: getattr(s, name, None) for name in (
                "artifact_id", "payload_sha256", "processor", "segment_index",
                "start_ms", "end_ms", "frame_sha256", "timeline",
                "word_indices", "text_sha256"
            )}

        output.append({"field_id": key, "state": state, "value": value,
                       "suppressed_by_guard": key in suppressed,
                       "support_count": len(supports), "veto_count": len(vetoes),
                       "provenance_sha256": _digest({
                           "supports": [projection(s) for s in supports],
                           "vetoes": [projection(s) for s in vetoes]})})
    return {
        "schema_version": VERSION,
        "status": ("PARTIAL_GUARDED_CANDIDATES_ONLY" if rejections
                   else "GUARDED_CANDIDATES_ONLY"),
        "tenant_id": guarded.tenant_id, "content_id": guarded.content_id,
        "object_id": guarded.object_id, "purpose": guarded.purpose,
        "source_fingerprint": fingerprint,
        "coverage": {k: coverage[k] for k in PROCESSORS},
        "rejected_processors": tuple(sorted(rejections)),
        "candidate_fields": tuple(output),
        "system_one_e1_text_observations_created": 0,
        "scientific_admissions_created": 0,
        "rubric_assessments_written": 0,
        "database_mutated": False,
        "independent_gold_available": False,
        "rights_reusable_outside_scope": False,
        "studio_write_allowed": False,
        "publication_allowed": False,
        "production_approved": False,
        "global_gates_released": False,
    }


def bridge_guarded_av_to_system_one(store, tenant: str, object_id: str,
                                    artifact_ids, *, purpose="research_analysis") -> dict:
    """Derive a bounded proposal only after fresh protected rights checks.

    No caller-provided guard/decision is accepted as authorization.
    ASR derive rights != E1 offline classification rights; OCR/VLM cannot be
    disguised as caption/transcript evidence.
    """
    from .asset_candidate_fusion import CandidateDecisions, evaluate_shared_av_coverage_guard

    if (type(artifact_ids) not in (tuple, list) or len(artifact_ids) != 4
            or len(set(artifact_ids)) != 4
            or any(type(x) is not str or not _ARTIFACT.fullmatch(x) for x in artifact_ids)):
        _deny("FOUR_DISTINCT_ARTIFACTS_REQUIRED")
    guard = evaluate_shared_av_coverage_guard(
        store, tenant, object_id, artifact_ids, purpose=purpose)
    if (type(guard) is not dict or not isinstance(guard.get("guarded"), CandidateDecisions)
            or not isinstance(guard.get("baseline"), CandidateDecisions)):
        _deny("GUARD_RESULT_INVALID")
    if ((guard["guarded"].tenant_id, guard["guarded"].object_id,
         guard["guarded"].purpose) != (tenant, object_id, purpose)):
        _deny("SOURCE_SCOPE_MISMATCH")
    return _project_guarded(guard)
