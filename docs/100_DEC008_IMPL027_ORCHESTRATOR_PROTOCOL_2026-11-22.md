# DEC-008 / IMP-027 — comparação pareada do orquestrador de agentes

**Status atual: DEC-008 ABERTA / benchmark INCOMPARÁVEL.** Este incremento instrumenta os candidatos para comparação e testa a orquestração direta real; não escolhe um vencedor, não conclui IMP-027/074 e não libera G0–G6 nem IMP-131.

## Pergunta e escopo

Segundo a Base Atemporal v6.1 (`03_Pesquisa_Tecnica_Atemporal.md`, `05_Metodologia_Cientifica_Atemporal.md`) e o Plano Único (`IMP-027`, `IMP-074`, `CAP-005`, `U05`), comparar LangGraph com orquestração direta **mantendo os mesmos hard gates** de dados, isolamento, direitos, RBAC e capacidade de recuperação. LangGraph é candidato prioritário, não requisito automático de stack (Documento Mestre, §4.1 vs §8). A escolha só pode ocorrer após execução real, benchmarks honestos, análise de complexidade, critérios de rollback e avaliação de operação, não por preferência de tecnologia.

## Implementação deste incremento

- `src/tapi_gate0/agent_graph_orchestrator_dec008.py` expõe **dois backends explícitos**: `direct` (o `execute_bounded` atual) e `langgraph` (um **StateGraph real**, com um nó que chama a mesma implementação `execute_next`, com decisão condicional para avançar até terminal). Nunca importa LangGraph na inicialização do produto. **Falta da dependência é erro nominal, sem fallback para `direct`.** Nenhum endpoint, credencial, grant ou acesso externo foi criado.
- `prepare_candidate` constrói/compila o backend **fora** da medição de tempo de execução. `execute_candidate` preserva a API simples para chamadas diretas. O grafo LangGraph usa somente hashes e recibos técnicos; a persistência continua no checkpoint SQL existente, não no checkpointer nativo de LangGraph. Portanto este desenho mede a **sobrecarga da orquestração com o mesmo ledger**, não a eficácia do checkpoint próprio da biblioteca.
- `scripts/dec008_orchestrator_benchmark.py` cria, a cada repetição, **um SQLite sintético descartável e idêntico**, nos três modos possíveis, sem dados externos e sem importações dependentes de provedores. Ordem alternada para atenuar viés de cache/aquecimento; separa tempo de compilação e de execução em p50/p95 (nearest-rank). Mesmos tenant, ator, plano, conteúdos, seguidores e métricas. Audita `status`, `revision`, `chain_sha256`, flags de direitos, e persistência por backend. Se o candidato real não existir, retorna **`NOT_COMPARABLE` com exit 2**, nunca declara LangGraph aprovado. A saída evita dados brutos de posts, prompts, segredos e nomes de contas reais.
- `tests/test_dec008_orchestrator.py`: 21 testes unitários: três modos no SQL real, falha segura quando LangGraph inexiste, backend inválido sem fallback, inputs não tipados, relatório incomparável nos três modos, parâmetros de execução fora do contrato, CLI explícito, auditoria de determinismo por ledger e **teste duplo etiquetado apenas como simulação de interface**, nunca benchmark do candidato real.
- `tests/test_dec008_langgraph_actual.py`: três testes de paridade usando **o LangGraph verdadeiro** quando a dependência estiver instalada. Ausência é SKIP identificado e não aceite; os três estão fora da seleção A11 obrigatória enquanto o pacote é opcional. A11 inclui o novo código e o teste unitário no SHA de fontes e exige **369 PASS/0 SKIP** na seleção A05/A07 (348 anteriores + 21 novos).

## Pré-registro de comparação real (a executar)

| Critério | Método / condição de interpretação |
|---|---|
| Segurança e finalidade | Eliminatórios: tenant/ator, origem autorizada, não publicação, `ABSTAIN`, isolamento, nenhum direito promovido; caso contrário candidato reprovado |
| Correção/reprodutibilidade | `status`, revisão, sequência/chain SHA devem coincidir em todos os modos em fixtures idênticas; nenhum erro, omissão ou replay extra |
| Reinício/crash | Ensaio completo de interrupção e recuperação de ambos, inclusive o checkpointer **nativo** LangGraph separado; não incluído neste microbenchmark |
| Latência | Medir p50/p95 de execução e preparação separadamente, com hardware e versões congeladas; não ordenar por um ganho numérico sem escopo/variância |
| Recursos / custo | Medir RSS, disco, energia e custo total de manutenção/licença em etapa posterior; **não medidos neste incremento** |
| Políticas e ferramentas | Mesmo backend SQL, conjunto de tools, fixtures, limites e permissão; comparar MCP/REST e prompt injection em avaliação futura |
| Decisão e rollback | Preservar baseline direto; decidir depois de evidência comparável, licença revisada e gate de recuperação. Rollback para a chamada direta já existente se alternativa não cumprir hard gate |

**Referências técnicas primárias consultadas:** [StateGraph](https://reference.langchain.com/python/langgraph/graph/state/StateGraph), [compile](https://reference.langchain.com/python/langgraph/graph/state/StateGraph/compile) e [checkpointers](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/checkpointers.mdx). O pacote LangGraph **não estava disponível** no ambiente isolado desta execução; tentativa de consultar índice de pacotes falhou por DNS. Não foi instalado por método alternativo nem simulada uma execução real da biblioteca.

## Evidência local de desenvolvimento (não normativo)

- `python -m pytest -q tests/test_dec008_orchestrator.py`: **21/21 PASS**.
- `python -m pytest -q tests/test_dec008_langgraph_actual.py`: **3 SKIP** por `DEC008_REAL_LANGGRAPH_DEPENDENCY_NOT_INSTALLED`; não é aprovação de LangGraph.
- `python -m scripts.dec008_orchestrator_benchmark --repetitions 5 --mode analisar`: status **`NOT_COMPARABLE`**, `DEC-008_OPEN`, benchmark direto sobre fixture sintética com 5 medições. A amostra é curta, sem alternativa medida, portanto **não permite ranking de desempenho nem decisão**. Não há aferição de gold/medição de cluster real.
- Gasto zero e espelho documental preservados. Validação A11 e regressão completa do novo HEAD devem ser registradas separadamente, com SHA real, inclusive erros/ignorados.

## Lacunas explícitas

Executar LangGraph real de versão/pacote/ambiente congelados; ensaiar estado em memória versus checkpointer SQL nativo; carga e cenários adversariais idênticos; alternativas de rollback, custo/manutenção, avaliação DEC-008 completa. Depois, conectar System One real e CreativeSpec/Studio com PEP transacional, sem ultrapassar as 23 capacidades/204 IMP. `DEC-018` institucional continua válida sem nova aprovação; permissões técnicas de provedores continuam separadas. **R$0, G0–G6 e IMP-131 BLOCKED; nenhum merge ou deploy.**
