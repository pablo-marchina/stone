"""A01.4: read existing ingestion assessments, never run a classifier.

Only the historical text/metadata baseline is exposed. Stored assertions
are provisional, not independently verified, and cannot authorize media.
"""
from datetime import datetime
from hashlib import sha256

from pydantic import ValidationError
from sqlalchemy import select

from .connectors import ConnectorError
from .domain import EvidenceModality, EvidenceStatus, RUBRIC_FIELD_NAMES, RubricAssessment
from .sa_store import rubric_assessments

VERSION = "external-stored-rubric-read.v1"
MAX_ASSESSMENTS = 100
_ALLOWED = {
    "tipo_post": EvidenceModality.METADATA,
    "tema_principal": EvidenceModality.CAPTION,
    "tem_cta": EvidenceModality.CAPTION,
    "tipo_cta": EvidenceModality.CAPTION,
}


def read_stored_rubric(db, tenant, post, now):
    rows = db.execute(select(rubric_assessments.c.id, rubric_assessments.c.recorded_at,
        rubric_assessments.c.payload).where(
        rubric_assessments.c.tenant_id == tenant,
        rubric_assessments.c.content_id == post.content_id).limit(MAX_ASSESSMENTS + 1)).all()
    if len(rows) > MAX_ASSESSMENTS:
        raise ConnectorError("INVENTORY_ASSESSMENT_LIMIT_EXCEEDED", 409)
    expected_id = "rub." + sha256(
        (tenant + ":" + post.content_id + ":" + (post.caption or "")).encode()
    ).hexdigest()[:18]
    matches = []
    for aid, recorded, raw in rows:
        try:
            a = RubricAssessment.model_validate_json(raw)
            if (a.tenant_id != tenant or a.content_id != post.content_id
                    or a.assessment_id != aid or aid != expected_id
                    or a.recorded_at != datetime.fromisoformat(recorded)
                    or not post.created_at <= a.recorded_at <= now
                    or a.assessor_kind != "model"
                    or a.assessor_ref != "caption-metadata-baseline"
                    or a.model_version != "deterministic-text-metadata-v1"
                    or a.rubric_version != "rubric-v1"):
                continue
            matches.append(a)
        except (ValidationError, TypeError, ValueError):
            continue
    assessment = matches[0] if len(matches) == 1 else None
    fields = {}
    for key in RUBRIC_FIELD_NAMES:
        cell = {"state": "not_assessed", "value": None, "modality": None,
                "reason": "NO_MATCHING_STORED_BASELINE", "canonical": False,
                "locator_kind": None}
        if assessment:
            ev = assessment.field_evidence.get(key)
            value = getattr(assessment.values, key)
            cell["reason"] = "NO_STORED_FIELD_EVIDENCE"
            if ev and ev.status == EvidenceStatus.NOT_OBSERVABLE:
                cell.update(state="abstained", reason="BASELINE_NOT_OBSERVABLE")
            elif ev and ev.status == EvidenceStatus.NOT_APPLICABLE:
                cell["reason"] = "BASELINE_NOT_APPLICABLE"
            elif ev and ev.status == EvidenceStatus.OBSERVED:
                modality = _ALLOWED.get(key)
                fragment = "media_type" if modality == EvidenceModality.METADATA else "caption"
                # No raw locators, arbitrary notes, text or audio/video payloads.
                valid = (modality is not None and ev.modality == modality
                         and ev.locator == str(post.source_url) + "#" + fragment
                         and ev.timestamp_s is None
                         and (value == post.media_type.value if key == "tipo_post"
                              else bool(post.caption and post.caption.strip())))
                if key == "tem_cta":
                    valid = valid and value is True and assessment.values.tipo_cta is not None
                if key == "tipo_cta":
                    valid = valid and assessment.values.tem_cta is True
                if valid:
                    cell.update(state="candidate", value=value, modality=modality.value,
                        reason="STORED_METADATA_MATCH" if key == "tipo_post" else "HISTORICAL_LEXICAL_CANDIDATE",
                        locator_kind=fragment)
                else:
                    cell["reason"] = "STORED_ASSERTION_WITHHELD"
        fields[key] = cell
    # Preserve the two CTA fields as a pair, even if one locator was invalid.
    if (fields["tem_cta"]["state"] == "candidate") != (fields["tipo_cta"]["state"] == "candidate"):
        for key in ("tem_cta", "tipo_cta"):
            fields[key] = {"state": "not_assessed", "value": None, "modality": None,
                "reason": "INCONSISTENT_CTA_PAIR", "canonical": False, "locator_kind": None}
    counts = {k: sum(c["state"] == k for c in fields.values())
              for k in ("candidate", "measurement_only", "abstained", "not_assessed")}
    return {"schema_version": VERSION, "scope": "historical_ingestion_baseline",
            "content_id": post.content_id, "assessment_records": len(rows),
            "matching_baseline_records": len(matches), "assessment_id": assessment.assessment_id if assessment else None,
            "recorded_at": assessment.recorded_at.isoformat() if assessment else None,
            "model_version": assessment.model_version if assessment else None,
            "rubric_version": assessment.rubric_version if assessment else None,
            "field_count": len(fields), "state_counts": counts, "fields": fields,
            "canonical": False, "semantic_revalidation_performed": False,
            "manifest_and_trace_reaudit_performed": False, "independent_gold": False,
            "caption_text_returned": False, "media_processing_allowed": False,
            "scientific_admission": False, "new_model_calls": 0}
