# A02.7 — Fail-closed ASR WER no contrato estrito do shared AV (23/11/2026)

## Evidência observada no Windows

Checkout exato da PR #73: `22ecf6d9a9aba4d6a79c9a6377c3dcf842f034a1`. Ambiente `tapi-dec008-586aabf6`; preflight pré-teste `PREREQUISITES_OBSERVED_NOT_AUTHORIZATION`, física livre 6560 MiB, commit 11987 MiB; sem blockers.

Regressão integral: **2144 passed, 2 failed, 2 skipped em 2715.29s**, exit 1. Falharam exclusivamente:

- `test_shared_av_native_pipeline[discard_fixture4-complementary]`
- `test_shared_av_native_pipeline[discard_fixture5-audio_only]`

Ambos lançaram `ASRFixtureQualityError: ASR_FIXTURE_WER_GATE` dentro de `asset_shared_av_fixture._asr_result`, processando o terceiro adaptador (ASR/VAD); etapas temporal e OCR anteriores concluíram. O teste `test_partial_shared_av_native_pipeline[discard_fixture0-complementary]` havia demonstrado, na mesma configuração de host, `wer=0.5714285714285714` e `candidate_partial`, com abstinência para ASR e campos sem suporte. Não confundir 2144 testes aprovados com liberação de `G0-G6`.

Os 2 skips devem permanecer explicitamente fora da contagem de aprovação: `test_discovery_eval_engine.py:212` (privilégio de symlink Windows) e `test_evidence_lab.py:125` (tripleta de relatórios locais ausente).

## Causa raiz e política conservadora

A opção `mode=shared_av` vincula `STRICT_QUALITY` em `asset_fixture_pipeline._shared_quality_policy`. Quando `asr.result_from_output` calcula WER acima de 0,50, o adaptador **deve falhar fechado** com `ASRFixtureQualityError`, sem emitir payload ASR, sem executar VLM e sem concluir candidato.

O contrato `mode=shared_av_partial` é deliberadamente diferente: transforma somente uma falha de WER estruturalmente validada em `SharedAVQualityRejection` + abstinência `fixture_quality_rejected`; o `coverage_guard` precisa ser obrigatório e não pode tornar o diagnóstico uma evidência científica homologada. A regressão de `shared_av_partial` já exercita os oito cenários, inclusive `complementary` e `audio_only`.

O teste estrito de integração incluía incorretamente os dois cenários de rejeição de WER no conjunto que exige `candidate_complete`. Esta PR altera **somente a semântica dos testes**, sem rebaixar limite, alterar inferência, persistência ou autorização.

## Correção testável

1. `test_shared_av_native_pipeline` permanece cobrindo os seis cenários estritos cuja qualidade é admitida: `inventory`, `silence`, `agreement`, `conflict`, `screen_only` e `tone_negative`.
2. Novo `test_shared_av_strict_quality_rejection_no_payload`, parametrizado para `complementary` e `audio_only`, executa temporal e OCR reais, **exige `ASR_FIXTURE_WER_GATE`**, verifica `wer>0.50`, nenhum recibo/payload do ASR, nenhum job VLM e nenhuma conclusão indevida. O lease do trabalho recusado permanece `running` para reconciliação explícita; não há retry automático.
3. Novo `tests/test_a027_shared_av_quality_contract.py`: dois ensaios sintéticos offline distinguem propagação estrita da exceção de abstinência tipada no modo parcial, e verificam que a rejeição parcial não propaga `hypothesis_sha256`.

Esses testes **ainda não estão confirmados em Windows** neste novo commit. A alteração não "conserta" a taxa de erro de transcrição, e não transforma falha científica em ganho de qualidade. A avaliação de WER fora das fixtures continua pendente.

## Homologação ordenada

No HEAD exato desta PR:

```powershell
python -m pytest -q -rs --tb=short tests/test_a027_shared_av_quality_contract.py
python -m scripts.a11_native_host_preflight --expected-head (git rev-parse HEAD)
python -m pytest -q -s -rs --tb=short -k "test_shared_av_strict_quality_rejection_no_payload" tests/test_asset_rights_registry.py
```

Se os testes focais passarem, executar a regressão integral com registro de SHA256 e os dois skips identificados. Permanecem bloqueados DEC-008, G0-G6, IMP-131 e produção. A PR é draft e encadeada na PR #73; não realizar merge antecipado.
