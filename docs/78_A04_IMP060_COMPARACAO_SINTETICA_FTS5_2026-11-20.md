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

## Evidência de validação da comparação (20/11/2026, HEAD 5122f4a)

Operador executou e confirmou no HEAD `5122f4a2bd0550b82c299d56ac2d8e7d40f33c5d`:

- **49 PASS** em 0,54 s nas seis suítes focais do Gold Registry, CT-04, FTS5, replay e comparação; política local de **gasto zero PASS**.
- `SYNTHETIC_BASELINE_CANDIDATE_COMPARISON_VERIFIED`, `comparison_scope=synthetic_validation_only`, fixture pin SHA256 `4c85e82412a31e63065685220db9f588870d5172ea014a42c61f04885a8571e6`, split `validation`, 2 conteúdos, 1 query, k=2.
- Baseline lexical exato vs. FTS5: Recall@2 sintético **1,0 / 1,0**, nDCG@2 sintético **1,0 / 1,0**, deltas **0,0**, hashes de ranking/snapshot iguais `51bb87b4df0b25c476dbbaf1b9183c5f182cdea8d63129146ff860ad554270ca`. Os dois algoritmos empataram **nesta fixture trivial**, não em recuperação real.
- Latência de consulta exploratória p95: baseline **0,0074 ms**, candidata **0,1199 ms**. N=1 query, métodos/instrumentação diferentes, cache não controlado, indexação/setup excluídos; **não são comparação de desempenho justa nem SLO**.
- `sealed_test_queried=false`, `candidate_selected_for_production=false`, `dec006_decided=false`, `gold_relevance_judgments_available=false`, `scientifically_validated=false`, `gates_released=false`, `database_mutated=false`, `external_data_accessed=false`, `production_approved=false`.
- Relatório PRIVADO `a04-imp060-comparison-20261120-190037-390.json`, SHA256 `dd16612603cb860569259e4d0bc35de8c92edbc5b00552153b71a67822ff98e6`.
- A00 `--profile full` no **mesmo HEAD**: `a00-imp060-comparison-20261120-190037-717`, `checks_passed=true`, **1267 PASS, 0 FAIL, 0 ERRORS, 202 SKIPPED**, `checkout_unchanged=true`; `A00_IMP060_COMPARISON_VERIFIED`.

**Interpretação / próximo passo:** A etapa de *infraestrutura sintética de avaliação comparativa* está tecnicamente comprovada no SHA acima. Sua repetição sem novas perguntas, algoritmos ou controles acrescenta pouco à aceitação do projeto. Priorizar agora **IMP-069** (runner de avaliação por versão, registro inclusive de FAIL e gate operacional apenas local), além de preparar avaliação com evidências efetivamente disponíveis sob DEC-018, sem alterar a dispensa de revisão humana nem inventar julgamento gold. IMP-060/069/071, CT-04, DEC-006, G0–G6 e IMP-131 permanecem **não aceitos**. PR #44 segue draft. Este commit documental é posterior à A00 e não recebe aprovação automática por herança do SHA testado.
