# A05 / CAP-005 / IMP-074 — checkpoints duráveis do agente (baseline técnico)

> Incremento aditivo da Base Atemporal v6.1; **DEC-008 ainda aberta**. Isto é uma implementação de infraestrutura de checkpoint, **não** o grafo LangGraph aprovado, o agente final, execução de tools, homologação dos três modos ou aceite IMP-074.

## Lacuna técnica atendida

`src/tapi_gate0/agent_graph_checkpoints.py` implementa uma trilha de estado persistente, usando as dependências SQLAlchemy/SQLite/PostgreSQL já existentes, para comparar futuramente orquestração direta e LangGraph sob o mesmo contrato. Não registra HTTP/MCP ou scheduler, não consulta dados privados nem aciona serviços. As três sequências previstas, estritamente limitadas e sem ferramentas executadas neste módulo, são:

| Modo | Nós de checkpoint previstos |
|---|---|
| `analisar` | `plan → retrieve → analytics → evidence_verify → output_verify` |
| `recomendar` | `plan → retrieve → analytics → evidence_verify → recommendation_draft → output_verify` |
| `gerar_criativo` | `plan → retrieve → analytics → evidence_verify → creative_spec_draft → output_verify` |

**Atenção:** registrar um hash num nó **não prova que o nó foi executado** ou que uma ferramenta funcionou. Este módulo nunca cria `CreativeSpec` real, `DesignDocument`, direitos, recomendações nem publica. Não existe nó que realize handoff externo ou envio privilegiado. O `studio_handoff` real deve ser implementado exclusivamente com o PEP existente e rechecagens transacionais próprias, separadamente.

## Invariantes funcionais

1. `begin_run` exige `tenant`, `actor`, `run_id`, modo da allowlist e SHA-256 do plano, não aceita IDs vazios, bools ou strings de controle. No contexto de aplicação, **tenant/actor precisam vir de sessão confiável**; este módulo não autentica o chamador e por isso não está exposto em endpoint público.
2. `record_node` só registra a próxima posição admissível com `expected_revision` exata. `PASS` avança; `ABSTAIN` e `BLOCKED` encerram de modo irreversível. Sem retries, aprovação implícita ou chamada de modelos. Repetir exatamente um recibo já gravado retorna o estado corrente sem novo evento; conflito de recibo/etapa é negado.
3. Um registro por `tenant_id,run_id`; `tenant` é bloqueado em transação para serializar CAS também no SQLite, e a revisão, digest e sequência de eventos são verificadas antes de qualquer gravação. Eventos só guardam identificadores técnicos, node, outcome e digests. A identidade do ator é armazenada como hash de escopo, não string original.
4. `resume_run` recalcula toda a cadeia hash e detecta lacunas, extras, alterações de payload/ordem e drift do estado. As ações externas continuam sem autorização mesmo que todos os hashes sejam válidos.
5. Recibos sempre incluem `node_execution_proved=false`, `rights_verified=false`, `scientifically_validated=false`, `studio_write_allowed=false`, `publication_allowed=false`, `production_approved=false` e `global_gates_released=false`.

**Limitação explícita de segurança:** cadeia SHA-256 detecta alterações incidentais, não é assinatura independente nem log imutável contra administrador de banco. Um atacante com escrita em todas as tabelas consegue recalcular hashes; auditoria externa, provas de PEP e execução real ainda faltam. A transação SQLite não comprova concorrência PostgreSQL nem restauração/backup.

## Migração e recuperação

Migração aditiva `0019_agent_graph_checkpoints`, dependente de `0018_studio_reference_bindings`, cria apenas tabelas privadas `agent_graph_runs` e `agent_graph_events`, com chaves primárias, referências tenant/run e **zero backfill/zero permissões**. `downgrade` nega eliminar qualquer uma delas se houver registros; **nunca aplicar em banco operacional agora**. `migrations/env.py` registra o esquema para Alembic; deve haver ensaio de cadeia completa, backup restaurável e verificação de drift antes de implantar.

## Verificações executadas no checkout local do incremento

- `tests/test_agent_graph_checkpoints.py`: **29 PASS** (três modos, retomada, replay idempotente, isolamento de tenant/ator, CAS, estados terminais, corrupção de cadeia, parâmetros negativos, nenhuma credencial no recibo).
- `tests/test_agent_graph_checkpoint_migration.py`: **3 PASS** (upgrade/downgrade vazios, downgrade com dados negado, zero backfill).
- Seleção abrangendo migrações A05 anteriores: **36 PASS** (32 desta alteração e 4 legados), no ambiente Linux isolado com a mesma árvore de código antes da publicação.
- `tests/test_a11_focal_evidence_packet.py` + novos testes: **64 PASS** na seleção conjunta (32 testes A11 e 32 novos). O catálogo focal A11 agora acrescenta esses dois módulos à seleção A05/A07, mantendo obrigatórios **302 PASS/0 SKIP** nessa etapa; o novo SHA precisa ser revalidado antes de herdar qualquer evidência. O A11 completo permanece distinto da regressão A00 e nunca libera gates.
- Preflight Python 3.11: **PASS** (386 arquivos); `verify_zero_spend.py`: **PASS**; espelho v6.1: **PASS**, 32 blobs, 204 IMP, 543 dependências, 23 CAP, DAG acíclico e sink IMP-131.

## Próximos elos (ainda NÃO_IMPLEMENTADOS/NÃO_ACEITOS)

- Selecionar/aprovar DEC-008 após comparação com LangGraph real na mesma carga e contratos. Associar o checkpoint a tools executadas sob RBAC/PEP e auditoria real de tempo, custo, permissões e evidências; nunca aceitar SHA arbitrário como prova.
- Construir grafo real para os três modos com checkpoints reexecutáveis, interrupção/reinício, fuga de prompt injection, validação de referências, modo abstain, recuperação de falha e binding de tool. Integrar A04/IMP-060/069/071, A06/Stone-S1 e geração CreativeSpec + Studio com direitos por operação.
- Ensaiar PostgreSQL concorrente, backup/restore, migração em cópia de dados e provedor operacional, mais CT-11, CT-STUDIO, ISO e G0–G6. Revisar o opt-in do runtime antes de qualquer release.

**Status:** incremento técnico de checkpoint em desenvolvimento. Não alterar 204 IMP/543 dependências, DEC-018 ou exigência de R$0. Sem dados externos, grants novos, chamadas pagas, modelos remotos, publicação, merge à `main`, produção ou alteração de `IMP-131=BLOCKED`.
