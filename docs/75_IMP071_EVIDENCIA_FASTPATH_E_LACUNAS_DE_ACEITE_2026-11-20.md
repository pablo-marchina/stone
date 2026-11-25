# IMP-071 — evidência técnica do fastpath e lacunas de aceite (2026-11-20)

**Estado:** qualificação técnica local validada pelo operador; aceite científico/IMP-071 NÃO concluído. PR #44 permanece **draft**. Documento de rastreabilidade, não ADR final, certificado de direitos ou liberação de gate.

## 1. Escopo e evidência operacional

Operador executou no HEAD `725f34c61bf967842eafca0aad55abfeae9d09a9`, ambiente `tapi-s1-recovery`:

- `PASS_ESPELHO_DOCUMENTAL`: 32 blobs exatos, backlog 204, dependências 543, DAG acíclico, sink IMP-131 único. O espelho declara `software_tests=not_run` e `gates=not_assessed` porque apenas espelha documentação.
- Sete suítes focais IMP-071: **75 PASS**, 0 FAIL, 0 ERROR, 1 StarletteDeprecationWarning (não bloqueante), 19.91 s. `verify_zero_spend.py`: PASS.
- Execução exclusivamente local `scripts.a6_retrieval_batch_fastpath`: `RETRIEVAL_BATCH_FASTPATH_LOCAL_VERIFIED`, três passagens com auditor em lote, checksum de manifesto/partição/ranking e prova privada de qualificação anterior.
- A00 `--profile full` no MESMO HEAD: `checks_passed=true`, **1218 PASS**, 0 FAIL, 0 ERROR, **202 SKIPPED**, `checkout_unchanged=true`; `A00_BATCH_FASTPATH_STANDARD_VERIFIED`. Os skips não são aprovações. O perfil não exigiu a integração multimodal opt-in.

### Evidência agregada, sem exportar dados privados

| Referência | SHA256 / identificação |
|---|---|
| Manifesto V12 scope27 | `d903366a975cb6e4c4e07c9e6300799c727c3efc3a8317530f14d90e19435b54` |
| Partição conteúdo/snapshot/legenda | `b842a43efd737abee7b78930ddb1243ccac93290cc7c45e9774d9bf542dafb44` |
| Ranking + snapshots (3 queries, top-5) | `ef5a496658f6500eeb824277828811251daeaf73eed309828342e280be7faee0` |
| Prova de qualificação local prévia | `f788b9a09f939a4f01a3bb2af0e1d0fa1cec4bfc5da7b21d24228d2b80613173` |
| Relatório de fastpath privado | `a05-imp071-batch-fastpath-20261120-154113-139.json` |
| SHA256 do relatório fastpath | `309a2b3f9f817d782c2523f342064553cbb6679cb446b8553c406e9879c55de4` |
| Relatório privado A00 | `artifacts/private/a00-imp071-batch-fastpath-20261120-154955-014/summary.json` |

Corpus técnico observado: **1069 conteúdos, 27 fontes**, 3 queries, hit counts **5 / 5 / 2**; ranking e snapshots coincidem com hash previamente qualificado. Não inserir IDs, captions, handles operacionais, grant tokens ou registros brutos neste documento.

Tempos da operação local apenas batch (ms): `[916.4078, 474.3233, 716.672]`; mediana `716.672`; p95 nearest-rank `916.4078` (n=3). Cada preview executou 3 verificações de escopo/rights, 2 readiness completos, auditoria técnica e checagem de partição; houve verificação final de escopo antes de gravar o relatório. As latências excluem setup do engine, leitura da prova e escrita do relatório. **Cache/carga não controlados, sem SLO de produção.** Não comparar diretamente com tempos de outra rodada como se fossem benchmark controlado.

O resultado reportou `database_mutated=false`, `external_data_accessed=false`, `scientific_admissions=0`, `scientifically_validated=false`, `production_approved=false`, `gold_relevance_judgments_available=false`. O auditor original segue padrão no readiness e demais entrypoints. O SHA256 do relatório de qualificação é **pin de integridade**, não assinatura de autenticidade ou outorga de direitos. O fastpath relê autorizações atuais e bloqueia por divergência. Rollback de operador: runner original `scripts.a6_retrieval_preview` sem flag batch; não há configuração de produção a reverter.

## 2. Lacunas contra o oráculo original

| Item da Base Atemporal v6.1 | Critério e estado |
|---|---|
| IMP-071, CAP-009, U04 | Baseline SQL/full-text **e ground truth** de relevância; `Recall@k`, `nDCG` e p95 em queries gold. **Baseline técnico exploratório e p95: evidência parcial; ground truth, Recall e nDCG: ausentes.** |
| IMP-060 | Registry de gold, splits por criador, sealed test; criadores não se repetem entre treino/validação/teste e prompts não incluem sealed test. **Não comprovado por este experimento.** |
| CT-04 / U04 | Isolamento EDD, detecção de leakage por criador e teste selado, comparação baseline+candidata com hashes e revisão humana. **Não executado/aceito aqui.** |
| DEC-006 / IMP-025 | Decisão SQL/FTS vs vetorial/híbrida/DuckDB com Recall@5, p95, TCO, dataset rights e rollback. **ABERTA_ATE_BENCHMARK.** |
| IMP-072 | Seleção de variante de recuperação baseada em incremento e custo, com rights-filter-first. **Não implementado/homologado por este resultado.** |
| DEC-018 / direitos | Corpus de legendas para avaliação exploratória sob escopo técnico não equivale a direito de mídia, perfil MPE provado, gold relevância ou autorização científica. **Sem nova autorização.** |

A existência de 1069 legendas e de 27 perfis não cria, por si, julgamentos independentes, prevalência de criadores MPE, correção de relevância ou aceitação institucional. `IMP-062` consta como dispensado pelo escopo declarado DEC-018, **não como cumprido**. Não restaurar artificialmente exigência de anotação nem alegar seu cumprimento sob o escopo atual.

## 3. Próxima frente (não autorizada nem executada automaticamente)

1. **Preregistro/autorizações:** confirmar se direitos e escopos permitem criar, guardar e avaliar julgamentos humanos; sem autorização, permanecer em estudo sintético/local e não marcar gold.
2. **Protocolo reprodutível:** congelar queries e corpus com referências e hashes, versão do tokenizer/SQLite/SQL/FTS e critérios binários/graduados de relevância; distinguir queries diagnósticas atuais de queries gold independentes.
3. **Isolamento EDD:** separar criadores em train/dev/sealed-test sem leakage; manter sealed-test fora de prompts, ajuste e configuração; registrar resultados negativos e verificação independente.
4. **Revisão humana:** definir guias claros, anotação independente e adjudicação onde autorizados, documentando suporte e divergências sem inventar rótulos.
5. **Bench comparável:** mesmo recorte autorizado, queries e hardware para SQL/FTS, eventual híbrido/vetorial e baseline; medir Recall@k, nDCG, p95 ponta-a-ponta, custo/TCO, riscos de autorização, e rollback. N pequeno/caches controlados onde viável; senão declarar limitação.
6. **Go/no-go separado:** só propor decisão DEC-006 ou aceite IMP-071 com evidência exigida, verificação de direitos, regressão atual no mesmo HEAD e revisão humana aplicável. G1, CT-04, IMP-131 não são liberados por `checks_passed` da A00.

## 4. Restrições preservadas

R$0 de serviços faturados; sem Meta/provedor externo, importação de mídia, edição/publicação, liberação de API/Creative Studio, merge ou release. Sem mudança no runtime default de `audit_run`. O fastpath é exclusivamente um entrypoint privado com flags e hashes explícitos, não um produto de busca autorizado.

**Conclusão:** documentação da *engenharia de recuperação* aprovada no experimento local; *validade científica e aceite formal* continuam pendentes.
