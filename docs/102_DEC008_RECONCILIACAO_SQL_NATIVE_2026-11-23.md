# DEC-008 / IMP-027 / IMP-074 — reconciliação limitada de checkpoints (dual-write)

**Status:** incremento de diagnóstico do executor local, não homologação do LangGraph operacional. DEC-008 continua **OPEN**; todos os gates G0–G6 e IMP-131 seguem **BLOCKED**. Sem novos endpoints, serviços, operações externas, licenças de mídia ou gasto financeiro.

## Nova evidência do operador (23/11/2026)

No HEAD `2ca82a048fd97f77dafe37b568eba1841fd93edd`, Windows Python 3.11, LangGraph 1.2.24 e `langgraph-checkpoint-sqlite==3.1.3` instalado, `pip check` sem conflitos, **4/4 PASS** (`tests/test_dec008_langgraph_native_sqlite.py` em 9,79 s, exit 0). O ensaio comprovou reabertura das duas persistências nos três modos e detecção de mudança de fonte, sob fixtures sintéticas. Não provocou interrupção entre commits nem garantiu exactly-once. O resultado foi recebido no log do operador, não como artefato CI assinado.

Os três JSON produzidos no benchmark de 20 pares por modo ainda não foram anexados, impedindo verificar p50/p95 e os hashes relatados anteriormente.

## Falha arquitetural e mecanismo de diagnóstico

Stone mantém um **ledger SQL transacional**; o LangGraph com `SqliteSaver` mantém um **segundo banco independente**. Não há transação distribuída: o processo pode cair **depois** do commit do evento Stone e **antes** do checkpoint nativo. Nesse caso, a retomada ingênua pode executar a próxima etapa como se o evento antigo não existisse. A paridade de runs completos não testa essa janela.

O módulo interno `agent_graph_reconciliation_dec008.py` implementa `execute_reconciled_step` para o caminho **sintético somente de leitura**, com os seguintes invariantes:

1. Lê a revisão do recibo nativo originado de **estado LangGraph confiável**, nunca do payload de uma API. Valida modo, versão de contrato, hash da cadeia, estado, cursor e campos de autorização. O ledger Stone permanece autoritativo.
2. Revalida a cadeia SQL e **reexecuta apenas consultas locais read-only** para recalcular todos os hashes das etapas anteriores, dentro de uma transação bloqueada por tenant, usando a mesma fonte que o executor atômico.
3. Se SQL e nativo estiverem em paridade, permite **um** novo nó. Se SQL estiver **exatamente uma revisão adiante**, retorna o recibo já persistido **sem gravar outro evento nem avançar a revisão**. Uma lacuna maior ou um recibo incompatível é negado, sem correção automática.
4. Mudança da fonte, recepção de grants forjados, outro ator/tenant, cadeia alterada ou revisão nativa adiantada levam a erros fixos e *fail-closed*. `gerar_criativo` continua terminando em `ABSTAIN`, sem criar documento, publicar ou tocar mídia.
5. `prepare_native_reconciled_graph` cria um `StateGraph` opcional que recebe um saver fornecido pelo host. `interrupt_after` força pausa por etapa. O componente **não é acionado pelo HTTP operacional**, não contém credenciais nem habilita modelos externos.

**Limite essencial:** nenhuma ferramenta com efeito externo pode adotar este padrão por analogia. Reexecutar queries para validação é aceitável no laboratório sintético, mas efeitos de Studio, rede, mídia, pagamentos ou publicação exigem idempotency keys verificadas no sistema externo, outbox transacional e compensação. Este módulo **não prova exactly-once**, recuperação após kill real, HA/multiworker, checkpoint PostgreSQL, observabilidade ou autorização por operação.

## Testes

- `tests/test_dec008_reconciliation.py`: **17 casos** SQLite reais, sem mocks de LangGraph, com três modos, um passo ausente por revisão, ausência de eventos duplicados, hashes e cursores forjados, rejeição de grants, tenant/actor, erro de planejamento, drift de fonte e recuperação de SQL-ahead.
- `tests/test_dec008_langgraph_dualwrite_actual.py`: **4 casos opcionais**, exigem LangGraph e SqliteSaver verdadeiros. Simulam a janela de commit SQL adiantado (salvam etapa 1 no nativo, executam etapa 2 no SQL sem atualizar nativo, reabrem ambas as bases, reconciliam e continuam) nos três modos, além do drift após uma lacuna. **A execução no Windows ainda está pendente.** Não são teste de kill abrupto ou da ordem real de escrita dos dois bancos.
- O A11 pinou novos arquivos no manifesto; seleção A05/A07 passou de **369 a 386 testes obrigatórios**, sem incluir os quatro testes opcionais. Não interpretar SKIP de LangGraph no Linux como sucesso.

## Próximos requisitos DEC-008

Obter os três JSON do benchmark anterior, executar os quatro novos casos no ambiente Windows; depois testar injeção de falha real no `SqliteSaver.put`, rollback/restore e tolerância a falhas PostgreSQL. Comparar latência, RSS e custo total de manutenção com os mesmos limites e decidir DEC-008 formalmente só após evidência operacional. **Sem merge, deploy ou liberação de gate por este incremento.**
