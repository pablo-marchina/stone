# A02.7 — Diagnóstico redigido do decoder AV protegido (23/11/2026)

## Evidência operacional de nova falha

A PR #74 no SHA `860c1ce60c3278dfc51184bfb72f22ded3f38c80` foi testada no Windows `tapi-dec008-586aabf6`: preflight **PASS** com física livre 4975 MiB, commit disponível 10575 MiB, paths de fixture presentes e dependências nativas sem blockers. O alvo `-k test_shared_av_strict_quality_rejection_no_payload` terminou **1 passed, 1 failed, 161 deselected em 60.50s**, `STRICT_NATIVE_EXIT=1`.

A falha foi no caso `complementary` durante **decodificação** ao iniciar o terceiro step (`asr_vad`), e **não** na asserção de WER. `asset_windows_job.JobError: PROBE_OUTPUT_INVALID;stage=unknown;exception=unknown;reason=unknown;exit=0x00000001;peak_commit_bytes=117071872`. O caso `audio_only` passou. Um processo Python protegido saiu 1 antes do reconhecimento de fala; não se pode inferir que ffmpeg especificamente falhou, que foi problema de memória, nem que o resultado de ASR foi válido. Foi fail-closed; nenhum resultado inválido recebeu aprovação.

## Diagnóstico sem vazamento e sem diminuir proteções

A função `_decoder` gera o mesmo programa auditável de decoder para as authored fixtures. Antes, qualquer erro no child Python/FFmpeg com stderr descartado era classificado pelo host usando protocolo específico de *modelo*, produzindo `stage=unknown`. A PR introduz **somente** marcadores fixos de erro do child para as etapas `video`, `audio`, `frame` e `samples`, e razões `spawn`, `runtime`, `nonzero`, `size` e `digest`. Eles são aceitos **apenas** para `returncode=31`, payload curto e valores em whitelist. Erros desconhecidos/malformados continuam a falhar fechados, sem eco de mídia, paths, stderr, exceção ou dados de saída.

O sucesso continua exigindo comparação exata de hash, payload e tamanho do decoder gerado, verificação de execução em Windows Job Object, integridade de lineage, direitos e leases. O programa gerado agora tem SHA-256 diferente, implicando nova configuração vinculada por digest, mas nenhum limiar, grant, política de WER, origem do fixture ou código de fusão foi alterado. Não realizar retry implícito.

Os testes portáteis `tests/test_a027_shared_av_decoder_diagnostics.py` exercitam a falha ao iniciar um binário ausente, a saída não zero de um child e a rejeição de marcadores inválidos. **NOT_RUN no commit desta PR** até evidência real.

## Ações de aceite

1. Executar os testes locais/offline de contrato e diagnostics no HEAD exato desta branch, ou via CI controlada quando disponível.
2. Somente se PASS, executar a bateria nativa de dois casos estritos no Windows. O passo 2 é inevitavelmente dependente de Windows e das fixtures FFmpeg/TTS/ASR fixadas — não exigível no ambiente Linux do assistente.
3. Se falha aparecer de novo, registrar **somente** código sanitizado `AV_DECODE_FAILURE;stage=...;reason=...;exit=...`, sem compartilhar mídia, tokens ou paths de modelos. Se passar, a intermitência permanece uma questão a avaliar sob repetição; não declarar sua causa resolvida só porque passou.
4. Regressão integral e A11 após validação focal, com hashes e exit codes; skips não são PASS.

PR empilhada sobre #74; PR #72 e #73 preservadas. DEC-008, G0–G6, IMP-131 e produção continuam bloqueados; não há alterações de gasto externo ou autorização.
