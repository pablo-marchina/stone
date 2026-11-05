"""IMP-071/076: deterministic evidence-first agent core, no model/API calls.

First vertical slice: orchestrate the existing tenant-scoped ranking tool and
produce traceable, conservative analysis/recommendation. NOT a full LLM agent
or MCP server. Abstention is mandatory when the tool has no eligible evidence.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .domain import Id, Origin, RankingRequest, RankingResult


class RankingTool(Protocol):
    def ranking(self, request: RankingRequest) -> RankingResult: ...


class EvidenceCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content_id: Id
    creator_id: Id
    snapshot_id: Id
    engagement_rate: str = Field(pattern=r"^\d+(?:\.\d+)?$")
    metric: Literal["(likes+comments)/followers"] = "(likes+comments)/followers"


class AgentFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["descriptive_ranking", "data_gap"]
    statement: str = Field(min_length=12, max_length=900)
    citations: list[EvidenceCitation] = Field(default_factory=list, max_length=5)


class AgentRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["tapi-evidence-agent-e1.v1"] = "tapi-evidence-agent-e1.v1"
    tenant_id: Id
    origin: Origin
    as_of: datetime
    action: Literal["inspect_ranked_examples", "collect_more_evidence"]
    abstained_from_pattern_claim: bool
    n_eligible_posts: int = Field(ge=0)
    n_creators: int = Field(ge=0)
    findings: list[AgentFinding] = Field(min_length=1, max_length=2)
    limitations: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def enforce_references(self):
        if self.action == "inspect_ranked_examples" and not any(
            finding.citations for finding in self.findings
        ):
            raise ValueError("AGENT_RECOMMENDATION_NEEDS_EVIDENCE")
        if self.n_eligible_posts == 0 and any(
            finding.citations for finding in self.findings
        ):
            raise ValueError("AGENT_NO_EVIDENCE_CANNOT_CITE")
        return self


def analyze_with_ranking(
    tool: RankingTool, *, tenant_id: str, origin: Origin,
    as_of: datetime, min_age_days: int = 14,
) -> AgentRecommendation:
    """A bounded internal tool call: no user-supplied facts become citations."""
    request = RankingRequest(
        tenant_id=tenant_id, origin=origin,
        as_of=as_of, min_age_days=min_age_days,
    )
    result = tool.ranking(request)
    if result.origin != origin:
        raise ValueError("AGENT_TOOL_ORIGIN_MISMATCH")
    if (result.n_posts != len(result.rows)
            or result.n_creators != len({row.creator_id for row in result.rows})
            or result.top_count != sum(row.is_top_decile for row in result.rows)):
        raise ValueError("AGENT_TOOL_RANKING_INTEGRITY_FAILURE")
    if len({row.content_id for row in result.rows}) != len(result.rows):
        raise ValueError("AGENT_TOOL_DUPLICATE_CONTENT")
    if not result.rows:
        return AgentRecommendation(
            tenant_id=tenant_id, origin=origin, as_of=as_of,
            action="collect_more_evidence", abstained_from_pattern_claim=True,
            n_eligible_posts=0, n_creators=0,
            findings=[AgentFinding(
                kind="data_gap",
                statement="Nenhuma publicação elegível foi retornada; não há base observada para recomendar um padrão editorial.",
            )],
            limitations=[
                "Nenhuma inferência foi gerada sem fontes elegíveis.",
                "Disponibilidade e permissões de fontes dependem da integração de dados.",
            ],
        )
    top = [row for row in result.rows if row.is_top_decile]
    if not top:
        raise ValueError("AGENT_NONEMPTY_RANKING_NEEDS_TOP_DECILE")
    refs = [
        EvidenceCitation(
            content_id=row.content_id, creator_id=row.creator_id,
            snapshot_id=row.snapshot_id, engagement_rate=format(row.engagement_rate, "f"),
        ) for row in top[:5]
    ]
    # A single top publication is a candidate to inspect, not a validated
    # strategy. Avoid causal claims even when n and creator coverage grow.
    limited = result.n_posts < 10 or result.n_creators < 3
    item = refs[0]
    findings = [AgentFinding(
        kind="descriptive_ranking",
        statement=(
            f"No recorte consultado, o conteúdo {item.content_id} apresenta "
            f"ER observado de {item.engagement_rate}, calculado por (curtidas + comentários) / seguidores. "
            "Isso identifica um exemplo para inspeção editorial, não causa de desempenho."
        ),
        citations=refs,
    )]
    return AgentRecommendation(
        tenant_id=tenant_id, origin=origin, as_of=as_of,
        action="inspect_ranked_examples",
        abstained_from_pattern_claim=True,
        n_eligible_posts=result.n_posts, n_creators=result.n_creators,
        findings=findings,
        limitations=[
            "Ranking descritivo não comprova efeito causal ou estratégia replicável.",
            "Seguidores e interações podem ter tempos de medição diferentes.",
            "A elegibilidade por idade e a integridade de snapshots dependem do dataset consultado.",
            "Nenhuma revisão científica independente ou desempenho populacional foi alegado.",
            "O ranking técnico não comprova que cada publicação vise MPEs ou possua rubrica multimodal revisada.",
        ] + (["Amostra pequena ou baixa diversidade de criadores; não generalizar."]
             if limited else []),
    )
