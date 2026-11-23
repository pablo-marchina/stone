# DEC-008 — contrato de recibo nativo e falha injetada no SqliteSaver

**Escopo:** incremento aditivo de diagnóstico do IMP-027 / IMP-074 sobre o PR #71. Sem merge, deploy, concessão de direitos, contas externas, chamadas pagas ou alteração de gates. DEC-008 permanece **OPEN**; G0–G6 e IMP-131 **BLOCKED**.

## Evidência Windows recebida

No commit `3d099e7f9cf930b09c5229db6adc6385460895cb`, o operador executou cinco módulos DEC-008 em Windows (Conda Python 3.11, LangGraph 1.2.24, `langgraph-checkpoint-sqlite` 3.1.3). Resultado **49 passed in 17.46s**, `TEST_EXIT=0`, sem skips, incluindo quatro cenários reais de reconciliação SQL/native. Registro no comentário de auditoria do PR #71. A simulação de uma revisão de atraso não é prova de interrupção dentro da gravação nativa nem de exactly-once de efeitos externos.

## Endurecimento no código

`agent_graph_reconciliation_dec008.py` aceita apenas a **estrutura exata do recibo técnico** produzido pelo checkpoint Stone. Rejeita campos adicionais, campos ausentes, `model_calls_performed` diferente de zero inteiro, `independent_gold_available=true` e `synthetic_or_technical_trace_only=false`. Já havia verificação de modo, estado, cursor, revisão, hash-chain e bloqueios de autoridade; esta alteração fecha o contrato do envelope durante a reconciliação. Não converte SHA-256 em assinatura independente.

`tests/test_dec008_reconciliation.py` inclui cinco novos exemplos negativos. O conjunto focal A05/A07 passa de 386 a **391 testes obrigatórios**, sem incorporar testes condicionais de ferramentas não instaladas. `scripts/a11_focal_evidence_packet.py` passa a identificar o novo arquivo opcional no inventário de SHA.

## Ensaio novo com checkpointer verdadeiro (opcional)

`tests/test_dec008_langgraph_saver_failure_actual.py` acrescenta quatro testes *sem fake*: três modos (`analisar`, `recomendar`, `gerar_criativo`) e um cenário de adulteração. O teste intercepta o método **real** `SqliteSaver.put`, deixa o ledger Stone confirmar a revisão 2 e provoca uma exceção **antes** de o saver gravar essa revisão. Fecha/reabre ambos os bancos SQLite locais, retoma com o grafo real e verifica ausência de duplicação dos eventos. No caso adversarial altera a evidência antes da retomada e exige *fail-closed*. Esse ensaio deve ser executado no Windows com as dependências opcionais já instaladas.

**O que não prova:** não faz kill -9/TerminatedProcess nem falha de energia; não é teste de dados operacionais, HA/multiworker, transação distribuída, outbox ou idempotência de criação/publicação. Uma exceção injetada em `put` também pode revelar gravações intermediárias do LangGraph e exigir adaptação da reconciliação antes de qualquer aceite. Nunca afirmar sucesso sem o resultado do Windows.

## Próximas evidências

- Executar os quatro novos testes opcionais no Windows no HEAD atualizado (guardar log e código de saída), corrigir qualquer falha descoberta.
- Anexar os três JSON de benchmark de 20 pares/modo já gerados para validar p50/p95 e hashes; não inferir decisão com logs parciais.
- Avançar a injeção para falha abrupta em processo isolado, PostgreSQL concorrente, backup/restore, observabilidade e outbox idempotente para tools com efeitos.
- Escolher DEC-008 somente após comparar confiabilidade, custo de manutenção e recuperação completos sob os hard gates do Plano Único.
