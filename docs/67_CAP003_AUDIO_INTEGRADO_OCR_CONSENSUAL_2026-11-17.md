# CAP-003 / IMP-063 — áudio integrado PASS e OCR consensual v2 (17/11/2026)

## Operador HEAD 8f33230
70 PASS / 0 SKIP em 8,51s; zero-spend PASS.
a6-ocr-fixtures-retry-20261117-170511.json: renderer TSV corrigido,
Tesseract 5.4.0.20240606, Pillow 12.3.0, tessdata_fast 4.1.0.
WER 2/17=11,76%, CER 4%; sales/cash/cta exatos, price 2/5=40%,
blank sem detecção, geometry 1 palavra falsa. Gate FAIL. Não promover
OCR v1 à rubrica. Hash por c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb
e eng 7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2.

a6-vad-asr-fixtures-20261117-170511.json: PASS, WER 9/60=15%,
9/9 VAD, 0 chamadas ASR/0 palavras nos negativos, 7 chamadas no total,
1 silêncio digital abstido, RTF positivos 1,496–2,405, carga Medium
7434,734ms. Três variantes inventory 3/8 erros cada; custos, duas regiões,
planejamento exatos. 60 palavras incluem variantes/repetições.
Seleção experimental do pipeline silence guard -> Silero -> Medium
CPU INT8; não prova ganho de velocidade causal sem comparação pareada
contra áudio integral. Nenhum acesso real, DB, admissão, produção.

## OCR v2 separado
bd-ocr-consensus.v2: duas leituras do mesmo engine/pesos, sem afirmar
independência. Primária PSM11 imagem original; suporte PSM6 após
normalizar polaridade pela mediana da borda superior e autocontraste.
Não muda geometria. Matching recíproco único por token NFC/casefold,
acentos preservados, IoU de caixas >=0,5 e confiança bruta >=60
em ambas. Não é probabilidade calibrada. Mantém texto/caixa primários
e palavra/caixa de suporte, índice, IoU, hashes fonte e vista.
Palavras não aceitas não são reconstruídas; transcript é junção para
métrica, não prova de texto integral, complete_text_verified=false.
Sem heurística que exclua texto de uma palavra. Critérios mantidos:
WER <=20% agregado, <=40% cada positivo, zero negativos, ambas suites.
Baseline seis imagens v1; challenge separado nove imagens: estoque,
margem, uma palavra, entrega, oferta, baixo contraste, cinza vazio,
retângulos/linha, círculos. 15 casos totais. Relatório contém 3 braços
(primary/supporting/consensus) por suite; permite comparar mesmos
pixels e pesos. Não é ablação multimodal integral. Sem input real.

## Smoke Linux isolado
Tesseract 5.5.0/Pillow 12.3.0, hashes por/eng iguais aos Windows acima.
Reproduzidas 15 imagens, comandos, transformação e matching em script
isolado, não teste do módulo completo. Baseline consenso: sales/cash/cta
exatos; price "PreXlo e margem de" (2 erros, WER 2/17); blank e geometry
sem palavras (primary geometry "mão", supporting "não"). Baseline
simulado PASS. Challenge: margin "Margem de" (1 erro em 3);
demais positivos exatos; círculos "OOO" em ambas as leituras, retido.
Challenge FAIL, falso positivo correlacionado; não esconder, ajustar
gate ou confundir concordância com validade. Windows pendente.
A proposta dos dois braços foi fixada antes desse smoke; não alterar
v2 para encaixar o resultado. Próxima comparação tessdata_best 4.1.0
com mesmos parâmetros, mesmas imagens e relatórios separados.
Documentação upstream:
https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html
https://tesseract-ocr.github.io/tessdoc/Data-Files.html
https://github.com/tesseract-ocr/tessdata_best/releases/tag/4.1.0

## Operador
```powershell
git pull --ff-only
git rev-parse --short HEAD
$tessdata="C:\Models\tapi\tessdata-fast-4.1.0"
$env:TAPI_OCR_TEST_TESSDATA=$tessdata
python -m pytest -q tests/test_multimodal_ocr_consensus.py tests/test_multimodal_ocr.py tests/test_multimodal_vad_asr.py tests/test_multimodal_vad.py tests/test_multimodal_asr.py tests/test_multimodal_temporal.py tests/test_offline_visual.py
python scripts/verify_zero_spend.py
$stamp=Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_multimodal_readiness.py --synthetic-ocr-consensus --tessdata-dir "$tessdata" --report-name "a6-ocr-consensus-fast-$stamp.json"
```
Comparar segunda família oficial de pesos, sem sobrescrever Fast:
```powershell
$best="C:\Models\tapi\tessdata-best-4.1.0"
New-Item -ItemType Directory -Force "$best"
foreach ($lang in @("por","eng")) {
    $file=Join-Path $best "$lang.traineddata"
    if (!(Test-Path $file)) { Invoke-WebRequest "https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/4.1.0/$lang.traineddata" -OutFile $file }
}
tesseract --list-langs --tessdata-dir "$best"
python scripts/a6_multimodal_readiness.py --synthetic-ocr-consensus --tessdata-dir "$best" --report-name "a6-ocr-consensus-best-$stamp.json"
```
O download público explícito é separado do benchmark local; hashes
registrados, não atestação independente. Gate exit 2 preserva relatório.
Não repetir áudio já aprovado; não descarregar checkpoints VLM grandes.
Próximos: OCR challenger/alternativa visual, benchmark VLM sob limites
de recursos, composição/ablação entre modalidades, integração Studio e
escopo autorizado por ativo. Novos testes do repositório ainda não
executados pelo assistente; somente smoke isolado descrito. Sem merge.
