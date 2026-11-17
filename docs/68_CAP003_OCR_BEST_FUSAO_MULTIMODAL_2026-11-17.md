# CAP-003 / IMP-063/064/136 — OCR Best e composição de evidências co-referenciadas (17/11/2026)

## Operador
HEAD c342d41, 78 PASS em 20,82s, zero-spend PASS.
a6-ocr-consensus-fast-20261117-171244.json: ambos splits FAIL,
WER 2/17 baseline e 1/17 challenge, 3 falsos positivos consensuais
(geometria, linhas, círculos).
a6-ocr-consensus-best-20261117-171244.json: ambos splits PASS,
WER 2/17 baseline e 1/17 challenge, zero negativos nos cinco casos.
WER agregado 3/34=8,82% (duas suites distintas), CER baseline 8%
(vs Fast 4%), challenge 13,13% ambos. Primário e suporte Best
reprovados nos negativos. Consenso Best escolhido baseline experimental
pela redução dos falsos positivos, não melhor WER/CER.
Hash por 711de9dbb8052067bd42f16b9119967f30bada80d57e2ef24f65d09f531adb04
e eng 8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba.
Esses hashes são observações locais, não atestação independente.
Pillow 12.3.0, Tesseract 5.4.0.20240606. Não tratar palavras parciais
como texto completo verificado. Fast e Best usaram fixtures definidas
igualmente; hashes de pixels de relatórios completos ainda não comparados.

## Incremento
multimodal_fusion.py: 20 campos com estado explícito; somente
tema_principal, tipo_cta, tem_cta derivado, texto_na_tela podem receber
candidatos. Reusa âncoras lexicais da regra grounded v1 (não GLiNER,
não aplica o gate híbrido de legendas). Nenhuma inferência de ausência,
tom, rosto, empreendedor real, hook ou pontuação. Veto de contexto
ou múltiplas âncoras; conflito entre modalidades leva a abstenção;
não concatenar texto de segmentos ou frames separados. OCR sem
sequência integral retida nas duas leituras só pode fornecer candidato
positivo de texto na tela, não âncora semântica. Mesmo sequência
integral retida não prova recuperação completa.
Sete braços: caption, audio, OCR isolados, os três pares e todos.
Métricas por campo: acertos candidatos, falsos candidatos, abstidos,
precisão/recall de candidatos (não acurácia populacional). Mesmo alvo
autoral em todos os braços. Não é ablação final GLiNER/VLM/metadata.

multimodal_shared_fixture.py: 7 clipes autorais de 6s, 960x540 cinza
4fps, FFV1+PCM mono 16kHz em MKV temporário; caption é contexto
autoral associado ao caso, não stream embutido. Verifica igualdade
byte a byte de pixels/PCM decodificados e hash do arquivo, frames
0s e 3s para OCR, amostras 4fps/64x64 para transições. Guarda
leituras OCR positivas/negativas, hashes de frames/vistas, boxes,
segmentos ASR e hashes PCM, caption e vínculo por ativo.
Pipeline OCR -> VAD -> limpeza de cache -> Whisper Medium CPU INT8
-> composição. Fixados hashes locais OCR Best e VAD observados,
peso Medium verificado pelo mecanismo anterior. Sem novo download.
Cenários: legenda isolada, fala isolada, OCR tardio isolado,
concordância, conflito CTA, negativo/negação+geometria, tema áudio.
Gate pré-declarado: todos os 7 casos, transições/integridade,
zero chamadas ASR quando a fixture não contém fala; no braço all,
zero candidatos errados e recall >=75% para tema, tipo_cta,
texto_na_tela. Tem_cta derivado; demais campos não avaliados.
Alvos autorais pequenos, alguns textos reutilizados de benchmarks,
não conjunto independente. Não usar resultados para validação real.
CLI --synthetic-shared-multimodal exige Medium explícito e tessdata
Best; relatório privado exclusivo. Sem input arbitrário, DB, mídia
externa, rubrica canônica, gold, VLM, publicação ou custos.

## Verificação
Smoke isolado Linux dos comandos FFmpeg em clipe OCR tardio:
24 frames, 12441600 bytes de vídeo e 192000 bytes de PCM decodificados
iguais às fontes, MKV 252339 bytes, transição 3,0s (diferença 0,89585).
Não é execução completa do módulo/ASR/OCR/fusão. Novos testes ainda
não executados integralmente pelo assistente; operador Windows pendente.

## Execução Windows (tapi-asr)
```powershell
git pull --ff-only
git rev-parse --short HEAD
$medium="C:\Models\tapi\faster-whisper-medium"
$best="C:\Models\tapi\tessdata-best-4.1.0"
$env:HF_HUB_OFFLINE="1"
$env:TRANSFORMERS_OFFLINE="1"
$env:TAPI_OCR_TEST_TESSDATA=$best
python -m pytest -q tests/test_multimodal_fusion.py tests/test_multimodal_ocr_consensus.py tests/test_multimodal_ocr.py tests/test_multimodal_vad_asr.py tests/test_multimodal_vad.py tests/test_multimodal_asr.py tests/test_multimodal_temporal.py tests/test_offline_visual.py
python scripts/verify_zero_spend.py
$stamp=Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_multimodal_readiness.py --synthetic-shared-multimodal --model-dir "$medium" --asr-candidate medium --tessdata-dir "$best" --report-name "a6-shared-multimodal-$stamp.json"
```
Em caso de reprovação, preservar relatório. Verificar espaço/RAM antes
de baixar VLM grande. Próximos: Qwen3-VL sob orçamento computacional,
ablação com VLM e modelo semântico, cobertura 20 campos calibrada,
asset rights e Evidence Studio. Sem merge ou gate global liberado.
