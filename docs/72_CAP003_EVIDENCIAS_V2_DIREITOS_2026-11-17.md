# CAP-003 — consolidação CTA v2, VLM v2 e replay de evidências (17/11/2026)

## Operador HEAD ed44af3
24 PASS em tapi-s1 (0,52s), 12 PASS em tapi-asr (0,58s);
zero-spend PASS. Total 36 testes, sem somar suítes anteriores.
a6-cta-directed-v2-20261117-182103.json: ambos splits de 24
surrogates PASS para directed_rule e directed_hybrid.
| Variante | Positivos corretos / 24 | Candidatos errados em 24 negativos | Gate ambos splits |
|---|---:|---:|---|
| lexical | 12 | 0 | FAIL |
| model_consensus | 22 | 17 | FAIL |
| grounded_hybrid | 12 | 0 | FAIL |
| directed_rule | 24 | 0 | PASS |
| directed_hybrid | 22 | 0 | PASS |
Directed rule recupera 12/12 explícitos e 12/12 paráfrases; híbrido
recupera 12/12 e 10/12. Repetição de uma classe sem evidência
extra não é observação independente. Gramática e fixtures autorais
co-desenvolvidas. Seleção experimental da regra dirigida, não promoção
canônica nem avaliação sobre posts reais. Avisos GLiNER persistem.

a6-vlm-single-scene-v2-20261117-182203.json: pesos/runtime verificados;
mesmo source_report_sha256 4808374885f1ae860507aa513c93830b0cd62ca8ce062160896912e8f93ea4fc.
26 posições: 25 corretas, 1 abstenção, zero erradas e inválidas;
16 imagens únicas: 15 corretas, 1 abstenção. 4 uniformes únicas
sem chamada, 12 inferências únicas, 11 corretas e 1 abstida.
Shared 14/14 posições (4/4 únicas) PASS; challenge 5/6 FAIL;
additional_authored 6/6 PASS. small_text "Vendas" retornou blank
bruto e NONUNIFORM_BLANK_CONFLICT -> uncertain; recall text_card
challenge 2/3=66,67%, abaixo de 75%; gate global FAIL preservado.
Carga 2207,911ms. Não confundir guard com capacidade intrínseca do
modelo, nem texto derivado com confirmação independente.

## Incremento — bd-multimodal-evidence-replay.v2
IMP-063/064/136, usa os sete clipes compartilhados já persistidos
e o relatório VLM v2. Nenhum checkpoint carregado, ASR/OCR não
reexecutados. Valida relatório shared com replay v1, gera novamente
os pixels autorais dos 26 frames, confere hashes PNG, identidade,
timestamp, partição, prompt, pins e consistência de guard, cache e
métricas VLM. Não atesta respostas do modelo criptograficamente nem
redecodifica o contêiner original. Relatório VLM FAIL é aceito como
evidência experimental, não aprovado.
15 subconjuntos não vazios de legenda, áudio, OCR, VLM; braços
comparam tema lexical, CTA regra dirigida v2 e presença positiva
de texto. CTA/tema não usam VLM nem OCR parcial. VLM isolado
exploratório; em braço OCR+VLM a palavra OCR é obrigatória para
candidato positivo; voto negativo VLM no mesmo frame veta essa
evidência, sem produzir false; não veto outros frames positivos.
Voto uncertain não confirma nem veta. A política é conservadora,
não melhoria demonstrada, pode reduzir cobertura. Não preenche
ausência de texto, não conserta ASR inventando transcrição. O
small_text do challenge permanece fora dos sete clipes; não
testamos recuperação dele neste replay. Gate experimental do
braço completo: zero candidatos errados, recall >=75% nos três
campos pontuados, sete casos; não altera o gate VLM.
Todos 20 campos representados. Quatro candidatos possíveis:
tema, tipo_cta, tem_cta, texto_na_tela. Quatro measurement_only:
duracao_faixa (segundos), legenda_tamanho (caracteres),
hook_primeiros_3s (frames/segmentos sobrepostos à abertura,
não texto limitado exatamente a 3s), ritmo_cortes_0a10
(contagem transições, não score). Outros 12 not_assessed.
Sem classificação canônica, bins inventados, scores ou afirmação
de hook semântico. 140 células, cobertura por estado/campo.
Proveniência por ativo e relatório; source_rights sintético
declarado, nenhuma autorização externa derivada.
CLI privado exclusivo, inputs limitados 8MB, sem sobrescrita,
mesma política synthetic_local. Novos testes unitários/integração
de consistência com imagens geradas; ainda não executados pelo
assistente. O próximo passo de Evidence Studio deve consumir
este envelope, com vínculo por campo, autenticação e RBAC;
não está integrado à UI nem ao banco.

## Fechamento da entrada de mídia legada
multimodal.inspect_approved_local_media agora bloqueia antes de
abrir qualquer arquivo de caller, inclusive root e SHA válidos.
Código MEDIA_VERIFIED_ASSET_GRANT_REQUIRED. O adaptador antigo
tratava root+hash como condição de processamento; isso comprova
integridade/confinamento, não direito. Nenhum serviço de grant
por ativo ligado a essa entrada; fail closed. O helper privado
de atestação mantém seus testes e não concede autorização.
inspect_generated_visual_fixture() sem inputs gera JPEG preto
e testa a implementação antiga OpenCV/Tesseract; whitelist
file,pipe no helper FFmpeg. A proteção do endpoint legado não
é um sandbox Python; a fronteira futura requer grant verificado,
tenant/asset/scope/expiry/revocation, controle de storage e
proveniência. VisualObservation legado e eventual persistência
ainda precisam de integração com essa fronteira. Sem liberação
de arquivos externos. docs/21 atualizado.

## Operador — sem novos downloads ou inferências
```powershell
git pull --ff-only
git rev-parse --short HEAD
conda activate tapi-asr
$env:HF_HUB_OFFLINE="1"
$env:TRANSFORMERS_OFFLINE="1"
python -m pytest -q tests/test_multimodal_evidence_replay.py tests/test_multimodal_fusion.py tests/test_multimodal_vlm_single_scene.py tests/test_multimodal_vlm.py tests/test_offline_visual.py
python scripts/verify_zero_spend.py
$stamp=Get-Date -Format "yyyyMMdd-HHmmss"
python -m scripts.a6_evidence_replay --shared-name "a6-shared-multimodal-20261117-174208.json" --vlm-name "a6-vlm-single-scene-v2-20261117-182203.json" --report-name "a6-multimodal-evidence-v2-$stamp.json"
```
Se gate FAIL, preservar relatório; não reexecutar modelos para
tentar encaixar resultados. Nenhuma mídia real, DB, gold, gastos,
merge ou produção. Próximo incremento: Evidence Studio/Rubric Lab,
grants por ativo, cobertura restante e demais CAP (LangGraph,
contrastes e playbook), sem confundir fixtures com corpus real.
