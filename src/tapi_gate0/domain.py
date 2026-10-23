"""Canonical TAPI Stone domain contracts.

These are executable DTOs, not a claim that external integrations are authorized.
Unknown rubric categories remain open where the institutional reference is ambiguous.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


Id = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]
NonBlank = Annotated[str, Field(min_length=1, max_length=2000)]


class Origin(str, Enum):
    SYNTHETIC = "synthetic_local"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    STONE = "stone_internal"


class MediaType(str, Enum):
    REELS = "reels"
    CAROUSEL = "carrossel"
    IMAGE = "imagem"
    SHORTS = "short"


class EvidenceModality(str, Enum):
    METADATA = "metadata"
    CAPTION = "caption"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TRANSCRIPT = "transcript"
    EXTERNAL_PROOF = "external_proof"
    HUMAN = "human_review"


class EvidenceStatus(str, Enum):
    OBSERVED = "observed"
    NOT_OBSERVABLE = "not_observable"
    NOT_APPLICABLE = "not_applicable"


def require_utc_date(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return value


class Tenant(DomainModel):
    tenant_id: Id
    display_name: NonBlank
    created_at: datetime


class UserPrincipal(DomainModel):
    actor_id: Id
    tenant_id: Id
    role: Literal["admin", "researcher", "annotator", "editor", "viewer", "service"]
    local_only: bool = False


class Connection(DomainModel):
    connection_id: Id
    tenant_id: Id
    origin: Origin
    authorization_status: Literal["pending", "denied", "verified"] = "pending"
    approval_reference: str | None = None

    @model_validator(mode="after")
    def no_unsupported_verification(self):
        if self.authorization_status == "verified" and not self.approval_reference:
            raise ValueError("verified connection requires approval reference")
        return self


class CreatorCreate(DomainModel):
    creator_id: Id
    tenant_id: Id
    origin: Origin
    handle: NonBlank
    audience_segment: str | None = None
    source_profile_id: str | None = None


class Creator(CreatorCreate):
    created_at: datetime


class ContentCreate(DomainModel):
    content_id: Id
    tenant_id: Id
    creator_id: Id
    origin: Origin
    media_type: MediaType
    published_at: datetime
    source_url: HttpUrl | None = None
    caption: str | None = Field(default=None, max_length=10000)
    is_synthetic: bool = False

    @model_validator(mode="after")
    def valid_origin(self):
        require_utc_date(self.published_at)
        if self.is_synthetic != (self.origin == Origin.SYNTHETIC):
            raise ValueError("is_synthetic must match origin=synthetic_local")
        if self.origin != Origin.SYNTHETIC and self.source_url is None:
            raise ValueError("external content requires traceable source_url")
        return self


class ContentItem(ContentCreate):
    created_at: datetime


class MetricsCreate(DomainModel):
    snapshot_id: Id
    tenant_id: Id
    content_id: Id
    observed_at: datetime
    followers_measured_at: datetime
    likes: int = Field(ge=0)
    comments: int = Field(ge=0)
    follower_count: int = Field(ge=0)
    views: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def timestamps(self):
        require_utc_date(self.observed_at)
        require_utc_date(self.followers_measured_at)
        return self


class FieldEvidence(DomainModel):
    status: EvidenceStatus
    modality: EvidenceModality | None = None
    locator: str | None = Field(default=None, max_length=4096)
    timestamp_s: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=1500)

    @model_validator(mode="after")
    def proof_when_observed(self):
        if self.status == EvidenceStatus.OBSERVED:
            if self.modality is None or not self.locator or not self.locator.strip():
                raise ValueError("observed field requires modality and evidence locator")
        else:
            if self.modality is not None or self.locator is not None or self.timestamp_s is not None:
                raise ValueError("unobservable/not-applicable field cannot claim evidence")
        return self


RUBRIC_FIELD_NAMES = (
    "tipo_post", "duracao_faixa", "formato_video", "hook_primeiros_3s", "tipo_hook",
    "forca_hook_0a10", "tema_principal", "tem_rosto", "criador_e_empreendedor_real",
    "prova_social", "texto_na_tela", "legenda_tamanho", "ritmo_cortes_0a10",
    "tom", "usa_linguagem_regional", "clareza_mensagem_0a10", "tem_cta",
    "tipo_cta", "oferta_ou_beneficio_explicito", "elementos_top5",
)
TEMPORAL_FIELDS = frozenset({"hook_primeiros_3s", "ritmo_cortes_0a10"})


class RubricFields(DomainModel):
    tipo_post: Literal["reels", "carrossel", "imagem", "short"] | None = None
    duracao_faixa: str | None = None  # operational categories pending approval
    formato_video: Literal["talking head", "tutorial", "bastidores", "antes/depois", "humor/esquete", "depoimento", "lista/dicas", "trend"] | None = None
    hook_primeiros_3s: str | None = None
    tipo_hook: Literal["pergunta", "promessa", "dor", "número", "polêmica", "curiosidade"] | None = None
    forca_hook_0a10: float | None = Field(default=None, ge=0, le=10)
    tema_principal: Literal["vendas", "finanças", "marketing", "atendimento", "gestão", "motivação", "ferramentas/maquininha", "história de empreendedor"] | None = None
    tem_rosto: bool | None = None
    criador_e_empreendedor_real: bool | None = None
    prova_social: bool | None = None
    texto_na_tela: bool | None = None
    legenda_tamanho: str | None = None  # operational cutoffs pending approval
    ritmo_cortes_0a10: float | None = Field(default=None, ge=0, le=10)
    tom: Literal["informal", "técnico", "inspiracional", "humorístico"] | None = None
    usa_linguagem_regional: bool | None = None
    clareza_mensagem_0a10: float | None = Field(default=None, ge=0, le=10)
    tem_cta: bool | None = None
    tipo_cta: Literal["comentar", "salvar", "link na bio", "DM", "seguir"] | None = None
    oferta_ou_beneficio_explicito: bool | None = None
    elementos_top5: list[NonBlank] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def relational_checks(self):
        if set(type(self).model_fields) != set(RUBRIC_FIELD_NAMES):
            raise ValueError("rubric does not match institutional 20 fields")
        if self.tem_cta is False and self.tipo_cta is not None:
            raise ValueError("tipo_cta is incompatible with tem_cta=false")
        return self


class RubricAssessmentCreate(DomainModel):
    assessment_id: Id
    tenant_id: Id
    content_id: Id
    rubric_version: NonBlank
    values: RubricFields
    field_evidence: dict[str, FieldEvidence] = Field(default_factory=dict)
    assessor_kind: Literal["human", "model"]
    assessor_ref: Id
    model_version: str | None = None
    prompt_version: str | None = None

    @model_validator(mode="after")
    def evidence_is_required_for_every_assertion(self):
        fields = self.values.model_dump()
        if set(self.field_evidence) - set(RUBRIC_FIELD_NAMES):
            raise ValueError("unknown rubric field_evidence key")
        for key, value in fields.items():
            asserted = value is not None and value != []
            ev = self.field_evidence.get(key)
            if asserted and (ev is None or ev.status != EvidenceStatus.OBSERVED):
                raise ValueError(f"{key} requires observed field evidence")
            if not asserted and ev is not None and ev.status == EvidenceStatus.OBSERVED:
                raise ValueError(f"{key} cannot claim observation without value")
            if not asserted:
                continue
            if key in TEMPORAL_FIELDS and (ev.modality != EvidenceModality.VIDEO or ev.timestamp_s is None):
                raise ValueError(f"{key} requires video evidence with timestamp")
            if key == "criador_e_empreendedor_real" and ev.modality != EvidenceModality.EXTERNAL_PROOF:
                raise ValueError("creator entrepreneurship requires external proof")
            if key == "tem_rosto" and ev.modality not in {EvidenceModality.IMAGE, EvidenceModality.VIDEO, EvidenceModality.HUMAN}:
                raise ValueError("face detection requires visual evidence or reviewed visual")
        if self.assessor_kind == "model" and not self.model_version:
            raise ValueError("model assessment needs model_version")
        return self


class RubricAssessment(RubricAssessmentCreate):
    recorded_at: datetime


class RankingRequest(DomainModel):
    tenant_id: Id
    origin: Origin = Origin.SYNTHETIC
    min_age_days: int = Field(default=14, ge=0, le=36500)
    as_of: datetime

    @model_validator(mode="after")
    def validate_time(self):
        require_utc_date(self.as_of)
        return self


class RankingRow(DomainModel):
    content_id: Id
    creator_id: Id
    likes: int
    comments: int
    followers: int
    engagement_rate: Decimal
    snapshot_id: Id
    is_top_decile: bool


class RankingResult(DomainModel):
    origin: Origin
    n_posts: int
    n_creators: int
    top_count: int
    metric_formula: Literal["(likes+comments)/followers"] = "(likes+comments)/followers"
    rows: list[RankingRow]
    excluded_no_positive_denominator: int
    excluded_too_recent: int
    excluded_without_metrics: int


class InsightCreate(DomainModel):
    insight_id: Id
    tenant_id: Id
    title: NonBlank
    claim: NonBlank
    source_content_ids: list[Id] = Field(min_length=1)
    analysis_kind: Literal["descriptive", "association", "causal_experiment"] = "descriptive"
    dataset_version: NonBlank
    limitations: list[str] = Field(default_factory=list)


class Insight(InsightCreate):
    created_at: datetime


class CreativeCreate(DomainModel):
    creative_id: Id
    tenant_id: Id
    based_on_insight_id: Id
    objective: NonBlank
    hook: NonBlank
    script: NonBlank
    caption: NonBlank
    cta: NonBlank
    reference_content_ids: list[Id] = Field(min_length=1)
    status: Literal["draft", "in_review", "approved"] = "draft"


class CreativeVersion(CreativeCreate):
    created_at: datetime


class Publication(DomainModel):
    publication_id: Id
    tenant_id: Id
    creative_id: Id
    channel: str
    status: Literal["not_authorized", "pending_approval", "published"] = "not_authorized"
    approval_ref: str | None = None


class Campaign(DomainModel):
    campaign_id: Id
    tenant_id: Id
    creative_id: Id
    max_spend_brl: Decimal = Field(default=Decimal(0), ge=0)
    status: Literal["not_authorized", "pending_approval", "active"] = "not_authorized"

    @model_validator(mode="after")
    def enforce_project_budget(self):
        if self.max_spend_brl != 0 or self.status == "active":
            raise ValueError("project budget is zero; paid campaign cannot activate")
        return self


class ConversionEvent(DomainModel):
    conversion_id: Id
    tenant_id: Id
    publication_id: Id
    event_type: str
    attribution_method: str | None = None
    rights_reference: str | None = None


class ResearchExperiment(DomainModel):
    experiment_id: Id
    tenant_id: Id
    hypothesis: NonBlank
    baseline_id: Id
    dataset_version: NonBlank
    sealed_test_ref: str | None = None
    primary_metric: NonBlank
    decision_status: Literal["registered", "running", "inconclusive", "approved", "rejected"] = "registered"


class EvaluationResult(DomainModel):
    eval_id: Id
    tenant_id: Id
    experiment_id: Id
    dataset_version: NonBlank
    metric_name: NonBlank
    measured_value: float | None = None
    sample_size: int = Field(ge=0)
    status: Literal["not_evaluated", "measured", "insufficient_support"] = "not_evaluated"


class AgentRun(DomainModel):
    run_id: Id
    tenant_id: Id
    mode: Literal["analisar", "recomendar", "gerar_criativo"]
    query: NonBlank
    status: Literal["not_started", "running", "completed", "failed", "blocked"] = "not_started"
    evidence_content_ids: list[Id] = Field(default_factory=list)


class DomainEvent(DomainModel):
    event_id: str
    tenant_id: Id
    aggregate_type: NonBlank
    aggregate_id: Id
    event_type: NonBlank
    aggregate_version: int = Field(ge=1)
    occurred_at: datetime
    payload: dict = Field(default_factory=dict)


class ProblemDetail(DomainModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    code: str


class LocalOperationRequest(DomainModel):
    source: str
    operation: str


class AccessDecisionResponse(DomainModel):
    permitted: bool
    code: str
    reason: str


DOMAIN_ENTITIES = (
    "tenant", "principal", "connection", "creator", "content_item", "metrics_snapshot",
    "rubric_assessment", "insight", "creative_version", "publication", "campaign",
    "conversion_event", "research_experiment", "evaluation_result", "agent_run", "domain_event",
)

# Additional canonical entities from the unified architecture, still disabled
# until their corresponding capabilities have rights and evaluation evidence.
class SourceUseGrant(DomainModel):
    grant_id: Id
    tenant_id: Id
    origin: Origin
    permitted_operations: list[NonBlank]
    status: Literal["pending","denied","verified"] = "pending"
    approval_reference: str | None = None
    @model_validator(mode="after")
    def verified_has_evidence(self):
        if self.status=="verified" and not self.approval_reference:
            raise ValueError("source use requires verified approval")
        return self

class MediaAsset(DomainModel):
    asset_id: Id
    tenant_id: Id
    content_id: Id
    media_kind: Literal["video","audio","image","text"]
    storage_ref: NonBlank
    use_rights_status: Literal["verified","pending","denied"]="pending"
    rights_reference: str | None = None
    @model_validator(mode="after")
    def require_rights(self):
        if self.use_rights_status!="verified" or not self.rights_reference:
            raise ValueError("unverified media must not be stored or processed")
        return self

class ContrastAnalysis(DomainModel):
    analysis_id: Id
    tenant_id: Id
    dataset_version: NonBlank
    winning_group_size: int=Field(ge=0)
    control_group_size: int=Field(ge=0)
    labeled_winners: int=Field(ge=0)
    labeled_controls: int=Field(ge=0)
    interpretation: Literal["descriptive","associative","causal"]="descriptive"
    effect_estimate: float | None=None
    @model_validator(mode="after")
    def contrast_valid(self):
        if self.labeled_winners>self.winning_group_size or self.labeled_controls>self.control_group_size:
            raise ValueError("labeled counts exceed cohort size")
        if self.effect_estimate is not None and (not self.labeled_winners or not self.labeled_controls):
            raise ValueError("comparison requires labels for both cohorts")
        if self.interpretation=="causal":raise ValueError("causal analysis requires separate experiment")
        return self

class ResourceUsage(DomainModel):
    usage_id: Id
    tenant_id: Id
    component: NonBlank
    cpu_seconds: float=Field(ge=0)
    storage_bytes: int=Field(ge=0)
    billed_cost_brl: Decimal=Field(default=Decimal("0"),ge=0)
    @model_validator(mode="after")
    def budget(self):
        if self.billed_cost_brl!=0:raise ValueError("zero spend budget")
        return self

class AgentToolCall(DomainModel):
    call_id: Id
    tenant_id: Id
    run_id: Id
    tool_name: NonBlank
    cost_brl: Decimal=Field(default=Decimal("0"),ge=0)
    @model_validator(mode="after")
    def zero_spend(self):
        if self.cost_brl!=0:raise ValueError("paid tool call disabled")
        return self

class QualityEvidence(DomainModel):
    evidence_id: Id
    tenant_id: Id
    requirement_id: Id
    iso_25010_characteristic: NonBlank
    test_id: Id
    evaluation_status: Literal["not_evaluated","failed","passed"]="not_evaluated"
    execution_reference: str | None=None
    @model_validator(mode="after")
    def no_unsubstantiated_pass(self):
        if self.evaluation_status=="passed" and not self.execution_reference:
            raise ValueError("pass requires execution evidence")
        return self

class DatasetManifest(DomainModel):
    dataset_id: Id
    tenant_id: Id
    source_grant_ids: list[Id]=Field(default_factory=list)
    dataset_version: NonBlank
    evaluated_status: Literal["not_evaluated","evaluated"]="not_evaluated"
    evidence_refs: list[NonBlank]=Field(default_factory=list)

class ReleaseManifest(DomainModel):
    release_id: Id
    tenant_id: Id
    build_digest: NonBlank
    approved_feature_ids: list[Id]
    quality_evidence_ids: list[Id]
    production_ready: bool=False
    @model_validator(mode="after")
    def requires_release_evidence(self):
        if self.production_ready and (not self.approved_feature_ids or not self.quality_evidence_ids):
            raise ValueError("release without verifiable evidence")
        return self

DOMAIN_ENTITIES=(*DOMAIN_ENTITIES,
    "source_use_grant","media_asset","contrast_analysis","resource_usage", "agent_tool_call",
    "quality_evidence","dataset_manifest","release_manifest", "identity_user", "identity_membership",
    "identity_session","event_outbox", "creator_comparison", "editorial_plan", "evaluation_dataset",
    "adaptive_policy", "content_rights")