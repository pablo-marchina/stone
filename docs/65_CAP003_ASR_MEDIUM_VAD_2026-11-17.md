# CAP-003 / IMP-063 — baseline ASR Medium e VAD independente (17/11/2026)

## Resultados do operador
HEAD f1b8458: 50 PASS, 1 SKIP OCR esperado, 7,29s; zero-spend PASS.
Disco C: 8655368192 bytes livres (~8,06 GiB). RAM utilizável 16208592 KiB
(~15,46 GiB), livre 2135084 KiB (~2,04 GiB); Intel Graphics. AdapterRAM
não é garantia de VRAM dedicada. CUDA não demonstrado. Não baixar
VLM grande ou carregar modelos simultaneamente sem avaliação de recursos.
9/9 hashes PCM iguais entre Small/Medium challenge v2.

| Candidato | Suite | WER | Erros/referência | Inserções negativos | Gate |
|---|---|---:|---:|---:|---|
| Small | v1 | 41,94% | 13/31 | 0 | FAIL |
| Small | v2 | 33,33% | 17/51 | 223 | FAIL |
| Medium | v1 retry | 9,68% | 3/31 | 0 | PASS |
| Medium | v2 | 11,76% | 6/51 | 0 | PASS |
| Medium | v3 guarded | 11,76% | 6/51 | 0 | PASS |

Relatórios a6-asr-medium-baseline-retry-20261117-154942.json e
a6-asr-medium-guarded-20261117-154942.json. Medium v1+v2: 9/82 erros
(10,98%) em 10 frases distintas; v3 repete v2, não somar suporte.
Guard: 3/3 silêncios digitais abstidos, 0,484–1,406ms; 4 negativos
tom/ruído efetivamente inferidos sem palavras. Seis frases v3 mantêm
WER e casos v2. Causa do bloqueio anterior não identificada; retry PASS.
Medium CPU INT8 selecionado como baseline experimental, não homologado.
Não houve transcrição real, gold, admissão, rubrica, acesso externo ou DB.
OCR ainda sem Tesseract.

## VAD v1 — avaliação independente
faster-whisper 1.2.1 inclui Silero VAD v6 ONNX e dependência onnxruntime
(https://raw.githubusercontent.com/SYSTRAN/faster-whisper/v1.2.1/faster_whisper/vad.py,
https://raw.githubusercontent.com/SYSTRAN/faster-whisper/v1.2.1/requirements.txt).
Usa asset local silero_vad_v6.onnx, SHA256 registrado antes/depois
(não independente), CPU provider upstream, sem download, sem carregar
Whisper. Opções fixas antes de executar: threshold 0,5, min fala 250ms,
min silêncio 300ms, pad 150ms. PCM 16kHz mono, max 15s.
9 fixtures: 3 frases com padding 2s antes/1s depois; 1 fala atenuada
a 25% amplitude, 1 mistura com ruído seed fixo atenuado, 1 caso duas
regiões de fala separadas por 2s; negativos silêncio/tom/ruído.
Referência é intervalo de TTS inserido após trim de zeros digitais,
não anotação fonética. Intervalos observados em índices de amostra
PCM, não PTS original. Validação de limites e ordenação, IoU, erro
máximo de fronteira, duração falso positivo e fala perdida.
Gate experimental: IoU >=0,60 por positivo, mesma quantidade de
intervalos, erro máximo de fronteira <=0,75s, 0s de fala detectada nos
negativos, todos os 9 casos. Não calibrar após observar sem nova versão.
Não testa integração VAD+ASR, não substitui guard, não valida mídias reais.
Nenhum caminho arbitrário de áudio aceito. CLI relatório privado exclusivo.
Testes unitários adicionados; execução Windows pendente. Não executados
pelo assistente. Nenhum novo download necessário para VAD se instalação
existente contém asset/onnxruntime.

## Execução
```powershell
git pull --ff-only
git rev-parse --short HEAD
python scripts/a6_multimodal_readiness.py --check-ready
python -m pytest -q tests/test_multimodal_vad.py tests/test_multimodal_asr.py tests/test_multimodal_temporal.py tests/test_multimodal_ocr.py tests/test_offline_visual.py
python scripts/verify_zero_spend.py
$stamp=Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_multimodal_readiness.py --synthetic-vad --report-name "a6-vad-fixtures-$stamp.json"
```
Se faltar eSpeak no PATH: $env:Path="C:\Program Files\eSpeak NG;$env:Path";
$env:ESPEAK_DATA_PATH="C:\Program Files\eSpeak NG".
Caso VAD falhe, manter relatório; não ajustar gate retroativamente.
OCR: executar instalação/provisionamento pequenos conforme docs/63
e benchmark, sem carregar Whisper/VAD ao mesmo tempo.
VLM, fusão, ablação integrada, direitos por ativo e Evidence Studio
continuam pendentes; nenhuma liberação de produção ou merge.
