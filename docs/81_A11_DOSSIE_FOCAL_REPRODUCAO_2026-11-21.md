# Stone — A11: dossiê focal de reprodução, direitos e não-aceite (21/11/2026)

**Natureza:** overlay de evidência para IMP-203/204, NÃO decisão normativa. Fonte oficial: Base Atemporal v6.1, Plano Único v5.2 e matrizes vigentes. Nenhum gate ou o aceite final IMP-131 foi liberado. PR #44 permanece Draft; teto de gastos R$0.

## 1. Corte comprovado pelo operador Windows

Os resultados abaixo pertencem exatamente ao HEAD **0b58c4d2c983b100b7d2bb8e638bbaa13b0755c0**, Conda tapi-s1-recovery:

| Verificação | Resultado observável |
|---|---|
| Python runner e CDP | 13 PASS, 0 FAIL, 0 SKIP — 1,03 s |
| Node exportação, HTML e timeline | 19 PASS, 0 FAIL, 0 SKIP — 433,985 ms |
| Chrome headless real | A073_BROWSER_PARITY_PASS 7/7 |
| Invariantes locais de gasto zero | PASS — invariantes locais de gasto zero e bloqueio externo |

No Chrome deste computador, a fixture sintética usou o exportador local real: comparação Canvas/PNG com limite médio de diferença <=2, JPEG com limite <=10, SVG renderizado com HTMLImageElement, marca de rascunho, XML escapado, versões e hashes, negação de direitos falsificados. Isso NÃO demonstra paridade interplataforma, confiança em fontes externas, direito de reutilização, autenticidade de contas, E2E do editor autenticado, mídia comercial ou publicação.

**Outro SHA e outro corte, sem somar como uma única execução:** a regressão focal A05/A06/A07 de 13 arquivos forneceu **114 PASS, 0 FAIL, 0 SKIP e um warning legado Starlette** no HEAD **96797a0d746c1bae6cd5dd917ad38e9e4cb74f71**. Ela não foi executada no mesmo SHA que os 13/19/7 acima. É preciso rerodá-la no SHA do pacote A11.

## 2. Gerador do pacote de evidências

O novo script scripts/a11_focal_evidence_packet.py é um **executor opt-in exclusivamente local**, não CI nem aprovação:

1. Confere Git HEAD completo, ausência de mudanças em arquivos rastreados e, opcionalmente, igualdade com o SHA exigido.
2. Calcula SHA-256 dos scripts, contratos e testes críticos; recusa fonte local ausente.
3. Executa PRIMEIRO scripts/verify_zero_spend.py. Se falhar, não inicia nenhum teste subsequente.
4. Executa 13 arquivos focais pytest A05/A06/A07 (114 casos no último corte, esperados), os dois arquivos CDP Python (13 esperados), três suítes Node (19 esperados) e as 7 verificações reais do Chrome. Um processo com exit 0 mas contagem parcial, skips ou DOM incompleto é rejeitado. Não baixa navegador nem bibliotecas, não usa pagamentos e não consulta serviços de terceiros.
5. Gera recibo JSON com schema tapi-a11-focal-evidence-packet.v1; inclui SHA, hash de arquivos e outputs, contagens, tempos, códigos de resultado e limitações. Não inclui os logs brutos, legendas, tokens ou imagens. O arquivo do recibo só pode ser criado: nunca sobrescreve outro.
6. Quando tudo passa, o status máximo é FOCAL_DIAGNOSTICS_VERIFIED_NO_GATE_RELEASE. O recibo SEMPRE mantém G0–G6 e IMP-131 em BLOCKED, além de production_approved=false, external_reference_rights_verified=false, science_approved=false e imp131_accepted=false.

A cobertura A00 full, a validação multimodal Strict, o gold independente, os CT-STUDIO completos, IMP-131 e os direitos externos operacionais **não** são verificados pelo pacote. Um recibo verde não se transfere para outro SHA. O Git check detecta arquivos rastreados modificados, mas não substitui uma revisão de todas as dependências e arquivos não rastreados de um ambiente comprometido.

### Reprodução PowerShell

No checkout limpo da branch Draft:

1. Capturar o SHA com git rev-parse HEAD e verificar git status --short.
2. Executar python -m pytest -q -rs tests/test_a11_focal_evidence_packet.py (esperados **10 casos**, ainda não executados no Windows).
3. Executar o pacote com os argumentos --expected-head SHA e --output artifacts/a11/focal-SHA.json (SHA deve ser o HEAD completo do checkout, não um SHA histórico).
4. Verificar SHA-256 do JSON com Get-FileHash -Algorithm SHA256. Conservar o recibo sem sobrescrever. Se a execução falhar, o recibo continua BLOCKED e contém os motivos e outputs apenas por hash.

Exemplo de execução:

    $head = (git rev-parse HEAD).Trim()
    git status --short
    python -m pytest -q -rs tests/test_a11_focal_evidence_packet.py
    if ($LASTEXITCODE -ne 0) { throw "A11 tests falharam" }
    $output = "artifacts/a11/focal-$head.json"
    python scripts/a11_focal_evidence_packet.py --expected-head $head --output $output
    if ($LASTEXITCODE -ne 0) { throw "A11 focal ainda nao validado" }
    Get-FileHash -Algorithm SHA256 $output

**Os 10 testes A11 e os 5 comandos do pacote são novos e AINDA NÃO têm PASS do operador no HEAD atual.** As contagens 114/13/19/7 são oráculos focais baseados em resultados históricos, não resultados desse novo SHA nem substitutos para CT-STUDIO e A00.

## 3. Matriz de bloqueios preservados

| Gate vigente | Evidência local que já existe | Lacuna impeditiva e estado |
|---|---|---|
| G0-PERMISSIONS | Bloqueios de operação externa, contratos técnicos e de referência | Direitos de reutilização por origem/operação com autoridade efetiva, prazo e revogação verificados; **BLOCKED** |
| G1-CONTRACT | Schemas Studio, CreativeSpec, Ed25519 local e testes | Contratos operacionais completos, oráculos normativos e PEP por ação; **BLOCKED** |
| G2-REPRODUCIBILITY | HEAD, SHA, testes e pipeline focal local | A00 full no mesmo HEAD, ambiente/perfis e reprodução multimodal Strict; **BLOCKED** |
| G3-EVAL | Snapshot sintético, avaliação/retrieval local, abstenção | Gold independente, amostra elegível, CT-04 e validade de inferências; **BLOCKED** |
| G4-SECURITY | Tenant/RBAC/revogação sintéticos, deny por fonte e XSS/SVG | Segurança E2E dos pontos de uso, evidência externa e validação independente; **BLOCKED** |
| G5-OPS | Gasto zero e ausência de operação externa por padrão | Observabilidade e controles operacionais completos, direitos e revogação reais; **BLOCKED** |
| G6-ISO | Logs e documentação rastreável por SHA | Rastreabilidade integral, qualidade/ISO e revisão admissível por oráculos; **BLOCKED** |

A tabela não substitui os CSV normativos da Base Atemporal; IMP-131 continua único sink e requer provas admissíveis de todos os gates. A regra DEC-018 de dispensa da revisão humana para IMP-062/CAP-004 permanece **dispensada, não cumprida**, e não concede direitos criativos.

## 4. Fronteiras do próximo incremento

- Executar e guardar um pacote A11 focal no novo HEAD. Investigar, não ajustar artificialmente, qualquer contagem ou comportamento divergente.
- Executar A00 full separadamente no HEAD consolidado. Os 2 FAIL Strict historicamente conhecidos não devem ser apagados por skip ou troca de limiar.
- Conferir os CT-STUDIO 01–10 e oráculos da matriz antes de quaisquer promessas de aprovação, integração de direitos em runtime, merge/deploy ou publicação.
- Não executar serviços externos, mídia sem licença, ASR repetitivo, FFmpeg worker produtivo ou chamadas pagas para demonstrar um resultado sintético.

## 5. Primeiro teste A11.1 no Windows: NÃO aprovado; correções pendentes de reteste (21/11/2026)

**SHA executado pelo operador: `e2e56c5400dbb116fb26a679ef4c6e791e05f49e`**, Conda `tapi-s1-recovery`. Saída entregue:
- `python -m pytest -q -rs tests/test_a11_focal_evidence_packet.py`: **2 PASS, 8 FAIL**, 1,11 s. Em sete falhas, `synthetic_runner()` lança `AssertionError: Unexpected command ['...python.exe', 'scripts/verify_zero_spend.py']`, porque a fixture testava presença de `"verify_zero_spend.py"` como item exato da lista, mas o argumento contém o prefixo `scripts/`. A oitava falha ocorre em `test_pytest_node_and_chrome_require_complete_counts_and_zero_exit`: o parser Node usava `[^\\w\\n]*` e, no `re` Unicode do Python, o símbolo TAP `ℹ` é considerado `\\w`, então não aceita a contagem legítima `ℹ pass 19`. Nenhum desses resultados comprova a correção do código novo.
- Mesmo após os testes falharem, o operador executou manualmente o pacote, que retornou `A11_PACKET_STATUS=BLOCKED_ZERO_SPEND_PREFLIGHT` (exit não-zero), com **nenhuma suíte focal adicional executada**. O recibo bloqueado foi criado em `artifacts/a11/focal-e2e56c5400dbb116fb26a679ef4c6e791e05f49e.json` e `Get-FileHash` confirmou SHA-256 `9336c8268877d3e9665f9c2bbe7e74d325524de23608338d766942825f57ef0b`. Preservar esse recibo como histórico de **FAIL/BLOCKED**, nunca editar, sobrescrever ou converter em green. Hash coincidente confirma integridade do arquivo, não aceite.
- **Hipótese adicional não comprovada para o preflight:** a mensagem `PASS — ...` produzida pelo Python filho pode ter sido codificada em Windows cp1252 em stdout redirecionado, enquanto o orquestrador decodificava como UTF-8 e exigia texto exato. O JSON compartilhado não contém stdout bruto, portanto a causa de `BLOCKED_ZERO_SPEND_PREFLIGHT` não foi isolada definitivamente; a regra financeira original permanece intacta.

**Correções publicadas após a execução, ainda NÃO testadas pelo operador Windows:**
- `tests/test_a11_focal_evidence_packet.py`: fixture reconhece comandos com os caminhos reais (`scripts/verify_zero_spend.py`, `tests/test_studio_synthetic_provenance_a067.py`, `scripts/a07_browser_visual_parity.py`) e confirma o argumento de codificação. Dois testes adicionais rejeitam resumo TAP falsificado ou duplicado, bytes de em dash corrompidos, saída financeira incompleta e exit não-zero; total **12 casos pytest previstos**, não comprovados.
- `scripts/a11_focal_evidence_packet.py`: parser Node passa a exigir explicitamente prefixos TAP `ℹ` (com variação opcional) ou `#`, nomes exatos, inteiros decimais, uma única ocorrência por campo e zero skip/fail/cancelled/todo; impede falso PASS de linhas arbitrárias. Subprocesso financeiro passa a ser `python -X utf8 scripts/verify_zero_spend.py` para estabilizar o em dash no stdout redirecionado Windows, **sem flexibilizar** a comparação exata, exit=0, política R$0 nem parada antes de qualquer outra operação. O parser foi testado conceitualmente com o TAP Unicode real, mas nenhum resultado Windows após patch foi recebido.
- O gate operacional A11 continua `BLOCKED_NOT_VALIDATED` até o novo HEAD passar os testes e produzir recibo novo; nenhum A00 full, direito externo, G0–G6 ou IMP-131 é liberado por essa correção.

**Reteste:** atualizar o checkout limpo, registrar SHA, executar `python -m pytest -q -rs tests/test_a11_focal_evidence_packet.py` (**12 casos esperados, não comprovados**) e só então `python scripts/a11_focal_evidence_packet.py --expected-head SHA_ATUAL --output artifacts/a11/focal-SHA_ATUAL.json`. O novo SHA gera nome de arquivo diferente, preservando o recibo bloqueado histórico. Conferir `A11_PACKET_STATUS`, as cinco verificações do JSON e `Get-FileHash`. Se ainda houver bloqueio financeiro, inspecionar somente `reason_code`, `process_exit_code` e `output_sha256` do recibo para orientar diagnóstico sem expor dados privados; não interpretar esse hash como prova de que stdout foi UTF-8.

## 6. A11.1 — pacote focal VALIDADO no Windows; A00 completo continua PENDENTE

**Última evidência enviada pelo operador, HEAD original `cf27214b1bf0e997a3565245a13aa062f400d025`, PowerShell Conda `tapi-s1-recovery`:**
- `python -m pytest -q -rs tests/test_a11_focal_evidence_packet.py` → **12 PASS / 0 FAIL / 0 SKIP**, 0,33 s.
- `python -X utf8 scripts/verify_zero_spend.py` → **PASS — invariantes locais de gasto zero e bloqueio externo**. Esta é uma verificação de configurações e bloqueio técnico local, NÃO prova de sistemas externos de cobrança.
- `python scripts/a11_focal_evidence_packet.py --expected-head cf27214b1bf0e997a3565245a13aa062f400d025 --output artifacts/a11/focal-cf27214b1bf0e997a3565245a13aa062f400d025.json` → **`A11_PACKET_STATUS=FOCAL_DIAGNOSTICS_VERIFIED_NO_GATE_RELEASE`**. O gerador emite esse status somente quando as **cinco verificações** passaram: gasto zero, 114/114 pytest A05/A06/A07, 13/13 pytest CDP, 19/19 Node e 7/7 Chrome, com zero skips nos conjuntos; esses valores correspondem ao **contrato verificado do gerador**, não a novos logs independentes de cada subprocesso colados na conversa.
- Recibo JSON confirmado por `Get-FileHash -Algorithm SHA256`: **`125fffecddf3c8a131e4a116b6f0dbd82b835153d6bc07beb4d06bf93ecd1ecc`**, que coincide com `A11_REPORT_SHA256` emitido na execução. Preservar o arquivo de evidência **sem sobrescrever**.
- O recibo anterior, para o SHA `e2e56c5400dbb116fb26a679ef4c6e791e05f49e`, com hash `9336c8268877d3e9665f9c2bbe7e74d325524de23608338d766942825f57ef0b`, continua histórico **BLOCKED_ZERO_SPEND_PREFLIGHT**. Nunca apagar, modificar ou substituí-lo por green.

**A11.1 validado somente no escopo focal do SHA cf27214b.** Mesmo com relatório aprovado, os campos G0–G6 e IMP-131 no recibo continuam BLOCKED e `full_a00_validated_on_this_head=false`. Os requisitos de direitos criativos externos, gold científico independente, revisão completa dos CT-STUDIO, demonstração E2E operacional e publicação permanecem sem aceite. A PR #44 continua Draft.

**Preparação A00 posterior, no HEAD ainda não validado no Windows:**
- `.gitignore` foi ampliado com `artifacts/a11/` para que os recibos privados históricos continuem preservados mas não tornem o `check_checkout` estrito do A00 automaticamente dirty. Isso NÃO exclui arquivos já versionados nem ignora artefatos de outro diretório.
- `scripts/a00_inspect_report.py` passou a aceitar os formatos `a00-local-baseline.v1` (histórico) e `a00-local-baseline.v2` (atual). Exige em `full/v2` a etapa independente `documentary_mirror` com verificação de hash do log; mantém em `v1` o conjunto histórico sem mirror e em `semantic` o conjunto sem etapas full. Não altera resultados antigos nem aceita relatório parcial.
- `tests/test_a00_inspect_report.py` recebeu três testes para v2 full, mirror ausente ou adulterado e v2 semantic; testes novos ainda NÃO executados no Windows. A execução A00 no novo HEAD exigirá checkout limpo (incluindo outros untracked não ignorados) e relatório privado com nome exclusivo.

**Próximo passo:** `python -m pytest -q -rs tests/test_a00_baseline.py tests/test_a00_inspect_report.py`; se aprovado, executar `python scripts/a00_baseline.py --expected-head <SHA_ATUAL> --profile full --report-name a00-full-<STAMP>` no ambiente local apropriado, sem `--require-multimodal` nem opt-ins de modelo. Depois executar `python -m scripts.a00_inspect_report --report-name <NOME>` para validar o relatório A00 atual, inclusive se houve falhas ou skips. Não confundir `checks_passed` com `full_regression_without_skips`. Não baixar modelos, executar ASR/FFmpeg operacional, serviços faturáveis, autorizar fontes externas ou habilitar publicação para obter um PASS.

## 7. A00 full v2 — regressão Windows 1.571 PASS, 46 SKIP; cobertura multimodal incompleta (21/11/2026)

**Relato do operador com execução no HEAD exato `a04a276f6c44db0ab05351a9c49b34c93334f26e`, árvore `be6464f032cc30a49fa5a45fec2e50c397962a42`, conda `tapi-s1-recovery` Python 3.11.18.** Primeiro, `python -m pytest -q -rs tests/test_a00_baseline.py tests/test_a00_inspect_report.py` → **28 PASS** em 2,48 s. Depois `scripts/a00_baseline.py --profile full` sem opt-ins de OCR/ASR/VLM e sem `--require-multimodal` produziu relatório privado `a00-full-20261121-162649` com:
- **1617 coletados, 1571 PASS, 0 FAIL, 0 ERROR, 46 SKIP**; pytest `exit_code=0` (734,342 s); Node `exit_code=0` (7 arquivos Node versionados); Gate0 legado, verificação de gasto zero e espelho documental 32 blobs `exit_code=0`; checkout idêntico após a execução. `checks_passed=true` e `full_regression_profile_executed=true`, porém **`full_regression_without_skips=false`**.
- Testes Python novos A00 do executor/inspetor **28 PASS** (fora da contagem full agregada? São testes potencialmente incluídos no full também; não somá-los como casos distintos). Todas as verificações locais passaram na configuração executada, mas a ausência de falhas não cobre os 46 testes saltados.
- O inspetor `scripts.a00_inspect_report` verificou hashes de todos os logs e JUnit, sem rerun. SHA-256 do `summary.json`: **`fef16fc26747a99e4e32a279bb4f485f028fcb703b6151477f0fe9d48207793d`**, confirmado novamente por `Get-FileHash`. SHA-256 do JUnit `pytest.xml`: **`1c7d070035e9fe12f13058f3fcc94a24428a23b19618628f5491b102e8990db4`**. Preservar relatório, logs e XML privados; não substituir nem reexecutar full sem motivo.
- `multimodal_coverage`: **11 dos 19 grupos requeridos com `passed_required=true`; 8 incompletos:** `ocr_decode` 0/3, `ocr` 0/6, `asr` 0/6, `vlm` 0/6, `bundle` 0/1, `fixture_pipeline` 8/12, `shared_av` 14/22, `shared_av_partial_native` 0/8. `all_required_passed=false`. Não converter skips em PASS ou alterar mínimos para obter verde.
- As 46 identidades saltadas no JUnit se distribuem por módulo: `tests.test_asset_rights_registry` **39** (integrações nativas com requisitos múltiplos), `tests.test_asset_ocr_fixture` **3**, `tests.test_multimodal_ocr` **1**, `tests.test_multimodal_ocr_consensus` **1** (OCR total **5**), `tests.test_evidence_lab` **1** (triplet local sem configuração) e `tests.test_discovery_eval_engine` **1** (symlink no Windows sem privilégio). Essa classificação por identidade **não certifica a causa precisa de cada skip**: consultar o `<skipped message=...>` no JUnit privado antes de decidir qualquer mudança. Grupo 39+5+1+1=46.
- Não foi executado opt-in nativo multimodal: `ocr_integration_opt_in=false`, `asr_integration_opt_in=false`, `vlm_integration_opt_in=false`, `multimodal_required=false`. Neste ambiente `faster-whisper`, `ctranslate2`, `onnxruntime` foram reportados **ausentes**; ferramentas locais `ffmpeg`, `ffprobe`, `tesseract`, `node` estavam disponíveis, mas binário não equivale a modelo/tessdata validado. `network_sandbox=false` no runner: não há sandbox de rede de SO; credenciais e URL operacional não foram encaminhadas, e `operational_database_tested=false`.
- **Não há FAIL Strict novo neste SHA.** As duas falhas de ASR `complementary`/`audio_only` documentadas em execução focal anterior são históricas de outro SHA e configuração; não considerá-las curadas nem reproduzidas por este full sem opt-ins.

**A00.4 de preparação posterior, ainda NÃO testado no Windows:** `scripts/a00_coverage_gap_report.py`, novo inspetor read-only do relatório A00 salvo, valida primeiro o inspetor v2 (hash dos logs, JUnit, contagens e etapas) e **recalcula** os 19 grupos multimodais do JUnit em vez de confiar no flag gravado. Categoriza agregadamente os skips por família do teste, sem revelar mensagens/tracebacks de arquivos privados. Sempre retorna G0–G6 e IMP-131 `BLOCKED`, nenhuma operação/modelo/rede ou alteração do DB. Não é inferência da causa específica. `tests/test_a00_coverage_gap_report.py` contém **7 testes novos, ainda sem PASS Windows**: JUnit válido e com gaps, sem skip mas multimodal insuficiente, cobertura adulterada, XML modificado, perfil inválido e categoria desconhecida.

**Próximo passo restrito, não repetir os 734 s automaticamente:** rodar `python -m pytest -q -rs tests/test_a00_coverage_gap_report.py` (**7 esperados, não comprovados**), depois `python -m scripts.a00_coverage_gap_report --report-name a00-full-20261121-162649` para confirmar os 46 skips e as oito lacunas no relatório salvo. **Só então** analisar no ambiente `tapi-asr-recovery` a disponibilidade local e os pins de `C:\\Models\\tapi\\tessdata-fast-4.1.0`, `C:\\Models\\tapi\\faster-whisper-medium`, `C:\\Models\\tapi\\qwen3-vl-2b-gguf` e exatamente um `llama-server.exe`; são caminhos reportados anteriormente, NÃO confirmados no novo teste. Sem download, reinstalação, opt-in ambiental implícito ou banco/ingestão. Caso faltarem artefatos, registrar UNAVAILABLE/BLOCKED, não forçar Strict.

A00 full no escopo executado tem **zero falhas**, mas a **cobertura obrigatória multimodal permanece bloqueada**. Isso não altera CT-STUDIO, A11 focal aprovado no SHA anterior, G0–G6, IMP-131 ou a PR Draft.

## 8. A00.4 — auditoria read-only de lacunas VALIDADA no Windows (21/11/2026)

**Corte informado pelo operador no HEAD `d116daf8d20df0b78ada5fb897008e1e1334de67`, Conda `tapi-s1-recovery`:**
- `python -m pytest -q -rs tests/test_a00_coverage_gap_report.py` → **7 PASS / 0 FAIL / 0 SKIP**, 0,75 s.
- `python -m scripts.a00_coverage_gap_report --report-name a00-full-20261121-162649` → **`A00_FULL_WITH_COVERAGE_GAPS`**, `checks_passed=true`, `full_regression_without_skips=false`, **1571 PASS/0 FAIL/0 ERROR/46 SKIP/1617 total**. **Nenhum teste reexecutado** pelo inspetor.
- Relatório de origem permanece **SHA Git `a04a276f6c44db0ab05351a9c49b34c93334f26e`**, **não** SHA do inspetor novo; logs e JUnit conferidos por hash. `summary_sha256=fef16fc26747a99e4e32a279bb4f485f028fcb703b6151477f0fe9d48207793d`, `junit_sha256=1c7d070035e9fe12f13058f3fcc94a24428a23b19618628f5491b102e8990db4`.
- **46 SKIP classificados sem provar causas individuais:** `NATIVE_MULTIMODAL_OPT_IN_TESTS=39`, `OCR_LOCAL_OPT_IN_TESTS=5`, `EVIDENCE_LAB_LOCAL_TRIPLET_OPT_IN=1`, `WINDOWS_SYMLINK_PRIVILEGE_TEST=1`. Interpretar a mensagem `<skipped>` real do JUnit antes de concluir por que uma fixture não rodou.
- Dos 19 grupos multimodais, **11** atendem os mínimos e **8** não: `ocr_decode=0/3`, `ocr=0/6`, `asr=0/6`, `vlm=0/6`, `bundle=0/1`, `fixture_pipeline=8/12`, `shared_av=14/22`, `shared_av_partial_native=0/8`. `multimodal_all_required_passed=false`, `model_inference_invoked=false`, `operational_database_mutated=false`, `external_rights_verified=false`, `independent_gold_available=false`.
- `python scripts/verify_zero_spend.py` → **PASS**, invariantes locais de gasto zero e bloqueio externo. **G0–G6/IMP-131 continuam BLOCKED**; `PR #44` Draft.

**Próximo controle, sem nova implementação:** antes de executar Strict, **reutilizar** o `scripts/a045_native_preflight.py` já existente, com `--mode asr`, `--mode vlm` ou `--mode both` em `tapi-asr-recovery`, depois de verificar localmente binário, checkpoints, dependências e memória. Esse preflight faz inspeção de metadados de pacotes, tipos de caminhos explicitamente configurados e snapshot de memória; **não carrega modelos nem prova hashes dos pesos**. Status máximo `READY_FOR_NATIVE_TEST_ATTEMPT` é apenas elegibilidade para uma tentativa local, não PASS Strict. Executar `a6_multimodal_readiness.py --check-ready` apenas se uma verificação separada de tessdata/ASR já local for necessária, nunca o modo de benchmark sem precondições. O A00 atual documenta `tapi-s1-recovery` sem os pacotes nativos; ele não informa se `tapi-asr-recovery` está pronto neste momento. Nenhum download/instalação/recriação de ambiente/worker ou opt-in de modelo foi autorizado por esta evidência.

**O que NÃO fazer:** não rodar novamente os 1617 casos para enumerar os skips, não marcar `46 skipped` como sucesso integral, não executar modelos com flags globais implícitas, não trocar thresholds WER/abstenção dos casos `complementary` e `audio_only` históricos e não declarar G2/G3/G4/G5/G6 liberados. Guardar a prova com SHA de origem separado do SHA do inspetor.

## 9. A04.5 — testes do preflight nativo Windows PASS; pré-requisitos reais NÃO avaliados (21/11/2026)

**Corte do operador:** HEAD `b9fbe00ff6fc031d133a4f4b739ecbb97e2e6eee`; `conda env list` confirmou presença de `tapi-asr-recovery` e `tapi-s1-recovery`; `conda activate tapi-asr-recovery` concluído (prompt mudou e guarda `CONDA_DEFAULT_ENV` não acionou exceção). `python -m pytest -q -rs tests/test_a045_native_preflight.py` retornou **8 PASS, 0 FAIL, 0 SKIP** em 0,16 s. `python scripts/verify_zero_spend.py` retornou **PASS — invariantes locais de gasto zero e bloqueio externo**.

**Interpretação restrita:** 8 testes exercitam o contrato do preflight com metadados, paths e snapshots simulados/parametrizados. **Não** foi executado `python scripts/a045_native_preflight.py --mode both` com os arquivos reais; não há neste corte dados factuais sobre `faster-whisper`, `ctranslate2`, `onnxruntime`, ASR model files, VLM GGUF, `llama-server.exe` nem memória disponível no ambiente `tapi-asr-recovery`. Presença do conda não implica readiness dos modelos. Nenhum peso carregado, modelo avaliado, benchmark/Strict executado, privilégio de symlink concedido ou banco/serviço utilizado.

**Próxima verificação de leitura, sem download nem inferência:**
1. Inspecionar localmente a existência dos caminhos já mencionados no histórico de operador: `C:\\Models\\tapi\\tessdata-fast-4.1.0` (arquivos `por.traineddata` e `eng.traineddata`), `C:\\Models\\tapi\\faster-whisper-medium` (arquivos `config.json`, `model.bin`, `tokenizer.json`, `vocabulary.txt`), `C:\\Models\\tapi\\qwen3-vl-2b-gguf` (par GGUF de modelo e mmproj) e **um** `llama-server.exe` no diretório `C:\\Models\\tapi\\llama-b6907`. Estes nomes são sugestões derivadas do histórico, **não confirmados** nesta execução. Não usar o diretório de outro modelo sem contrato específico.
2. Somente se os quatro pré-requisitos locais forem encontrados, definir `TAPI_ASR_TEST_MODEL_DIR`, `TAPI_VLM_TEST_MODEL_DIR`, `TAPI_VLM_TEST_SERVER_EXE` com variáveis *Process* temporárias (não modificar configuração persistente do sistema) e executar `python scripts/a045_native_preflight.py --mode both`. Registrar o JSON com `packages` (incluindo pin `faster-whisper==1.2.1`), `optins` e `memory`. Qualquer `BLOCKED`, `PIN_MISMATCH`, `MISSING_OR_INVALID`, `HEADROOM_INSUFFICIENT` ou executável não encontrado deve permanecer falha do preflight; não instalar pacotes, não alterar limiares, não carregar modelos.
3. O status `READY_FOR_NATIVE_TEST_ATTEMPT`, se ocorrer, **não prova** hashes de pesos nem compatibilidade de runtime, porque o próprio script fixa `models_loaded=false`, `checkpoints_verified=false`, `runtime_compatibility_verified=false` e `production_approved=false`. É só um pré-requisito para um futuro teste focal, mediante avaliação dos recursos, pins e relatos anteriores de falhas ASR.

**Estado global:** A00 base `a04a276f` continua **1571 PASS/46 SKIP**, oito grupos nativos pendentes; A00.4 auditoria read-only passou 7/7 no `d116daf8`; A04.5 contrato do preflight passou 8/8 no `b9fbe00f`. São SHAs distintos. A11 focal já validado mantém seu SHA e recibo próprios. G0–G6, IMP-131 permanecem BLOCKED, PR #44 Draft, R$0, nenhuma publicação.
