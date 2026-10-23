"""Evidence-aware, cost-free classification baseline: text + metadata only.

Provides an explicit multimodal evidence boundary. No visual/audio observations
are asserted without authorized frame, audio or verified human evidence.
"""
from __future__ import annotations

import re
from hashlib import sha256

from .connectors import NormalizedItem
from .domain import (RubricAssessmentCreate,RubricFields,RUBRIC_FIELD_NAMES,
                     FieldEvidence,EvidenceStatus,EvidenceModality)


TOPICS={
    "vendas":(r"\bvendas?\b",r"\bvender\b"),
    "finanças":(r"\bfinanceir[oa]s?\b",r"\bcaixa\b"),
    "marketing":(r"\bmarketing\b",r"\bdivulga"),
    "atendimento":(r"\batendimento\b",r"\bclientes?\b"),
    "gestão":(r"\bgest[aã]o\b",r"\bgestor"),
}
CTA={"comentar":r"\bcoment[ea]\b","salvar":r"\bsalv[ea]\b",
     "seguir":r"\bsiga\b|\bseguir\b","DM":r"\b(direct|dm)\b",
     "link na bio":r"\blink na bio\b"}


def classify_metadata_caption(item:NormalizedItem,tenant_id:str,content_id:str,
                              revision:str="rubric-v1", visual=None) -> RubricAssessmentCreate:
    """Deterministic partial classifier. Unknown ≠ false; abstain from 3-second hook, image, audio."""
    values={"tipo_post":item.media_type.value}
    ev={"tipo_post":FieldEvidence(status=EvidenceStatus.OBSERVED,
         modality=EvidenceModality.METADATA,locator=f"{item.source_url}#media_type")}
    cap=item.caption or ""
    low=cap.casefold()
    if cap:
        matches=[key for key,terms in TOPICS.items() if any(re.search(t,low) for t in terms)]
        if len(matches)==1:
            values["tema_principal"]=matches[0]
            ev["tema_principal"]=FieldEvidence(status=EvidenceStatus.OBSERVED,
                modality=EvidenceModality.CAPTION,locator=f"{item.source_url}#caption")
        ctas=[k for k,pattern in CTA.items() if re.search(pattern,low)]
        if len(ctas)==1:
            values["tem_cta"]=True; values["tipo_cta"]=ctas[0]
            for field in ("tem_cta","tipo_cta"):
                ev[field]=FieldEvidence(status=EvidenceStatus.OBSERVED,
                    modality=EvidenceModality.CAPTION,locator=f"{item.source_url}#caption")
    if visual is not None:
        # Local file only; visual signals are provisional pending independent review.
        if visual.face_detected and visual.face_locator:
            values["tem_rosto"]=True
            ev["tem_rosto"]=FieldEvidence(status=EvidenceStatus.OBSERVED,
                modality=EvidenceModality.VIDEO if visual.frames_examined>1 else EvidenceModality.IMAGE,
                locator=visual.face_locator,timestamp_s=visual.face_timestamp_s,
                note="Preliminary local OpenCV evidence; human review required")
        if visual.text_detected and visual.text_locator:
            values["texto_na_tela"]=True
            ev["texto_na_tela"]=FieldEvidence(status=EvidenceStatus.OBSERVED,
                modality=EvidenceModality.VIDEO if visual.frames_examined>1 else EvidenceModality.IMAGE,
                locator=visual.text_locator,timestamp_s=visual.text_timestamp_s,
                note="Preliminary local OCR evidence; human review required")
    for field in RUBRIC_FIELD_NAMES:
        if field not in ev:ev[field]=FieldEvidence(status=EvidenceStatus.NOT_OBSERVABLE,
                            note="requires additional authorized modality or reliable semantic evidence")
    fingerprint=sha256((tenant_id+":"+content_id+":"+(item.caption or "")).encode()).hexdigest()[:18]
    return RubricAssessmentCreate(assessment_id="rub."+fingerprint,tenant_id=tenant_id,
      content_id=content_id,rubric_version=revision,values=RubricFields(**values),
      field_evidence=ev,assessor_kind="model",assessor_ref="caption-metadata-baseline",
      model_version="deterministic-text-metadata-v1")
