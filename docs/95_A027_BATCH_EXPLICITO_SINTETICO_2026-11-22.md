# A02.7 — executor explícito e limitado de fixtures autorizadas

> Incremento da Base Atemporal v6.1, sem criar backlog paralelo nem substituir a fila, o vault, o supervisor, as permissões, os testes CT ou as decisões de arquitetura.

## Fronteira existente, agora coordenada

O Stone **já possuía** `FixturePipeline` em `src/tapi_gate0/asset_fixture_pipeline.py`: modo sintético tipado, etapas `step()` com checagem de direitos, leases, ciphertext de derivados, fusão S1 e suporte parcial shared-AV. O modo operacional de mídia externa continua expressamente bloqueado. O novo `asset_fixture_batch.py` só organiza chamadas explícitas desse pipeline, sem criar um segundo executor ou outro fluxo de direitos.

`run_explicit_fixture_batch(pipeline, worker, expected_plan_sha256=..., max_ticks=...)`:
- recebe **exatamente** uma instância `FixturePipeline` já construída no host confiável e um identificador de worker validado;
- exige fingerprint SHA-256 do plano, jobs com IDs verificáveis, um único tenant, asset e purpose `research_analysis`, configurações imutáveis, no máximo oito jobs e budget explícito de até `n+1` ticks;
- executa `pipeline.step(..., retry_stopped=False)`, mantendo a rechecagem real de direitos e fence já existente **a cada tick**; não chama manutenção, não renova lease, não reutiliza autorização, não faz retries automáticos nem passa `retry_stopped=True`;
- interrompe imediatamente em `busy`, `blocked`, `recovery_required`, saída desconhecida, recibo inconsistente, plano alterado, tentativa de repetir job ou atingimento do orçamento;
- quando o pipeline original retorna candidato terminal, exige **`CandidateDecisions` tipado** e os mesmos tenant/object/purpose, fingerprint de evidência, artifact IDs e origem de qualidade. O modo `shared_av_partial` permanece candidato experimental e reporta só os processadores com quality rejection;
- não marca avaliações científicas, rubrica canônica, direitos de mídia externa, publicação ou produção. Todo recibo próprio tem `synthetic_fixture_only=true`, `auto_retry_enabled=false`, `production_approved=false` e `global_gates_released=false`.

**Não é um scheduler de produção**: o host faz o pedido deliberado do budget e mantém a autoridade de certificados/keys, enquanto o runner só usa a API tipada e autorizada existente. Um `CANDIDATE_ONLY` não é validação científica nem relatório aceito pela rubrica canônica. Ao terminar o budget, o operador decide conscientemente se pode chamar outra vez; nenhuma automação de reintento está habilitada.

## Evidência

- `tests/test_asset_fixture_batch.py`: **28 PASS** locais com substitutos controlados para `FixturePipeline`, `CandidateDecisions` e `AssetRightsDenied`. Casos: terminal tipado, budget, busy/blocked/recovery, SHA inválido, identidade de worker, job e artefato falsos, fraude de marcação científica, job repetido, mudança de plano durante a execução, cross-tenant, qualidade parcial e negação de classe de pipeline não confiável.
- Exatamente os mesmos bytes de módulo/testes publicados foram conferidos por comprimento, soma e checksum ponderado. A sintaxe do novo módulo passou sob Python 3.11; os testes locais rodaram em Python 3.13.
- **A11 focal** agora inclui `python_a027_fixture_batch` com **28 casos esperados** e hash de `asset_fixture_batch.py`, `asset_fixture_pipeline.py` e `asset_candidate_fusion.py`. O runner possui **9 etapas** (zero-spend, sintaxe, A02 ASR 62, A02.7 batch 28, A05/A07 269, A06/E1 29, A07 CDP 13, Node 19, Chrome 7).
- **Não foi executada** a suíte integrada do checkout íntegro no HEAD desta PR; logo, não existe prova atual de que `FixturePipeline` e os jobs nativos estejam homologados juntos. O teste local não prova grants, execução de subprocessos, Windows Job Objects, VLM, ASR, migração, PostgreSQL, CI ou os sete gates.

## Validação no checkout exato da branch

```powershell
git rev-parse HEAD
python -m scripts.a05_python_source_preflight
python -m pytest -q -rs tests/test_asset_fixture_batch.py tests/test_a11_focal_evidence_packet.py
python scripts/verify_zero_spend.py
python docs/base_atemporal/ferramentas/validar_espelho.py
```

Depois, executar no host nativo com as fixtures e chaves locais **já autorizadas**, seguindo o Plano Único e a evidência de direitos, e então A00/A11/CT integrais **no mesmo SHA**. Fechamento da arquitetura ainda requer direitos reais e operação A02, gold e avaliação científica independente, retrieval/agentes, Studio e homologação G0–G6/IMP-131 antes de deploy. Sem custos, migração ou publicação nesta PR.

### Resultado da revisão do contrato da fila

O `AssetJobQueue.claim` devolve também `quota`, `rights_blocked` e `empty`. O executor passou a tratá-los como **paradas sem retry**, sem categorização de sucesso ou promoção de candidatos. Três testes parametrizados adicionais elevaram a suíte isolada de 25 para **28 PASS**. A suite integrada do novo SHA continua **NOT_RUN**.


## Integração com os componentes reais do Stone — incremento posterior

Para evitar confundir testes de interface com autorização real, foi adicionado
`tests/test_asset_fixture_batch_integration.py`, aproveitando as fixtures
assinadas **já existentes** em `tests/test_asset_rights_registry.py`
(`registry`, `discard_fixture`, `queue_fixture`, `_pipeline`).

**Cinco testes de integração preparados para execução nativa no checkout integral:**

1. Quatro jobs de header sintético avançam por **fila SQLite verdadeira**, grant assinado Ed25519, índice de linhagem, vault, armazenamento criptografado de derivados e fusão do `CandidateDecisions` real. Reexecução da mesma seleção não deve aumentar os quatro attempts registrados.
2. Orçamento de dois ticks interrompe sem avaliação; reconstrução explícita do plano com fingerprint pinado conclui os jobs restantes sem duplicar attempts ou ciphertexts.
3. Revogação assinada após construir o plano bloqueia a execução antes de qualquer attempt ou escrita de payload derivado.
4. Lease previamente reivindicado por outro worker retorna `HALTED/busy`, sem roubar o lease, reiniciar job ou disparar nova tentativa.
5. Invalidação da linhagem após o primeiro resultado criptografado bloqueia qualquer processamento adicional e preserva o total de tentativas.

**Escopo exato:** a execução do child adapter Windows é substituída por **uma observação de cabeçalho sintético já definida no projeto**, gravada por `DerivedPayloadStore.finish`. **Não são** substituídos a fila, o banco, o verificador de rights, a criptografia dos derivados nem a fusão. Nenhum conteúdo de terceiros, inferência externa ou autorização de publicação é habilitado.

A11 separa os resultados para evitar falso positivo: `python_a027_fixture_batch` continua com **28 casos de componente esperados**; novo `python_a027_integrated` exige **5 testes reais de SQLite/rights/vault**, e o runner passa a exigir **10 etapas**. Os cinco testes foram **compilados estaticamente**, mas permanecem **NOT_RUN contra o repositório completo**, porque o checkout privado íntegro não está montado neste ambiente. A11 completo e A00 full também permanecem NOT_RUN neste HEAD.

### Comandos para validar a integração no checkout íntegro

```powershell
git rev-parse HEAD
python -m scripts.a05_python_source_preflight
python -m pytest -q -rs tests/test_asset_fixture_batch.py tests/test_asset_fixture_batch_integration.py tests/test_a11_focal_evidence_packet.py
python scripts/verify_zero_spend.py
python docs/base_atemporal/ferramentas/validar_espelho.py
```

Nenhum teste isolado deve ser interpretado como aceite G0–G6, IMP-131 ou autorização de deploy.


## Revisão de proveniência durável do candidato terminal (2026-11-22)

A análise cruzada do contrato `FixturePipeline.step` e das tabelas reais `AssetJobQueue` revelou uma fronteira adicional: o coordenador validava formato e quantidade de `artifact_ids`, mas não reconciliava os IDs terminais com os **recibos persistidos de cada JobSpec**. Um ID de artefato bem formado, porém trocado ou de outro job, podia passar pela validação independente do batch.

A implementação agora consulta `pipeline.queue.status(tenant_id, job_id)` para **cada spec** antes de aceitar o terminal e exige `state=completed`, `reason=encrypted_payload`, mesma identidade tenant/object/job, `receipt_sha256` hexadecimal exato. Recalcula então o ID usando a função original `asset_derived_payloads._artifact_id(spec, receipt_sha256)` e exige a **mesma sequência e valores** devolvidos no candidato final. Nenhum acesso externo, retry, gravação ou concessão de direitos é realizado pela checagem. A validação da fila e do fusion original permanece obrigatória.

**Evidência realmente executada:** 34/34 PASS no laboratório Python isolado da coordenação (28 casos anteriores e seis novos: artefatos trocados, ID bem formado alheio e quatro corrupções parametrizadas do recibo persistido). Utilizou a **fórmula original de `_artifact_id`** e uma fila substituta explícita. Os arquivos publicados foram confrontados por comprimento e checksums de conteúdo com as versões testadas. Esta evidência é de contrato isolado, não de fila SQL.

**Integração pendente:** o arquivo `tests/test_asset_fixture_batch_integration.py` agora tem **seis** casos com fixture assinada/SQLite/vault reais; o sexto injeta swap de artefatos no último recibo, exigindo `ARTIFACT_PROVENANCE_MISMATCH` com quatro jobs processados e nenhuma tentativa adicional. Os seis testes continuam **NOT_RUN** no checkout completo neste HEAD. A11 separa **34 testes isolados esperados** e **6 de integração esperados**; qualquer falta bloqueia a sequência antes do A05/A07. Nenhuma alegação de aprovação G0–G6/IMP-131 decorre das contagens.


## Revisão transacional do PEP final (2026-11-22)

Foi fechada uma janela na fronteira entre a fusão de candidatos e a resposta pública do executor A02.7. A versão anterior lia cada status de job pela `queue.status()` separadamente, depois de o pipeline ter terminado a checagem de direitos. Uma revogação assinada ou uma alteração de permissões entre a fusão e essas leituras poderia não ser reavaliada no **mesmo snapshot transacional** que os recibos finais.

Agora o estágio terminal é **fail-closed** dentro de uma transação única de `AssetJobQueue._transaction()`:
- para cada `JobSpec`, reexecuta `_check_rights` e o grant específico `Permission(operation="derive", field="rubric_evidence", purpose=spec.purpose)`;
- lê o job persistido via `_row` e `_spec`, compara todas as identidades e exige `completed/encrypted_payload`;
- deriva o `artifact_id` do recibo persistido com a implementação original `_artifact_id`, na mesma ordem das `specs`;
- exige que **todos** os `supports` e `vetoes` de cada campo `CandidateDecisions` apontem para artefatos da partição terminal aprovada.

Nenhuma destas verificações cria novas permissões, baixa mídia, renova leases, faz retry, publica conteúdo ou eleva candidatos a ciência. O último recheck é uma prova de autorização **no instante de sua transação**, não uma concessão permanente de direito para usar artefatos depois; consumidores posteriores continuam obrigados a revalidar.

**Evidência efetivamente executada nesta rodada:** `40 passed in 0.21s` de `tests/test_asset_fixture_batch.py`, usando o arquivo real e completo `asset_fixture_batch.py` reproduzido localmente a partir do HEAD do GitHub. Arquivo e testes tiveram igualdade verificada de comprimento, soma de codepoints e checksum ponderado; `ast.parse(feature_version=(3,11))` passou nos dois. As dependências exteriores foram **substituídas explicitamente** (classes fila, PEP, grants, SQL, vault, fusion); logo, estes 40 PASS são **unitários**, não prova de integração/execução nativa.

**Evidência integrada preparada e ainda pendente:** `tests/test_asset_fixture_batch_integration.py` ganhou um sétimo cenário que revoga o ativo com assinatura Ed25519 **depois** de quatro resultados criptografados e da fusão, mas **antes** de o batch devolver o candidato. Espera-se `ASSET_RIGHTS_REVOKED` e nenhum novo attempt; o caso precisa rodar no checkout íntegro, com SQLite/rights/vault reais. A11 exige agora **40 casos de componente e 7 de integração** A02.7, e os 10 estágios continuam sem poder liberar G0–G6 ou IMP-131. **NOT_RUN no HEAD**: A11 completo, A00 integral, os 7 testes de integração, modelo nativo e ciência independente. A PR permanece draft e produção NO-GO.


## Convergência experimental A02.7 + A02/A06/A11 (22/11/2026)

Branch isolada `integration/a027-a06-a11-convergence-20261122`, derivada exatamente de `2a97a55e06ab82e98b0d745eecdcae922f33870b` (PR #69) e importando quatro arquivos pinados do PR #70 no SHA `85817452bc6a458d5dd0a628818cebae0657e02b`. O runner e os testes A11 foram reconciliados **sem retroceder** os limites do PR #69:

- `python_a02_asr_diagnostic`: **91 casos esperados** (não 62);
- `python_a06_e1`: **35 casos esperados** (34 do PR #69 + 1 teste lateral do PR #58; não 29);
- `python_a05_a07`: **270 casos esperados** (269 do PR #69 + 1 teste lateral do PR #49);
- `python_a027_fixture_batch`: **40 casos esperados**;
- `python_a027_integrated`: **7 casos esperados**;
- dez estágios focais, zero-spend e preflight de sintaxe obrigatórios; nenhum estágio muda G0–G6/IMP-131.

Os PRs de origem permanecem em draft. Nesta branch de convergência também foram portadas seletivamente as correções laterais #49 (lock do grant criativo e teste negativo de grant ausente) e #58 (remoção do recibo incompleto em falha de fsync e respectivo teste), sem promover os PRs de origem a aceitos. Os demais limites de integração e homologação permanecem. O código novo de A02.7 teve somente a evidência isolada histórica 40 PASS da PR #70; os 7 testes reais de SQLite/assinatura/vault, o runner A11 focal, A00 integral e os controles multimodais nativos estão **NOT_RUN nesta branch de convergência**. A presença de novas contagens na suite não é execução. Nenhum deploy, merge à main, migração operacional, mídia externa, chamada paga ou liberação de direito foi realizado.

A próxima ação obrigatória é executar a suite no **HEAD exato e checkout limpo** desta branch, validar o espelho documental e gasto zero, diagnosticar qualquer falha com logs locais redigidos e só então preparar a reconciliação dos PRs laterais. Não alterar o Plano Único ou tratar esta nota como aceite de IMP.


## Regressão focal do A11: 140 PASS, 3 FAIL (operador Windows, 22/11)

No HEAD anterior `6f80a22f48efb5422009893d3a7ced04b9eb886d`, após o operador fixar explicitamente a importação ao worktree, o preflight Python 3.11 observou **380 fontes, status PASS**, sem autorização de deploy, e a seleção focal reportou **140 PASS, 3 FAIL** (75,23 segundos; warning não bloqueante do Starlette). Os três FAIL estavam restritos a `tests/test_a11_focal_evidence_packet.py`:

- duas asserções exigiam o SHA de `asset_fixture_batch.py` e do teste integrado no pacote A11; a fixture de teste havia substituído `SOURCE_FILES` por um conjunto de apenas dois arquivos sintéticos, sem esses caminhos;
- o teste de A02.7 SQL incompleto esperava que o runner interrompesse a cadeia, mas `build_packet` continuava depois do diagnóstico negativo, chegando até Chrome.

Correção posterior no PR de integração:

1. A fixture passou a criar todos os arquivos sintéticos de que as asserções de A02.7 precisam, preservando o inventário mockado deliberadamente pequeno;
2. A11 interrompe após o primeiro estágio não aprovado, conservando `BLOCKED_NOT_VALIDATED` e o recibo do estágio falho (os reason codes exclusivos de zero-spend/preflight permanecem);
3. foi acrescentado teste para ASR incompleto interromper antes da fila/Studio;
4. `pyproject.toml` fixa `pytest.pythonpath=["src"]` para isolamento entre checkout do worktree e pacote editável em outro clone; A11 agora calcula também seu hash de fonte, e um teste verifica a configuração.

**Evidência:** verificação de conteúdo do HEAD GitHub, não execução. Os 140 PASS pertencem **somente ao SHA anterior** e não podem ser transferidos à revisão atual. Executar `tests/test_a11_focal_evidence_packet.py` no HEAD exato antes de tentar A11 full. Nenhum gate, dado externo ou produção foi liberado.


## A11 / A02 ASR — divergência da coleta Windows no HEAD `3237796fb...`

**Resultado real do operador:** `scripts.a05_python_source_preflight` PASS em 380 arquivos e `pytest tests/test_a11_focal_evidence_packet.py` **30 PASS**. A execução focal `scripts.a11_focal_evidence_packet --expected-head 3237796...` retornou `BLOCKED_NOT_VALIDATED` após `zero_spend` PASS, `syntax_preflight` PASS e `python_a02_asr_diagnostic` **88 PASS observados / 91 exigidos**. Este bloqueio é correto e não concede aceite de gate.

**Diagnóstico por inspeção da suite pinada:** quatro módulos ASR continham **89 casos coletáveis estimados estaticamente** (19 + 9 + 53 + 8). O módulo CLI continha um `pytest.skip` condicional se o Windows não permitisse criar symlink, compatível com observar 88 casos aprovados; o usuário não forneceu a linha de total de skips, portanto **não se afirma que 1 skip foi confirmado**.

**Incremento de segurança:** preservar o requisito de **91 PASS**, sem alterar thresholds científicos. O teste de symlink da origem agora usa um substituto do verificador `Path.is_symlink` quando o sistema recusa criar um symlink real; mantém a mesma negação de `cli.main`. Dois casos de segurança independentes foram adicionados: diretório privado marcado symlink e caminho de output marcado symlink, ambos devem retornar negação sem criar artefatos. Os 4 módulos passaram a conter **91 casos estimados pela inspeção do código parametrizado** (19 + 11 + 53 + 8) e **nenhum `pytest.skip` explícito** nesses módulos. Em host que suporte symlink, o teste existente ainda usa a criação real.

**Limite de evidência:** `91` é ainda apenas um inventário estático dos casos e não 91 novos PASS. Para verificar, rodar `python -m pytest -q -rs tests/test_asr_strict_diagnostic.py tests/test_a02_asr_strict_diagnostic_cli.py tests/test_shared_av_asr_diagnostic.py tests/test_shared_av_asr_cli.py` em worktree limpo e no HEAD exato. Continuar a exigir `91 passed, 0 skipped, 0 failed` para a entrada A11. Outras etapas A11, A00 integral e aceitação G0–G6/IMP-131 continuam NOT_RUN/BLOCKED neste HEAD. Sem mídia externa, ASR real, licença de terceiros ou production deploy.


## A11 22/11 — passagem ASR/A02.7 e bloqueio A05/A07 264/270

No HEAD `3aca66141bd9e94bd81d9ec206cebf72a14a2268`, o operador informou execução real do packet A11: `zero_spend` PASS; `syntax_preflight` PASS; `python_a02_asr_diagnostic` **91/91 PASS, 0 skipped**; `python_a027_fixture_batch` **40/40 PASS, 0 skipped**; `python_a027_integrated` **7/7 PASS, 0 skipped**. O estágio seguinte `python_a05_a07` registrou **264/270 PASS, 0 skipped, A11_PYTEST_INCOMPLETE**. A11 encerrou a cadeia sem executar A06/Node/Chrome, como previsto pela política fail-closed. `validation_status=BLOCKED_NOT_VALIDATED`; G0–G6 e IMP-131 seguem bloqueados.

Análise do inventário de fontes do próprio `PY_A05_A07` com 25 arquivos: os **270 casos são previstos pela expansão estática** de testes com `@pytest.mark.parametrize`, portanto o limite de 270 **não foi reduzido**. O relatório redigido no terminal não apresentou `observed_fail_count` nem o trace dos erros; por isso, 6 casos não aprovados **não podem ainda ser atribuídos** a seis falhas concretas, erros na execução ou outro motivo.

**Incremento de diagnóstico posterior:** A11 agora registra `observed_error_count` numérico e redigido de `pytest`, juntamente com `observed_fail_count` preexistente, sem guardar logs brutos. Dois testes sintéticos verificam que os perfis hipotéticos `264 passed, 6 failed` e `264 passed, 6 errors` provocam `BLOCKED_NOT_VALIDATED` e interrompem a cadeia ANTES do A06. Os números desses dois novos testes são **fixtures de regressão**, não a causa verificada da falha do operador. Necessário revalidar a suite unitária A11 no novo HEAD.

**Para identificar a causa real, executar a mesma seleção de `PY_A05_A07` diretamente pelo pytest** no HEAD de integração atualizado e checkout limpo, com logs guardados localmente e sem colocar credenciais, payloads privados ou reportes não redigidos no GitHub. Nenhum resultado anterior é transferível a um novo commit. Sem alteração de direitos, dados externos, baseline, políticas de ciência, custo zero, deploy ou aceites globais.


## Diagnóstico A05/A07: seis FAILs reais no Windows

**Log do operador no SHA `a832caf82312caef2467ff69ef7fc9baa3da655a`:** `tests/test_a11_focal_evidence_packet.py` **32 PASS**; execução direta dos 25 arquivos `PY_A05_A07`: **264 PASS, 6 FAIL, zero SKIP, 1 warning (Starlette)**, em ~254 s.

As falhas identificadas e o tratamento planejado, preservando direitos:

1. `test_secure_api_imports_and_mounts_creative_routes`: a checagem filtrava rotas por `isinstance(..., APIRoute)`, omitindo rotas do aplicativo montado. A asserção passa a inspecionar `path` e `methods` das rotas registradas, **sem remover nenhum dos quatro endpoints obrigatórios**.
2. `test_all_legacy_studio_document_post_routes_have_signed_reference_guard`: mesmo filtro ocultava todos os POSTs da verificação. Agora inspeciona todos os `POST /v1/studio/documents/{document_id}...` e **bloqueia se faltar a árvore de dependências ou o guard `deny_unchecked_signed_document_mutation`**.
3. `test_denies_mutation_between_two_checks`: mock do `EvidenceRetriever.handoff` não aceitava `connection=`, usado pela reentrada do método real. Teste corrigido para preservar o argumento e modificar uma única vez o payload após a chamada externa do handoff, exigindo ainda `A05_REFERENCE_DRIFT`.
4. `test_handoff_requires_actual_synthetic_flag_not_just_origin[tamper0]`: payload com `origin=synthetic_local` e `is_synthetic=False` é inválido no modelo e deve negar até leitura de metadados com `EVIDENCE_STORED_PAYLOAD_INVALID`; URL externa válida sem direito de uso continua negada no handoff com `CREATIVE_REFERENCE_RIGHTS_PEP_REQUIRED`. Teste atualizado sem relaxar a validação.
5–6. `test_external_reference_denied_and_no_document_created` e `test_mixed_references_fail_atomically`: os fixtures tentavam criar `instagram` por `POST /v1/creators`, mas esta entrada deve retornar **403** sem grant. Agora confirmam o 403 e criam registros de terceiros **fictícios, somente no banco SQLite descartável de teste**, garantindo que `EvidenceRetriever.get` localiza a referência; em seguida exigem que o endpoint de criativos negue a criação e não grave documentos.

**Status:** seis correções publicadas e seus diffs inspecionados, **NOT_RUN no novo SHA**. Manter A05/A07 **270 PASS** como requisito do A11. Os resultados do SHA antigo não podem ser transferidos. Conferir primeiro os seis testes focais, depois os 25 módulos completos A05/A07 e a cadeia A11 no mesmo HEAD. Garantir que o texto do traceback ou logs a compartilhar sejam redigidos, sem payloads privados nem tokens de sessão.

Nenhum aumento de direitos, bypass no runtime, alteração normativa, gasto, inferência externa, merge à main, G0–G6/IMP-131 ou deploy autorizado.


## A05/A07 268/270 — rotas no aplicativo vs origem dos módulos

O operador executou em `c72096997bda6f219fd56eea96bbacfd580e3fdd` os seis testes A05/A07 previamente falhos: **4 PASS e 2 FAIL**, ambos limitados a **enumeração de rotas**, sem indício de falha dos quatro testes corrigidos de evidências/rights. A11 focal chegou novamente a **ASR 91/91, A02.7 40/40 e integração A02.7 7/7 PASS**, mas `python_a05_a07` reportou **268/270 PASS, 2 FAIL, zero ERROR** e bloqueou por `A11_PYTEST_INCOMPLETE`, corretamente sem prosseguir para A06/Node/Chrome.

Os dois testes restantes exigem os quatro POSTs de `/v1/agent/creative-drafts...` e o guard `deny_unchecked_signed_document_mutation` em todos os POSTs legados `/v1/studio/documents/{document_id}...`. Inspeção no commit demonstrou que os módulos da branch atual **definem** essas rotas, porém os objetos retornados ao pytest anterior não continham as rotas dinâmicas esperadas. Isto **não demonstra ainda** se a origem é uma importação de outra revisão ou divergência de montagem em runtime.

**Incremento de diagnóstico:** as duas verificações exigem, antes da enumeração, que `tapi_gate0`, `secure_api`, `agent_api_e1` e `studio_api` tenham `__file__` exatamente em `stone-pr71/src/tapi_gate0` (relativamente à própria origem dos arquivos de teste). Erros são fixos `A05_WRONG_WORKTREE_IMPORT:<nome do módulo>`, sem divulgar caminhos absolutos. Se as origens baterem mas faltarem rotas, o teste A05 lista apenas nomes/métodos públicos do agente; o teste Studio lista nomes/métodos públicos do Studio, mantendo negação se o guard ou a árvore de dependências não forem encontrados.

**Ação seguinte:** executar só os dois testes em ambiente isolado, confirmando o `PYTHONPATH` para `stone-pr71/src`, sem reproduzir a suite de 270 testes antes de identificar a causa. Se houver import de revisão errada, corrigir a resolução de módulos e repetir. Se as origens forem corretas, tratar a divergência de rotas no próprio runtime. Critérios originais inalterados: os 4 POSTs, todos os guards, 270 PASS e G0–G6/IMP-131 bloqueados até aceite. Atualizações no novo SHA **NOT_RUN** no operador; nenhuma produção ou chamada externa.
