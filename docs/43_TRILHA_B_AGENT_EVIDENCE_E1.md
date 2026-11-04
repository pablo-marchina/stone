# Trilha B — Agente de recomendações fundamentadas (incremento B1)

**Estado:** núcleo determinístico de análise/recomendação e endpoint autenticado, sem LLM remoto, sem MCP servidor, sem geração multimodal. É o início de IMP-071/076, não o aceite do agente completo.

## Implementado

- `src/tapi_gate0/agent_evidence_e1.py`: consulta limitada à ferramenta `RankingTool.ranking` existente; o servidor fornece tenant/recorte e o tool devolve `RankingResult`.
- Se não há dados elegíveis, abstém-se de recomendar padrões e informa ausência de base.
- Se há dados, oferece exemplos para **inspeção editorial**, com `content_id`, `creator_id`, `snapshot_id`, ER observado e fórmula oficial; não inventa fonte, URL ou conversão.
- Nunca afirma causalidade, performance futura ou validação científica. Ranking técnico não prova direcionamento a MPEs.
- `src/tapi_gate0/agent_api_e1.py`: `POST /v1/agent/analyze-ranking` no modo seguro com autenticação revogável, tenant extraído **exclusivamente** do token, sem operação externa.
- Testes: abstinência, fonte exata, integridade do ranking, duplicatas, recorte, RBAC de autenticação e isolamento do tenant do request.

## Verificar

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_agent_evidence_e1.py
python -m pytest -q
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
git rev-parse HEAD
```

## Próxima implementação de B2

Ferramentas reais de busca/recuperação de trechos autorizados e revisão de rubrica, planejador de três modos (analisar/recomendar/gerar), fonte/citações verificáveis a partir do banco, boundary MCP com schemas fixos, defesa de prompt injection, quotas, auditoria e ligação ao CreativeSpec da trilha C. Modelos locais somente após benchmark; baseline determinístico é intencional.

**Atenção à integração:** B e C adicionam um roteador ao mesmo `secure_api.py`. Se forem integrados na mesma `main`, combinar **ambas** as linhas de import e `include_router`, mantendo os dois endpoints; não substituir um pelo outro.
