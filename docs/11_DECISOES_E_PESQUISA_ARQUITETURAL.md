# Registro inicial das 12 decisões — sem vencedores presumidos

| ID | Alternativas/recorte | Estado |
|---|---|---|
| DEC-001 | Monólito modular vs microsserviços; TCO/carga/operação | CANDIDATO_BASELINE: monólito modular |
| DEC-002 | Vite/React vs Next.js; UX, SSE, acessibilidade, custo | ABERTO |
| DEC-003 | OIDC gerenciado vs self-hosted, RBAC/RLS | ABERTO |
| DEC-004 | Jobs PostgreSQL/outbox vs Dramatiq/Redis vs Temporal | ABERTO |
| DEC-005 | API Instagram e restrições YouTube; dados próprios | BLOQUEADO POR AUTORIZAÇÃO |
| DEC-006 | PostgreSQL SQL/FTS vs pgvector vs DuckDB/Parquet | SQL = baseline provisório |
| DEC-007 | Texto/metadata vs VLM temporal + transcrição | BLOQUEADO PARA MÍDIA REAL |
| DEC-008 | LangGraph tools vs orquestração direta; compatibilidade TAPI | ABERTO |
| DEC-009 | OTel+pytest vs Phoenix/MLflow/DeepEval e combinações | ABERTO |
| DEC-010 | Local, PaaS gerenciado, VM, split app/DB/worker | COMPARAR; sem cloud escolhida |
| DEC-011 | Matriz ISO por REQ vs checklist | CANDIDATO: matriz rastreável |
| DEC-012 | Op externa negada por padrão vs habilitada automaticamente | NEGADA por segurança |

**Protocolo obrigatório**: registrar questão, critérios (hard gates antes dos escores), strings de busca, versões das fontes, conflito de interesse, baseline mais simples, procedimento de benchmark, infraestrutura e corpus, métricas e IC, resultado, incerteza e condição de rollback. Alternativa não usar componente deve estar na comparação. Nunca interpretar preferência inicial como tecnologia homologada.

**Proposta de pesos para DEC-010, ainda não aprovada e a congelar antes dos testes**: TCO 35%, confiabilidade/recuperação 25%, custo de manutenção humana 15%, desempenho 15%, portabilidade 10%. Segurança, licenças, uso comercial permitido, privacidade, controle de acesso e backup restaurável são eliminatórios. Fazer análise de sensibilidade dos pesos e comparar pontos de Pareto. Sem carga/volume não há vencedor.
