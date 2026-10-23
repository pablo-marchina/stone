# ISO/IEC 25010:2023 — avaliação inicial do Gate 0

| Característica | Prova no Gate 0 | Estado |
|---|---|---|
| Adequação funcional | `/healthz` e `/v1/gate0/status` funcionam; capacidades de negócio não implementadas | PARCIAL |
| Eficiência de desempenho | Benchmark definido, cargas reais ainda não medidas | NÃO AVALIADO |
| Compatibilidade | Modelos JSON Schema candidatos validados; REST final/MCP não implementados | PARCIAL |
| Capacidade de interação | Frontend não implementado, WCAG a testar | NÃO AVALIADO |
| Confiabilidade | Policy fail closed verificada; jobs/restore não implementados | PARCIAL |
| Segurança | Gate deny-all e CI com read-only; autenticação final não implementada | PARCIAL |
| Manutenibilidade | Testes, pyproject e CI inicial, sem cobertura de produto integral | PARCIAL |
| Flexibilidade | Componentização planejada, sem teste de substituição de fornecedor | NÃO AVALIADO |
| Safety | Efeitos externos tecnicamente inexistentes/bloqueados no bootstrap | PARCIAL |

Estado `PARCIAL` refere-se ao **bootstrap**, não à plataforma integral. Nenhuma certificação ou conformidade ISO é alegada. A matriz completa por capacidade/requisito está no Plano Único.
