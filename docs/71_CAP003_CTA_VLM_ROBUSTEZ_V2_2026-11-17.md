# CAP-003 / IMP-063/064 — falhas de robustez CTA/VLM, versões v2 (17/11/2026)

## Operador HEAD 90410c8
10 PASS em 0,83s, zero-spend PASS. Avisos GLiNER/torch anteriores
persistem; execução concluída.
a6-multimodal-cta-challenge-20261117-180039.json:
| Variante | Explícito | Paráfrase | Erros negativos | Recall total | Precisão candidato | Gate |
|---|---:|---:|---:|---:|---:|---|
| lexical | 6/6 | 0/6 | 0/12 | 50% | 100% | FAIL |
| model_consensus | 6/6 | 5/6 | 8/12 | 91,67% | 57,89% | FAIL |
| grounded_hybrid | 6/6 | 0/6 | 0/12 | 50% | 100% | FAIL |
Consenso acerta paráfrases p01–p05, abstém p06; falsos candidatos
n01–n05, n08, n10, n11 (relatos/menção/hipótese/múltiplas ações e
fragmentos incompletos). Não promover consenso, não chamar recall
de acurácia. Lexical/híbrido não substituídos; todos FAIL no desafio.

VLM Qwen3-VL-2B GGUF provisionado pelo operador, ambos SHA verificados,
1107409952 + 445053216 bytes, ZIP b6907 hash conferido; executável
4b7b76781602666a54170536852c0975c71b0344e9a3b2f9b9bc95d36713414d
observado (não atestação independente de DLLs).
a6-vlm-frames-20261117-180534.json, source_report_sha256
4808374885f1ae860507aa513c93830b0cd62ca8ce062160896912e8f93ea4fc.
RAM pré-voo 5442658304 bytes, disco 7151673344 bytes.
Carga 4630,751ms, 10 imagens únicas em 20 posições, 27,864–43,394s
por inferência única. Gate FAIL, zero JSON inválidos.
Shared presença texto yes 5/5, no 2/9; cena blank 7/7, geometry
0/2, text_card 5/5. Challenge presença yes 3/3, no 2/3; cena
blank 1/1, geometry 2/2, text_card 3/3. 8 posições com yes+blank
contraditórios, correspondem a 2 imagens únicas uniformes.
Cena geometry shared errada em 2 posições de 1 imagem única.
Agregado imagens únicas: presença yes 5/5, no 3/5; cena 9/10.
Não são amostras independentes, não estimar qualidade real.
Nenhuma mídia real, banco, admissão ou rubrica canônica.

## CTA v2 — directed request
bd-cta-directed-request.v2, nova regra com ação dirigida e objeto
de publicação/canal no mesmo fragmento; spans e hashes; veto
contextual original + hipótese; múltiplas ações ou conflito entre
fragmentos abstêm. Não concatenar modalidades. Híbrido exige consenso
PT/EN no mesmo fragmento que a âncora e ausência de conflito.
Gramática limitada, não prova de intenção geral. 24 casos v1 agora
explicitamente desenvolvimento observado; 24 novos casos autorais
adicionais (6 explícitos, 6 paráfrases, 12 negativos). Alvos e
gramática desenvolvidos juntos; não gold cego/independente.
Cinco variantes: três originais + directed_rule + directed_hybrid.
Gate por variante por split: >=75% recall em cada estrato positivo,
zero candidatos errados, partição completa. Gate de saída exige
directed_hybrid nos dois splits; preservar qualquer FAIL e não
selecionar variante automaticamente. Não alterar v1 nem integrar à
rubrica/legendas reais. CLI --cta-directed-challenge em tapi-s1.
Não é nova avaliação ASR, são textos surrogates autorais.

## VLM v2 — single scene
bd-vlm-single-scene.v2, mesmo checkpoint/runtime já provisionados.
Novo prompt e JSON com apenas scene: blank/text_card/geometry/uncertain.
Presença de texto derivada dessa classe, não medida independente.
Guard exato de uniformidade por extrema de todos os canais L/RGB,
sem OCR ou limiar de contraste; só fixtures opacas 960x540.
Se uniforme, blank/no, sem chamada VLM; se não uniforme e VLM
retorna blank, abstenção uncertain (não inventa geometry).
A definição literal de blank é própria da fixture; não permite
inferir ausência de texto no conteúdo real. Preserva model_scene,
hash da resposta e guard_reason. V1 intacto, parâmetros de servidor
default mantidos; v2 usa schema/prompt separados.
20 posições originais (observadas) + 6 novas autorais (duas
uniformes, duas geométricas, duas com texto incluindo OOO escrito).
Métricas por suite, por posição e imagem única, mesmas exigências
>=75% recall por classe, zero errado/invalid, todos 26 casos.
Sem esconder abstenção ou contar guard como acerto intrínseco VLM.
Não se deve promover VLM por gate sintético nem integrar v2 real.
Novos testes adicionados, ainda não executados pelo assistente.

## Execução
Não repetir v1 nem provisionar pesos. Usar ambientes separados:
```powershell
git pull --ff-only
git rev-parse --short HEAD
conda activate tapi-s1
$env:TAPI_SYSTEM_ONE_ENABLED="1"
$env:HF_HUB_OFFLINE="1"
$env:TRANSFORMERS_OFFLINE="1"
python -m pytest -q tests/test_multimodal_cta_directed.py tests/test_multimodal_cta_challenge.py tests/test_multimodal_semantic_replay.py
python scripts/verify_zero_spend.py
$stamp=Get-Date -Format "yyyyMMdd-HHmmss"
python -m scripts.a6_semantic_replay --cta-directed-challenge --model-dir "C:\Models\tapi\gliner25-multi-decide" --report-name "a6-cta-directed-v2-$stamp.json"
conda activate tapi-asr
python -m pytest -q tests/test_multimodal_vlm_single_scene.py tests/test_multimodal_vlm.py
$vlm="C:\Models\tapi\qwen3-vl-2b-gguf"
$runtime="C:\Models\tapi\llama-b6907"
$servers=@(Get-ChildItem $runtime -Recurse -File -Filter llama-server.exe)
if ($servers.Count -ne 1) { throw "Expected one llama-server.exe" }
$server=$servers[0].FullName
python -m scripts.a6_vlm_benchmark --verify --model-dir "$vlm" --server-exe "$server"
if ($LASTEXITCODE -ne 0) { throw "Verification blocked" }
$stamp=Get-Date -Format "yyyyMMdd-HHmmss"
python -m scripts.a6_vlm_benchmark --single-scene --model-dir "$vlm" --server-exe "$server" --input-name "a6-shared-multimodal-20261117-174208.json" --report-name "a6-vlm-single-scene-v2-$stamp.json"
```
Se v2 reprovar, preservar resultado. Não executar modelos em paralelo.
Sem novo download, gasto, DB, mídia externa, publicação, merge,
admissão ou gate global liberado. Não atrasar indefinidamente as
outras CAP por otimização de benchmark pequeno: próxima etapa deve
também avançar direitos por ativo, cobertura 20 campos e Evidence Studio.
