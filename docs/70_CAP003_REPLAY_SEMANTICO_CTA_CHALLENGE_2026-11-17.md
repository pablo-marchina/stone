# CAP-003 / IMP-064 — replay semântico PASS e challenge CTA (17/11/2026)

## Operador HEAD b5cae78
22 PASS / 1 deselected em tapi-s1 (0,93s); 1 PASS / 8 deselected
em tapi-asr (1,39s). Separação de ambientes confirmada; 23 testes
únicos aprovados. Zero-spend PASS no run anterior 4664064; não foi
reexecutado neste log.

a6-multimodal-semantic-20261117-175610.json: source_report_sha256
4808374885f1ae860507aa513c93830b0cd62ca8ce062160896912e8f93ea4fc.
GLiNER revisão e173bca1f0c4217d7a55b3b0c705d5ece8a0218d, pesos
9efe0f88c99f2aa794452e9559dc60e98d60d9fa2bf1b60cf2710411b6da5b4e,
torch 2.15.0, gliner2 2.1.0, transformers 5.22.1, safetensors 0.8.0.
Carga 30243,326ms. Avisos Transformers de arquitetura gliner2/extractor
e depreciação torch.jit.script; execução concluída, preservar avisos.

| Braço | Lexical acertos/erros | Consenso PT/EN acertos/erros | Híbrido acertos/erros |
|---|---|---|---|
| caption_only | 4/1 | 4/1 | 4/1 |
| audio_only | 1/0 | 3/0 | 1/0 |
| ocr_only | 5/1 | 5/1 | 5/1 |
| caption_audio | 5/1 | 6/1 | 5/1 |
| caption_ocr | 8/0 | 8/0 | 8/0 |
| audio_ocr | 6/1 | 7/1 | 6/1 |
| all | 9/0 | 10/0 | 9/0 |

Denominador de 10 candidatos em 7 conteúdos, 3 campos pontuados;
não 10 conteúdos nem medida de acurácia populacional. Todos os gates
all PASS. Consenso sozinho recupera CTA salvar exclusivamente falado.
audio_only e agreement: WER 2/7=28,57%, regra NO_UNAMBIGUOUS_ANCHOR,
GLiNER PT/EN salvar, híbrido abstém no fragmento. São variantes da
mesma frase de referência, não 2 observações independentes.
audio_topic WER 0/9, PT sugeriu seguir, EN abstém, consenso abstém.
Conflito entre CTAs e negativo preservados. Não promover consenso
automaticamente; a concordância PT/EN é do mesmo modelo. Não se
conhece a transcrição exata pelos logs resumidos; não inventar erros.

## Challenge CTA separado
bd-multimodal-cta-challenge.v1: 24 casos autorais de texto, não clipes,
nem transcrição extraída de áudio real ou simulação calibrada de ASR.
Modalidade é contexto declarado da fixture, não prova de localização
temporal/espacial. 6 comandos explícitos, 6 paráfrases, 12 negativos
ou ambíguos (relato, negação, citação, hipótese, múltiplas ações,
conflito entre modalidades, frase separada). Cobre as 5 classes CTA.
Políticas lexical, modelo consensual e híbrida existentes intactas;
mesmos vetos; nenhum novo padrão aprendido a partir do replay.
Gate novo pré-declarado por variante: >=75% recall em cada estrato
positivo, zero candidatos incorretos em todos os casos, partição
completa. O exit 2 indica gate híbrido não aprovado e preserva
relatório. É esperado que a exigência de âncora literal limite
paráfrases; medir explicitamente, não flexibilizar após observar.
Nenhum resultado do challenge autoriza promoção do modelo.
CLI existente ganha modo --cta-challenge exclusivo com --input-name,
mesmo GLiNER pin, offline e arquivo privado sem sobrescrita.
Novos testes não executados pelo assistente. Sem dependências novas.

## VLM pré-voo PASS
RAM disponível 5524127744 bytes (~5,14 GiB), disco 8766050304 bytes
(~8,16 GiB), provision_disk_ready / run_memory_ready / run_disk_ready
true. Checkpoint ainda não verificado, VLM ainda não avaliado.
Provisão explícita de Qwen3-VL e runtime CPU b6907 conforme docs/69
permitida se os recursos continuarem disponíveis. Não carregar GLiNER
ou Whisper durante VLM. Não baixar por meio do benchmark.
Reexecutar pré-voo antes do download e da inferência; se memória
insuficiente, fechar aplicações não necessárias, sem apagar dados.

## Operador
```powershell
git pull --ff-only
git rev-parse --short HEAD
conda activate tapi-s1
$env:TAPI_SYSTEM_ONE_ENABLED="1"
$env:HF_HUB_OFFLINE="1"
$env:TRANSFORMERS_OFFLINE="1"
python -m pytest -q tests/test_multimodal_cta_challenge.py tests/test_multimodal_semantic_replay.py
python scripts/verify_zero_spend.py
$stamp=Get-Date -Format "yyyyMMdd-HHmmss"
python -m scripts.a6_semantic_replay --cta-challenge --model-dir "C:\Models\tapi\gliner25-multi-decide" --report-name "a6-multimodal-cta-challenge-$stamp.json"
```
Depois conda activate tapi-asr, seguir provisionamento e avaliação
VLM do docs/69. Sem repetir replay, áudio, OCR ou mux já aprovados.
Nenhum merge, gasto pago, mídia real, DB, classificação canônica,
admissão científica ou produção. Próximos: VLM e ablação ampliada,
cobertura dos 20 campos, direitos por ativo, Evidence Studio.
