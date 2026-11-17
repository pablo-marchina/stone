# CAP-003 / IMP-063 — ASR comparativo e OCR local (17/11/2026)

## Resultado do operador (preservado)
HEAD 327a5b7, ambiente tapi-asr Windows, 26/26 PASS 3,81s.
eSpeak NG 1.52.0, FFmpeg 8.1, faster-whisper 1.2.1, CTranslate2 4.9.0,
NumPy 2.4.6, tokenizers 0.23.3, HF Hub 1.33.0.
a6-asr-fixtures-20261117-151105.json: Small v1 FAIL, 13/31 erros,
WER agregado 41,935%; vendas 5/7, caixa 3/8, atendimento 1/9, CTA 4/7.
Silêncio/tom zero inserções; 6/6 executados; carga 2286,215ms.
Hash peso publicado verificado. Auxiliares registrados:
config b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828
tokenizer fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab
vocabulary 34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913
Não atestado independentemente. Nenhum gate científico/real aberto.

## Comparação ASR
Preservado Small e suite baseline v1, parâmetros CPU INT8, 4 threads,
pt, beam 5, sem prompt/VAD. Candidato Medium (MIT, ~1,53 GB)
Systran/faster-whisper-medium, rev 7832330bcea9a8d5fd6d6637c49fe5d256e98277,
SHA256 9b45e1009dcc4ab601eff815b61d80e60ce3fd8c74c1a14f4a282258286b51ae.
Hash publicado no commit de upload 4d9f76bb96174a5625e9ed85e89be563d98d528c,
config da revisão 7832330; rejeitar se divergência na máquina local.
Fontes:
https://huggingface.co/Systran/faster-whisper-medium/tree/7832330bcea9a8d5fd6d6637c49fe5d256e98277
https://huggingface.co/Systran/faster-whisper-medium/blob/4d9f76bb96174a5625e9ed85e89be563d98d528c/model.bin
Suite challenge v2: seis frases inéditas de negócios (estoque, custos,
planejamento, atendimento, preço, entrega), velocidades 135–180,
silêncio/tom/ruído pseudoaleatório com semente fixa. Mesmo gate v1 em
cada suite (WER <=30% agregado, <=50% cada frase, zero inserções sem fala).
Quatro combinações possíveis, resultados separados, challenge não é
teste independente, não é gold. Comparar somente se versão/PCM/condições
coincidirem. Nenhuma mudança nos parâmetros após observação.
Sem mudança de política; processamento real e produção continuam bloqueados.

## OCR v1
Tesseract local por+eng, OEM1/PSM11, imagem gerada 960x540, fonte default
do Pillow, quatro textos autorais (inclui acentos, polaridade inversa e
variação de tamanho), branco e geometria sem texto. SHA256 da imagem,
hash dos arquivos por/eng, versão, latência, caixas px, confiança bruta
(não calibrada), texto/hash, WER e CER normalizados NFC/casefold com
acentos preservados. Gate: WER agregado <=20%, cada frase <=40%, zero
palavras/caixas negativas, seis casos obrigatórios. Sem VLM, sem rubrica,
sem DB, sem imagem externa.
Smoke isolado Linux do mesmo layout e comando TSV (não suíte do repo):
sales/cash/cta exatos, price "PreXlo e margem de contribuikXo", blank
vazio, geometry "mão". Falha qualitativa nos negativos e acentos; não
alterar gate ou apagar resultado. A fonte default e pacote de idiomas
podem diferir entre plataformas; investigar uma versão futura.
https://tesseract-ocr.github.io/tessdoc/Installation.html
https://github.com/tesseract-ocr/tessdata_fast

## Operador
No ambiente tapi-asr, sem recriar ambiente:
```powershell
git pull --ff-only
python -m pytest -q tests/test_multimodal_asr.py tests/test_multimodal_ocr.py tests/test_multimodal_temporal.py tests/test_offline_visual.py
python scripts/verify_zero_spend.py
$small = "C:\Models\tapi\faster-whisper-small"
$medium = "C:\Models\tapi\faster-whisper-medium"
$env:HF_HUB_DISABLE_TELEMETRY="1"
$env:HF_HUB_DISABLE_IMPLICIT_TOKEN="1"
Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
python -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-medium',revision='7832330bcea9a8d5fd6d6637c49fe5d256e98277',local_dir=r'C:\Models\tapi\faster-whisper-medium',allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.txt'],token=False)"
$env:HF_HUB_OFFLINE="1"
$env:TRANSFORMERS_OFFLINE="1"
python scripts/a6_multimodal_readiness.py --check-ready --model-dir "$medium" --asr-candidate medium
$stamp=Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_multimodal_readiness.py --synthetic-asr --model-dir "$medium" --asr-candidate medium --report-name "a6-asr-medium-baseline-$stamp.json"
python scripts/a6_multimodal_readiness.py --synthetic-asr --model-dir "$small" --asr-suite challenge --report-name "a6-asr-small-challenge-$stamp.json"
python scripts/a6_multimodal_readiness.py --synthetic-asr --model-dir "$medium" --asr-candidate medium --asr-suite challenge --report-name "a6-asr-medium-challenge-$stamp.json"
```
Para OCR instalar Tesseract via winget/UB Mannheim, adicionar PATH e
verificar por+eng. Se faltar por, instalar ambos de uma release fixa
tessdata_fast (4.1.0), em diretório local separado; sem sobrescrever
dados existentes, registrar hashes. Exemplo:
```powershell
winget install --id UB-Mannheim.TesseractOCR --exact
$env:Path="C:\Program Files\Tesseract-OCR;$env:Path"
$tessdata="C:\Models\tapi\tessdata-fast-4.1.0"
New-Item -ItemType Directory -Force "$tessdata"
foreach ($lang in @("por","eng")) {
    $file=Join-Path $tessdata "$lang.traineddata"
    if (!(Test-Path $file)) { Invoke-WebRequest "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/$lang.traineddata" -OutFile $file }
}
tesseract --list-langs --tessdata-dir "$tessdata"
$env:TAPI_OCR_TEST_TESSDATA=$tessdata
python -m pytest -q tests/test_multimodal_ocr.py
$stamp=Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_multimodal_readiness.py --synthetic-ocr --tessdata-dir "$tessdata" --report-name "a6-ocr-fixtures-$stamp.json"
```
ASR/ OCR benchmark exit 2 em reprovação; relatório preservado.
Nenhuma nova suíte executada pelo assistente, apenas smoke OCR descrito.
VLM, fusão, ablação e integração Evidence Studio pendentes. Sem merge.
