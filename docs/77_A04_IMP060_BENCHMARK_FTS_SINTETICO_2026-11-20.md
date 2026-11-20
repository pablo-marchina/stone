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
