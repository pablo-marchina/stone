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
