# A06 / DEC-017 — ponte auditável de AV sintético para System One E1

> Incremento de engenharia da Base Atemporal v6.1 (IMP-063/064/136), não backlog paralelo, mudança de DEC, aceite científico, aprovação de mídia externa ou liberação dos gates G0–G6/IMP-131.

## Caminho funcional implementado

O benchmark compartilhado de multimodalidade produz relatórios locais de **sete clipes originalmente criados pelo laboratório** com evidência de legenda, áudio, OCR e vínculo exato aos bytes de mídia. O System One E1 já possuía `EvidenceBundle` e `ObservedText` com SHA-256, mas faltava uma adaptação que respeitasse o escopo textual de E1.

Novo `src/tapi_gate0/multimodal_system_one_bridge.py`:
1. `bridge_verified_synthetic_report` **só** aceita relatório com os controles de laboratório sintético, integridade temporal/asset, política `engineering_gate_passed`, verificações do relatório original pelo `multimodal_semantic_replay.validate_report` e `validate_asset_binding` por conteúdo. Não aceita flag de bypass, mídia arbitrária nem declaração de direitos genérica.
2. Gera um `EvidenceBundle(source_kind=synthetic)` **por observação textual**. Legenda = `caption`; fragmento de áudio = `transcript`. Cada item tem locator contendo SHA da mídia, SHA do texto e, para áudio, limites temporais e SHA do PCM de origem. Dois trechos não são concatenados para fabricar uma CTA.
3. Usa somente `DeterministicTextDecider` do E1 para emitir candidatos textuais, de modo offline e sem inferência remota. OCR/VLM não são promovidos a `ObservedText`, pois o contrato E1 não inclui essas modalidades. Se não houver evidência textual elegível, o E1 recebe `observation=None` e abstém.
4. O relatório retornado é `SYNTHETIC_TEXT_CANDIDATES_ONLY`, com SHA do relatório estruturado original, decisões com fingerprint verificável e invariantes `scientific_admissions=0`, `independent_gold=false`, `rubric_assessments_written=0`, `external_data_accessed=false`, `database_mutated=false`, `production_approved=false`, `global_gates_released=false`.
5. Contagem `text_observation_count` considera **apenas** legendas/transcrições reais. Placeholders de abstenção não contam como texto.

6. Cada observação textual também registra `observation_provenance_sha256`, calculado de SHA da mídia, ID do caso, modalidade, SHA do texto e locator exato com timestamps. Dois trechos idênticos de áudio em instantes distintos permanecem rastreáveis com hashes diferentes. O fingerprint E1 anterior **não** era sensível a locators e não foi alterado.
7. `case_text_consensus` reúne candidatos textuais por campo somente para uso exploratório. Se legendas e áudio oferecerem valores conflitantes, retorna `CONFLICTING_TEXTUAL_CANDIDATES` e **abstém** para o campo; se concordarem, fornece supports com hash de proveniência. Sem âncora, `NO_TEXTUAL_CANDIDATE`. Jamais promove a etiqueta a gold ou rubrica canônica.

`scripts/a06_system_one_bridge.py` expõe um fluxo executável offline usando somente `artifacts/private`, arquivo de entrada já existente, HEAD Git exato, SHA-256 **dos bytes de entrada** e arquivo novo de saída. O script não aceita caminho arbitrário, não sobrescreve relatório anterior, impede symlinks finais e em falha emite apenas `A06_E1_SYNTHETIC_BRIDGE_BLOCKED`.

### Exemplo de uso local

```powershell
git rev-parse HEAD
python -m scripts.a06_system_one_bridge --expected-head <SHA-completo-do-checkout> --input-name <relatorio-sintetico.json> --input-sha256 <sha256-dos-bytes-de-entrada> --output-name <novo-recibo-a06-e1.json>
```

Os marcadores são argumentos ilustrativos, não arquivos ou SHAs fornecidos por este documento. A origem deve ser o relatório *realmente validado* do benchmark sintético da instalação local. Nenhum modelo deve ser baixado nem fonte de terceiro processada para satisfazer o comando.

## Verificações e limitações reais

- `tests/test_multimodal_system_one_bridge.py`: **18 casos** (9 funções + 7 expansões parametrizadas), cobrindo hash de legenda, transcript fragmentado, conflitos, abstenção em OCR-only, flags inválidas, integridade temporal, validador real incompleto, duplicações e identificador de tenant inválido.
- `tests/test_a06_system_one_bridge_cli.py`: **8 casos** (6 funções + 2 expansões), cobrindo SHA da entrada, output novo e privado, bloqueio de caminhos, HEAD inválido, falhas sanitizadas e pasta privada ausente.
- **26 PASS no ambiente isolado após a atualização**, com o **mesmo código fonte** dos dois módulos e testes publicado no GitHub (checksums de conteúdo comparados). O ambiente isolado utilizou dublês para o validador AV completo e partes do contrato E1: esse resultado testa a ponte e a segurança do CLI, **não** avalia a inferência real do benchmark.
- **A11 agora tem sete etapas**: zero-spend, sintaxe, Python A05/A07 (269 casos esperados), Python A06/E1 (26), A07 CDP (13), Node (19) e Chrome (7). O recibo nunca libera gates nem o único sink IMP-131.
- **Não foi executada** a regressão integrada A11, A00, processamento nativo FFmpeg/Whisper/Tesseract/VLM ou teste científico independente no novo HEAD; sem CI. O Strict A02 continua com **6 PASS e 2 FAIL** no histórico — ambos na porta ASR WER — e não deve ser contado como aprovado.

## Próximas dependências da arquitetura

Integrar o supervisor e seus `EvidenceBundle` operacionais sob vault/grants reais sem depender de fixtures; executar a suíte no checkout limpo do SHA; fechar o ASR Strict e critérios multimodais, gold independente e avaliação científica; conectar agentes, sistema editorial, Studio e observabilidade/recuperação segundo CAP/IMP/CT do Plano Único.

Até lá, a ponte fica estritamente **sintética, textual, experimental e offline**. Sem merge na main, migração operacional, concessão de direitos, gasto, publicação ou deploy.


## Incremento de consenso textual e identidade temporal

Esta revisão adicionou dois casos focais: concordância entre legenda e áudio sem promoção a avaliação científica; e texto idêntico em dois intervalos de áudio com provenance hashes distintos, apesar de fingerprints E1 legados iguais. Também reforçou os testes já existentes de conflito e abstenção OCR-only. **26/26 testes isolados PASS** e parse Python 3.11 PASS nos dois arquivos alterados. Isso não resolve A02 Strict nem verifica os modelos verdadeiros ou as licenças de terceiros. O pacote A11 foi atualizado para **26 casos esperados** no grupo A06/E1, mantendo 269 A05/A07 e todos os gates bloqueados.
