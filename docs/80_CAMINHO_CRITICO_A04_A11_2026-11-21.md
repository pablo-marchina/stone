# Stone — retomada do caminho crítico A04 → A05 → A06/A07 → A11 (21/11/2026)

> **Overlay de execução, não backlog ou decisão normativa.** A fonte vigente é a Base Atemporal v6.1 (`01_Nucleo/11_Plano_Unico_Atemporal.md` e as 13 matrizes `03_Plano_Unico/matrizes/`), sincronizada com o plano v5.2 + DEC-016–018. A fase A00–A11 é uma visão operacional. Este documento **não** modifica os 204 IMP, 543 dependências, 23 CAP, 18 U, 18 DEC vigentes, 28 CT, 7 gates, oráculos, decisões ou o único aceite IMP-131.

## 0. Decisão e invariantes

- Encerrar a exploração **repetitiva** dos mesmos perfis ASR nos mesmos áudios TTS. A02.7.3 já documentou 35 avaliações de recuperação (v1 14, v2 14, v3 Small 7), sem candidato aprovado; manter Whisper Medium baseline, limiar WER 0,50 e a falha do Strict. Não executar novamente v1/v2/v3 por rotina nem atribuir erro de modelo ao supervisor sem prova.
- Shared AV: **Strict 6 PASS e 2 FAIL** (`complementary` e `audio_only`, ambos `ASR_FIXTURE_WER_GATE`); **Partial 8 PASS focais** com abstenção tipada nos casos CTA. Resultados vêm de execuções independentes: não constituem JUnit integral A00, não autorizam alegar semântica recuperada, validação científica, nem `multimodal_coverage.all_required_passed`.
- **DEC-018:** manter a dispensa comunicada de revisão humana `IMP-062`/CAP-004 no plano interno como **dispensada, não cumprida**. Não pedir nova aprovação institucional genérica; tampouco inventar gold/revisores. Acesso operacional exige as provas técnicas de fonte, grant, conta, lease e direitos por ação efetivamente vigentes.
- **R$0** desembolso e serviços faturáveis; sem chamadas externas pagas, publicações, ads, automação de Meta/YouTube, mídias não licenciadas, credenciais reais em teste ou alteração do runtime default.
- PRs #43 e #44 em Draft; sem merge/deploy/release. Qualquer PASS é atribuído ao SHA exato, ferramenta, relatório e escopo. Invariantes G0–G6 continuam BLOCKED e `IMP-131` permanece único sink de aceite.

## 1. Foto do corte e limites da evidência

| Frente | Evidência do projeto | O que **não** comprova |
|---|---|---|
| A03 corpus | Em 19/11, base técnica reportou **1.630 registros / 29 perfis**, mas recorte autorizado `V12-scope27` tem **1.069 legendas / 27 perfis**; duas fontes fora do recorte por grants expirados. | Corpus científico completo 2–5 mil / 30+ elegíveis; aprovações de cada conteúdo; inferência causal. |
| A04 rubrica e ranking | ER/top 10% exploratórios e cobertura declarada dos 20 campos; `IMP-060` Gold Registry sintético, baseline lexical/FTS5 e `IMP-069` Evaluation Engine local com `PASS`, `FAIL`, `BLOCKED` registrados. | Gold independente, CT-04 aceito, avaliação válida de métricas por campo, decisão DEC-006, G3-EVAL. |
| A05 retrieval/agente | `IMP-071` fastpath local read-only qualificado (75 testes focais e A00 **1218 PASS/202 SKIP** no HEAD histórico `725f34c`); recorte 1.069/27, três queries, hits 5/5/2; preview editorial 1 hipótese, 4 refs e 0 criativos. | Ganho real sobre baseline, recuperação gold, agente multietapa LangGraph validado, recomendações causais ou cinco criativos. |
| A06/A07 Studio | Contratos B2 `CreativeSpec`, C/E3–E8 DesignDocument, edição e render local documentados, testes isolados de integração existentes. | Jornada E2E no HEAD atual, direitos de todas as mídias, export final aprovado, render paritário e publicação. |
| A00 | `--profile full` sem opt-ins: **1.445 PASS, 46 SKIP, 0 FAIL** no HEAD histórico `e57fd8a` (21/11). Multimodal **11/19 grupos** nessa única execução. | Nova A00 no HEAD presente, `full_regression_without_skips`, `--require-multimodal` ou gates globais. |

**Fonte factual principal:** `docs/74_A00_BASELINE_REGRESSAO_2026-11-17.md`, `docs/75_IMP071_EVIDENCIA_FASTPATH_E_LACUNAS_DE_ACEITE_2026-11-20.md`, `docs/76`–`79`; registro dos dois FAIL Strict ao fim de `docs/79`. Metadados históricos prevalecem sobre expectativas; não somar testes de SHAs diferentes.

## 2. Caminho operacional por dependências (prioridade, não aceitação)

### Passo A04 — consolidar avaliação auditável sem falso gold

**IMP existentes:** `IMP-060` (dep. 011, 038), `IMP-069` (017, 042, 060), `IMP-055/057/058/059` (ranking e comparações) e `IMP-064/065` (rubrica/eval, com dependências adicionais, inclusive evidência humana historicamente prevista e dispensa DEC-018). **Gates relacionados:** G2/G3.

1. **Imediato, sem rede/DB:** validar sobre o **mesmo HEAD e ambiente** os contratos `tests/test_discovery_gold_registry.py`, `tests/test_discovery_gold_registry_cli.py`, `tests/test_discovery_gold_retrieval_eval.py`, `tests/test_discovery_eval_engine.py`, `tests/test_discovery_synthetic_comparison.py` **se o último arquivo existir**, além de `scripts/verify_zero_spend.py` e o espelho documental. Registrar contagens/skips e SHA; nunca substituir arquivo ausente por PASS.
2. Elaborar a **matriz de proveniência para handoff A04→A05**, vinculando cada possível insumo a `reference_kind`, `source_scope`, `snapshot/manifest/partition hash`, `rights_checked`, `quality_policy`, `evaluation_spec_sha256`, `independent_gold_available`, `allowed_use` e a decisão `ABSTAIN/BLOCKED` quando a prova faltar. Para dataset sintético, `independent_gold_available=false`, uso exclusivamente experimental; para o corpus 1.069/27, escopo autorizável/descritivo e **sem rótulos científicos presumidos**.
3. Próximo incremento de código recomendado: testar/implementar somente esse **contrato fail-closed de handoff** entre relatórios versionados de A04 e consulta/preview A05, sem escrever DB operacional, sem chamar modelos, sem inventar `gold`, sem alterar baseline de SQL/FTS, sem habilitar agente/Studio por padrão. Testes negativos mínimos: hash divergente, escopo expirado/revogado, sealed test em prompt, missingness tratada como negativo, report `FAIL/BLOCKED` apresentado como `PASS`, mistura de splits ou de tenants.
4. **Saída da etapa:** relatório técnico de comparação e proveniência com casos positivos/negativos, hashes e limites. **Não é aceite** de `IMP-060/065/069` nem de CT-04 sem cumprir oráculos e dependências vigentes.

### Passo A05 — ferramentas, recuperação e agente auditáveis

**IMP existentes:** `IMP-071` (057, 060), `IMP-072` (025, 071), `IMP-073` (013, 044, 071), `IMP-074` (073, 027, 040, 122), `IMP-075` (069, 074), `IMP-076` (073, 074). **Gates:** G1/G3/G4.

1. Reusar o recorte `V12-scope27` e seus hashes somente enquanto elegibilidade/leases continuarem válidos; A05 read-only e nenhuma ingestão concorrente. Não requisitar mídia externa.
2. Contratar teste integrado de `EvidenceRetriever`/SQL truth/Citation com fonte real autorizada, verificando fonte, snapshots, escopo/tenant, revogação, ordens de ranking, erro tipado, ataque via caption e ausência de claims não sustentados.
3. Ligar o agente de três modos e ferramentas existentes aos contratos, com recuperação/checkpoint e negativas de privilégio; manter o preview determinístico marcado como exploratório quando o grafo completo ainda não estiver comprovado.
4. **Saída da etapa:** relatório de ferramentas e agente com métricas rastreáveis, erros negativos, referências auditadas e status; nenhum `IMP-074/075/076` promovido apenas por mock/preview.

### Passo A06/A07 — demonstração de ponta a ponta do conteúdo editável

**IMP existentes:** `IMP-077/078/079/080`, `IMP-174/175/176/177/178/179/180/181/182/183/184/185`, `IMP-187/188/189`, `IMP-197/198/199/201`. Respeitar o DAG: `IMP-078` depende de `IMP-075/077/136`, `IMP-180` de `IMP-078/175/179`, `IMP-198` de `IMP-184/185/191/197`.

1. Verificar em teste de integração o contrato B2→CreativeSpec→DesignDocument, sem aceitar `content_id` do cliente sem consulta à evidência vinculada ao tenant e ao rights scope.
2. Exercitar em fixtures sintéticas autorizadas: criar brief, editar camadas, salvar/reabrir versão, fazer preview, exportar e inspecionar paridade; o documento editável é fonte da verdade, raster/vídeo é derivado.
3. Registrar claramente dois estados: **demo sintética funcional** versus **criativo fundamentado elegível para uso**. Não produzir cinco `creative_playbook` falsos para fechar meta; condicionar à evidência, marca e direitos, e registrar `ABSTAIN` se faltarem.
4. Aplicar CT-STUDIO-01…10, isolamento tenant, SSRF/XSS, assets/licenças, revogação, safe area e orçamentos; nunca ligar worker nem publicação por padrão.

### Passo A11 — dossiê de segurança, reprodução e não-aceite

**IMP existentes:** `IMP-203` (198, 201, 202, 170), `IMP-204` (203, 199, 200, 196), `IMP-131` (158, 204), mais a frente A00 transversal. Todos os sete gates são avaliados separadamente.

1. Manter registro SHA→testes/artefatos/checkpoints/skips/rights, com uma seção por gate e evidência exigida; status insuficiente continua `BLOCKED`.
2. Regressão A00 `--profile full` no HEAD de código que produzir a integração, com matrizes e resultados completos; uma futura `--require-multimodal` deve preservar os 2 FAIL Strict, sem fake skips ou WER alterado. Não executar uma bateria cara apenas para confirmar falha conhecida quando não houver nova hipótese.
3. Produzir README/runbook de reprodução da demo, quadro de limitações e dossiê do aceite único. `IMP-131` só muda quando **todos** os critérios aplicáveis e todos os gates tiverem prova admissível; nenhuma autorização de merge/release resulta desta documentação.

## 3. Primeiro lote objetivo (A04.6): o que executar antes de alterar código

**Ambiente preferencial:** `tapi-s1-recovery`, sem flags externas; preservar sessão/DB/credenciais operacionais fora do runner. Confirmar `git status --short`, `git rev-parse HEAD`, espelho, focal A04, `verify_zero_spend.py`; registrar explicitamente `passed/failed/skipped/deselected`. Em caso de FAIL, diagnosticar e registrar antes de implementar. Não executar mídia nativa, ASR v1/v2/v3, modelos externos, bancos reais ou `--persist-studio-drafts`.

A lista de testes é derivada da árvore existente e deve ser restrita ao arquivo real: `test_discovery_gold_registry.py`, `test_discovery_gold_registry_cli.py`, `test_discovery_gold_retrieval_eval.py`, `test_discovery_eval_engine.py`, `test_discovery_synthetic_comparison.py`. **Alvo de implementação após esse baseline:** handoff seguro A04→A05, com testes negativos de proveniência e uso permitido. Se qualquer etapa do plano carecer de artefato ou pré-condição, marcar `BLOCKED/NOT_RUN` e seguir apenas os ramos independentes do DAG.

## 4. Critério de revisão deste overlay

Atualizar este registro somente com outputs do operador e SHA real. Para cada avanço, anotar: IMP responsável, dependências verificadas/não verificadas, código, testes, relatório privado+hash, limitações, rollback e próximo desbloqueio. Não atualizar os 13 CSVs ou as condições de aceite por uma anotação de progresso. O marco de 25/11 é prazo de apresentação/dossiê, **não** autorização para reduzir os oráculos.

**Status deste documento:** decisão de reorientação registrada e primeiro lote A04.6 preparado; **nenhum teste novo foi executado por este commit documental**, nenhuma tarefa aceita, nenhum gate liberado.

## A04.6 — baseline focal Windows e primeiro contrato isolado de ligação A04→A05 (21/11/2026)

### Evidência enviada pelo operador

- `python docs/base_atemporal/ferramentas/validar_espelho.py`: trecho final `dag=acyclic`, `unique_sink=IMP-131`, `software_tests=not_run`, `gates=not_assessed`; exit 0 na sessão, confirmado pelo `if ($LASTEXITCODE -ne 0) ...` sem throw. Não confundir verificação documental com execução do software.
- Cinco arquivos de pytest: `test_discovery_gold_registry.py`, `test_discovery_gold_registry_cli.py`, `test_discovery_gold_retrieval_eval.py`, `test_discovery_eval_engine.py`, `test_discovery_synthetic_comparison.py` ⇒ **49 PASS, 1 SKIP, 0 FAIL em 0,47 s**, `tapi-s1-recovery`. Único SKIP: `tests/test_discovery_eval_engine.py:212` — criação de symlink de diretório requer privilégio no Windows. Não tratar como PASS; testes de travessia/isolamento por symlink nessa condição ainda são lacuna de cobertura.
- `python scripts/verify_zero_spend.py` ⇒ `PASS — invariantes locais de gasto zero e bloqueio externo`.
- O recorte enviado pelo operador **não inclui `git rev-parse HEAD`**, portanto não atribuir um SHA exato comprovado ao checkout Windows desse bloco. O HEAD da branch remota na inspeção pré-implementação do assistente era `944317870f99d8032cba633cb93cc63563ea7bec`; esta é informação de branch, não prova de HEAD local da execução.

### Implementação técnica, ainda não validada no checkout Windows

1. `src/tapi_gate0/discovery_eval_handoff.py`: contrato puramente local, stdlib e sem I/O `link_private_reports`. Recebe **bytes de dois relatórios privados** e seis pins SHA-256 (`evaluation_report`, `retrieval_report`, spec, fixture, manifesto, partição). Verifica tamanho, hashes, JSON com chaves únicas, status de avaliação sintética `PASS`, contrato de provenance/linhagem, split permitido, flags negativas, status da prévia `SCOPED_FTS_LOCAL_PREVIEW_COMPLETED`, população/query counts, digest de queries, vínculos manifesto e ausência de `gold_metrics`.
2. Saída positiva usa `status=TECHNICAL_REPORTS_LINKED` e `permitted_use=private_diagnostic_only`. **Mesmo nesse estado** `tenant_scope_currently_verified=false`, `source_rights_currently_verified=false`, `independent_gold_available=false`, `a05_agent_handoff_allowed=false`, `creative_handoff_allowed=false`, `gates_released=false` e `production_approved=false`. Dados dos relatórios são de naturezas distintas: synthetic fixture não demonstra relevância de corpus técnico, e um preview com direitos verificados historicamente não prova elegibilidade atual. O módulo não é ligado ao A05, API, MCP, DB, Studio nem endpoint.
3. Saídas negativas `BLOCKED` têm razão tipada/sanitizada: adulteração de SHA, split selado, PASS falso, flags de gold/produção proibidas, drift do manifesto/partição, consulta com `gold_metrics`, contagens inconsistentes, JSON duplicado. Nunca devolve captions, IDs, snapshots, consultas ou tenant.
4. `tests/test_discovery_eval_handoff.py`: **23 PASS em 0,05 s no ambiente Python isolado do assistente**, com source equivalente de módulo, sem consultar banco/serviços. Este é somente smoke de testes unitários locais, **não execução da suíte do repositório no Windows**. O código está publicado em commits específicos e requer rerun do operador com SHA exato, espelho, suíte focal expandida e gasto zero. Não alegar testes de integração real com A05 ou uso de relatórios privados reais.

**Próxima saída obrigatória A04.6:** operador executar `tests/test_discovery_eval_handoff.py` junto às cinco suítes A04 já conhecidas, registrar SHA/contagem/skip; depois considerar teste integrado contra `evaluate_versioned_synthetic` e `preview_scoped_fts` sem dados operacionais, e somente então planejar contrato distinto de direitos vivos por tenant no boundary autenticado de A05. Handoff de recomendação e CreativeSpec continuam desabilitados. Não relaxar DEC-018, hashes, direitos, limiar ASR ou G0–G6; PR #44 permanece Draft.
