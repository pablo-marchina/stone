"""Baselines sintéticos de contrato, NÃO ranking validado com corpus autorizado.

Pontos abertos: tie-break e tratamento de coletas sem seguidores são decisões
operacionais candidatas, não escolhas homologadas da Stone.
"""
from decimal import Decimal
from dataclasses import dataclass
from math import ceil

@dataclass(frozen=True)
class Metric:
    post_id: str
    likes: int
    comments: int
    followers_at_collection: int

def engagement(metric: Metric) -> Decimal:
    if metric.likes < 0 or metric.comments < 0:
        raise ValueError('Métricas negativas inválidas')
    if metric.followers_at_collection <= 0:
        raise ValueError('Seguidores devem ser positivos; ausência não pode ser tratada como zero')
    return (Decimal(metric.likes) + Decimal(metric.comments)) / Decimal(metric.followers_at_collection)

def top_decile_candidate(rows: list[Metric]) -> list[tuple[str, Decimal]]:
    """Proposta: ceil(10%) com desempate por post_id; depende de aprovação."""
    if len({x.post_id for x in rows}) != len(rows):
        raise ValueError('IDs duplicados')
    ranked = sorted(((x.post_id, engagement(x)) for x in rows),key=lambda x: (-x[1],x[0]))
    return ranked[:ceil(len(ranked)/10)]
