# DEC-008 / IMP-027 — checkpointer SQLite nativo do LangGraph, recuperação em reinício

**Estado:** protocolo de diagnóstico **opcional e ainda não executado com o checkpointer real**. Não decidir DEC-008, não declarar durabilidade completa ou liberar G0–G6 / IMP-131 a partir destes testes.

## Evidência do operador em Windows (HEAD `586aabf60dbca1149b37915956065888dba49dfa`)

- Conda isolado Python **3.11.18** Windows x64, LangGraph **1.2.24** instalado, `pip check` sem conflitos.
- **24/24 PASS**, incluindo os três testes de paridade com LangGraph real antes não executados no ambiente Linux.
- Benchmark pareado real, **20 execuções por backend e modo**, três modos (`analisar`, `recomendar`, `gerar_criativo`) com `PAIRED_PARITY_VERIFIED_SYNTHETIC_ONLY`, `parity_verified=true` e exit 0. Todos mantêm `DEC-008_OPEN`.
- Os resultados foram recebidos **somente no log do PowerShell**. Os três relatórios `.json` e seus valores p50/p95 ainda precisam ser anexados. Os hashes SHA-256 impressos pelo CLI são evidência declarada, ainda não reconciliada com os respectivos bytes:
  - `analisar`: `5363b62b1b9c277e8417744ccd0ec850dde5ecf1eea3094915ec572192706db0`
  - `recomendar`: `f0852fbd9227237a194ab4310d3e8c4f27a8493ea0ad44c0ebed49f8e46a4382`
  - `gerar_criativo`: `f425912f6cddffba600b0d9364328f5e388707159cfab20dc4153c12f9fab13c`

**Interpretação:** a comparação prova paridade sintética entre dois orquestradores reais na trilha que utiliza o ledger SQL Stone. **Não compara** a persistência nativa LangGraph, PostgreSQL concorrente, tolerância a queda entre dois commits, consumo de memória/energia, direitos de terceiros, validade científica ou custo operacional.

## Novo ensaio de recuperação nativa

`tests/test_dec008_langgraph_native_sqlite.py` adiciona **4 testes condicionais de integração real** (sem mocks):

1. Em cada um dos três modos, usar duas bases **SQLite sintéticas e separadas**: o ledger transacional Stone e o `SqliteSaver` nativo LangGraph. Executar uma etapa, fechar ambos os engines, reabrir os dois arquivos e continuar com `graph.invoke(None, config)` usando o mesmo `thread_id`. Comprovar revisão, status final, hash-chain, ausência de duplicações e persistência só de recibos técnicos no saver.
2. Após registrar o hash do conteúdo, fechar/reabrir os dois bancos, adulterar a fonte e exigir `LOCAL_GRAPH_SOURCE_DRIFT_RESTART_REQUIRED`; nenhuma revisão extra pode ser persistida.

O grafo do teste usa `interrupt_after=["one_atomic_sql_step"]` para forçar checkpoint nativo após cada nó e executa **as mesmas funções reais** `execute_next` e `record_node` usadas pelo caminho direto. Esses testes não ativam endpoints ou jobs pagos.

**Dependências opcionais pinadas para o diagnóstico:** `langgraph==1.2.24` e `langgraph-checkpoint-sqlite==3.1.3`. A segunda é distribuída separadamente do LangGraph principal. A ausência de qualquer uma é **SKIP** explícito, nunca resultado PASS. A versão 3.1.3 foi escolhida por disponibilidade/compatibilidade e para não utilizar releases mais antigos com alertas de segurança conhecidos. O checkpointer SQLite é destinado a ensaios síncronos locais, **não é backend operacional escalável multiworker**.

## Comando proposto para o operador

```powershell
Set-Location "C:\Users\Inteli\Documents\Projetos\stone-pr71"
conda activate tapi-dec008-586aabf6
if (git status --porcelain) { throw "WORKTREE_NOT_CLEAN" }
git fetch origin
git switch --detach origin/integration/a027-a06-a11-convergence-20261122
$env:PYTHONPATH = Join-Path (Get-Location).Path "src"
python -m pip install "langgraph-checkpoint-sqlite==3.1.3"
python -m pip check
python -m pytest -q -rs tests/test_dec008_langgraph_native_sqlite.py
```

**Pendências:** conferir no Windows os quatro testes com saver real, adicionar cenário específico de falha entre commit do ledger Stone e commit nativo (dual-write sem transação distribuída), concorrência PostgreSQL e restore de backups. Não usar o SqliteSaver como solução de produção por inferência. **DEC-008 continua aberta, IMP-027/074 não completos, G0–G6 e IMP-131 bloqueados, nenhum merge/deploy.**
