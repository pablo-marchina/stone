# CAP-003 / IMP-063/064 — fusão lexical PASS, replay semântico e VLM local (17/11/2026)

## Operador
HEAD 3fa975e: 87 PASS em 23,46s, zero-spend PASS.
a6-shared-multimodal-20261117-174208.json: sete clipes, integridade
temporal e de ativo PASS, zero chamadas ASR negativas, gate PASS.
Fusão all: tema 3/3, CTA 3/4, texto na tela 3/3, zero candidatos
errados; 9/10 candidatos esperados, 7 conteúdos. Braços legenda 4/10
e 1 errado; áudio 1/10 e 0; OCR 5/10 e 1; legenda+áudio 5/10 e 1;
legenda+OCR 8/10 e 0; áudio+OCR 6/10 e 1; all 9/10 e 0.
CTA exclusivamente falado (salvar) abstido. Não inferir a causa sem
examinar transcrição/âncora. OCR e áudio isolados não são substitutos
da composição. Sem gold, mídia real, DB, rubrica canônica ou produção.

## Replay semântico (IMP-064)
bd-multimodal-semantic-replay.v1, reusa relatório privado do benchmark
acima sem nova decodificação/ASR/OCR. Valida partição dos 7 clipes
autorais, hashes/políticas selecionados, vínculos de fragmentos,
consenso OCR e partição completa de fragmentos, e recompõe todos
os braços lexicais para comparar métricas. Isto valida consistência
interna do relatório, não atesta pixels/PCM originais (não persistidos).
GLiNER local já provisionado: revisão e173bca1f0c4217d7a55b3b0c705d5ece8a0218d,
pesos 9efe0f88c99f2aa794452e9559dc60e98d60d9fa2bf1b60cf2710411b6da5b4e.
Comparação 3 variantes x 7 braços: lexical; modelo PT/EN consensual
exploratório, com vetos de contexto/conflito; híbrido grounded com
concordância regra+modelo. A regra lexical não é abandonada por
predição unilateral; divergências levam a abstenção. OCR parcial
não alimenta semântica. Campos avaliados continuam tema/CTA/texto,
tem_cta derivado. Gate híbrido original: zero candidatos errados e
recall >=75% por campo no braço all. Não selecionar variante
automaticamente. Diagnóstico de áudio por WER e âncora/razão/predição,
sem transcript no stdout; relatório privado tem evidências.
Não é teste independente, nenhum novo campo canônico ou real liberado.

## VLM (IMP-063)
bd-vlm-frame-fixture.v1: Qwen/Qwen3-VL-2B-Instruct-GGUF oficial,
Apache-2.0, rev d38d39f5972e27cd58023f9b1e9f994b0c85ca47:
Qwen3VL-2B-Instruct-Q4_K_M.gguf SHA256
089d75c52f4b7ffc56ba998ffc50aae89fcafc755f9e7208aacca281dca6c2ae
mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf SHA256
f9a68fabba69c3b81e153367b2c7521030b0fa8bb0de400c9599c8e6725f9c82
~1,56 GB de pesos/encoder juntos. Runtime CPU llama.cpp b6907 (bea0452),
release indicada pelo model card. ZIP Windows x64 CPU SHA256
92d5b71fda1035ce5f65ed823568e0905bfe6fff4f7d142f550bceb06ac09dfd.
Não instalar como serviço; processo filho temporário com --offline,
CPU 4 threads, contexto 2048, uma sequência, porta loopback, chave
efêmera, sem UI, sem URLs remotas, proxy desabilitado, aliases
verificados, termina ao sair. Hash do executável observado; ZIP
verificado pelo operador antes da extração, não atestação de cada DLL.
Pré-voo RAM disponível >=4 GiB, disco provisão >=4 GiB, execução
>=512 MiB nos volumes pertinentes. Limiares conservadores de engenharia,
não exigência oficial nem garantia de execução. Última RAM livre 2,04
GiB: não baixar/rodar antes do novo pré-voo. Não carregar Whisper e
GLiNER simultaneamente com VLM.
20 posições de frame: 14 do relatório shared (regenerar pixels,
comparar SHA256 da imagem bruta com o registro OCR) + 6 challenge
autorais coloridos/layout. Imagens idênticas reutilizam inferência;
não contar como amostras independentes. Predições estritas JSON:
presença texto yes/no/uncertain e cena blank/text_card/geometry/
uncertain. Gate cada classe em cada suite >=75% recall, zero
classificação errada, zero resposta inválida, todos 20 casos.
No/no-text é somente alvo do benchmark sintético, não ausência
canônica real. Sem rostos reais, sem inferência de vídeo contínuo,
sem semântica temporal de hook, sem VLM no braço all anterior.
VLM separado, futura integração e ablação final ainda pendentes.

Fontes upstream:
https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/tree/d38d39f5972e27cd58023f9b1e9f994b0c85ca47
https://github.com/ggml-org/llama.cpp/releases/tag/b6907
https://github.com/ggml-org/llama.cpp/releases/expanded_assets/b6907
https://github.com/ggml-org/llama.cpp/blob/b6907/tools/server/README.md

## Execução
Na branch A6, git pull --ff-only. Primeiro usar ambiente tapi-s1,
sem novo download, com o checkpoint GLiNER existente:
```powershell
conda activate tapi-s1
$env:TAPI_SYSTEM_ONE_ENABLED="1"
$env:HF_HUB_OFFLINE="1"
$env:TRANSFORMERS_OFFLINE="1"
$stamp=Get-Date -Format "yyyyMMdd-HHmmss"
python -m pytest -q tests/test_multimodal_semantic_replay.py tests/test_multimodal_vlm.py tests/test_multimodal_fusion.py -m "not media_integration"
python scripts/verify_zero_spend.py
python -m scripts.a6_semantic_replay --model-dir "C:\Models\tapi\gliner25-multi-decide" --input-name "a6-shared-multimodal-20261117-174208.json" --report-name "a6-multimodal-semantic-$stamp.json"
```
Não repetir áudio/OCR. Novo relatório preservado se gate reprovar.
Para VLM: ambiente tapi-asr (httpx/Pillow existentes), sem carregar
GLiNER, verificar RAM/disco:
```powershell
conda activate tapi-asr
python -m pytest -q tests/test_multimodal_fusion.py -m media_integration
$vlm="C:\Models\tapi\qwen3-vl-2b-gguf"
python -m scripts.a6_vlm_benchmark --plan --model-dir "$vlm"
```
Se run_memory_ready ou provision_disk_ready false, adiar
provisionamento e manter relatórios. Se ambos true, baixar apenas
os dois GGUF e o ZIP CPU b6907 de origem pública, verificar SHA
antes de executar, restaurar offline. Comandos:
```powershell
$env:HF_HUB_DISABLE_TELEMETRY="1"
$env:HF_HUB_DISABLE_IMPLICIT_TOKEN="1"
Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
Remove-Item Env:TRANSFORMERS_OFFLINE -ErrorAction SilentlyContinue
python -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen3-VL-2B-Instruct-GGUF',revision='d38d39f5972e27cd58023f9b1e9f994b0c85ca47',local_dir=r'C:\Models\tapi\qwen3-vl-2b-gguf',allow_patterns=['Qwen3VL-2B-Instruct-Q4_K_M.gguf','mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf'],token=False)"
$env:HF_HUB_OFFLINE="1"
$env:TRANSFORMERS_OFFLINE="1"
$runtime="C:\Models\tapi\llama-b6907"
$zip="C:\Models\tapi\llama-b6907-bin-win-cpu-x64.zip"
if (!(Test-Path $zip)) { Invoke-WebRequest "https://github.com/ggml-org/llama.cpp/releases/download/b6907/llama-b6907-bin-win-cpu-x64.zip" -OutFile $zip }
if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne "92d5b71fda1035ce5f65ed823568e0905bfe6fff4f7d142f550bceb06ac09dfd") { throw "ZIP hash mismatch" }
if (!(Test-Path $runtime)) { Expand-Archive -Path $zip -DestinationPath $runtime }
$servers=@(Get-ChildItem $runtime -Recurse -File -Filter llama-server.exe)
if ($servers.Count -ne 1) { throw "Expected one llama-server.exe" }
$server=$servers[0].FullName
python -m scripts.a6_vlm_benchmark --verify --model-dir "$vlm" --server-exe "$server"
if ($LASTEXITCODE -ne 0) { throw "Verification blocked" }
$stamp=Get-Date -Format "yyyyMMdd-HHmmss"
python -m scripts.a6_vlm_benchmark --benchmark --model-dir "$vlm" --server-exe "$server" --input-name "a6-shared-multimodal-20261117-174208.json" --report-name "a6-vlm-frames-$stamp.json"
```
Downloads públicos de pesos/runtime separados da avaliação offline;
nenhuma aquisição social/serviço pago. Não apagar arquivos existentes
nem abrir servidor manualmente. Gate exit 2 guarda relatório se
concluído; bloqueio operacional não equivale a falha de qualidade.
Novos módulos/testes não executados pelo assistente, apenas revisão
estática das APIs/flags upstream. Operador Windows deve validar.
Sem merge/produção/DB/mídia real/admissão. VLM+fusão semântica,
calibração 20 campos, direitos por ativo e Evidence Studio pendentes.

## Correção operacional — ambientes separados
Operador HEAD 4664064 em tapi-s1: 22 PASS / 1 FAIL (ausência de PIL
em test_shared_lossless_mux_and_timeline); zero-spend PASS.
Não é reprovação de qualidade de GLiNER/VLM ou da fusão. O mesmo
mux já passou em tapi-asr no conjunto de 87 testes do HEAD 3fa975e.
Marcador media_integration registrado e aplicado ao teste que exige
Pillow e FFmpeg. Rodar 22 testes sem esse marcador em tapi-s1 e o teste
marcado em tapi-asr; não há skip novo nem mudança de assertions.
Não instalar Pillow em tapi-s1 apenas para o replay, que consome JSON.
Benchmark VLM permanece em tapi-asr para reconstruir pixels com
Pillow 12.3.0 e verificar os hashes. Replay e VLM ainda não executados.
