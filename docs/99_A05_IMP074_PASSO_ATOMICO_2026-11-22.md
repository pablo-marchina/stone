# A05 / IMP-074 / CAP-005 — leitura consistente e checkpoint no mesmo passo transacional

**Estado:** incremento de segurança e consistência no executor local *read-only* do agente. Não encerra IMP-074, não decide DEC-008, não cria ferramentas LangGraph/MCP, não libera produção, publicação nem autorização de uso de evidência externa.

## Lacuna corrigida

O executor `agent_graph_readonly_runner.py` já recuperava checkpoints duráveis e recomputava as consultas anteriores, mas antes cada consulta de ranking/evidência e a escrita do evento de checkpoint podiam usar transações diferentes. Uma gravação concorrente no corpus entre consulta e `record_node` poderia criar um recibo para uma observação que já havia mudado antes de o evento ser persistido.

O novo passo `execute_next` mantém **uma conexão e uma transação** entre `begin_run`, `resume_run`, releitura/validação de cada recibo anterior, leitura de todas as fontes necessárias, cálculo do ranking, confirmação de citações e `record_node`. Os métodos do checkpoint aceitam uma conexão interna **somente** quando `connection.engine` é o engine contratado e a transação já está ativa; o funcionamento anterior sem argumento continua disponível. Erro em qualquer estágio aciona o rollback da etapa inteira (inclusive a reserva de um novo run). Os códigos de erro de SQL são sanitizados, sem URLs, SQLs ou payloads privados.

Para **SQLite local**, a atualização deliberada da linha de tenant, antes de consultar o corpus, obtém o lock de escrita e impede um segundo writer local até o commit do checkpoint. Para **PostgreSQL**, o executor solicita transação `REPEATABLE READ` e usa locks compartilhados (`FOR SHARE`) sobre linhas consultadas em evidência, criador, métricas e ranking; a eficácia em concorrência/isolamento e os índices do PostgreSQL **ainda exigem ensaio no banco de teste**. Esse isolamento é por etapa, **não** uma visão imóvel ao longo de múltiplas chamadas HTTP. A cada retomada, o executor recalcula e nega alterações no conteúdo integral, na identidade de criador e nas métricas.

## Compatibilidade e salvaguardas

- `SqlDomainStore.ranking(request, connection=...)` aceita a conexão da transação; as invocações legadas `ranking(request)` continuam suportadas.
- `EvidenceRetriever.get(..., connection=..., lock_rows=True)` é opt-in para o executor; leitores existentes e handoffs A05 mantêm a chamada anterior.
- Nenhuma coluna, tabela, migração, interface externa, grant, token, corpus, classificação científica ou CreativeSpec foi acrescentada. O modo `gerar_criativo` continua em **ABSTAIN**, sem publicar ou criar documentos.
- Não há acesso a provedores, mídia externa, LLM remoto, credencial paga ou infraestrutura operacional. DEC-018 permanece vigente sem novo pedido de aprovação institucional; R$ 0.
- A cadeia SHA-256 e as consultas internas ainda não constituem auditoria externa independente, permissão de uso de terceiros ou prova de gold científico.

## Oráculos adversariais acrescidos

Novos casos em `tests/test_agent_graph_readonly_runner.py`: mesma conexão em SQL de corpus/ranking/checkpoint **por etapa**; rollback da reserva de run quando uma ferramenta falha; preservação de revisão em falha posterior; simulação de escritor SQLite concorrente, comprovando que só consegue alterar a fonte após o commit; detecção do novo drift no reinício; rejeição de conexão transacional de outro engine em `begin`, `resume` e `record`; rejeição de conexão sem transação; falhas SQL com razão sanitizada e rollback completo.

O manifesto de SHA do A11 passa a incluir `src/tapi_gate0/sa_store.py`, pois a semântica de ranking ligada à transação deve ser pinada junto do executor. O estágio focal A11 A05/A07 passa a exigir **348 PASS/0 SKIP** (339 anteriores + 9 novos). A regressão completa, A11 no HEAD exato e testes PostgreSQL/Windows permanecem verificações distintas. A aprovação dessa suíte não conclui os critérios científicos/operacionais de CAP-005, IMP-075, CT-05 ou CT-STUDIO.

**Próximo elo:** comparar formalmente LangGraph x orquestração direta sob DEC-008 usando a mesma política de segurança e workload; integrar o executor ao fluxo de System One com evidência validada, PEP por operação, observabilidade e testes de concorrência PostgreSQL. **G0–G6 e IMP-131 seguem BLOCKED.**
