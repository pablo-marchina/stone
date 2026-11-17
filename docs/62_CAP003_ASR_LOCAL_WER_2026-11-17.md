# CAP-003 / IMP-063 — ASR local e benchmark de WER (17/11/2026)

## Baseline e execução anterior
Plano Único v5.2 IMP-063 (áudio/vídeo autorizado, hash, frame/timecode,
WER/temporal e ablação), IMP-136 (atributos temporais não observáveis sem
modalidade), IMP-064/065 e IMP-083 dependentes. Arquitetura v5.2 escolhe
faster-whisper como candidato de ASR, Qwen3-VL candidato de VLM, OCR/visão
local. Não altera critérios institucionais, DEC-016/017/018 ou gates.
Operador HEAD d5b57b9: 117 testes focais PASS 18,32s, zero-spend PASS.
a6-multimodal-temporal-20261117-145844.json: 3/3 fixtures PASS; 12 frames
por clipe, duração 3s, transições sem erro, PCM 3,008s. FFmpeg/ffprobe 8.1,
OpenCV e NumPy disponíveis; Tesseract/faster-whisper ausentes. Nenhum
vídeo real, ASR/VLM, rubrica ou admissão científica.

## Incremento
multimodal_asr.py: checkpoint multilíngue small (MIT, 486 MB) de
Systran/faster-whisper-small, revisão 536b0662742c02347bc0e980a01041f333bce120,
SHA256 publicado model.bin
3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671.
Exige config.json, tokenizer.json, vocabulary.txt e model.bin local
sem arquivos extras além de .cache; hashes dos arquivos auxiliares
registrados e verificados antes/depois, não comparados a hashes publicados.
faster-whisper==1.2.1; CPU int8, quatro threads, idioma pt, beam 5,
temperatura zero, sem prompt de referência, sem VAD, sem download no
runner. HF_HUB_OFFLINE e TRANSFORMERS_OFFLINE antes de importação,
local_files_only e tokenizer obrigatório; não é sandbox de rede.
Seis fixtures: quatro frases autorais de negócios em pt-BR por eSpeak NG
local em velocidades diferentes; silêncio e tom 440 Hz sem fala.
Arquivos temporários removidos; FFmpeg PCM mono 16kHz, limite 15s.
Registra hash PCM, segmentos com timestamps estimados (não PTS original),
hash/texto, tempo de inferência, RTF, WER Levenshtein, erros e suporte.
Normalização NFC/casefold, pontuação removida, acentos mantidos.
Gate experimental proposto antes da execução: WER agregado <=30%,
cada frase <=50%, zero palavras inseridas em silêncio/tom, seis casos
obrigatórios. Não é homologação, WER populacional nem alinhamento temporal
validado. Gate falho gera relatório e exit 2. Sem rótulo ou DB.
Versões/latências registradas. Sem treino, API paga, licença de mídia
externa, mudança de política ou publicação.

Fontes públicas: https://pypi.org/project/faster-whisper/1.2.1/ ;
https://huggingface.co/Systran/faster-whisper-small/tree/536b0662742c02347bc0e980a01041f333bce120 ;
https://huggingface.co/Systran/faster-whisper-small/blob/main/model.bin ;
https://github.com/espeak-ng/espeak-ng/blob/master/docs/languages/roa/pt.md .

## Operador (PowerShell)
Atualizar branch e executar testes focais no tapi-s1 antes de instalar ASR.
Para isolar dependências do GLiNER, criar ambiente separado tapi-asr
(Python 3.11), instalar pacote editável e extras dev/asr_local. Instalações
públicas gratuitas são explícitas e separadas do benchmark offline.
```powershell
git pull --ff-only
python -m pytest -q tests/test_multimodal_asr.py tests/test_multimodal_temporal.py tests/test_offline_visual.py
python scripts/verify_zero_spend.py

conda create -n tapi-asr python=3.11 pip -y
conda activate tapi-asr
python -m pip install -e ".[dev,asr_local]"
python -m pip check
winget install --id eSpeak-NG.eSpeak-NG --exact --version 1.52.0
```
Se eSpeak não aparecer em PATH, reabrir PowerShell ou adicionar o
diretório de instalação à sessão; verificar Get-Command espeak-ng, ffmpeg.
Se ffmpeg estava apenas no ambiente tapi-s1, instalar binário gratuito
no novo ambiente ou configurar PATH para o mesmo binário já validado.

```powershell
$asrModel = "C:\Models\tapi\faster-whisper-small"
$env:HF_HUB_DISABLE_TELEMETRY = "1"
$env:HF_HUB_DISABLE_IMPLICIT_TOKEN = "1"
Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
python -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-small',revision='536b0662742c02347bc0e980a01041f333bce120',local_dir=r'C:\Models\tapi\faster-whisper-small',allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.txt'],token=False)"
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
python scripts/a6_multimodal_readiness.py --check-ready --model-dir "$asrModel"
python -m pytest -q tests/test_multimodal_asr.py tests/test_multimodal_temporal.py
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_multimodal_readiness.py --synthetic-asr --model-dir "$asrModel" --report-name "a6-asr-fixtures-$stamp.json"
```
Não usar endpoint de inferência hospedado nem token HF, Meta ou mídia real.
Não alterar gate após observar resultados; registrar falhas e avaliar nova
versão separadamente. Retornar ao ambiente tapi-s1 para pipeline de corpus.

## Estado
Código, testes e documentação publicados. Não executado benchmark ASR nem
suíte nova pelo assistente (modelo/eSpeak NG ausentes). Instalação e teste
real no Windows pendentes. Próximos: OCR local e VLM, composição de
evidências por campo, licença/escopo específico por ativo, ablação e
integração Agent/Evidence Studio. Gates globais permanecem bloqueados.
