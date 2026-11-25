# A05 / IMP-074 / CAP-005 — adaptador HTTP autenticado de diagnóstico local

**Incremento técnico do Plano Único v6.1**, dependente dos checkpoints 0019 e do executor read-only; não altera a decisão DEC-008, os critérios de aceitação ou a liberação de qualquer gate.

## Contrato de execução adicionado

O módulo `src/tapi_gate0/agent_graph_local_api.py` adiciona **somente sob opt-in de fábrica** o endpoint `POST /v1/agent/local-graph/step` ao app seguro. Cada chamada executa **no máximo um nó** do executor local `agent_graph_readonly_runner` e devolve apenas o recibo técnico do ledger. Não existe HTTP de publicação, CreativeSpec, modelos remotos, mídia, LangGraph, fila ou SSE.

A flag Python `enable_local_graph_diagnostic` em `create_secure_app` é **False por padrão**. Só pode ser True simultaneamente com `allow_http_local=True`, `initialize_schema=True` e URL SQLite local. O caminho normal `from_environment()` **não lê nem propaga essa flag**, de modo que não existe habilitação por variável de ambiente ou por banco operacional. Quando habilitado, o adaptador restringe a identidade da conexão a `127.0.0.1`, `::1` ou host sintético `testclient` e rejeita peers remotos mesmo com Bearer válido ou `X-Forwarded-For` forjado. Essa restrição é defesa adicional; não substitui segmentação de rede ou controle de implantação.

O corpo tipado `StepRequest` contém **apenas** `run_id` e `plan`, ambos validados com `extra="forbid"`. O plano aceita apenas `synthetic_local`, modos `analisar`, `recomendar` ou `gerar_criativo`, instante UTC e idade mínima autorizada pelo contrato. `tenant` e `actor` **nunca vêm da requisição**, mas de `identity.resolve()` em cada passo; funções aceitas: `admin`, `researcher`, `editor`. `viewer` e `service` não iniciam nem retomam checkpoints por este endpoint. A revogação de sessão tem efeito na chamada seguinte.

A passagem JSON → `LocalGraphPlan` usa `model_validate_json` antes de executar ferramentas porque Pydantic estrito aceita o instante ISO UTC como data em JSON, mas não como string Python dentro da validação de um objeto aninhado do FastAPI. A validação original de `LocalGraphPlan` é preservada; datas sem timezone, modos desconhecidos, campos extras e dados externos continuam a ser rejeitados. Erros internos de checkpoint/replay retornam código sanitizado `409` sem conteúdo de fonte.

## Validação de regressão

`tests/test_agent_graph_local_api.py`: **16 casos** de contrato e abuso, incluindo opt-in desabilitado por padrão, negação de uso operacional, sessão sem token ou revogada, viewer, tentativa de trocar tenant/actor/grants, peer TLS remoto com `X-Forwarded-For`, retomada sem duplicação, agente read-only, abstenção no criativo, uso do mesmo run_id com isolamento por tenant, conflito de ator e plano inválido. Os testes usam SQLite sintético; não comprovam uso de provedores, nem aceitação do agente final.

O A11 focal agora inclui este módulo e seu código no inventário de SHA, exigindo **339/339 PASS** em A05/A07, sem skips, falhas ou erros; os demais limites focais permanecem inalterados. Antes do release, voltar a executar o A11 no HEAD exato e a regressão mais abrangente; nunca atribuir aprovação científica a esses testes.

## Lacunas preservadas

Continua faltando a API operacional autenticada com política final, comparação e decisão DEC-008, LangGraph real, propagação de confiança/tokens para todas as tools, registros auditáveis independentes, PEP e CreativeSpec/Studio transacionais, concorrência PostgreSQL, recuperação distribuída, SLO, avaliação científica e CT-05/G5. **G0–G6 e IMP-131 BLOCKED; `production_approved=false`; zero gasto, nenhum merge/deploy e nenhuma alteração em credenciais ou grants.** A DEC-018 institucional continua vigente sem novo pedido de aprovação.
