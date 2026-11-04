"""DEC-017 E1: opt-in, text-only structured decision laboratory.

No web clients, uploads, video decoding, training or corpus mutation.
A decision is a candidate annotation, NOT a human scientific review.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Literal, Protocol
import os
import re

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, model_validator

from .classification import TOPICS, CTA
from .domain import (Id, RubricFields, RubricAssessmentCreate, FieldEvidence,
                     EvidenceStatus, EvidenceModality, RUBRIC_FIELD_NAMES)


E1_FIELDS = (
    "tema_principal", "tom", "tipo_hook", "tem_cta", "tipo_cta",
    "oferta_ou_beneficio_explicito", "mpe_targeted",
)
E1_LABELS = {
    "tema_principal": ("vendas", "finanças", "marketing", "atendimento", "gestão",
                       "motivação", "ferramentas/maquininha", "história de empreendedor"),
    "tom": ("informal", "técnico", "inspiracional", "humorístico"),
    "tipo_hook": ("pergunta", "promessa", "dor", "número", "polêmica", "curiosidade"),
    "tem_cta": (True, False),
    "tipo_cta": ("comentar", "salvar", "link na bio", "DM", "seguir"),
    "oferta_ou_beneficio_explicito": (True, False),
    "mpe_targeted": (True, False),
}
E1_SCHEMA_VERSION = "tapi-system-one-e1.v1"


class ObservedText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modality: Literal["caption", "transcript"]
    text: str = Field(min_length=1, max_length=10000)
    locator: str = Field(min_length=3, max_length=4096)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify_integrity(self):
        if not self.text.strip():
            raise ValueError("EMPTY_TEXT_EVIDENCE")
        if sha256(self.text.encode("utf-8")).hexdigest() != self.sha256:
            raise ValueError("TEXT_EVIDENCE_SHA256_MISMATCH")
        return self


class EvidenceBundle(BaseModel):
    """Caller-asserted local rights plus verified textual bytes.

    'approved_local' is a policy precondition, not proof that the grant is genuine.
    This experiment cannot automatically approve rights, posts or the corpus.
    """
    model_config = ConfigDict(extra="forbid")
    tenant_id: Id
    content_id: Id
    creator_id: Id
    source_kind: Literal["synthetic", "approved_local"]
    rights_reference: str | None = Field(default=None, max_length=512)
    allowed_operations: list[Literal["offline_classification"]] = Field(default_factory=list)
    observation: ObservedText | None = None

    @model_validator(mode="after")
    def require_operator_rights(self):
        if self.source_kind == "approved_local":
            if not self.rights_reference or len(self.rights_reference.strip()) < 12:
                raise ValueError("LOCAL_CLASSIFICATION_RIGHTS_REFERENCE_REQUIRED")
            if "offline_classification" not in self.allowed_operations:
                raise ValueError("LOCAL_CLASSIFICATION_SCOPE_REQUIRED")
        if len(self.allowed_operations) != len(set(self.allowed_operations)):
            raise ValueError("DUPLICATE_ALLOWED_OPERATION")
        return self

    def fingerprint(self) -> str:
        item = self.observation
        evidence_hash = item.sha256 if item is not None else "none"
        return sha256((self.tenant_id + ":" + self.content_id + ":" +
                       evidence_hash + ":" + (item.modality if item else "none")).encode()).hexdigest()


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_id: Literal[
        "tema_principal", "tom", "tipo_hook", "tem_cta", "tipo_cta",
        "oferta_ou_beneficio_explicito", "mpe_targeted",
    ]
    value: StrictStr | StrictBool | None = None
    abstained: bool = True
    reason: str = Field(min_length=3, max_length=128)
    modality: Literal["caption", "transcript"] | None = None
    locator: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def safe_decision(self):
        if self.abstained:
            if self.value is not None or self.modality is not None or self.locator is not None or self.confidence is not None:
                raise ValueError("ABSTENTION_CANNOT_CLAIM_EVIDENCE_OR_VALUE")
        else:
            if self.value not in E1_LABELS[self.field_id] or self.modality is None or not self.locator:
                raise ValueError("DECISION_NEEDS_ALLOWED_VALUE_AND_OBSERVED_TEXT")
            if self.field_id in {"tem_cta", "oferta_ou_beneficio_explicito"} and self.value is False:
                raise ValueError("TEXT_ONLY_CANNOT_ASSERT_VIDEO_WIDE_ABSENCE")
            if self.field_id == "tipo_hook":
                raise ValueError("FIRST_SECONDS_NOT_OBSERVED_BY_E1")
        return self


class DecisionBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["tapi-system-one-e1.v1"] = E1_SCHEMA_VERSION
    evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_id: str = Field(min_length=3, max_length=120)
    model_version: str = Field(min_length=3, max_length=120)
    decisions: list[Decision] = Field(min_length=1, max_length=7)
    duration_ms: float = Field(ge=0)
    is_scientific_review: Literal[False] = False

    @model_validator(mode="after")
    def unique_fields(self):
        keys = [d.field_id for d in self.decisions]
        if len(keys) != len(set(keys)):
            raise ValueError("DUPLICATE_DECISION_FIELD")
        return self


def _abstain(field: str, reason: str) -> Decision:
    return Decision(field_id=field, reason=reason)


def _observed(field: str, value: str | bool, item: ObservedText) -> Decision:
    return Decision(field_id=field, value=value, abstained=False,
                    reason="textual_candidate_for_human_review", modality=item.modality,
                    locator=item.locator)


class DecisionModel(Protocol):
    model_id: str
    model_version: str

    def evaluate(self, evidence: EvidenceBundle,
                 fields: tuple[str, ...] = E1_FIELDS) -> DecisionBundle: ...


def _select_fields(fields: tuple[str, ...]) -> tuple[str, ...]:
    if not fields or len(fields) != len(set(fields)) or any(f not in E1_FIELDS for f in fields):
        raise ValueError("INVALID_E1_FIELDS")
    return fields


def _finish(evidence: EvidenceBundle, model_id: str, version: str,
            answers: list[Decision], started: float) -> DecisionBundle:
    return DecisionBundle(evidence_fingerprint=evidence.fingerprint(),
                          model_id=model_id, model_version=version,
                          decisions=answers, duration_ms=(perf_counter()-started)*1000)


class DeterministicTextDecider:
    """Comparable conservative subset of the existing TOPICS/CTA regex baseline."""
    model_id = "tapi-deterministic-caption-baseline"
    model_version = "deterministic-text-e1-v1"

    def evaluate(self, evidence: EvidenceBundle,
                 fields: tuple[str, ...] = E1_FIELDS) -> DecisionBundle:
        started = perf_counter()
        fields = _select_fields(fields)
        item = evidence.observation
        if item is None:
            return _finish(evidence, self.model_id, self.model_version,
                           [_abstain(f, "no_observed_text") for f in fields], started)
        lower = item.text.casefold()
        topics = [name for name, patterns in TOPICS.items()
                  if any(re.search(pattern, lower) for pattern in patterns)]
        ctas = [name for name, pattern in CTA.items() if re.search(pattern, lower)]
        outputs = []
        for field in fields:
            if field == "tema_principal" and len(topics) == 1:
                outputs.append(_observed(field, topics[0], item))
            elif field == "tem_cta" and len(ctas) >= 1:
                outputs.append(_observed(field, True, item))
            elif field == "tipo_cta" and len(ctas) == 1:
                outputs.append(_observed(field, ctas[0], item))
            else:
                outputs.append(_abstain(field, "insufficient_textual_evidence"))
        return _finish(evidence, self.model_id, self.model_version, outputs, started)


class LocalGLiNERDecider:
    """GLiNER2.5-multi-Decide, only with preinstalled OFFLINE local weights.

    Loading from a Hugging Face repo ID or an URL is never accepted; the
    environment is forced into offline mode before optional import/loading.
    The injectable classifier is exclusively for unit tests and is never an
    extension hook exposed through HTTP or arbitrary Python evaluation.
    """
    model_id = "gliner2.5-multi-decide-local"
    model_version = "gliner2.5-multi-decide-e1-v1"

    def __init__(self, model_dir: str | Path, *, _test_model=None):
        self.model_dir = Path(model_dir).resolve()
        if not self.model_dir.is_dir():
            raise ValueError("LOCAL_SYSTEM_ONE_WEIGHTS_DIRECTORY_REQUIRED")
        self._model = _test_model

    def _load(self):
        if self._model is not None:
            return self._model
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        try:
            from gliner2 import AutoExtractor
        except ImportError as exc:
            raise RuntimeError("INSTALL_OPTIONAL_GLINER2_LOCAL_EXTRA") from exc
        self._model = AutoExtractor.from_pretrained(str(self.model_dir))
        return self._model

    def evaluate(self, evidence: EvidenceBundle,
                 fields: tuple[str, ...] = E1_FIELDS) -> DecisionBundle:
        started = perf_counter()
        fields = _select_fields(fields)
        if os.getenv("TAPI_SYSTEM_ONE_ENABLED", "0") != "1":
            raise PermissionError("SYSTEM_ONE_EXPERIMENT_DISABLED")
        item = evidence.observation
        if item is None:
            return _finish(evidence, self.model_id, self.model_version,
                           [_abstain(f, "no_observed_text") for f in fields], started)
        remote_fields = tuple(f for f in fields if f != "tipo_hook")
        heads = {}
        for field in remote_fields:
            if field in {"tem_cta", "oferta_ou_beneficio_explicito", "mpe_targeted"}:
                heads[field] = ["sim", "nao", "indefinido"]
            else:
                heads[field] = [*E1_LABELS[field], "indefinido"]
        raw = self._load().classify_text(item.text, heads) if heads else {}
        if not isinstance(raw, dict):
            raise ValueError("INVALID_LOCAL_CLASSIFIER_OUTPUT")
        outputs: list[Decision] = []
        for field in fields:
            if field == "tipo_hook":
                outputs.append(_abstain(field, "first_three_seconds_not_observed"))
                continue
            label = raw.get(field)
            if isinstance(label, bool):
                label = "sim" if label else "nao"
            if not isinstance(label, str) or label not in heads[field] or label == "indefinido":
                outputs.append(_abstain(field, "model_unknown_or_out_of_schema"))
                continue
            if field in {"tem_cta", "oferta_ou_beneficio_explicito", "mpe_targeted"}:
                value = label == "sim"
                if value is False and field != "mpe_targeted":
                    outputs.append(_abstain(field, "text_cannot_prove_absence_in_video"))
                    continue
            else:
                value = label
            if field == "tipo_cta" and raw.get("tem_cta") not in ("sim", True):
                outputs.append(_abstain(field, "cta_presence_not_corroborated"))
                continue
            outputs.append(_observed(field, value, item))
        return _finish(evidence, self.model_id, self.model_version, outputs, started)


def to_rubric_assessment(evidence: EvidenceBundle,
                         decisions: DecisionBundle) -> RubricAssessmentCreate:
    """E1 candidate rubric only; never writes scientific reviews or DB records."""
    if decisions.evidence_fingerprint != evidence.fingerprint():
        raise ValueError("DECISIONS_EVIDENCE_MISMATCH")
    for d in decisions.decisions:
        if not d.abstained and (
            evidence.observation is None
            or d.modality != evidence.observation.modality
            or d.locator != evidence.observation.locator
        ):
            raise ValueError("DECISION_LOCATOR_NOT_IN_EVIDENCE_BUNDLE")
    vals = {}
    proof = {}
    for d in decisions.decisions:
        if d.abstained or d.field_id == "mpe_targeted":
            continue
        vals[d.field_id] = d.value
        proof[d.field_id] = FieldEvidence(
            status=EvidenceStatus.OBSERVED,
            modality=EvidenceModality(d.modality), locator=d.locator,
            note="Experimental E1 textual candidate; independent human review required")
    if vals.get("tipo_cta") is not None and vals.get("tem_cta") is not True:
        vals.pop("tipo_cta", None)
        proof.pop("tipo_cta", None)
    for name in RUBRIC_FIELD_NAMES:
        if name not in proof:
            proof[name] = FieldEvidence(status=EvidenceStatus.NOT_OBSERVABLE,
                                        note="not assessed/observable in E1 text-only")
    ident = sha256((decisions.evidence_fingerprint+":"+decisions.model_version).encode()).hexdigest()[:24]
    return RubricAssessmentCreate(
        assessment_id="e1." + ident, tenant_id=evidence.tenant_id,
        content_id=evidence.content_id, rubric_version="rubric-v1",
        values=RubricFields(**vals), field_evidence=proof,
        assessor_kind="model", assessor_ref=decisions.model_id,
        model_version=decisions.model_version)
