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
