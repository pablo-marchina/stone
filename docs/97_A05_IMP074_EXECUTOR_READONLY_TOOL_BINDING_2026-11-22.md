# A05 / IMP-074 / CAP-005 — execução determinística de tools com checkpoints

**Tipo:** incremento técnico aditivo sobre `0019_agent_graph_checkpoints`, sem alteração da Base Atemporal v6.1 ou da DEC-008. **Não equivale ao agente LangGraph homologado**, à implantação de System Two, à conclusão do IMP-074 ou à aprovação dos gates.

## Problema e solução implementada

O baseline anterior conseguia persistir hashes de etapas enviados por um host, mas não possuía uma implementação que efetivamente executasse uma ferramenta e derivasse seu recibo do resultado verificado. O novo módulo `src/tapi_gate0/agent_graph_readonly_runner.py` conecta o ledger às ferramentas locais já existentes:

- **`plan`** fixa um `LocalGraphPlan` tipado (modo, publicação sintética, data UTC, idade mínima, ID de conteúdo) e um SHA-256 reproduzível. O plano congela somente entradas técnicas, não permissões externas.
- **`retrieve`** chama `EvidenceRetriever.get()` no tenant do host. Verifica origem `synthetic_local`, ausência de `source_url` externo, publicação não futura e snapshot observado. Associa o recibo não só à legenda abreviada, mas ao hash dos payloads integrais de conteúdo, criador e snapshots armazenados. Nenhuma legenda, token, prompt ou payload de ferramenta é persistido no ledger.
- **`analytics`** chama `analyze_with_ranking(SqlDomainStore)` com tenant, origin e `as_of` vinculados ao plano; ausência de posts elegíveis leva a `ABSTAIN`.
- **`evidence_verify`** reconsulta ranking e valida, para cada citação, conteúdo, criador, snapshot e valor de ER calculado a partir de SQL existentes e pertencentes ao tenant. Caso o conteúdo escolhido não integre o conjunto citado, há `ABSTAIN` conservador, nunca citação fabricada.
- **`recommendation_draft`** apenas valida o resultado determinístico e seu caráter descritivo não causal. Não produz padrões científicamente aceitos sem gold.
- **`creative_spec_draft`** sempre gera `ABSTAIN` com código fixo `CREATIVE_RIGHTS_PIPELINE_NOT_BOUND`. **Não** aciona geração criativa, `StudioStore`, PEP de direitos, modelos remotos, publicação ou render.
- **`output_verify`** revalida a consulta do agente nos modos read-only, sem autorizar qualquer uso externo.

`execute_next` executa **no máximo um nó** por chamada; `execute_bounded` executa até o limite fixo de nós. As duas operações são somente chamadas internas de Python — **não existe rota HTTP/MCP, fila externa, serviço pago, despacho remoto nem agendador**. O host responsável deverá obter `tenant` e `actor` da sessão autenticada antes de usar este módulo; o módulo não autentica ninguém por si próprio.

## Invariantes de retomada

1. Antes de cada passo, `begin_run`/`resume_run` validam tenant, ator, run ID, revisão, hash da cadeia e modo. O passo subsequente exige CAS por revisão.
2. Todos os recibos de nós anteriores são **recomputados** executando novamente **somente consultas locais e read-only** do plano. Se qualquer resultado mudar — inclusive o final da legenda não exposto no preview, o criador ou snapshots — a execução nega com `LOCAL_GRAPH_SOURCE_DRIFT_RESTART_REQUIRED`, sem registrar uma nova etapa ou reutilizar silenciosamente o estado antigo.
3. A execução pode ser reiniciada após interrupção com a mesma base SQLite, sem duplicar etapas. Se houver mudança de evidência, um novo plano/run sob revisão explícita é necessário. Nenhuma escrita em tabelas de corpus é feita; **apenas as tabelas de checkpoint** podem receber registros.
4. Falta de conteúdo ou snapshot gera abstenção; inconsistência de payload ou citação gera bloqueio. Nunca promover o estado do ledger a autorização de direito, validação científica, operação de dados externos ou liberação de produção.
5. A cadeia SHA-256 é detecção técnica de drift e não assinatura ou prova independente contra um administrador de DB. A etapa pode ter executado a consulta local, mas `node_execution_proved=false` permanece no recibo padrão até existir um mecanismo de atestação externa auditável.

## Testes e limites da evidência

`tests/test_agent_graph_readonly_runner.py` contém **21 casos** locais com SQLite sintético, métricas/identidade reais do domínio e checkpoints duráveis: dois modos read-only completos, modo criativo abstém, retomada após reabrir o engine, no-op de retry, drift de legenda integral e métricas, integridade entre tenants, esquema tipado adversarial, falta de fonte/snapshot, rejeição de payload inconsistente, citação forjada e nenhuma promoção de direitos. São testes de implementação, não gold independente.

O A11 inclui o novo módulo em `SOURCE_FILES` e os testes no estágio `python_a05_a07`, sem mexer nos thresholds dos demais estágios: a seleção focal passa de **302 para 323** aprovações esperadas e **zero skipped**. Executar o validador focal completo em worktree Git limpo e registrar a identidade da árvore; `FOCAL_DIAGNOSTICS_VERIFIED_NO_GATE_RELEASE` jamais libera G0–G6/IMP-131.

**Próximos elos ainda ausentes:** orquestração LangGraph real comparada com DEC-008, binding de tools MCP/Python/REST com RBAC e permissões operacionais, atestação de execução, hooks de System One/multimodal, CreativeSpec/Studio com PEP por operação e transação, interrupção concorrente em PostgreSQL, testes adversariais completos e UI Agent Studio SSE. `gerar_criativo` continua sem saída criativa autorizada, por decisão de fail-closed.

**Estado declarado:** desenvolvimento do IMP-074 em curso; 23 capacidades e 204 IMP continuam governadas pelo Plano Único, sem nova lista paralela. DEC-018 vigente sem repetição de aprovação institucional; zero gasto; sem dados externos, grants novos, merge, deploy, liberação de publicação, homologação de CT-05/G5 ou IMP-131.
