# A04 / IMP-060 — comparação técnica sintética entre baseline lexical e FTS5

**Corte:** 2026-11-20. **Estado:** código novo e testes implementados no PR #44 draft; **execução local pendente**. Não constitui aceite de IMP-060/069/071, CT-04, DEC-006 ou gates.

## Evidência anterior, registrada e verificada

Operador executou no HEAD `6e50cac5a8363e308cff46de79c37c28982febbf`: 39 testes focais PASS em 0.56 s; zero_spend PASS; `SYNTHETIC_EVALUATION_REPLAY_VERIFIED` com 3 rodadas idênticas em validation (2 docs, 1 query, k=2). Fixture SHA256 `4c85e82412a31e63065685220db9f588870d5172ea014a42c61f04885a8571e6`; resultado determinístico `7367581c75a0088680b67af5faa4fb99a36bae3537d85565097d8d48798d2b18`; ranking `51bb87b4df0b25c476dbbaf1b9183c5f182cdea8d63129146ff860ad554270ca`. A00 padrão no mesmo HEAD: 1257 PASS / 0 FAILED / 0 ERRORS / 202 SKIPPED, `checks_passed=true`, checkout inalterado. Os resultados não se transferem automaticamente a HEAD novo.

Relatório privado replay `a04-imp060-eval-replay-20261120-183334-913.json`; hash `04ffce87eeef48092b849ac15a0770429b20a8ac21aa3de965a1c9fb5c35b997`. A00 privado `a00-imp060-versioned-eval-20261120-183851-555`.

## Novo incremento (ainda não validado)

- `src/tapi_gate0/discovery_synthetic_comparison.py`: `compare_synthetic_baseline_candidate` verifica SHA256 de todos os bytes e chama primeiro o benchmark FTS5 existente, que já exige integridade de todas as referências, completo por split e sem duplicatas. Usa **o mesmo recorte development/validation** para um baseline independente de consulta por termos AND (`casefold` + tokens Unicode, desempate por content_id) e candidata SQLite FTS5/BM25. Nenhum rótulo é usado para definir o ranking. Os scores do baseline são calculados pelo registry, e os da candidata pelo benchmark FTS5 anteriormente validado.
- `scripts/a4_synthetic_compare.py`: CLI lê somente `tests/fixtures/CT-04_fts_*.json` com SHA256 fornecido e grava resultados agregados em `artifacts/private` por criação exclusiva (`O_EXCL`). Sem IDs, legendas, consultas, rótulos ou tenant no stdout/relatório.
- `tests/test_discovery_synthetic_comparison.py`: 10 testes novos de contrato, ordem de métodos, SHA, relevância estritamente sintética, bloqueio de sealed-test, creator leakage, schema e métricas inválidas, drift, relatório privado e ausência de overwrite. As cinco suítes Gold Registry e FTS replay anteriormente testadas tinham 39 casos; **49 focais esperados** no novo HEAD, ainda sem execução.

## Interpretação

Protocolo técnico sintético com dois algoritmos distintos, **não** SQL/PostgreSQL baseline comparado a vetor/híbrido; não resolve DEC-006 nem IMP-072. Métricas devem ser reportadas como `baseline_synthetic_*` e `candidate_synthetic_*`, com delta explícito e sem seleção de vencedora para produção. Latências das consultas não incluem construção do índice e são **diagnósticas**, não SLO nem benchmark de TCO comparável. A fixture contém apenas 2 documentos por split e uma consulta, logo nenhuma inferência sobre o corpus real é válida.

`sealed_test` não é indexado nem consultado; a comparação é proibida nesse split. A proteção atual para leakage é verificável em IDs/hashes/splits; não detecta automaticamente quase-duplicatas ou paráfrases e não equivale a isolamento de todo o ciclo de desenvolvimento. DEC-018 preservada: sem revisão humana independente, `scientifically_validated=false`, `gold_relevance_judgments_available=false` e `gates_released=false`. Sem mídia, rede, bancos operacionais, agentes, API ou produção; R$0 e PR draft.

## Próxima validação

1. Validar o espelho documental e checkout/HEAD; executar `pytest -q` nos seis módulos focais: `test_discovery_gold_registry.py`, `test_discovery_gold_registry_cli.py`, `contracts/test_ct_04.py`, `test_discovery_gold_retrieval_eval.py`, `test_discovery_synthetic_eval_run.py`, `test_discovery_synthetic_comparison.py`.
2. Verificar `scripts/verify_zero_spend.py`; executar `scripts.a4_synthetic_compare` em validation com pin SHA256 da fixture verificada e nome de relatório privado exclusivo. Conferir `SYNTHETIC_BASELINE_CANDIDATE_COMPARISON_VERIFIED`, `dec006_decided=false`, `candidate_selected_for_production=false`, `sealed_test_queried=false`, `scientifically_validated=false`, `gates_released=false`.
3. Se passar, executar A00 `--profile full` no MESMO HEAD; registrar SHA, PASS/FAIL/SKIP, checkout inalterado e erros. 202 skips do perfil padrão anterior não equivalem a aprovação multimodal opt-in.
4. Manter DEC-006, CT-04, IMP-060/069/071, G0–G6 e IMP-131 pendentes. Não alterar o backlog original, ativar pipeline, mesclar PR ou publicar artefatos privados.
