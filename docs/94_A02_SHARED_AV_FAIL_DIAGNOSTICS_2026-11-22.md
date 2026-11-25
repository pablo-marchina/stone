# A02 — Diagnóstico de ASR em relatórios shared-AV reprovados

> Complemento instrumental da Base Atemporal v6.1, empilhado sobre a PR #59. Não substitui os contratos de processamento multimodal, aceites científicos, direitos efetivos ou gates G0–G6/IMP-131.

## Lacuna encerrada neste incremento

O diagnóstico ASR anterior aceitava somente relatórios do benchmark independente (`ASR_FIXTURE_BENCHMARK_COMPLETED`). O experimento multimodal compartilhado contém **sete clipes sintéticos autorais** e produz relatório `SHARED_MULTIMODAL_FIXTURE_BENCHMARK_COMPLETED`, com referências de fala embutidas em `multimodal_shared_fixture.CASES`, transcrições em `row.audio.transcript`, VAD, OCR e evidências de fusão.

O validador `multimodal_semantic_replay.validate_report` exige `engineering_gate_passed=true`; portanto, não deve ser usado para diagnosticar relatórios **reprovados**. O novo módulo `shared_av_asr_diagnostic.py` cria uma fronteira somente diagnóstica, sem alterar o validador de aprovação anterior.

## Integridade e comportamento

- Exige relatório sintético, policy/shared/fusion fixadas, checkpoint `faster-whisper-medium` declarado com ID/revisão/digest conhecidos, hash dos recursos VAD/OCR selecionados e nenhuma ação externa, mídia real, banco, ciência ou aprovação.
- Confere ordem e partição exatas dos sete casos, legenda, valores esperados, duração, hashes de legenda e mídia, flags temporais e `shared.validate_asset_binding` com a implementação real do repo.
- Reconstrói de forma exata os fragmentos de legenda e áudio; todo segmento ASR deve existir com hash do texto, origem PCM, chunk PCM, timestamp, região VAD e fragmento correspondente. Confere `audio.transcript` com chunks e todos os arms via `fusion.fuse`, depois `fusion.evaluate` e a fórmula real do gate shared-AV.
- Usa as mesmas funções `multimodal_asr.word_errors` e `_alignment` do diagnóstico independente, produzindo edições palavra a palavra apenas no JSON privado. Distingue reprovação da fusão, chamadas ASR indevidas em clipes negativos, palavras geradas em casos sem fala, WER agregado e WER individual.
- **Não confunde limites:** `MAX_POOLED_WER=0.30` e `MAX_CASE_WER=0.50` são apresentados no shared-AV **somente como indicadores informativos**, não como novos critérios da avaliação fusion.
- O diagnóstico nunca libera gate e emite `source_bytes_independently_verified=false`, `checkpoint_independently_attested=false`, `independent_gold=false`, `production_approved=false`, `global_gates_released=false`. Verificação interna de relatório não demonstra existência/proveniência externa dos bytes de mídia ou autenticidade do checkpoint real.

## Interface offline e compatibilidade

O CLI existente ganha opção **explícita** `--report-kind shared_av`. Seu modo padrão, `asr_fixture`, continua com a semântica anterior; formatos diferentes não são identificados automaticamente.

```powershell
git rev-parse HEAD
python -m scripts.a02_asr_strict_diagnostic `
  --report-kind shared_av `
  --expected-head "<SHA40-checkout-limpo>" `
  --input-name "shared-av-ja-existente.json" `
  --input-sha256 "<SHA256-dos-bytes-completos>" `
  --output-name "diagnostico-shared-av-novo.json"
```

Fonte e saída são limitadas à pasta ignorada `artifacts/private/`, com hash obrigatório, bloqueio de path traversal, symlink, duplicação de chaves JSON e sobrescrita. O terminal não imprime transcrições, apenas resumo e SHA do novo recibo. Em caso de falha, não há recibo de autorização.

## Testes realmente executados nesta execução

**62/62 PASS** com Python 3.13 em ambiente local isolado, com sintaxe do novo código também analisada sob gramática **Python 3.11**. São 28 testes do diagnóstico ASR original e 28 novos casos shared-AV (incluindo 16 mutações parametrizadas de report, áudio, métricas e hash, além de entradas privadas da CLI). O código publicado foi comparado por comprimento e checksums com a versão executada.

**Limite da evidência:** os testes locais usam funções de WER/fixtures copiadas do código do repositório e substitutos explícitos de `shared.validate_asset_binding` e `fusion.evaluate`. Eles não executaram o pipeline FFmpeg/VAD/Whisper/OCR real, a suíte completa no checkout, PostgreSQL, licença externa nem o benchmark multimodal com um relatório autenticado. A suíte integrada no HEAD continua NOT_RUN.

No A11, `python_a02_asr_diagnostic` passa de **28 para 62 casos esperados**; os grupos A05/A07 (**269**) e A06/E1 (**29**) permanecem independentes. Nenhum desses números é aprovação do A11 completo.

## Próxima dependência crítica

Executar este modo com relatório **realmente gerado** pelo shared-AV no ambiente nativo, confirmar integridade/consistência da origem, examinar exatamente os erros que persistem na ASR Strict, corrigir perfis ou qualidade de forma controlada e repetir os oráculos congelados sem afrouxar thresholds. Concluir A02.7, evidência operacional, avaliação científica independente, agentes, Studio, A00/A11 full e todos os gates antes de deploy. Custo absoluto R$0 e DEC-018 permanecem invariantes.


## Revisão adicional — completude OCR (2026-11-22)

A inspeção do código revelou que validar somente os fragmentos **presentes** não garante que o conjunto seja completo: uma leitura OCR válida poderia ser omitida do array `fragments` e o array `arms` recalculado, mantendo a aparência de um relatório coerente. Esta versão reconstrói obrigatoriamente os dois quadros de origem nos timestamps [0, 3] usando a função congelada `shared.consensus.consensus_words`, exige a exatidão de `words`, `complete_primary_and_supporting_sequence_retained`, status da observação, hashes e locator, e compara a sequência integral **OCR → legenda → áudio** (sem entradas extras, omissões ou reordenações). A validação permanece *read-only* e vale inclusive para relatórios com engenharia reprovada.

**Seis novos casos:** (1) reintrodução de fragmento OCR válido e posterior exclusão deliberada, ainda que as métricas sejam recalculadas, e (2–6) alteração de timestamp, hash do frame, status, bit de completude e SHA de mídia. **62/62 PASS** localmente (28 diagnósticos standalone + 34 shared-AV/CLI), inclusive ao trocar o substituto OCR simplificado pela lógica real copiada de `multimodal_ocr_consensus.consensus_words` para o laboratório isolado. **Ainda não é validação do pipeline nativo** ou dos módulos integrados completos.

No A11, `python_a02_asr_diagnostic` agora espera **62 casos**, mantendo `python_a05_a07=269` e `python_a06_e1=29`. Não há liberação de gates, direitos, gold, CI ou produção por esta correção.
