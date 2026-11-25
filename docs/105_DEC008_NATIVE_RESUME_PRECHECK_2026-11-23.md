# DEC-008 / IMP-027/074 — falha real do SqliteSaver e revalidação na retomada

**Estado:** incremento na PR #72 (empilhada na #71), sem regressão Windows pós-correção. DEC-008 OPEN; G0–G6 e IMP-131 BLOCKED. Sem deploy, autorização externa, gasto ou merge.

## Evidência Windows do operador (SHA 314861540e189da6066a450dbd4a2b66e3cb6997)

Python 3.11, LangGraph 1.2.24 e SqliteSaver 3.1.3: **8 passed, 4 failed, 0 skipped**. Seis testes do DAG e dois da jornada vertical passaram. Os quatro FAIL ocorreram na injeção de exceção em SqliteSaver.put:

- Após Stone SQL confirmar revisão 2 e o saver levantar exceção, get_state() exibia revisão nativa 2, não 1 como o teste assumia.
- Após alteração de legenda, invoke(None) não negou a retomada como esperado.
- Hipótese: checkpoints ou escritas intermediárias já tornaram a revisão 2 visível sem existir um nó pendente. Isso requer medição de next/tasks e histórico antes de firmar a causa.
- Zero spend, espelho Base v6.1 e pip check PASS, mas nenhuma homologação.

## Correções desenvolvidas

- validate_native_resume: lê sem criar eventos, checa plano SHA, ledger Stone, tenant/ator, hash-chain e reproduz os hashes de todos os recibos. Não assume que invoke(None) vai executar um nó. Divergência nativo/SQL acima de uma revisão é negada.
- prepare_native_reconciled_graph agora retorna uma superfície diagnóstica restrita invoke/get_state; invoke(None) faz o preflight sempre. Se SQL estiver OPEN e o snapshot nativo não tiver nós pendentes, somente nesta trilha local/sintética/read-only, reinicia a próxima etapa fornecendo recibo SQL validado. A função de nó faz uma segunda revalidação.
- Os testes de put failure agora aceitam revisão nativa 1 ou 2 como observação intermediária e exigem avanço monotônico sem duplicação até a revisão terminal, ou rejeição de drift antes de reexecutar.
- tests/test_dec008_resume_preflight.py: novos testes de preflight para SQL-ahead, paridade, plano forjado, dados alterados, wrapper sem next e ausência de thread confiável.

**Limites:** Sem efeitos externos, autorização criativa, trânsito HTTP, prova exactly-once, transação distribuída ou produção. SqliteSaver segue exclusivo do diagnóstico síncrono local.

## Validação Windows pendente no HEAD atual da PR #72

PowerShell, no worktree limpo com PYTHONPATH apontando para src do próprio checkout:

    python -m pytest -q -rs tests/test_dec008_resume_preflight.py tests/test_dec008_langgraph_saver_failure_actual.py tests/test_dec008_langgraph_native_sqlite.py tests/test_dec008_langgraph_dualwrite_actual.py tests/test_dec008_langgraph_actual.py tests/test_dec008_reconciliation.py tests/test_dec008_orchestrator.py tests/test_architecture_vertical_synthetic.py tests/test_a11_architecture_frontier.py
    python scripts/verify_zero_spend.py
    python docs/base_atemporal/ferramentas/validar_espelho.py

Preservar log e exit code. Se falhar, coletar apenas StateSnapshot.next, revisões nativa/SQL e erro sanitizado, não payloads ou tokens. Não declarar testes PASS até a execução. Depois da aprovação: A11 focal, regressão integral e evidência por SHA. Ainda faltam kill real, PostgreSQL concorrente, backup/restore, RSS/latência/custo e idempotência de tools com efeitos.
