# CAP-003 / IMP-063 — VAD aprovado, renderer OCR e integração áudio (17/11/2026)

## Resultado do operador
HEAD 8e6d0b3, 61 PASS / 1 SKIP OCR esperado, 10,51s; zero spend PASS.
a6-vad-fixtures-20261117-155804.json: 9/9 PASS, IoU positivo médio
0,9297548175; mínimo 0,9126260, fronteira máxima 0,2291875s,
zero segundos perdidos nas regiões TTS e zero positivos nos três
negativos. Seis positivos têm padding excedente (0,25–0,331s), não
confundir com zero falso positivo em todos os casos. 6,9–25,6ms inferência.
Asset silero_vad_v6.onnx SHA256
4cbf549b8326f60f80f2536d9eefeb450a9abe83365a098031c89719f1be17d2,
observado localmente, não atestado independentemente; ONNXRuntime 1.32.0.
Selecionado Silero VAD baseline experimental, não homologado.
Tesseract Windows 5.4.0.20240606 já instalado; PATH ajustado; por+eng
tessdata_fast 4.1.0 disponíveis. OCR 10 PASS / 1 FAIL integração:
OCR_INVALID_TSV, stdout texto simples "Organize suas vendas".
Não há WER/CER Windows medido nem gate OCR avaliado.

## Correção OCR
Reproduzido em Linux Tesseract 5.5.0 com pasta temporária contendo
apenas por.traineddata/eng.traineddata do sistema: comando original
tsv retorna stderr "Can't open tsv" e stdout texto simples.
O config nominal tsv depende de tessdata/configs/tsv. Substituído por
-c tessedit_create_tsv=1 -c tessedit_create_txt=0; mantém por+eng,
OEM1/PSM11, imagens, parser estrito e gate v1. Não aceitar texto simples.
Smoke real isolado Linux: TSV header e boxes corretos nos seis casos;
sales/cash/cta exatos, price "PreXlo e margem de contribuikXo", blank
vazio, geometry "mão". Confirma correção do renderer, não qualidade;
Linux linguagens/fontes não necessariamente iguais às do Windows.
Novos testes regressão do comando e rejeição de texto puro.
Não alterar os critérios após observar resultado.

## Integração VAD + ASR
bd-vad-asr-fixture.v1, Medium fixado, CPU INT8, mesmos parâmetros
anteriores. Nove fixtures VAD v1, seis positivas (60 palavras contando
repetições/variantes, não 60 palavras independentes), três negativas.
PCM hash integral + hash dos chunks, índices start/end, referências
TTS autorais, WER, RTF, tempos VAD/ASR separados. Guard silêncio digital
exato antes do VAD; VAD avalia restantes. Sem regiões, zero chamadas
ao Whisper e abstenção NO_VAD_SPEECH_REGION. VAD processa todo lote e
limpa cache antes de carregar Whisper; não implica prova de liberação
total de RAM pelo SO. Cada região é transcrita separadamente, sem
concatenar pausas. Timestamp original do modelo preservado no chunk;
offset remapeia à timeline PCM. Limite de final do segmento pode ser
recortado apenas dentro da tolerância existente 250ms, com flag e
coordenada bruta, sem atribuir texto a região não processada.
Não é PTS original, alinhamento humano ou prova semântica.
Gate pré-definido: 9/9 VAD, WER agregado <=30%, individual <=50%,
zero inserções e zero chamadas ASR nos três negativos, todos os casos.
Benchmark independente v1 VAD e ASR v1/v2/v3 não alterados.
Sem novos downloads, mídia externa, rubrica, banco, admissão ou release.
Testes novos não executados integralmente pelo assistente; smoke OCR
isolado executado conforme acima.

## Operador
```powershell
git pull --ff-only
git rev-parse --short HEAD
$env:Path="C:\Program Files\Tesseract-OCR;C:\Program Files\eSpeak NG;$env:Path"
$env:ESPEAK_DATA_PATH="C:\Program Files\eSpeak NG"
$tessdata="C:\Models\tapi\tessdata-fast-4.1.0"
$env:TAPI_OCR_TEST_TESSDATA=$tessdata
python -m pytest -q tests/test_multimodal_ocr.py tests/test_multimodal_vad_asr.py tests/test_multimodal_vad.py tests/test_multimodal_asr.py tests/test_multimodal_temporal.py tests/test_offline_visual.py
python scripts/verify_zero_spend.py
$stamp=Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_multimodal_readiness.py --synthetic-ocr --tessdata-dir "$tessdata" --report-name "a6-ocr-fixtures-retry-$stamp.json"
$medium="C:\Models\tapi\faster-whisper-medium"
$env:HF_HUB_OFFLINE="1"
$env:TRANSFORMERS_OFFLINE="1"
python scripts/a6_multimodal_readiness.py --synthetic-vad-asr --model-dir "$medium" --asr-candidate medium --report-name "a6-vad-asr-fixtures-$stamp.json"
```
Se OCR gate FAIL, guardar relatório e avaliar versões posteriores
separadamente. Não instalar VLM grande ainda devido a RAM/disco.
Próximos: diagnóstico de erros OCR (fonte/modelo/preprocessamento),
VLM, composição e ablação multimodal, direitos por ativo, Evidence
Studio. Nenhuma autorização de mídia real derivada de gates sintéticos.
