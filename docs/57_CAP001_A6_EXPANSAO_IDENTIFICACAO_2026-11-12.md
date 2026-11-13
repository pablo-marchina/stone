# CAP-001 A6 — expansão sistemática e identificação de fontes (incremento inicial)

Data: 12/11/2026. Base empilhada: PR #43, commit `0aa7d86e6d14531d394c6df06ed2174879b7e373`. A5 ainda aguarda confirmação do backup e autorização de merge. A6 não autoriza integração antecipada de A5, produção, admissões científicas ou agendamento.

## 1. Resultado documental A6.1 (parcial)

O arquivo `evidence/acquisition/bd_a6_candidate_expansion_20261112.json` contém 18 novos candidatos em nove estratos documentais, com URLs de evidência e finalidade. Todos estão em `candidate`, sem IDs Meta ou grants inventados. Somados aos 15 registros do manifesto privado A5 reportado (3 aprovados, 12 candidatos), espera-se 33 registros (3 aprovados, 30 candidatos); a contagem final será determinada pelo merge offline. O limite do schema permanece 100 fontes. Meta de 50 candidatos não atingida neste incremento.

- Dez Salas do Empreendedor: Água Boa, Torres, Espírito Santo/RN, São Lourenço do Sul, Santa Maria, Belo Jardim, Maceió, Cristalina, São Luís e Ângulo, com evidência institucional municipal/estadual. Não presumir volume, atividade, identidade Meta atual ou independência amostral.
- Loja Integrada e Contabilizei: canais divulgados pela própria organização e finalidade de pequenos negócios.
- Omie: publicação da organização no LinkedIn indica `omie.oficial`; materiais anteriores citam `omieoficial`, portanto identidade permanece incerta e não deve ser resolvida por suposição.
- Andrael: diretório de parceiros Bling, consultoria ERP, finalidade MPE incerta.
- Rede Mulher Empreendedora, Mente Empreendedora, Feira Preta e Endeavor: referência editorial Santander de perfis de empreendedorismo; não é prova de identidade oficial atual ou audiência exclusivamente MPE.

Os dez perfis municipais representam 10/18 da nova tranche. Evitar superrepresentação regional/institucional e grupos relacionados. A próxima tranche deverá priorizar segmentos ainda pouco representados (varejo, beleza, serviços, logística, associações independentes, empreendedorismo e comércio digital), sem inserir handles sem evidência. Nenhum perfil recebe autorização de coleta só porque foi localizado. A6.1 é uma expansão documental de conveniência e não constitui amostra probabilística.

## 2. Identificação oficial A6.2 (implementação inicial)

`scripts/a6_identify_sources.py` e `src/tapi_gate0/discovery_identity_a6.py` oferecem plano offline e execução opt-in. Até cinco handles explícitos por lote, uma requisição por handle por dia, máximo dez reservas de identidade por dia UTC; reservas contam no orçamento compartilhado de 80 unidades conservadoras (quatro por run de ingestão Instagram, uma por identidade). Não é uma medição da quota ou cobrança efetiva da Meta.

Executar somente com administrador autenticado, flags `TAPI_BD_IDENTITY_ENABLED=1`, `TAPI_OFFICIAL_METADATA_READS=1`, `TAPI_ZERO_BILLING_CONFIRMED=1`, token válido no ambiente. A aprovação institucional DEC-018 já foi concedida e é aplicada automaticamente: nenhum `IdentityScope`, arquivo de escopo, confirmação de aprovação ou validade institucional é solicitado. O contexto operacional deriva do tenant, viewer, hash do manifesto e handles explícitos. A identificação não equivale a um grant de leitura de mídia.

A única consulta é `business_discovery.username(handle){id,username}` no transporte fixo Meta Graph v26.0. Valida viewer, handle, formato de ID, ID esperado se existir e conflitos com IDs conhecidos no manifesto e lote atual. Identificações de lotes separados deverão ser reconciliadas antes de atualizar o manifesto ou criar grants. Para no primeiro erro, não repete automaticamente e não devolve reservas mesmo se não utilizadas.

Cada reserva e resultado vira evento de domínio e outbox; a reserva registra DEC-018, operação, actor, viewer, handle e hash do manifesto, nunca token ou conteúdo de mídia. Reserva de todo lote antes da primeira chamada. Compartilha lease A5/A6, reconhecido pelo recovery já existente; em recuperação de lease órfão não há devolução de reservas. Outros entrypoints A3/A4 não compartilham a lease e não podem operar em paralelo no mesmo tenant. Não exige migração adicional (reusa tabelas 0012, domain_events e event_outbox). Não cria grants, não altera o manifesto, não lê posts e não admite corpus.

## 3. Prévia operacional (sem rede)

Após preservar alterações locais e confirmar checkout A6, com todos os processos de ingestão desligados:

```powershell
git fetch origin
git switch feat/cap001-a6-source-expansion-20261112
git pull --ff-only
$env:PYTHONPATH = "src"
$env:TAPI_DATABASE_URL = "sqlite:///C:/stone-data/tapi.sqlite3"
$env:TAPI_TENANT_ID = "local-research"
$env:TAPI_META_IG_ID = "17841459971757521"
$env:TAPI_BD_IDENTITY_ENABLED = "0"
$env:TAPI_OFFICIAL_METADATA_READS = "0"
$env:TAPI_BD_TECHNICAL_INGEST = "0"
$env:TAPI_BD_CONTINUOUS_ENABLED = "0"
$env:TAPI_ZERO_BILLING_CONFIRMED = "0"
python scripts/a5_expand_source_frame.py `
  --base artifacts/private/bd_manifest_a5_v1.json `
  --candidates evidence/acquisition/bd_a6_candidate_expansion_20261112.json `
  --output artifacts/private/bd_manifest_a6_v1.json

python scripts/a6_identify_sources.py `
  --manifest artifacts/private/bd_manifest_a6_v1.json `
  --source nuvemshop --source contabilizei --source lojaintegrada `
  --source redemulherempreendedora --source saladoempreendedor.saoluis
```

Se o manifesto de saída já existir, não sobrescrever. O plano deve retornar PLAN_ONLY_NO_EXTERNAL_READ, cinco fontes e zero grants; caso contrário, avaliar o bloqueio. A prévia não exige token. Antes de `--execute`, manter backup consistente, executar regressão Windows, preservar as condições técnicas de acesso e custo zero. Não solicitar outra aprovação institucional. A6 ainda não foi executada no banco do operador.

## 4. Validação e próximos incrementos

Sete testes A6: expansão sem aprovar, prévia sem escrita, identidade oficial simulada e orçamento compartilhado, identidade divergente (na versão anterior também expiração de escopo manual), rate limit e reserva preservada, autorização administrativa e flags, CLI sem credenciais. Regressão focada A4/A5/A6/preflight: 46 PASS; verify_zero_spend PASS. Banco temporário SQLite e transporte simulado, sem operação Meta real.

A6.1 continuará até pelo menos 50 candidatos documentais; A6.2 requer teste real de identidade antes da incorporação segura dos IDs. A6.3: reconciliação de resultados, curadoria e registro de grants administrativos específicos, sem promover candidatos automaticamente. A6.4: diversidade de fontes autorizadas, A6.5: expansão histórica, A6.6: agendamento local supervisionado com limites e recuperação, A6.7: cobertura e falhas, A6.8: elegibilidade científica separada. 197 posts únicos e três fontes são a última evidência A5 reportada; não avançaram nesta entrega. Sem gasto contratado.

Regressão completa local Linux: **393 PASS**, 40,20 s, exit code 0, sem credencial Meta e com flags externas desligadas no ambiente do processo. Seis blobs de implementação, teste e manifesto conferidos com a cópia testada; configuração `.env.example` revisada separadamente. Cópia local reconstruída, não CI remoto nem regressão Windows A6.


## Primeira prévia operacional reportada — 12/11/2026

Operador reportou `CANDIDATE_FRAME_EXPANDED`: 15 → 33 entradas, 3 aprovadas preservadas, 30 candidatas, grants_created=0 e external_data_accessed=false. Manifesto privado resultante SHA-256 `e7d0151ef6eab424fffcd0556906e2576e27dd6ef50f2d6d91ee75284074cb45`. Prévia A6 `PLAN_ONLY_NO_EXTERNAL_READ`: selecionados nuvemshop, contabilizei, lojaintegrada, redemulherempreendedora e saladoempreendedor.saoluis. Limite cinco requisições de identidade, zero reservas de identidade no dia, orçamento compartilhado conservador 52/80, nenhum grant e nenhuma chamada externa. Se a execução posterior reservar o lote completo sem operações intermediárias, total esperado 57/80. Evidência reportada pelo operador, não inspeção independente do DB. A6.1 parcial e prévia A6.2 confirmadas; permanecem pendentes regressão Windows A6, backup consistente, execução oficial e reconciliação. PR #44 continua draft sobre #43. Não confundir prévia com autorização de coleta ou identificação concluída.


## Fluxo sem nova aprovação institucional — decisão do responsável de 12/11/2026

Prevalece sobre instruções históricas de aprovação/escopo: utilizar DEC-018, sem pedir referência ou validade novamente. O helper de criação de escopo foi removido, a CLI não possui `--scope` e a função de identificação não recebe `IdentityScope`. O novo teste confirma rejeição de seleção inválida antes de qualquer reserva; o teste de sucesso confirma a referência DEC-018 nos eventos e zero grants novos. Autenticação, flags de operação e custo zero, token, limites, identidade e arquivo privado exclusivo continuam necessários. A CLI não lê o antigo arquivo de escopo, caso exista.

Exemplo de execução, após regressão e com credencial já configurada e condições de gratuidade efetivas:

```powershell
$env:TAPI_BD_IDENTITY_ENABLED = "1"
$env:TAPI_OFFICIAL_METADATA_READS = "1"
$env:TAPI_ZERO_BILLING_CONFIRMED = "1"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_identify_sources.py --manifest artifacts/private/bd_manifest_a6_v1.json --source nuvemshop --source contabilizei --source lojaintegrada --source redemulherempreendedora --source saladoempreendedor.saoluis --execute --report "artifacts/private/a6-identity-$stamp.json"
```

O único prompt desta execução é a senha do administrador para autenticação; não é aprovação. A nova versão precisa de regressão; não reutilizar a contagem de testes anterior como se fosse resultado do código atualizado. Ver [DEC-018](53_DEC018_CONFIRMACAO_ALCANCE_E_CRITERIO_REVISAO_2026-11-05.md) e [AGENTS.md](../AGENTS.md).


## Primeiro lote real A6 — recusa do provedor e diagnóstico — 12/11/2026

Operador reportou `a6identity-20261112162207-5398ce38`, IDENTITY_BATCH_STOPPED, manifesto `e7d0151ef6eab424fffcd0556906e2576e27dd6ef50f2d6d91ee75284074cb45`, DEC-018 aplicada automaticamente. A primeira consulta (nuvemshop) retornou PROVIDER_PERMISSION_DENIED. Quatro fontes restantes não foram consultadas. Cinco reservas registradas, zero identificações, zero grants, zero posts, zero admissões científicas. Orçamento local esperado 57/80, dos quais 5/10 reservas de identidade no dia UTC. Não devolver reservas, repetir esses handles no mesmo dia ou contornar recusa do provedor. O campo external_data_accessed=false pertence ao plano prévio, não ao resultado da execução. O log não permite distinguir HTTP 401/403, token expirado, escopo efetivo ou acesso específico ao perfil. Não afirmar recusa definitiva do perfil.

Incremento de diagnóstico: OfficialHttp preserva somente http_status, code e error_subcode numéricos limitados, quando presentes, para erros HTTP Instagram. Não grava mensagem, fbtrace_id, payload, credencial, URL ou cabeçalho. Mantém códigos internos e comportamento de parada/quotas. A6 inclui diagnóstico no evento de resultado e relatório. A resposta bruta anterior não foi guardada e não é recuperável por este código. Verificar o token no depurador oficial da Meta, localmente e sem compartilhá-lo; conferir validade, app, conta e permissões efetivas antes de nova leitura. Não mudar de token para contornar restrição ao perfil. Depois de resolver a credencial/permissão e em novo dia UTC, executar lote de um perfil para diagnóstico antes de retomar lotes maiores. A DEC-018 não requer nova aprovação institucional.

Testes: 10 novos casos de diagnóstico (HTTP 401/403/400/429/500, payload inválido, tipos não numéricos, recursão, YouTube). 38 PASS na regressão local focada com testes existentes de ingestão, cursor e preflight Business Discovery, em cópia do checkout anterior cuja versão original do connector e blobs corrigidos/testes correspondem exatamente ao GitHub. Teste A6 de persistência do diagnóstico em evento/relatório atualizado, ainda não executado na branch final; suíte completa e Windows pendentes. Nenhuma chamada externa ou mutação no banco do operador nesta correção.


## Regressão focal Windows e proteção diária confirmadas — 12/11/2026

Operador reportou `python -m pytest -q tests/test_meta_error_diagnostics.py tests/test_discovery_identity_a6.py`: **18 passed in 4.22s**. A tentativa posterior de identificação unitária de nuvemshop retornou `BD_IDENTITY_DAILY_ATTEMPT_EXISTS`. Conferido no código: a validação ocorre em plan_identity, dentro da lease, antes de qualquer nova reserva ou chamada ao transporte oficial. Não houve novo diagnóstico Meta nem nova reserva de identidade por essa tentativa; a CLI pode ter criado relatório vazio e eventos locais de autenticação/lease. Não apagar reservas nem repetir o perfil antes da mudança do dia UTC (13/11/2026 00:00 UTC, 12/11/2026 21:00 em Brasília). Manter o relatório privado vazio, caso exista, ou usar novo nome na próxima execução. Evidência reportada pelo operador, não inspeção independente da base. A regressão focal do diagnóstico e A6 está confirmada em Windows; suíte completa atualizada, diagnóstico efetivo da recusa inicial e identificação bem-sucedida continuam pendentes. Nenhuma nova aprovação institucional necessária (DEC-018).


## Diagnóstico real de credencial Meta — 13/11/2026 UTC (12/11 Brasília)

Operador reportou prévia no novo dia UTC com orçamento reservado 0/80 e zero reservas de identidade. O lote unitário `a6identity-20261113014108-09a7544c` consultou nuvemshop e parou em PROVIDER_PERMISSION_DENIED; diagnóstico preservado: HTTP 401, Graph code 190, error_subcode 463. A documentação Meta associa 190/463 a sessão/token expirado ou inválido, com reautenticação necessária. Isso identifica a falha atual como autenticação, não comprova recusa específica do perfil nem permite atribuir retrospectivamente o erro anterior à mesma causa. Nenhum ID, grant, post, admissão científica ou liberação de produção. Uma reserva de identidade e orçamento conservador esperado 1/80 no dia UTC, se não houve operações intermediárias. Não repetir nuvemshop no dia UTC 13/11; não devolver reserva. Renovar a credencial do mesmo aplicativo/conta via ferramentas oficiais, verificar validade e permissões no Access Token Debugger sem compartilhar o token. Preferir token de maior duração se suportado pelo fluxo efetivo. Após correção da credencial, é possível planejar um perfil distinto já documentado e ainda não reservado, sem contornar bloqueio de fonte (a recusa atual é de autenticação); não consultar outras fontes até corrigir a credencial. Nova tentativa de nuvemshop a partir de 14/11 00:00 UTC = 13/11 21:00 Brasília. Diagnóstico seguro A6 validado em execução real; sucesso de identificação e regressão completa permanecem pendentes. DEC-018 segue vigente, sem nova aprovação institucional. Evidência reportada pelo operador, sem inspeção independente da base ou novas chamadas externas pelo assistente.


## Primeiro sucesso real e reconciliação A6.3 — 13/11/2026 UTC

Operador reportou `a6identity-20261113014308-f39d45ee`: `IDENTITY_BATCH_COMPLETED`, contabilizei IDENTIFIED, ID `17841400139166475`, mesmo manifesto SHA-256 `e7d0151ef6eab424fffcd0556906e2576e27dd6ef50f2d6d91ee75284074cb45`. A credencial funcionou em chamada oficial após o diagnóstico 190/463; não inferir acesso às publicações nem causa definitiva da recusa inicial. Uma nova reserva; total esperado 2/10 identidade e 2/80 compartilhado no dia UTC se não houve operações intermediárias. 33 fontes documentadas, 3 grants existentes, 197 posts únicos; nenhum novo grant, post, admissão científica ou liberação de produção. Evidência reportada pelo operador, sem inspeção direta da base.

Implementação A6.3 inicial: `discovery_reconcile_a6.py` e `scripts/a6_reconcile_identities.py`. Lê eventos de reserva e resultado de `bd_identity` no tenant local, valida versões 1/2, vínculo aggregate_id derivado da reserva UTC, outbox, sequência, viewer, DEC-018, operação, hash exato do manifesto e handle. Aceita somente IDENTIFIED; bloqueia conflitos handle/ID inclusive entre lotes do tenant e com fontes já presentes. Reservas sem resultado e falhas ficam excluídas. Não confia em ID copiado do terminal ou relatório JSON arbitrário. Preserva decisões e grants existentes, adiciona somente expected_ig_id à entrada candidata. Não altera o banco, não usa token, não faz consulta externa e não promove a fonte para approved. Saída nova privada e exclusiva, opcional; sem output funciona como prévia. Até 20 ciclos por chamada, todos vinculados à versão exata do manifesto de entrada. Não misturar ciclos de manifestos diferentes; preservar versões anteriores.

```powershell
git pull --ff-only
python -m pytest -q tests/test_discovery_reconcile_a6.py
python scripts/a6_reconcile_identities.py --manifest artifacts/private/bd_manifest_a6_v1.json --cycle a6identity-20261113014308-f39d45ee
python scripts/a6_reconcile_identities.py --manifest artifacts/private/bd_manifest_a6_v1.json --cycle a6identity-20261113014308-f39d45ee --output artifacts/private/bd_manifest_a6_v2.json
```

Esperado: verified_identities=1, ids_added=1, contabilizei/candidate, sources=33, approved=3, grants_created=0, database_written=false, external_data_accessed=false. Usar v2 para novos lotes após confirmar o resultado. Nuvemshop e Contabilizei já reservadas neste dia UTC; não repetir. 

10 testes novos PASS (1,02s) em SQLite temporário com eventos sintéticos equivalentes à estrutura real A6, em cópia reconstruída do checkout anterior e modelo A4. Três blobs novos conferidos com GitHub por hash. Não é regressão completa da branch atual ou validação do banco operacional. Validação Windows pendente. Provisionamento de grants técnicos em lote e curadoria continuam no próximo incremento A6.3, com DEC-018 como referência automática e sem pedidos institucionais repetidos; não simular permissões do provedor.


## Reconciliação real e segundo lote bem-sucedido — 13/11 UTC

Operador confirmou `IDENTITY_RECONCILIATION_PLANNED` e `IDENTITIES_RECONCILED` para contabilizei (ciclo a6identity-20261113014308-f39d45ee), 1 ID acrescentado, 33 fontes, 3 aprovadas, sem escrita DB, grants ou rede. Manifesto v2 SHA-256 `7538bb28ead98ac07a95a418196141893a17f798a6baece46cb366a9baf737cf` (v1 e7d0151ef6eab424fffcd0556906e2576e27dd6ef50f2d6d91ee75284074cb45). Prévia e execução correspondentes.

Segundo lote `a6identity-20261113015031-9e1b751a` sobre v2, IDENTITY_BATCH_COMPLETED: lojaintegrada 17841400335392901; redemulherempreendedora 17841400631433694; saladoempreendedor.saoluis 17841440388740768. Três novas identificações; cumulativo A6 quatro identidades, cinco reservas no dia UTC (2 anteriores + 3, orçamento esperado 5/80). Zero grants novos, posts, admissões ou produção. Contabilizei já reconciliada; outras três ainda devem ser reconciliadas. Última cobertura 197 posts técnicos, 3 fontes com coleta real. Evidência reportada pelo operador, não inspeção independente.

## A6.3 — provisionamento técnico em lote

Implementados `discovery_grants_a6.py` e `scripts/a6_provision_grants.py`: prévia sem credencial/rede; execução autenticada admin, até dez candidatos/review explícitos, IDs conciliados com eventos A6 (reserva/resultado/outbox, DEC-018, viewer e conflitos cruzados), evidência de audiência documentada e intenção não excluída. Grava todos os novos grants em uma transação, audit/outbox existentes, referência `DEC-018:A6:business_discovery_metadata_read:<viewer>:<target>`. Não solicita nova aprovação institucional. TTL técnico local de 30 dias escolhido como limite operacional revogável, **não** vencimento institucional nem garantia de token válido. Não reativa grant revogado, expirado ou conflitante; reexecução sobre manifesto de entrada com grants ativos idênticos reutiliza os registros sem duplicar eventos. Mantém grants prévios intactos. Novos grants têm technical_verified_at nulo. Prefixo restrito: rota genérica de ingestão e rota científica recusam, rota técnica valida viewer/target. Sem nova migração. Não é liberação de direitos de mídia, admissão científica ou prova de acesso às publicações; as leituras oficiais posteriores continuam sujeitas aos gates técnicos existentes. Não executar outros processos de ingestão simultaneamente.

Saída exclusiva privada: v3 após reconciliação; v4 após provisionamento. Banco e arquivo são recursos distintos: se a gravação do manifesto falhar após commit, usar manifesto v3 original e um nome de saída novo, reaproveitando os grants idênticos ativos. Não apagar nem reativar grants para recuperar. A prévia não cria arquivo. Recomenda-se backup consistente e regressão completa antes de mutações operacionais.

```powershell
git pull --ff-only
python -m pytest -q tests/test_discovery_grants_a6.py tests/test_discovery_reconcile_a6.py
python -m pytest -q
python scripts/verify_zero_spend.py
python scripts/a6_reconcile_identities.py --manifest artifacts/private/bd_manifest_a6_v2.json --cycle a6identity-20261113015031-9e1b751a --output artifacts/private/bd_manifest_a6_v3.json
python scripts/a6_provision_grants.py --manifest artifacts/private/bd_manifest_a6_v3.json --source contabilizei --source lojaintegrada --source redemulherempreendedora --source saladoempreendedor.saoluis
python scripts/a6_provision_grants.py --manifest artifacts/private/bd_manifest_a6_v3.json --source contabilizei --source lojaintegrada --source redemulherempreendedora --source saladoempreendedor.saoluis --execute --output artifacts/private/bd_manifest_a6_v4.json
```

A última linha altera o banco local; executar somente após regressão e backup, sem novos pedidos de aprovação institucional. Resultado esperado 4 novos grants técnicos, 7 fontes aprovadas tecnicamente no manifesto, zero posts novos. Se algum candidato não satisfizer as condições, todo lote é bloqueado. Nenhuma execução no banco do operador realizada pelo assistente.

Validação: 15 PASS em 1,31 s (10 reconciliação + 5 grants/CLI/isolamento) em SQLite temporário e cópia reconstruída do código com as mesmas alterações de guards sobre versão anterior; três blobs novos do provisionamento conferidos por hash. verify_zero_spend PASS. Não é teste integral do head A6 (os módulos A5/A6 completos não estavam disponíveis no checkout local); proteção na rota científica revisada por código, não exercitada em teste específico novo. Regressão completa do PR, Windows e prova operacional de grant/ingestão pendentes. A6.1 expansão documental para 50 candidatos também pendente.


## Provisionamento operacional concluído — 13/11/2026 UTC

Operador reportou reconciliação v2→v3 (`55f23249266b33102a8df685db5167e35337e7e5d1fda3c854e6dbfb12adfc36`), 3 IDs acrescentados, 33 fontes, 3 aprovadas, sem escrita no DB ou rede. Prévia TECHNICAL_GRANTS_PLANNED selecionou quatro candidatos conciliados, nenhum grant existente para eles. Execução autenticada TECHNICAL_GRANTS_PROVISIONED criou 4 grants técnicos, manifesto v4 `12c9d33bfd6392df30b173e2d206bc90b17a86d356a9d0dc3cb6431c44e786e3`, total 7 entradas aprovadas tecnicamente e 26 não aprovadas; TTL operacional 30 dias, DEC-018 automática, zero leitura externa, technical_verified=false, zero admissões. Quatro fontes novas: contabilizei 17841400139166475; lojaintegrada 17841400335392901; redemulherempreendedora 17841400631433694; saladoempreendedor.saoluis 17841440388740768. A6.3 validada pelo resultado operacional reportado; a base não foi inspecionada diretamente. Última cobertura real 197 posts/3 fontes, não 7 fontes observadas. Regressão integral do head e backup ainda sem evidência reportada.

Próximo passo A6.4/A6.5: piloto de histórico com manifesto v4, quatro fontes, duas páginas de dez por fonte (até 8 chamadas oficiais e 80 observações elegíveis no máximo; 16 unidades conservadoras reservadas caso as quatro sejam iniciadas). O planner existente prioriza fontes sem checkpoint; confirmar seleção exata das quatro novas antes de executar. Se plano divergir ou bloquear, não executar. No dia UTC 13/11, se não houve operações intermediárias, orçamento antes 5/80 e depois até 21/80. Não confundir cota local com faturamento. Após validar regressão com flags externas desligadas e preservar backup consistente, habilitar somente os flags técnicos necessários e usar credencial válida. Não executar outros processos de ingestão simultaneamente.

```powershell
python scripts/a5_business_discovery_cycle.py --manifest artifacts/private/bd_manifest_a6_v4.json --mode history --max-sources 4 --page-limit 10 --max-pages 2 --daily-request-budget 80
# Após verificar seleção e condições técnicas:
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a5_business_discovery_cycle.py --manifest artifacts/private/bd_manifest_a6_v4.json --mode history --max-sources 4 --page-limit 10 --max-pages 2 --daily-request-budget 80 --execute --report "artifacts/private/a6-history-pilot-$stamp.json"
```

Auditar individualmente cada run efetivamente concluído com `scripts/a3_business_discovery_first_batch.py --audit <run_key>`; relatar observações, validade das trilhas e cobertura. Sem nova aprovação institucional. Se ocorrer falha, parar e inspecionar; o batch técnico ainda não propaga os códigos numéricos do provedor no resumo, diferentemente da A6 identidade. Não agendar, não presumir recuperação robusta ou corpus científico aceito.


## Primeiro ciclo histórico A6 bem-sucedido e regressão integral Windows — 13/11/2026 UTC

Operador reportou suíte completa **419 passed, 1 warning in 147.92s** e `verify_zero_spend.py` PASS, após desabilitar flags externas conforme procedimento. Warning não detalhado; evidência reportada, não CI independente. Código operacional correspondente ao head anterior `dfa375951f6ca37cc1bffc0ebedc142445533d36` presumido pela sequência dos comandos; git rev-parse não fornecido.

Prévia do manifesto v4 (`12c9d33bfd6392df30b173e2d206bc90b17a86d356a9d0dc3cb6431c44e786e3`): 33 fontes, 7 aprovadas; seleção exata contabilizei, lojaintegrada, redemulherempreendedora, saladoempreendedor.saoluis; 5/80 unidades reservadas, 8 chamadas máximas, 80 observações máximas, 197 registros únicos, 3 perfis observados, zero duplicidade entre fontes.

Execução `a5history-20261113020343-48e4f64b`: BATCH_COMPLETED; 8 páginas examinadas, 80 retornadas, 24 recentes demais, 56 elegíveis tecnicamente e **56 novos registros**, zero refresh/duplicatas/duplicatas do provedor; **197→253 IDs únicos, 3→7 perfis com registros**, zero duplicidade entre fontes. Zero admissões científicas, scientifically_validated=false, production_approved=false. Relatório privado `artifacts/private/a6-history-pilot-20261112-230343.json`. O resumo agregado não informa contagem individual nem estado de checkpoint de cada fonte; extrair do relatório local e reauditar os quatro runs. Orçamento conservador esperado após o ciclo: 21/80 (5 anteriores + 4 reservas de ingestão ×4); 5/10 identidade. Conferir no próximo plano. Não confundir reserva com chamadas efetivas ou cobrança. 

Próxima etapa: reauditoria local dos runs -01 a -04 e inspeção do relatório privado; preservar checkpoints; backup consistente após as mutações. A expansão documental ainda precisa alcançar a meta, e a seleção diversificada e operação contínua não estão finalizadas. Com 7/30 perfis e 253/2000 posts técnicos, cobertura é 23,33% e 12,65% das metas mínimas técnicas, não comparabilidade científica. PR #44 permanece empilhado draft sobre #43, sem merge. Não agendar até corrigir/validar recuperação de falhas e coordenação entre entrypoints. Nenhuma nova aprovação institucional necessária.


## Reauditoria do piloto A6 e backup consistente — 13/11/2026 UTC

Operador extraiu relatório privado do ciclo `a5history-20261113020343-48e4f64b` e reexecutou `a3_business_discovery_first_batch.py --audit` para os quatro runs. Resultados:

| Fonte | Sufixo run | Novos / observações reauditadas | Páginas | Checkpoint | Audit / persisted |
|---|---|---:|---:|---|---|
| contabilizei | -01 | 15 | 2 | continuation_available | true / true |
| lojaintegrada | -02 | 17 | 2 | continuation_available | true / true |
| redemulherempreendedora | -03 | 4 | 2 | continuation_available | true / true |
| saladoempreendedor.saoluis | -04 | 20 | 2 | continuation_available | true / true |

Total 56 observações reauditadas, 8 páginas, quatro trilhas válidas e quatro checkpoints de continuação. Cobertura anterior reportada permanece 253 IDs técnicos únicos e 7 fontes com registros; nenhum novo acesso externo nesta reauditoria. SQLite backup pela API nativa, origem aberta em modo somente leitura, `PRAGMA integrity_check` igual a ok; operador reportou BACKUP_VERIFICADO em `C:\stone-data\backups\tapi-a6-20261112-230541.sqlite3`. Evidência de backup pós-A6, não prova backup pré-migração A5 nem teste de restauração. Não registrar conteúdo privado no Git.

Próximo lote de identificação proposto: contaazul (gestão MPE), abraselnorn (alimentação/associação), abihpecoficial (beleza/cosméticos, intenção incerta), feirapretaoficial (empreendedorismo negro/economia criativa, intenção incerta), menteempreendedora (educação empreendedora, intenção incerta). Todos já documentados nos JSON A5/A6, com referência de audiência. A escolha substitui a sugestão anterior de três perfis comerciais individuais cujo registro original não contém audience_rationale_reference: serem negócios pequenos não comprova audiência MPE (DEC-016), e não preencher justificativa artificialmente. Evitar duas regionais Abrasel no mesmo lote. Identificação não determina automaticamente elegibilidade de publicações. Confirmar prévia em v4 e quota; expectativa 5/10 reservas de identidade e 21/80 compartilhado antes do lote, 10/10 e 26/80 depois se ainda no mesmo dia UTC e sem operações intermediárias. Identificar somente via API oficial com credencial válida; parar em falha e não reusar reserva. Reconciliar resultado com v4 antes de provisionar os novos grants. PRs #43/#44 permanecem draft; backup atual confirmado, sem merge. Recuperação sob falhas reais e coordenação entre entrypoints seguem pendentes, portanto manter execução serial supervisionada. DEC-018 vigente, sem nova aprovação institucional.


## Terceiro lote de identidade real — 13/11/2026 UTC

Operador reportou prévia sobre v4 `12c9d33bfd6392df30b173e2d206bc90b17a86d356a9d0dc3cb6431c44e786e3`, 5/10 reservas de identidade e 21/80 compartilhado, confirmando a contabilidade do piloto. Execução `a6identity-20261113020813-710eacbc`: IDENTITY_BATCH_COMPLETED, cinco IDs oficiais distintos, nenhuma falha:

| Fonte | Instagram ID |
|---|---|
| contaazul | 17841400850775253 |
| abraselnorn | 17841401199718642 |
| abihpecoficial | 17841407256098039 |
| feirapretaoficial | 17841402334344300 |
| menteempreendedora | 17841402289934850 |

Cumulativo A6: nove identidades bem-sucedidas; 10/10 reservas de identidade no dia UTC, orçamento compartilhado esperado 26/80 se não houve operações intermediárias. Zero novos grants, posts, admissões e liberação de produção nesta identificação. O campo external_data_accessed=false está no plano prévio, não caracteriza a execução. Cobertura real preservada: 253 IDs únicos, 7 fontes observadas, 33 fontes documentadas. Evidência reportada, não inspeção independente do DB. Intenção MPE de três novas fontes incerta; identificação não implica elegibilidade científica. Não repetir identificação neste dia UTC.

Próximo fluxo operacional, sem nova aprovação institucional: reconciliar v4→v5 a partir do ciclo persistido; planejar e provisionar os cinco grants técnicos em v5→v6, utilizando DEC-018. Se bem-sucedido, 12 fontes habilitadas, ainda 7 observadas. Usar plano A5 histórico com v6, cinco fontes, duas páginas de dez itens por fonte para piloto (10 requisições oficiais máximas, 100 observações máximas, 20 unidades conservadoras por cinco reservas). Confirmar seleção exata dos cinco novos perfis, cobertura de partida 253/7 e orçamento 26/80 antes de executar. Teto 353 posts únicos e 12 fontes observadas, não previsão garantida; orçamento esperado até 46/80. Depois reauditar todos os runs concluídos e preservar checkpoints. Manter execução serial supervisionada; nenhuma nova chamada externa ou mutação do banco feita pelo assistente.

```powershell
python scripts/a6_reconcile_identities.py --manifest artifacts/private/bd_manifest_a6_v4.json --cycle a6identity-20261113020813-710eacbc --output artifacts/private/bd_manifest_a6_v5.json
python scripts/a6_provision_grants.py --manifest artifacts/private/bd_manifest_a6_v5.json --source contaazul --source abraselnorn --source abihpecoficial --source feirapretaoficial --source menteempreendedora
python scripts/a6_provision_grants.py --manifest artifacts/private/bd_manifest_a6_v5.json --source contaazul --source abraselnorn --source abihpecoficial --source feirapretaoficial --source menteempreendedora --execute --output artifacts/private/bd_manifest_a6_v6.json
python scripts/a5_business_discovery_cycle.py --manifest artifacts/private/bd_manifest_a6_v6.json --mode history --max-sources 5 --page-limit 10 --max-pages 2 --daily-request-budget 80
# Somente após conferir o plano, flags, credencial e ausência de outros processos:
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a5_business_discovery_cycle.py --manifest artifacts/private/bd_manifest_a6_v6.json --mode history --max-sources 5 --page-limit 10 --max-pages 2 --daily-request-budget 80 --execute --report "artifacts/private/a6-history-pilot-$stamp.json"
```

Backup pós-piloto anterior confirmado, não contém necessariamente este lote; preservar backup atualizado após novas mutações. Regressão reportada 419 PASS permanece referência (incrementos desde então documentais). PRs #43/#44 ainda draft. Recuperação, renovação técnica dos grants e agendamento contínuo não homologados.


## Segundo piloto histórico A6 — 13/11/2026 UTC

Evidência operacional reportada pelo operador no log anexado. Reconciliação v4→v5: cinco IDs acrescentados, 33 fontes, 7 aprovadas; hash v5 `3f8783b437345fd71e03f1dce388fcfcb6e8ff43fa9eae357c6bf77139f2579b`. Provisionamento dos cinco grants concluído, DEC-018, v6 `9d09ce2981d42a2aa1de643d4135096740809bad922279eed3e2b4dd939d1079`, total 12 fontes habilitadas, 21 não habilitadas, zero rede durante provisionamento. Prévia do histórico v6 confirmou 26/80 unidades reservadas e seleção abihpecoficial, abraselnorn, contaazul, feirapretaoficial, menteempreendedora.

Ciclo `a5history-20261113021012-0b5d54d6`: BATCH_COMPLETED, 10 páginas examinadas, 100 retornadas, 62 recentes demais, 38 elegíveis e novas, zero refresh/duplicatas. Cobertura **253→291 IDs únicos e 7→10 fontes com registros**, zero duplicidade entre fontes e zero admissões científicas. Dois perfis do lote não produziram registros elegíveis; o resumo agregado não identifica quais, nem informa checkpoints individuais. Relatório privado `artifacts/private/a6-history-pilot-20261112-231010.json`. Reauditoria individual dos cinco runs pendente (para fontes sem observações, has_persisted_observations=false pode ser resultado esperado; conferir contagem, status, trilha e checkpoint). Não interpretar ausência de registros como falha da fonte nem como prova de inadequação científica.

A6 acumulada: 94 novos posts, 9 novos grants, 7 novos perfis observados em relação ao ponto de partida A5 (197/3). Orçamento esperado 46/80 após cinco reservas de ingestão; 10/10 identidade. Restam 34 unidades, capacidade de oito reservas de ingestão (32 unidades) se não houver outras operações no mesmo dia UTC. Após reauditar e conferir checkpoints, é possível planejar dois ciclos históricos sequenciais, até 5 e 3 fontes, quatro páginas de dez itens por fonte, teto combinado de 320 observações (não garantia de novas publicações), orçamento esperado 78/80. A fila padrão prioriza checkpoints mais antigos e não necessariamente os dois perfis sem registros; não prometer seleção antes de verificar o plano. Executar somente com credencial válida, flags técnicos e sem processos concorrentes; parar em qualquer falha. Manter quotas e reauditar cada ciclo. Backup pós-primeiro piloto não abrange necessariamente este novo lote; atualizar backup depois das mutações. Regressão Windows de 419 PASS permanece referência (sem alteração executável neste registro). PRs #43/#44 seguem draft; recuperação e agendamento não homologados. Nenhuma nova aprovação institucional necessária.


## Aprofundamento histórico e fechamento do orçamento diário — 13/11/2026 UTC

Operador reportou reauditoria dos cinco runs do segundo piloto `a5history-20261113021012-0b5d54d6`: ABIHPEC 19, Abrasel RN 3, Conta Azul 0, Feira Preta 16, Mente Empreendedora 0; todos all_traces_valid=true, todos continuation_available, e has_persisted_observations=false somente nas duas fontes sem observações. Total 38 observações reauditadas.

Dois ciclos reais adicionais sobre manifesto v6 `9d09ce2981d42a2aa1de643d4135096740809bad922279eed3e2b4dd939d1079`:

| Ciclo | Fontes selecionadas | Páginas | Retornadas | Novos | Cobertura após |
|---|---|---:|---:|---:|---:|
| a5history-20261113021226-32f8ca85 | sebrae, seliganoton, stone, contabilizei, lojaintegrada | 20 | 200 | 194 | 485 |
| a5history-20261113021333-91da7237 | redemulherempreendedora, saladoempreendedor.saoluis, abihpecoficial | 12 | 120 | 120 | 605 |

Ambos BATCH_COMPLETED; 291→485→605 media IDs únicos, 10 perfis com registros mantidos, zero duplicidades entre fontes, zero refresh/duplicatas e zero admissões científicas. Primeiro ciclo: 200 retornadas, 194 elegíveis, 0 recentes; seis exclusões não detalhadas no resumo agregado. O leitor mantém contadores unsupported_format, missing_metrics, invalid_metadata no provider_counts por fonte, mas o agregado não os expõe. Inspecionar relatório privado para determinar a categoria, sem presumir causa. Segundo ciclo: 120/120 elegíveis. Relatórios `artifacts/private/a6-history-expansion-20261112-231225.json` e `artifacts/private/a6-history-expansion-20261112-231332.json`.

A6 cumulativa: 408 novos posts (197→605), 9 novos grants (3→12), 7 novos perfis observados (3→10), 17 runs de histórico A6 (4+5+5+3), 50 páginas examinadas (8+10+20+12), 500 retornadas, 86 recentes demais, 6 outras exclusões a classificar, 408 elegíveis/novas. 94 observações A6 reauditadas antes destes dois ciclos; reauditoria dos 314 novos registros e inspeção individual de oito checkpoints pendentes. 419 PASS Windows permanece última regressão reportada; código não alterado. Evidências reportadas pelo operador, não inspeção independente.

Planos confirmaram 46/80 antes da expansão 1 e 66/80 antes da expansão 2. Após a última, expectativa 78/80 (10 reservas de identidade + 17 reservas de ingestão ×4), 10/10 identidade. As duas unidades restantes não comportam uma reserva de ingestão (4); não executar mais chamadas neste dia UTC, não reduzir ou reiniciar artificialmente a quota. Verificar em prévia local. Próxima renovação diária 14/11 00:00 UTC = 13/11 21:00 Brasília. Conta Azul/Mente Empreendedora permanecem sem registros e com cursor de continuação do piloto. Priorizar retomada na próxima janela, evitando alegar seleção antes de prévia. Metas técnicas 605/2000 (30,25%) e 10/30 (33,33%); 12 habilitadas, 33 documentadas, zero comparabilidade científica.

Antes de retomar: reauditar oito runs, extrair contadores de exclusão por fonte, verificar backup pós-605 em novo arquivo SQLite e confirmar ausência de runs/leases ativos com CLI de inspeção somente leitura. O backup anterior pós-253 não contém necessariamente os novos dados. Trabalhar offline na expansão documental A6.1, distribuição por estrato e correção de recuperação/coordenação; agendamento ainda não homologado. PRs #43/#44 seguem draft. DEC-018 vigente, nenhuma nova aprovação institucional necessária.


## Reauditoria integral dos ciclos de expansão — 13/11/2026 UTC

Operador confirmou as oito reauditorias dos ciclos a5history-20261113021226-32f8ca85 e a5history-20261113021333-91da7237: 40/40/34/40/40 e 40/40/40 observações, respectivamente; todos all_traces_valid=true e has_persisted_observations=true. Total 314 observações reauditadas. Contadores privados da expansão 1 confirmaram seis exclusões por missing_metrics exclusivamente na Stone; zero unsupported_format e invalid_metadata nas cinco fontes. Não imputar métricas ausentes como zero. Todos os cinco checkpoints da expansão 1 continuation_available; estados individuais dos três checkpoints da expansão 2 ainda não apresentados.

A6 acumulada: 408 novos registros em 17 runs históricos, todos reauditados, 500 retornadas, 86 recentes e 6 métricas ausentes, 50 páginas, zero duplicidades entre fontes. Cobertura 605 posts técnicos únicos, 10 fontes observadas, 12 habilitadas, 33 documentadas, zero admissões científicas. Reconstrução aritmética por fonte com base nas contagens anteriores: Stone 106, Ton 105, Sebrae 100, Sala São Luís 60, ABIHPEC 59, Loja Integrada 57, Contabilizei 55, Rede Mulher 44, Feira Preta 16, Abrasel RN 3, Conta Azul 0, Mente Empreendedora 0. Confirmar distribuição diretamente no DB antes de utilizá-la em análise científica. Backup pós-605 e inspeção de recuperação ainda pendentes; backup anterior pós-253 confirmado. Evidências reportadas pelo operador, não inspeção direta do DB. Orçamento esperado 78/80 e 10/10 no dia UTC. Não iniciar novas leituras até a próxima janela; trabalhar offline na expansão documental, relatório consolidado e robustez da recuperação. DEC-018 permanece vigente. Nenhuma nova aprovação institucional.


## A6.7 — Reauditoria consolidada de relatórios históricos

Novo `scripts/a6_audit_history_reports.py`: leitura exclusivamente local de até 20 relatórios históricos privados A5/A6 concluídos e do SQLite existente. Verifica ordem das fontes, identidade de run, unicidade dos runs, tenant, plataforma, conta, estado completed, auditoria existente, observações/evidências correlacionadas, viewer para observações persistidas, método e ausência de avaliação científica. Consolida contadores de exclusão e verifica as identidades aritméticas e totais agregados do lote. Não requer token, não escreve no banco, não faz leitura Meta e não cria admissão científica. O status de checkpoint é o do relatório histórico, não inspeção do cursor atual; as exclusões são contadores do relatório local, não reconsulta independente ao provedor. Para run sem observações, valida o ledger, mas não pode corroborar viewer por evidência de post. Não é prova criptográfica de integridade dos relatórios nem substitui auditoria científica ou recuperação.

Validação: 10 PASS em 1,55 s, SQLite temporário, usando observações reais persistidas por transporte simulado no fixture A3 da cópia reconstruída anterior; relatórios históricos sintéticos. Testes de contagem, run repetido, escopo e exclusões, inclusive zero observações. Dois blobs publicados conferidos por hash. Suíte completa atualizada e execução Windows sobre relatórios operacionais ainda pendentes.

```powershell
git pull --ff-only
python -m pytest -q tests/test_a6_audit_history_reports.py
python scripts/a6_audit_history_reports.py --report artifacts/private/a6-history-pilot-20261112-230343.json --report artifacts/private/a6-history-pilot-20261112-231010.json --report artifacts/private/a6-history-expansion-20261112-231225.json --report artifacts/private/a6-history-expansion-20261112-231332.json
```

Esperado: HISTORY_REPORTS_REAUDITED, reports=4, runs=17, returned=500, accepted=408, observations=408, new_records=408, pages_examined=50, too_recent=86, missing_metrics=6, demais exclusões zero, sem rede ou escrita DB. Manter relatórios privados. Operar serialmente; backup pós-605 e inspeção de recuperação pendentes. DEC-018 vigente.


## Aceite operacional A6.7 e nova expansão documental — 13/11 UTC

Operador reportou HISTORY_REPORTS_REAUDITED, 4 relatórios, 17 runs, 500 retornadas, 408 elegíveis/observações/novos registros, 86 recentes, 6 métricas ausentes, zero formatos/metadados inválidos, duplicatas, refresh, admissões ou escrita DB; 50 páginas. Todos os 17 runs audit_valid=true e checkpoint_at_run=continuation_available, inclusive os três da última expansão. Estados dos checkpoints são os registrados no relatório histórico, não uma nova inspeção dos cursores. RECOVERY_INSPECTION: lease=null, latest_a5_blocked_runs=[], reserved_runs=0; não foi executada recuperação destrutiva. Acervo 605/10, 12 habilitadas. Regressão integral após os dez testes A6.7 ainda não reportada; última suíte 419 PASS. Backup pós-605 ainda não confirmado.

### A6.1 — segunda onda documental

Pesquisa em fontes públicas institucionais em 12/11/2026 (Brasília). Arquivo `evidence/acquisition/bd_a6_candidate_expansion_wave2_20261113.json` contém 9 novos candidatos, sem IDs Meta ou grants. Referências de handle e finalidade no próprio JSON; seleção dirigida, não amostra representativa. Foram descartadas entradas sem vínculo suficientemente claro entre handle e organização. Para quatro perfis, o URL de destino do link institucional foi identificado, mas a página Instagram não pôde ser recuperada (ricardodeoliveirapet, aanadesales, wabizapp, melhorenvio); o mesmo ocorreu para amarefashiongo. Não confundir vínculo documental com identidade oficial atual. Nenhuma mídia, métrica ou perfil foi coletado via API Meta; a pesquisa documental usou páginas públicas externas.

| Handle | Estrato | Intenção preliminar | Limitação |
|---|---|---|---|
| ifoodparaparceiros | Capacitação foodservice | mpe_targeted | Página oficial do iFood declara canal para estabelecimentos; público inclui negócios de vários portes |
| agisaalimentos | Segurança alimentar | uncertain | Diretório Abrasel identifica handle e atuação B2B; audiência MPE não comprovada |
| anatex | Educação marketing digital | mpe_targeted | Página própria nomeia handle e Sebrae descreve contribuição à Semana do MEI; classificação preliminar, não de todos os posts |
| ricardodeoliveirapet | Educação para varejo pet | mpe_targeted | Link no site Fórmula Pet Shop, orientação para pequenos estabelecimentos |
| aanadesales | Arquitetura foodservice | uncertain | Link no diretório Abrasel; consultoria setorial, audiência MPE não comprovada |
| wabizapp | Tecnologia delivery | uncertain | Link no diretório Abrasel; produto B2B, público específico incerto |
| melhorenvio | Logística e-commerce | mpe_targeted | Link no blog próprio, documentação de soluções para lojistas pequenos e digitais; audiência mista possível |
| empreendedorasdabelezagb | Empreendedorismo beleza | mpe_targeted | FAQ oficial do Grupo Boticário nomeia Instagram e programa para profissionalização/negócio próprio |
| amarefashiongo | Moda e economia criativa | uncertain | Link no portal Sebrae Goiás, iniciativa de moda com múltiplos públicos |

Nove registros novos, 33→42 fontes documentadas previstas (12 habilitadas, 30 não habilitadas). Meta de 50 fontes totais ainda exige 8; se critério for 50 candidatos não habilitados, faltam 20 após intake. Evitar sobre-representação: iFood/Wabiz/Agisa/A Sales têm afinidade foodservice; não selecionar todos juntos apenas por volume. Amarê vinculado ao ecossistema Sebrae; Melhor Envio e Bling a LWSA; registrar dependências de grupos quando verificadas, não inferir independência. Pré-classificação mpe_targeted é intenção documental, não prova de audiência, direito de uso ou elegibilidade científica. Campos JSON verificados para comprimento/padrão/unicidade; sem execução do Pydantic ou teste integral novo no ambiente do operador. A expansão só passa a existir no manifesto privado após intake.

```powershell
git pull --ff-only
python scripts/a5_expand_source_frame.py --base artifacts/private/bd_manifest_a6_v6.json --candidates evidence/acquisition/bd_a6_candidate_expansion_wave2_20261113.json --output artifacts/private/bd_manifest_a6_v7.json
```

Esperado 33→42, approved=12, grants_created=0, external_data_accessed=false para o intake offline. Quota diária de identidade continua 10/10, orçamento compartilhado esperado 78/80; não executar identificação ou ingestão até nova janela UTC. Priorizar no próximo dia histórico de Conta Azul/Mente Empreendedora e novas identidades de segmentos menos cobertos, com prévia e quotas. Manter backup pós-605, executar regressão completa sem flags externas; PRs #43/#44 permanecem draft. Recuperação robusta, agendamento, renovação de grants e admissão científica pendentes. DEC-018 vigente, sem nova aprovação institucional.


## Intake v7 confirmado e terceira onda documental — 13/11 UTC

Operador reportou CANDIDATE_FRAME_EXPANDED, 33→42 fontes, 12 aprovadas tecnicamente, zero grants criados, external_data_accessed=false. Hash v7 `1f8586aed636b2977a3d45924125b993934156f85aa9c3b4cdad507ed56eff2d`. Acervo anterior 605/10 preservado; nenhuma mutação do DB nesta operação.

Terceira onda: `evidence/acquisition/bd_a6_candidate_expansion_wave3_20261113.json`. Oito novos candidatos, referências públicas consultadas em 12/11/2026 (Brasília), sem IDs ou grants; verificação estrutural de campos e ausência de colisão com as listas públicas anteriores.

| Handle | Estrato | Intenção | Evidência/limitação |
|---|---|---|---|
| aliancaempreendedora | Microempreendedorismo inclusivo | mpe_targeted | Site próprio nomeia perfil e detalha programas para microempreendedores; não assumir independência de programas parceiros |
| varejointeligentecdlbh | Capacitação digital do varejo | mpe_targeted | FAQ da CDL/BH identifica o canal oficial do projeto; ação CDL/Sebrae para pequenos negócios; perfil pode ter atividade intermitente e vínculo Sebrae |
| abfoficial | Franchising | uncertain | Site ABF nomeia handle; possui ações para microfranquias, mas público inclui grandes redes |
| abavnacional | Gestão de agências de viagens | uncertain | Página institucional nomeia canal; programa 2026 de qualificação das agências; tamanho dos negócios não verificado |
| instituto_cea | Inclusão produtiva na moda | mpe_targeted | Artigo do Instituto C&A identifica canal e programas para micro/pequenos negócios; também empregabilidade |
| institutolojasrenner | Moda circular e inclusão | uncertain | Edital oficial indica Instagram, criação de negócios e empregabilidade; audiência pode incluir OSCs e beneficiárias |
| prodarteoficial | Acesso a mercado para artesãos | mpe_targeted | Prefeitura Recife indica perfil oficial para participação em feiras e formalização; público artesanal, não comprova porte individual |
| casa.artemisia.escola | Cosméticos naturais/capacitação | uncertain | Reportagem local de 03/11/2026 identifica canal de cursos para geração de renda; iniciativa recém-inaugurada, atividade, identidade profissional e maturidade não verificadas |

A seleção é intencional, não amostragem probabilística. Quatro classificações mpe_targeted e quatro uncertain; intenção documental não determina audiência real de posts. Foram evitados perfis cujo canal é explicitamente orientado ao consumo final. A ABF e ABAV ampliam setores, mas não são exclusivamente MPE. Instituto C&A e Instituto Lojas Renner têm afinidade temática e devem ser avaliados como grupos distintos, sem assumir independência estatística. A nova onda eleva o total previsto a 50 (12 habilitadas + 38 candidatas); a meta mais estrita de 50 candidatas não habilitadas ainda exige 12. Não alterar os grants existentes. Sem acesso à API Meta, sem alteração do código executável, sem consulta a posts e sem custos financeiros. Pesquisa documental em sites públicos externos distinta do intake offline.

```powershell
git pull --ff-only
python scripts/a5_expand_source_frame.py --base artifacts/private/bd_manifest_a6_v7.json --candidates evidence/acquisition/bd_a6_candidate_expansion_wave3_20261113.json --output artifacts/private/bd_manifest_a6_v8.json
```

Esperado 42→50, approved=12, grants_created=0, external_data_accessed=false. Intake operacional ainda pendente; não declarar meta atingida no manifesto privado antes da execução. Última regressão integral reportada 419 PASS; nova suíte após A6.7 e backup pós-605 ainda não reportados. No dia UTC 13/11 quota esperada 78/80 e identidade 10/10; não realizar novas chamadas até a renovação diária. PRs #43/#44 draft, recuperação robusta e agendamento pendentes. DEC-018 vigente.


## Intake v8 confirmado e primeiro endurecimento da recuperação — 13/11 UTC

Operador confirmou CANDIDATE_FRAME_EXPANDED, 42→50 fontes, 12 habilitadas, zero grants novos e zero leituras externas. Manifesto v8 SHA-256 `3c57b923292aa4c69fd67506c474c01f78606593a0b68af96cabb0a1cb43325c`. Meta inicial de 50 fontes totais atingida (38 candidatas não habilitadas); meta estrita de 50 candidatas ainda demanda 12. Cobertura operacional anterior preservada: 605 IDs técnicos únicos, 10 perfis observados, 408 observações A6/17 runs reauditados. Sem novas chamadas Meta ou escrita no DB pelo assistente.

### A6.6 — recuperação fail-closed (primeiro incremento)

Revisão do código confirmou que o contador de observações de recovery já utiliza o aggregate/evento correto. Lacunas efetivas: a ingestão técnica persistia motivo genérico para todas as falhas, review_failure permitia liberar falhas sem classificação, e cycle_lease podia liberar a lease mesmo com reserva pendente após exceção. Alterações publicadas:
- `discovery_recovery_policy.py`: allowlist de motivos recuperáveis sem observações persistidas (PROVIDER_RATE_LIMITED, PROVIDER_UNAVAILABLE, BD_ORPHANED_RUN_OPERATOR_RECOVERY); reinício de histórico explícito somente para BD_PAGINATION_STALLED/BD_HISTORY_CURSOR_CYCLE e zero observações. Os demais motivos (incluindo falha de auditoria, identidade, permissão, erro genérico legado ou escrita parcial) bloqueiam review. Não libera automaticamente qualquer retry.
- `discovery_technical.py`: conserva código interno do ConnectorError no ledger em vez de apagar a causa; falhas sem classificação continuam genéricas.
- `discovery_recovery.py`: inspeção valida tenant, informa reason_code e recovery_action; revisão aplica a política antes de qualquer mutação. Reset explícito permitido registra SHA-256 do checkpoint anterior e contagem/run, sem cursor bruto. Quotas e registros preservados.
- `discovery_history.py`: lease é preservada se houver reserva pendente com prefixo do ciclo, mesmo quando a exceção passa pelo finally. A recuperação de lease continua explícita e exige parada dos processos; não é nova aprovação institucional.
- Testes: 16 PASS em 0,16 s no módulo puro de classificação, blobs do módulo e testes idênticos aos publicados; dois novos testes de integração no fixture A5 (falha de auditoria com observações parciais, interrupção deixando reserva). Integração revisada contra código real do PR, mas **não executada** no checkout integral aqui. Windows/regressão e backup pós-605 ainda pendentes. Última regressão integral operacional reportada 419 PASS, antes dos 10 testes A6.7 e 18 casos novos; expectativa 447 testes se suíte não sofreu outras mudanças.

```powershell
git pull --ff-only
$env:TAPI_BD_IDENTITY_ENABLED = "0"
$env:TAPI_OFFICIAL_METADATA_READS = "0"
$env:TAPI_BD_TECHNICAL_INGEST = "0"
$env:TAPI_BD_CONTINUOUS_ENABLED = "0"
$env:TAPI_ZERO_BILLING_CONFIRMED = "0"
python -m pytest -q tests/test_discovery_recovery_policy.py tests/test_discovery_recovery_a5.py tests/test_discovery_history_a5.py tests/test_a6_audit_history_reports.py
python -m pytest -q
python scripts/verify_zero_spend.py
python scripts/a5_recover_business_discovery.py
```

Não executar comandos de recuperação que alterem estado na base saudável. Limitações: ainda não há fencing de persistência/finalização de workers antigos, coordenação abrangente com todos os entrypoints, tratamento de leases órfãs legadas sem linha de lease, classificação de autenticação global/expiração do cursor pelo diagnóstico Meta, nem revalidação de revisões antigas. A política não torna agendamento automático seguro por si só; manter ingestão supervisionada e serial, quotas existentes, PRs draft. Sem migração, sem merge, sem nova aprovação institucional. DEC-018 vigente.


## Aceite operacional da recuperação fail-closed e fencing de escrita — 13/11/2026 UTC

Operador reportou regressão integral Windows **447 passed, 1 warning in 145.98s**, verify_zero_spend PASS e RECOVERY_INSPECTION lease=null, latest_a5_blocked_runs=[], reserved_runs=0. Assim, o primeiro incremento A6.6 passou inclusive nos testes de integração publicados. Warning não detalhado, SHA local não reportado; sequência corresponde ao head anterior `80122c1`. Não houve necessidade de recuperação real. Backup pós-605 ainda não confirmado.

### A6.6 — proteção contra finalização/escrita de run encerrado

- `IngestionStore._lock_reserved_run`: bloqueia a linha do tenant, depois verifica e bloqueia por UPDATE condicional o run reservado, com escopo opcional plataforma/conta. Mesmo lock de tenant usado pela recuperação A5.
- `_finish`: aceita somente estados terminais completed/failed e transição de reserved; rejeita terminal/missing com INGESTION_RUN_NO_LONGER_RESERVED, não altera contadores ou reason_code anteriores e não executa after_finish quando bloqueado. Callback continua transacional; falha no callback desfaz transição.
- `TechnicalDiscoveryService`: verifica reserva ativa antes da escrita de technical_verified_at e antes de cada persistência de item, na mesma transação de escrita. Escopo tenant/Instagram/target/run. Uma recuperação que encerre a reserva impede novas escritas locais por este serviço atualizado, inclusive proveniência; observações já comprometidas não são apagadas.
- Cinco novos testes em `tests/test_discovery_run_fencing.py`: interrupção simulada antes da verificação técnica e antes da persistência, tentativa de finalizar novamente como completed/failed e rollback do callback. **19 PASS em 1,99 s** (5 novos + 14 A3) na cópia reconstruída anterior com os mesmos blocos alterados, SQLite temporário e transporte simulado; verify_zero_spend PASS. Blob do arquivo de teste publicado conferido. Não é regressão integral do head atual, nem teste PostgreSQL ou corrida com processos reais.
- Escopo limitado: _finish protege todas as rotas que usam esse método; a verificação por item e verificação de grant foram conectadas somente à rota Business Discovery técnica. Rotas genérica/científica ainda não receberam fencing de todas as suas escritas; não existe coordenação global de reserva/quotas entre entrypoints. A proteção não cancela requisições externas já iniciadas, não impede processo rodando código antigo, nem substitui parada explícita antes de recuperação. Não habilitar agendamento ainda. Sem migração, sem alteração do banco do operador e sem chamadas Meta. DEC-018 vigente.

```powershell
git pull --ff-only
$env:TAPI_BD_IDENTITY_ENABLED = "0"
$env:TAPI_OFFICIAL_METADATA_READS = "0"
$env:TAPI_BD_TECHNICAL_INGEST = "0"
$env:TAPI_BD_CONTINUOUS_ENABLED = "0"
$env:TAPI_ZERO_BILLING_CONFIRMED = "0"
python -m pytest -q tests/test_discovery_run_fencing.py tests/test_discovery_technical_a3.py tests/test_discovery_history_a5.py tests/test_discovery_recovery_a5.py
python -m pytest -q
python scripts/verify_zero_spend.py
python scripts/a5_recover_business_discovery.py
```

Expectativa 452 testes (447+5), sem novas falhas. Preservar backup pós-605. Próximo incremento: coordenação global de reserva/lease e quota, incluindo rotas manuais e identidade; proteção de demais escritas e teste de concorrência. PRs #43/#44 continuam draft, sem merge. 


## Aceite Windows do fencing e coordenação compartilhada — 13/11/2026 UTC

Operador reportou 36 PASS focal (20,76 s), **452 PASS, 1 warning em 145,32 s** na suíte integral, verify_zero_spend PASS, RECOVERY_INSPECTION lease=null, latest_a5_blocked_runs=[], reserved_runs=0. Warning identificado: StarletteDeprecationWarning de `fastapi.testclient` sobre `httpx` com `starlette.testclient`, sugerindo httpx2. Não trocar dependências de transporte sem teste específico; aviso não causou falha. Head de referência anterior `a9858f4` pela sequência reportada, sem SHA local independente. Backup pós-605 continua não confirmado.

### A6.6 — coordenação de reservas Instagram

- Reserva compartilhada em `IngestionStore._reserve`: lock transacional de tenant antes de verificar lease e adquirir lock do grant; preserva checagem de run duplicado e quota por fonte. Uma reserva Instagram ativa impede outra reserva Instagram no mesmo tenant, inclusive de outra fonte. Entrada manual não pode se apropriar de uma lease por coincidência de prefixo do run; contexto de ciclo é argumento interno, não parte do payload HTTP.
- A5 passa cycle_key explicitamente pela camada batch e serviço técnico. A reserva recusa contexto de ciclo expirado ou diferente. A3/A4, ingestão genérica Instagram e rota científica usam a mesma reserva e não entram durante lease A5/A6. A4 não ganha lease do lote inteiro: cada run é isolado, e pode ocorrer interleaving entre runs, sujeito à quota; não afirmar exclusão mútua de lotes manuais completos.
- Aquisição de lease A5/A6 verifica reserva Instagram ativa sob o mesmo lock. Identidade A6 confere lease antes de reservar, antes da chamada de identidade e antes de registrar resultado; ausência de lease impede novo registro. Não cancela chamada já iniciada e não garante cancelamento entre a verificação e a rede.
- Teto compartilhado de 80 unidades/dia UTC por tenant agora verificado na transação da reserva (4 por run Instagram de qualquer status +1 por evento identity_reserved). Limite por fonte de 5 e limite de identidade de 10 continuam; planner A5/A6 pode ser mais restritivo. Não é medidor de faturamento nem quota real do provedor. Probes de leitura sem ledger de ingestão e processos externos/versões antigas não são cobertos. YouTube permanece fora desse orçamento específico Instagram.
- Definição SQLAlchemy de bd_cycle_leases movida para ingestion.py, reexportada por discovery_history.py; mesma tabela, nenhuma alteração do schema/migração. Importação antecipada evita ausência da tabela em fixtures de criação isolada via metadata.create_all. DB operacional deve estar em 0012 ou posterior.
- Batch agora preserva provider_diagnostic numérico seguro quando disponível no relatório privado. O stdout compacto da CLI continua podendo omitir esse detalhe.
- Testes: **5 PASS em 1,24 s** em SQLite temporário, incluindo disputa de duas threads com um único vencedor, lease contra manual/prefixo forjado, reserva manual ativa bloqueando ciclo e outra fonte, contexto encerrado e orçamento 78/80 recusando nova reserva. Cópia reconstruída sobre zip anterior com os blocos equivalentes de reserva/lease/finalização, função real de contagem de identidade e fixture mínimo A4; não checkout integral. Blob do teste publicado 5264f0dbcabe2caa04350ef95f2cfe0a71b69537 conferido idêntico ao local. Integração A5/A6 e regressão Windows do novo head ainda não executadas aqui; não afirmar teste PostgreSQL.
- Limitações: proteção de escrita item/grant ainda não conectada integralmente às rotas genérica/científica; reserva manual abandonada sem lease pode bloquear o tenant e precisa de caminho de recuperação auditado específico (não remover linha manualmente). Não há coordenação para preflights/probes sem reserva, fencing de rede, autenticação global, renovação automática ou scheduler. Manter execução serial supervisionada e flags externos desligados durante testes. Sem chamada Meta, mutação do DB operacional, merge ou nova aprovação institucional.

```powershell
git pull --ff-only
$env:TAPI_BD_IDENTITY_ENABLED = "0"
$env:TAPI_OFFICIAL_METADATA_READS = "0"
$env:TAPI_BD_TECHNICAL_INGEST = "0"
$env:TAPI_BD_CONTINUOUS_ENABLED = "0"
$env:TAPI_ZERO_BILLING_CONFIRMED = "0"
python -m pytest -q tests/test_discovery_shared_reservations.py tests/test_discovery_history_a5.py tests/test_discovery_identity_a6.py tests/test_discovery_run_fencing.py tests/test_discovery_recovery_a5.py
python -m pytest -q
python scripts/verify_zero_spend.py
python scripts/a5_recover_business_discovery.py
python scripts/a5_business_discovery_cycle.py --manifest artifacts/private/bd_manifest_a6_v8.json --mode history --max-sources 5 --page-limit 10 --max-pages 4 --daily-request-budget 80
```

Esperado 457 testes (452+5), inspeção saudável e plano somente leitura confirmando limite compartilhado (78/80 se mesmo dia UTC sem novas operações). Não habilitar agendamento ainda. Backup pós-605 pendente. DEC-018 vigente.


## Regressão Windows da coordenação compartilhada e adequação do teste A4 — 13/11/2026 UTC

Operador reportou 35 PASS focal (14,85 s), regressão integral **456 PASS, 1 FAIL, 1 warning em 167,45 s** no incremento de coordenação (head de referência 650a572, SHA local não reportado). Falha única em test_concurrent_cross_source_collision_is_serialized: BrokenBarrierError. O teste antigo sincronizava dois serviços em _persist_item, mas a exclusão mútua adicionada na reserva impede o segundo de chegar à barreira. Zero-spend PASS e RECOVERY_INSPECTION sem lease/reservas/bloqueios. Não declarar regressão integral aprovada antes da reexecução.

Correção exclusivamente de testes em `tests/test_discovery_batch_a4.py`: manter teste original de colisão concorrente, agora diretamente na camada de armazenamento (dois itens com mesmo media ID, fontes diferentes, duas threads, barreira antes da persistência, um criado e outro BD_CROSS_SOURCE_MEDIA_ID_CONFLICT, exatamente um registro/content/snapshot). Adicionar teste de serviço com eventos determinísticos: primeiro run permanece ativo enquanto segundo tenta reservar, segundo recebe ACCOUNT_INGESTION_IN_PROGRESS antes de rede e sem ledger; após completar o primeiro, segunda fonte pode reservar mas colisão do mesmo media ID é rejeitada, com auditoria do vencedor válida e zero observações no perdedor. Não remover proteção, não afrouxar quota, não desabilitar teste. Nenhum código de produção modificado.

Validação local: 7 PASS em 1,43 s (2 cenários A4 + 5 testes de reservas compartilhadas), em cópia reconstruída anterior, SQLite temporário, blocos equivalentes de reserva/persistência/serviço e fixture HTTP simulado. Dois novos corpos de teste publicados e conferidos com a versão executada; não é checkout integral do PR. Esperado 458 testes (um substituído por dois). Regressão integral Windows pendente; warning conhecido de Starlette/httpx permanece.

```powershell
git pull --ff-only
python -m pytest -q tests/test_discovery_batch_a4.py tests/test_discovery_shared_reservations.py
python -m pytest -q
python scripts/verify_zero_spend.py
python scripts/a5_recover_business_discovery.py
```

Manter flags externos desligados. Backup pós-605 ainda não reportado. Não iniciar agendamento ou recuperação destrutiva. Nenhuma chamada Meta, migração, alteração da base operacional, merge ou nova aprovação institucional. DEC-018 vigente.
