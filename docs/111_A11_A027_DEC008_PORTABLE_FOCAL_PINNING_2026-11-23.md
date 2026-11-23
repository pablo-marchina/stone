# A11 / A02.7 / DEC-008 — pinagem focal portátil e falsificação de autoridade (23/11/2026)

## Objetivo

Acelerar a convergência da arquitetura v6.1 sem confundir testes sintéticos com autorização operacional. Reforçar o pacote focal A11 para que as correções fail-closed recentes da A02.7 não fiquem apenas na regressão integral longa; aumentar a cobertura de superfície nativa DEC-008 com tentativas explícitas de elevação de autoridade sem escrever no ledger.

## Mudanças desenvolvidas

- `scripts/a11_focal_evidence_packet.py` inclui, na etapa existente `python_a027_integrated`, duas suítes portáteis adicionais: `tests/test_a027_shared_av_quality_contract.py` (2) e `tests/test_a027_shared_av_decoder_diagnostics.py` (7). A contagem esperada da etapa **7 -> 16**. O número total de etapas A11 continua **10**; saída, hashes, gates e recusa de skips/falhas não são relaxados.
- `SOURCE_FILES` passa a vincular via SHA-256 os novos testes e o código que eles cobrem: `asset_shared_av_fixture.py`, `asset_asr_fixture.py` e `asset_windows_job.py`. Uma futura alteração em qualquer um desses arquivos muda o digest do pacote.
- Um caso novo em `tests/test_dec008_resume_preflight.py` testa 16 corrupções de recibo nativo: flags de direitos, ouro independente, validade científica, autorização de Studio/publicação/produção/gates, falsa execução do nó, contadores de modelo incorretos, revisão falsa, cursor/chain falsificados e campo extra. Todos devem ser negados e não podem modificar a quantidade de eventos SQL. A etapa `python_a05_a07` aumenta **406 -> 407**.
- `tests/test_a11_focal_evidence_packet.py` atualiza asserts de contagens, invocações obrigatórias, inventário de fontes e a negação sintética quando falta um caso. Não modifica autorização ou persistência de produção.

## Escopo e evidência

O pacote da Base Atemporal v6.1 fornecido contém **204 IMP, 543 dependências, 23 CAP**, DAG acíclico e sink final IMP-131. A trilha crítica de estimativas históricas soma **301 h**, dentro de **1.561 h** totais estimadas. **Essas horas são estimativas do plano, não horas restantes ou progresso medido**. O principal ganho em velocidade é reprovar mais cedo alterações que comprometem direitos, recuperação ou qualidade dos adapters, antes do A11/CT completo.

Este incremento foi gravado em GitHub como código, mas **não houve execução de pytest da nova branch em Windows/Linux com checkout completo neste ambiente**. Não declarar 16/16 ou 407/407 PASS antes de resultado real. As últimas evidências de execução permanecem:

- PR #72, pacote focal anterior: 10/10 etapas; 406/406 A05/A07 (em HEAD `c2815cd3...`);
- PR #73, regressão integral: 2144 PASS / 2 FAIL / 2 SKIP (em HEAD `22ecf6d9...`);
- PR #74, strict native: 1 PASS / 1 FAIL (decoder `exit=1` no caso complementary; `audio_only` passou);
- PR #75, strict complementary: 1 PASS em 34.50s no HEAD `351e623e...`, sem reproduzir o erro de decoder anterior.

## Sequência de validação sem gasto

1. No checkout completo, `python -m pytest -q -rs --tb=short tests/test_a027_shared_av_quality_contract.py tests/test_a027_shared_av_decoder_diagnostics.py tests/test_dec008_resume_preflight.py tests/test_a11_focal_evidence_packet.py`.
2. Se PASS, `python -m scripts.a11_focal_evidence_packet --expected-head SHA_EXATO --output CAMINHO_NOVO.json`; respeitar read-only, sem fontes externas, e não aprovar skips.
3. Investigação de intermitência AV nativa ainda exige Windows Job Object + modelos fixados; não reproduzir indiscriminadamente regressões de 45 minutos antes de estabilizar cenários focais. Se a falha reaparecer, registrar marcador sanitizado de estágio.
4. Após homologação focal, executar regressão integral em HEAD exato e validar formalmente requisitos/capacidades/CT, independente gold e autorização de dados/fontes, antes da aprovação de release indivisível.

**Status:** implementado, NÃO EXECUTADO no commit novo; DEC-008 OPEN; G0–G6 e IMP-131 BLOCKED; produção, publicação e uso de mídia não autorizados.
