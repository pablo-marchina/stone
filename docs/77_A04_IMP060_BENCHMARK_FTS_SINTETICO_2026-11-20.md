# A04 / IMP-060 + IMP-071 — benchmark FTS5 sintético integrado (2026-11-20)

**Estado:** implementado no PR #44 draft, SEM execução de testes locais do operador para este HEAD. Sem aceite IMP-060, CT-04, IMP-071, CAP-009, DEC-006, ou liberação dos gates.

## Mudança técnica

- src/tapi_gate0/discovery_gold_retrieval_eval.py: benchmark_synthetic_fts recebe bytes e pin SHA256; exige JSON estrito sem chaves duplicadas, referências synthetic_fixture, synthetic_local e synthetic_oracle, hashes exatos de documentos e consultas, e verificação de splits e completude pelo Gold Registry v1.
- Indexa somente development ou validation usando TransientScopedFts (SQLite FTS5 em memória); sealed_test não entra na busca nem em prompts. A comparação selada sintética agregada continua separada no Gold Registry e exige chamada explícita.
- As consultas são executadas pela implementação real FTS5. As médias Recall@k/nDCG@k são explicitamente sintéticas, com p95 das consultas (exclui construção do índice), contagens e sem referências ou textos na saída.
- tests/fixtures/CT-04_fts_synthetic.json: corpus de seis textos fabricados com hashes verificáveis, três consultas, seis julgamentos sintéticos, isolados em três conjuntos.
- scripts/a4_gold_fts_benchmark.py: CLI de leitura de testes/fixtures/CT-04_fts_*.json com SHA256 fornecido, sem acessar DB operacional, mídia ou rede.
- tests/test_discovery_gold_retrieval_eval.py: 11 novos testes esperados, incluindo consulta FTS real, isolamento, SHA, textos adulterados, leakage de criador, julgamentos incompletos, JSON duplicado e bloqueios do CLI.

## Propriedades e limites

Versão tapi-imp060-fts-synthetic-benchmark.v1; status esperado SYNTHETIC_FTS_BENCHMARK_VERIFIED. Sempre gold_relevance_judgments_available=false, scientifically_validated=false, gates_released=false, production_approved=false, external_data_accessed=false, database_mutated=false e sealed_test_queried=false.

O runner não está ligado a agentes, HTTP, MCP, Creative Studio, fontes reais, banco de domínio, jobs ou publicação. SHA256 é pin de integridade, não autorização ou prova externa de origem. O teste selado só é validado quanto a hashes da fixture sintética, nunca indexado; os resultados não são gold de domínio. A proteção contra leakage de IDs/hashes não substitui detecção semântica ou isolamento de processos/ciclos.

## Validação pendente do novo HEAD

Com ambiente tapi-s1-recovery, checkout limpo e operadores cientes de R$0: validar espelho documental, executar as quatro suítes Gold Registry/CT-04/FTS sintético (esperados 29 PASS), verificar gasto zero, rodar o CLI com pin SHA256 calculado localmente e repetir A00 --profile full em SHA idêntico e relatório privado exclusivo. Documentar FAIL, skips, SHA, e sem alegar aprovação antes do resultado do operador.

A A00 previamente confirmada no HEAD 5aea36e tem 1236 PASS, 0 FAIL, 0 ERROR e 202 SKIPPED; esse resultado não vale automaticamente para os commits novos.

## Passo seguinte após validação

Avançar para rastreabilidade de avaliações por versão, separar rigorosamente dados usados em ajuste dos dados selados e manter DEC-018. Nenhuma validação independente é alegada. O backlog original 204 IMP, 543 dependências, PR #44 draft, custo R$0 e gates abertos permanecem inalterados.


## Evidência executada pelo operador — 20/11/2026, HEAD bf9afaa

No HEAD `bf9afaa4de70ec563bfd94a50fb71441045eb637`, operador reportou `29 passed in 0.37s` nas quatro suítes Gold Registry/CT-04/FTS sintético; `verify_zero_spend`: PASS; runner `scripts.a4_gold_fts_benchmark`: `SYNTHETIC_FTS_BENCHMARK_VERIFIED`, pin SHA256 do bundle `4c85e82412a31e63065685220db9f588870d5172ea014a42c61f04885a8571e6`, split validation, 2 docs, 1 query, k=2, `macro_synthetic_recall_at_k=1.0`, `macro_synthetic_ndcg_at_k=1.0`, `query_latency_p95_ms=0.1216` (consulta, **não indexação/E2E**); `sealed_test_queried=false`, nenhuma admissão científica, nenhuma escrita no banco ou rede, aprovação de produção false.

A00 --profile full no MESMO HEAD: `A00_IMP060_SYNTHETIC_FTS_VERIFIED`, relatório privado `a00-imp060-fts-20261120-181334-920`, `checks_passed=true`, **1247 PASS, 0 FAILED, 0 ERRORS, 202 SKIPPED**, `checkout_unchanged=true`. Os skips não contam como aprovação multimodal. Não há reconhecimento institucional de gold nem aceite IMP-060/CT-04/IMP-071. Os resultados pertencem somente ao HEAD identificado; quaisquer commits seguintes exigem novos testes, e o PR #44 continua draft.


## Próxima camada implementada: replay versionado exclusivamente sintético — A04.3

**Status:** código implementado, testes do operador **ainda não executados neste novo HEAD**. Depois do PASS em bf9afaa, foram acrescentados:

- `src/tapi_gate0/discovery_gold_retrieval_eval.py`: digest SHA256 determinístico dos rankings com IDs e snapshots **somente em memória**; a saída inclui apenas o digest, não as referências. O digest permanece estável entre execuções idênticas, independentemente do cronômetro.
- `src/tapi_gate0/discovery_synthetic_eval_run.py`: repete o *mesmo* FTS5 no mesmo split permitido de uma fixture pinada (2–5 vezes), exige paridade exata das métricas, população, política, status e SHA256 do ranking; falha em drift ou promoção de `scientifically_validated`/`gates_released`. Calcula hash determinístico separado das amostras de latência; tempos reportados são exploratórios, não SLO.
- `scripts/a4_synthetic_eval_report.py`: só aceita arquivos `tests/fixtures/CT-04_fts_*.json`, exige pin SHA256 e grava relatório **privado** em `artifacts/private` por criação exclusiva (sem overwrite); stdout agregado, sem textos, IDs, julgamentos ou conteúdo de sealed_test.
- `tests/test_discovery_synthetic_eval_run.py`: 9 testes de replay, assinatura estável, split diferente, prova em arquivos privados, erros tipados, recusa de seal, drift de ranking, campos científicos falsamente aprovados, latência NaN e segurança no CLI. Um teste adicional em `tests/test_discovery_gold_retrieval_eval.py` valida o digest. **10 novos testes pendentes**, total **39 focais esperados** (29 previamente aprovados + 10 novos).
- O uso do mesmo FTS5 repetido é um experimento de **reprodutibilidade de engenharia**, **não** comparação independente baseline versus candidata. O relatório define `baseline_candidate_comparison_completed=false`. Nenhum novo caminho de produção, provedor, HTTP/MCP, DB operacional, uso do teste selado ou validação científica.

Para validar, executar as quatro suítes originais **mais** `tests/test_discovery_synthetic_eval_run.py` (39 PASS esperados), `scripts/verify_zero_spend.py`, o replay local em fixture sintética pinada e A00 `--profile full` no novo HEAD. A aprovação A00 anterior (1247 PASS / 202 SKIP em bf9afaa) não se transfere ao SHA novo. Nenhum gate é liberado automaticamente.
