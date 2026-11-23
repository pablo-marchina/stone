# PR #77 — Reparos determinísticos dos testes portáteis A02.7/A11 (23/11/2026)

## Evidência de execução (operador Windows)

Em HEAD `bfb70e41146e951a2b4df25e7779db69e0568132` da PR #76: `47 passed, 2 failed in 11.60s`, `PORTABLE_FOCAL_EXIT=1`, 49 casos coletados nos quatro arquivos de teste. Falhas:

1. `tests/test_a027_shared_av_decoder_diagnostics.py::test_decoder_child_nonzero_reports_only_allowlisted_stage`: esperado `TAPI_AV_DECODE_FAIL:video:nonzero`, observado `TAPI_AV_DECODE_FAIL:video:size`.
2. `tests/test_a11_focal_evidence_packet.py::test_true_sqlite_signed_rights_batch_is_a_separate_blocking_a11_stage`: assert de presença de hash do teste `test_a027_shared_av_quality_contract.py` em `receipt["source_sha256"]` falhou.

Nenhum destes resultados exige mudança em WER, dados reais, Windows Job Object, grants ou autorização científica.

## Causas e correções

**Subprocesso determinístico.** O teste tentou provocar `nonzero` passando `sys.executable` como se fosse FFmpeg. O argumento `-hide_banner` começa por `-h`; o Python de Windows/Linux pode imprimir ajuda e sair com código zero, o que corretamente produz o diagnóstico `video:size`, não `video:nonzero`. O teste novo substitui **somente no processo filho sintético do próprio teste** `subprocess.run` por um `CompletedProcess(..., returncode=17)`, garantindo de modo portátil que o código real do decoder exercite exatamente o caminho `nonzero`. O decoder, Job Object, timeout, redaction e todas as checagens de produção ficam intactos.

**Inventário A11.** A fixture de teste `local_files` trocava `SOURCE_FILES` por um subconjunto fixo, mesmo depois da introdução de fontes pinadas no pacote real, de modo que o recibo *mockado* não continha os novos hashes. Agora a fixture cria bytes fictícios para **todas** as entradas reais em `packet.SOURCE_FILES`, sem sobrescrever seu inventário. Os asserts passam a fiscalizar o mesmo inventário que o empacotador utiliza; não simulam execução de teste ou admissão de direito.

**Validação direta no ambiente do assistente (sem repo privado completo):** reprodução isolada do child Python após a injeção test-only retornou exit 31 e o marcador exato `TAPI_AV_DECODE_FAIL:video:nonzero`; executou também a invocação problemática de CPython com flags de FFmpeg e observou exit 0, confirmando a razão do erro. **Isso não é pytest da PR inteira.**

## Estado e aceite

Modificados exclusivamente `tests/test_a027_shared_av_decoder_diagnostics.py` e `tests/test_a11_focal_evidence_packet.py`; nenhum código de produção. As metas A11 permanecem `16/16` na etapa A02.7 e `407/407` na A05/A07, 10 etapas ao todo. A PR #77 é draft sobre #76. O novo SHA exige execução dos quatro arquivos portáteis (sem modelos) antes de afirmar PASS. Regressão integral Windows de 45 minutos e novas cargas nativas *não são necessárias nesta etapa*. G0-G6 / IMP-131 BLOCKED, DEC-008 OPEN e produção não autorizada.
