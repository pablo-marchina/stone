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


## Aceite Windows da coordenação e recuperação de reservas sem lease — 13/11/2026 UTC

Operador reportou **19 PASS focal em 4,30 s; 458 PASS, 1 warning em 143,42 s** na regressão integral, verify_zero_spend PASS, RECOVERY_INSPECTION sem lease/reservas/bloqueios. Corrigida a regressão do teste de barreira A4, sem relaxar os invariantes. Warning conhecido Starlette/TestClient/httpx. SHA local não reportado; head de referência anterior f7c6dc7. Backup pós-605 ainda não confirmado.

### A6.6 — recuperação de reserva Instagram órfã sem lease e fencing das demais rotas

- Novo `discovery_orphan_run.py`: fechamento auditado de exatamente uma reserva Instagram abandonada sem lease. Exige administrador autenticado, todos os processos de ingestão efetivamente parados (controle técnico, não nova aprovação institucional), identificador exato, idade mínima de 30 minutos, ausência de lease e de qualquer outra reserva no tenant. Não é recuperação automática por timeout. Aplicável também a reservas A5 legadas sem lease.
- Transação sob lock do tenant: preserva linha original, data de reserva, contadores e quaisquer registros/checkpoints previamente comprometidos; transição reserved→failed com reason_code BD_ORPHANED_MANUAL_RUN_QUARANTINED; evento business_discovery.orphan_run_recovered e outbox atômicos. Não reembolsa quota e não assume ausência de escritas parciais (rotas antigas não permitem correlacioná-las integralmente com run).
- Quarentena fail-closed da fonte afetada em _reserve e plan_cycle, inclusive se houver um run mais recente. Não há liberação automática nem procedimento implementado para remover a quarentena; requer futura reconciliação técnica explícita. As outras fontes podem operar respeitando quotas. Nenhuma linha é apagada; não editar ledger para contornar a quarentena.
- Inspeção somente leitura passa a apresentar orphan_runs_without_lease e quarantined_sources. CLI adiciona --recover-orphan-run RUN_KEY ao grupo mutuamente exclusivo de recuperação; usa autenticação administrativa e controle de processos já existentes. Não executar mutação na base saudável.
- Rota genérica: fencing antes de atualização do grant e em cada persistência de item (também YouTube quanto à escrita); checkpoint Instagram de primeira parte é persistido no callback da mesma transação da finalização. A rota científica recebe fencing em cada item/proveniência e antes da marcação de verificação técnica do grant. Não altera critérios científicos ou direitos. Não protege processos que executam código antigo, requisições externas em voo ou probes sem ledger. A retomada genérica ainda lê cursor antes da reserva (possível stale read se operação anterior concluir entre leitura e reserva); tratar separadamente.
- Validação local: **35 PASS em 9,40 s**, 5 novos testes em test_discovery_orphan_run.py e 30 anteriores (test_ingestion_cursor.py, test_discovery_corpus_ingestion.py, test_official_ingestion.py), em cópia reconstruída anterior, SQLite temporário, mock HTTP; módulo novo e testes conferidos pelos hashes Git 307249179eee4b3ec11f926c3ac6dabdef346b08 e 8ddd6b1efa9998c68952acf1576ebe2e8d19cb98. Blocos de produção equivalentes testados; integração com CLI/planner/inspeção não executada localmente. Não é regressão integral do head, nem prova de concorrência PostgreSQL. 463 testes esperados após atualização. Sem chamada Meta, migração ou mutação do DB do operador.

```powershell
git pull --ff-only
python -m pytest -q tests/test_discovery_orphan_run.py tests/test_ingestion_cursor.py tests/test_discovery_corpus_ingestion.py tests/test_official_ingestion.py tests/test_discovery_recovery_a5.py tests/test_discovery_history_a5.py
python -m pytest -q
python scripts/verify_zero_spend.py
python scripts/a5_recover_business_discovery.py
```

Manter flags externos desabilitados. Esperado lease=null, latest_a5_blocked_runs=[], orphan_runs_without_lease=[], quarantined_sources=[], reserved_runs=0. Não executar --recover-orphan-run na base saudável. Backup pós-605 ainda pendente; coordenação de probes, revalidação do cursor de primeira parte, reconciliação de fontes em quarentena, credenciais, renovação de grants e scheduler pendentes. PRs #43/#44 draft, DEC-018 vigente.


## Aceite Windows da recuperação de órfãos e proteção global de autenticação — 13/11/2026 UTC

Operador reportou 52 PASS focal em 26,70 s, **463 PASS, 1 warning em 217,00 s** integral, verify_zero_spend PASS e RECOVERY_INSPECTION sem lease, blocked runs, reservas, orphan_runs_without_lease ou quarantined_sources. Primeiro incremento de recuperação sem lease e fencing das demais rotas validado na regressão integral. Warning conhecido de Starlette/TestClient/httpx. SHA local não apresentado; head de referência anterior 1e625fc. Acervo anterior 605 posts/10 fontes observadas, 12 grants, 50 fontes documentadas; não houve nova aquisição neste turno. Backup pós-605 ainda não reportado.

### A6.6 — circuit breaker persistente para credenciais Meta

Motivação observada: falha anterior Meta 190/463 em identificação real, após expiração de credencial, renovada pelo operador naquele momento. O novo mecanismo reage a falhas futuras; não reinterpreta retrospectivamente eventos legados, nem afirma que a credencial atual está válida.

- Novo `discovery_auth_guard.py`: identifica somente diagnóstico numérico Meta code=190 em HTTP 400/401/403 como falha global de autenticação. HTTP 403 genérico, rate limit, erros de identidade e outras falhas não são automaticamente tratados como expiração. Sem novas consultas ou armazenamento de token/hash, mensagem bruta, resposta do provedor ou fbtrace_id.
- O bloqueio persistente é por tenant, no agregado bd_meta_auth com eventos business_discovery.meta_auth_blocked / meta_auth_reset e outbox atômico. A decisão conservadora de bloquear todo o tenant assume o uso de credencial Meta compartilhada; não distingue credenciais diferentes do mesmo tenant. Não é bloqueio global entre tenants.
- Nas três rotas de ingestão Instagram, a falha de credencial gera bloqueio na mesma transação que finaliza a reserva; sem observações contabilizadas, reason_code=BD_META_AUTH_INVALID. Nas reservas subsequentes, _reserve exige auth disponível sob lock do tenant antes de criar novo run. Identidade A6 verifica no planejamento, reserva e antes da leitura, e registra bloqueio no mesmo commit do resultado. Não devolve reservas antigas.
- A5 expõe meta_auth no plano e não seleciona fontes quando bloqueado. Após reset, runs com AUTH_INVALID e contadores zerados voltam à seleção normal respeitando os demais gates e quotas; outros motivos de falha e quarentenas continuam bloqueados. Tentativas de identidade já reservadas permanecem bloqueadas no mesmo dia UTC. Não retroativamente liberar falha genérica de permissão.
- Inspeção read-only inclui meta_auth. NOT_CHECKED significa ausência de evento de bloqueio, não validação da credencial. RESET_UNVERIFIED significa reset técnico registrado, não verificação OAuth. O estado persiste sem provar validade atual do token. A primeira falha 190 após reset bloqueia novamente. Não há reset automático por tempo.
- CLI existente recebe `--reset-meta-auth-after-rotation`, mutuamente exclusivo com outras recuperações; somente após substituição real da credencial, com token presente no ambiente, administrador autenticado, processos parados e sem reservas/leases ativas. Nenhuma nova aprovação institucional; reset técnico não verifica a credencial nem consome rede. Nunca executar na base saudável apenas para teste. Não expor tokens no terminal/chat.
- Testes: **46 PASS em 11,81 s** no checkout reconstruído anterior (6 novos + 40 casos existentes: órfãos, cursor, corpus, ingestão oficial e reserva compartilhada). SQLite temporário e mock HTTP; módulo novo e teste novo idênticos aos publicados (blobs c6b86144c2c3d57146a758055767594e7aa82f1f e 70d2566f78fed58added1c2f80aa49b2169825db). Blocos de integração genérica/técnica/científica reconstruídos; não é teste integral do novo head. Dois casos A5/A6 adicionais publicados em test_discovery_identity_a6.py (identidade→bloqueio A5 e A5→bloqueio identidade, reset e quotas), ainda não executados localmente por ausência do checkout integral. Esperado **471 testes** na regressão (463+8).
- Limitações: não prediz expiração nem renova tokens; não autentica substituição local, não impede rede já em voo, processos antigos ou probes sem ledger; não substitui controles de escopo, grants ou auditoria; sem PostgreSQL. Auth reset requer administração técnica, não aprovação institucional. Sem migração, chamada Meta, escrita no DB operacional ou merge. Próximas frentes: acompanhamento de expiração sem novas chamadas indevidas, renovação dos grants A6 e prioridade por diversidade; scheduler somente após controles e testes.

```powershell
git pull --ff-only
$env:TAPI_BD_IDENTITY_ENABLED = "0"
$env:TAPI_OFFICIAL_METADATA_READS = "0"
$env:TAPI_BD_TECHNICAL_INGEST = "0"
$env:TAPI_BD_CONTINUOUS_ENABLED = "0"
$env:TAPI_ZERO_BILLING_CONFIRMED = "0"
python -m pytest -q tests/test_discovery_auth_guard.py tests/test_discovery_identity_a6.py tests/test_discovery_history_a5.py tests/test_discovery_orphan_run.py tests/test_discovery_recovery_a5.py
python -m pytest -q
python scripts/verify_zero_spend.py
python scripts/a5_recover_business_discovery.py
```

Esperado 471 PASS, recuperação saudável, meta_auth NOT_CHECKED/blocked=false se não houve nova falha após instalação. Backup pós-605 pendente. PRs #43/#44 draft. DEC-018 vigente.


## Aceite reportado do circuit breaker e renovação técnica A6 — 13/11/2026

Operador informou "Todos foram aprovados" após instruções de regressão e inspeção do incremento de autenticação. Aceite reportado; total esperado 471 PASS, sem log bruto, SHA local, duração, contagem de warnings ou saída específica da inspeção neste turno. Não atribuir medições exatas não apresentadas. Última regressão integral com log explícito: 463 PASS, 1 warning; backup pós-605 permanece não confirmado. Acervo conhecido 605 IDs técnicos, 10 fontes observadas, 12 habilitadas, manifesto v8 50 fontes; nenhuma nova aquisição reportada.

### A6.6 — renovação do ciclo de vida dos grants técnicos A6

- Novo `src/tapi_gate0/discovery_grant_renewal.py`: modo read-only por padrão, seleção de todos os grants aprovados com prefixo A6 DEC-018, viewer/target exatamente correspondentes, identidade auditada (reserva/resultado/outbox e ausência de conflitos de handle/ID), linha existente e escopo somente business_discovery_metadata_read. Grant revogado/desabilitado ou fonte em quarentena não é reativado. Grants anteriores não A6 não são gerenciados por este mecanismo.
- Janela local de manutenção de sete dias: grant habilitado que vencer em até sete dias ou já tiver vencido pode receber mais 30 dias a partir da renovação. São parâmetros de manutenção técnica, não prazo de autorização institucional. Sem reaprovação institucional e sem ampliação de escopo. A permissão real da Meta continua sendo exigida em cada leitura. Não equivale à renovação do token OAuth.
- Mutação somente com principal admin do mesmo tenant, lock de tenant, sem lease/reserva ativa. Atualiza exclusivamente expires_at; conserva referência, criação, identidade, verificação técnica histórica, quotas e checkpoints. Evento business_discovery.technical_grant_renewed em agregado próprio (não interfere na sequência original criação/revogação) e outbox atômicos, incluindo seq da evidência de identidade, fingerprints antes/depois, expiry anterior e novo, ator e operação.
- Se DB já tiver sido atualizado mas a saída privada não for gravada, o mesmo manifesto de entrada pode ser reconciliado com a última renovação exata auditada, enquanto o novo prazo ainda for válido; não prolonga o prazo novamente. Divergência não explicada falha fechada. Usar nome de saída novo, não sobrescrever o manifesto de entrada. Não é transação distribuída DB/arquivo; o CLI ainda pode deixar arquivo vazio se interrompido. Repetição com outros manifestos ou cadeia de várias renovações não é reconciliação automática garantida.
- CLI `scripts/a6_provision_grants.py` aceita `--renew-due` mutuamente exclusivo com `--source`. Prévia não requer token; execução usa o mesmo login administrativo e arquivo privado exclusivo já existentes, sem solicitar nova aprovação institucional. Provisionamento A6 também passa a recusar lease ativa, além de reservas.
- Validação local efetivamente realizada: 6 PASS em 1,21 s em SQLite temporário com ledger e eventos de identidade semeados, testes independentes de smoke (não os sete testes publicados); módulo novo idêntico ao blob Git c9b9c69d78a6bd929ca5d96b071dd9e9208feaa9. Dependências reconstruídas (modelo BatchManifest, _trace e constantes da política); não checkout integral. Sete casos publicados em test_discovery_grant_renewal.py (incluindo CLI, prévia sem token e fixture de provisionamento real) aguardam execução. Expectativa de 478 testes na suíte se a anterior realmente teve 471. Não há teste PostgreSQL, validação operacional de renovação real, monitoramento de validade OAuth ou agendamento automático.
- Nenhuma chamada Meta, migração, escrita no DB do operador, custo ou merge neste turno. PRs #43/#44 draft. DEC-018 vigente.

```powershell
git pull --ff-only
python -m pytest -q tests/test_discovery_grant_renewal.py tests/test_discovery_grants_a6.py tests/test_discovery_reconcile_a6.py
python -m pytest -q
python scripts/verify_zero_spend.py
python scripts/a6_provision_grants.py --manifest artifacts/private/bd_manifest_a6_v8.json --renew-due
```

Manter flags externos desabilitados. A prévia deverá classificar os nove grants A6 (os três iniciais legados não são modificados); se os grants ainda tiverem mais de sete dias, grants_to_renew=0. Sem pressupor o resultado do DB privado. Não executar renovação se não houver itens a renovar ou reconciliar. Quando devida, usar `--execute --output artifacts/private/<novo-manifesto>.json` com arquivo inexistente, após backup; adotar novo manifesto somente após sucesso e conferir hash. Próximas frentes: monitoramento local de expiração OAuth, priorização por diversidade e operação contínua; backup pós-605 ainda pendente.


## Aceite da renovação e monitoramento local de expiração OAuth — 13/11/2026 UTC

Operador confirmou "Todos foram aprovados" para a regressão da renovação (478 era a expectativa, contagem/duração/SHA local não reapresentados). Prévia operacional real reportou TECHNICAL_GRANT_RENEWAL_PLANNED, manifesto v8 SHA-256 3c57b923292aa4c69fd67506c474c01f78606593a0b68af96cabb0a1cb43325c, grants_to_renew=0, grants_renewed=0, changes=[], grants_created=0, external_data_accessed=false e scientific_admissions=0. Nove grants A6 NOT_DUE: saladoempreendedor.saoluis, redemulherempreendedora, lojaintegrada, contabilizei vencem em 13/12/2026 01:56:07 UTC; contaazul, abraselnorn, abihpecoficial, menteempreendedora, feirapretaoficial em 13/12/2026 02:10:02 UTC. Janela técnica de renovação começa sete dias antes (06/12 UTC, 05/12 à noite em Brasília). Não confundir com expiração OAuth. Nenhuma renovação executada, manter v8; os três grants anteriores não são cobertos. Último log integral explícito 463 PASS, os incrementos subsequentes foram aceitos pelo operador sem log bruto. Acervo anterior 605 posts/10 fontes observadas/12 habilitadas/50 documentadas; backup pós-605 não confirmado.

### A6.6 — acompanhamento offline da expiração declarada da credencial

- Novo `discovery_credential_expiry.py`: lê somente os metadados de tempo opcionais de ambiente TAPI_META_TOKEN_EXPIRES_AT e TAPI_META_DATA_ACCESS_EXPIRES_AT, ISO 8601 com fuso explícito. Não lê o segredo, não solicita introspecção, não calcula hash do token e não registra valores inválidos brutos. Normaliza UTC e utiliza o menor prazo conhecido. Nenhuma inferência a partir do prazo do grant local.
- Estados UNKNOWN (nenhuma data, compatível com operação supervisionada existente), WITHIN_DECLARED_WINDOW, EXPIRING_SOON (até sete dias), EXPIRED (bloqueia), INVALID_CONFIGURATION (bloqueia) e EXPIRY_REQUIRED (bloqueia se TAPI_META_REQUIRE_TOKEN_EXPIRY=1 e prazo do token ausente). O modo obrigatório é opcional, padrão 0; ausência do prazo de acesso a dados não é presumida como ausência de expiração. provider_verified=false sempre. Aviso de sete dias é escolha técnica, não regra de OAuth.
- Integração com require_auth_available: mantém precedência do circuit breaker persistente, e verifica expiração antes de reserva Instagram em todas as rotas com ledger e na identidade A6. A5 apresenta meta_credential_expiry e defere fontes antes da aquisição se bloqueada. A6 inclui o diagnóstico em plano bem-sucedido. Inspeção de recuperação inclui meta_credential_expiry sem mutação ou rede; meta_auth continua independente.
- A configuração é por processo/ambiente, não metadado persistente ligado a um token específico. Atualizar datas reais junto com cada rotação, propagar a todos os processos e não usar datas inventadas. Não há prova de que a data informada corresponde ao token atual, não prevê revogação antecipada, não cancela rede em voo, não cobre probes fora do ledger e não renova OAuth. Sem datas, UNKNOWN não significa credencial válida. O scheduler ainda não existe; quando implementado, considerar exigir prazo conhecido antes da operação desassistida.
- Validação efetiva: 14 PASS em 1,19 s (oito casos novos em test_discovery_credential_expiry.py e seis anteriores do circuit breaker) em cópia reconstruída, SQLite temporário e transporte simulado. Módulo novo a5744ad050af00a2138adfef730075b8f32b30b8, testes 88cb46291252b5ce9bec395f6cddce0cdbe95ecc e auth guard 85de0372a0da0e9e4cf6edfc85abcad3b6eca501 conferem com os blobs testados. Um caso adicional de integração A5/A6/inspeção publicado em test_discovery_identity_a6.py com transporte mock, ainda não executado localmente. Expectativa 487 PASS (478+9) se contagens anteriores correspondem ao esperado; regressão integral Windows pendente, sem teste PostgreSQL. Nenhuma alteração operacional ou consulta Meta.

```powershell
git pull --ff-only
python -m pytest -q tests/test_discovery_credential_expiry.py tests/test_discovery_auth_guard.py tests/test_discovery_identity_a6.py tests/test_discovery_history_a5.py
python -m pytest -q
python scripts/verify_zero_spend.py
python scripts/a5_recover_business_discovery.py
```

Manter flags externos desabilitados e as variáveis de expiração não configuradas durante a regressão (os testes focalizados usam datas simuladas isoladas). Inspeção sem configuração esperada: meta_credential_expiry.status=UNKNOWN, blocked=false, provider_verified=false; nenhuma consulta. Para configurar, copiar apenas datas reais verificadas na ferramenta oficial do provedor para o ambiente privado, em ISO 8601 com fuso; não colar o token no chat, logs ou Git. Não é necessário configurar ou resetar a credencial para validar esta atualização. Próximo incremento: priorização de fontes por cobertura e diversidade, seguido de scheduler supervisionado/validação operacional. Backup pós-605 pendente. PRs #43/#44 draft, sem merge, migração, escrita no DB operacional, despesa ou nova aprovação institucional. DEC-018 vigente.


## A6 — política experimental de prioridade por cobertura (13/11/2026)

**Vínculo obrigatório ao Plano Único v5.2:** CAP-001, IMP-048 (amostragem), IMP-052 (lotes e cobertura), IMP-053 (data card), IMP-167 (diversidade de fontes) e IMP-170 (evidência de cobertura); preparação de comparação de políticas para CAP-021, sem declarar IMP-124/125 completos. DEC-016 e DEC-018 preservadas; sem novos IDs, backlog paralelo ou liberação de gate.

- O planejamento histórico aceita `--priority-policy coverage` como opt-in; padrão `recency` permanece idêntico na seleção e refresh não aceita a política de cobertura. Nenhuma mudança nos filtros prévios (grant, expiração, autenticação, quotas, falhas e checkpoint), capacidade, orçamento ou caminho de execução. O executor reutiliza exatamente a política no replanejamento sob lease.
- Um slot preserva a seleção por checkpoint mais antigo (ou ainda não iniciado); slots seguintes minimizam repetição de estrato no ciclo e priorizam fontes sem registros, menor número de fontes observadas no estrato, menor inventário técnico do estrato, menor inventário da fonte, recência e username. Com capacidade de um, a política é igual ao baseline por desenho. Não estima relevância científica nem yield. Estratos são os rótulos documentais atuais; não são evidência de representatividade.
- Contagens de media IDs distintos por fonte aprovada do manifesto (inclusive deferidas) no tenant e somente metadata_only Instagram. Somatórios entre fontes são inventário técnico, não unicidade global nem admissões; não contam snapshots repetidos. A política não admite candidatos nem cria grants.
- A prévia privada registra inputs, contagens por estrato, versão `bd-history-coverage.v1`, ordem/razões de seleção, baseline e política com mesmos candidatos/capacidade; métricas planejadas: diversidade de estratos, fontes sem observações e inventário prévio. Não publica cursores, tokens ou referências brutas.
- Validação efetiva: 12 testes unitários puros PASS em 0,07 s, incluindo fixture pareada (1→3 estratos no mesmo orçamento de três fontes), determinismo e limites. Não prova melhoria em coleta real. Três testes adicionais de integração planner/execução/CLI publicados mas ainda não executados; regressão integral do HEAD, backup pós-605 e revisão A5/A6 pendentes. Sem chamada Meta, escrita operacional, migração, merge, scheduler ou nova aprovação institucional.
- Próximo aceite: comparar as prévias privadas no manifesto v8, com quota disponível, verificar a regressão Windows e os contadores; manter recency como fallback, sem ativar agendamento antes do aceite operacional. Não extrapolar ganhos para CAP-021 ou corpus científico.

```powershell
git pull --ff-only
python -m pytest -q tests/test_discovery_priority.py tests/test_discovery_history_a5.py
python -m pytest -q
python scripts/verify_zero_spend.py
python scripts/a5_recover_business_discovery.py
python scripts/a5_business_discovery_cycle.py --manifest artifacts/private/bd_manifest_a6_v8.json --mode history --max-sources 3 --priority-policy coverage
```

A última linha é prévia offline; não usar --execute nesta verificação. Se a quota estiver esgotada, capacidade zero é resultado válido, não reiniciar o ledger ou forçar chamadas. Backup pós-605 e teste de restauração continuam pendentes. PRs #43/#44 permanecem draft.


## Aceite da priorização e backup/restore isolado — 13/11/2026

- Operador: 26 PASS focal (6,82 s), **502 PASS integral** (249,02 s, 1 warning Starlette conhecido), zero-spend PASS. Inspeção sem lease, reservas, órfãos, quarentena ou bloqueio de autenticação; validade OAuth UNKNOWN (não verificada).
- Prévia v8 confirma 50 fontes, 12 aprovadas, 10 observadas, 605 media IDs únicos, zero duplicidades e admissões. Capacidade 0 (78/80 reservas conservadoras, cada run exige quatro unidades); 12 elegíveis deferidas por orçamento, 38 não aprovadas. Nenhuma leitura externa. Inventário dos três maiores perfis soma 311/605; duas fontes aprovadas sem observações (Conta Azul e Mente Empreendedora). Ambas as políticas retornam seleção vazia: não há comparação operacional de diversidade com capacidade positiva. Não alterar quota.
- Novo incremento **IMP-091/144 (CAP-022/G5-OPS), suporte IMP-040/052/170 (CAP-001)**: backup SQLite de todos os tenants pelo operador de filesystem, somente com parada explícita de todos os escritores (API, workers, ingestão, scheduler). Sem lease ou run reservado em qualquer tenant. Origem aberta read-only, snapshot SQLite backup API (inclui WAL comprometido), head 0012 obrigatório; validação integrity_check/foreign_key_check, fingerprint de schema, contagem de todas as tabelas e cobertura técnica do tenant. Cópia em arquivo novo, exclusivo, sob artifacts/private; restauração de teste em diretório descartável privado, revalidada, nunca sobre a origem. SHA-256, bytes e tempos observados no relatório. Não é lock distribuído, backup criptografado, teste de recuperação de aplicação ou RPO/RTO de produção.
- Proteja artifacts/private por ACL do sistema (modo POSIX 0600 não configura ACL Windows) e não sincronize/enviar o banco: contém todos os tenants e dados sensíveis. A confirmação de parada é operacional, não uma nova aprovação institucional. Não executar com processos escritores ativos; o ledger não detecta todos os escritores.
- Testes efetivamente executados: 12 PASS em 0,43 s, SQLite temporário com schema reduzido e dependência local reconstruída, incluindo WAL, bloqueio de lease/reserva de outros tenants, integridade referencial, destino exclusivo, falha de cópia, CLI. Blobs módulo/CLI/teste conferidos. Sem checkout completo nem execução Windows real. Esperado 514 se a regressão anterior de 502 for preservada. Backup pós-605 e restore operacional ainda pendentes; nenhum merge, migração, scheduler, escrita no DB operacional, chamada Meta, despesa ou nova aprovação institucional.

```powershell
git pull --ff-only
python -m pytest -q tests/test_discovery_backup.py
python -m pytest -q
python scripts/verify_zero_spend.py
python scripts/a5_recover_business_discovery.py
```

Após parar efetivamente API, workers e todos os escritores do banco, manter o ambiente local e as flags externas desligadas. Usar nome exclusivo (não sobrescrever backup anterior):

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_backup_restore_drill.py --output-name "tapi-a6-post605-$stamp.sqlite3" --confirm-all-writers-stopped
```

Esperar BACKUP_RESTORE_VERIFIED, integrity_check=ok, foreign_key_check=ok, inventory_matches=true, cobertura 605/10 se não houve nova ingestão, live_restore_performed=false. Guardar backup e relatório JSON localmente; compartilhar somente relatório sanitizado, nunca o arquivo SQLite. Se BLOCKED, não forçar nem apagar dados. Próximo incremento: agendador supervisionado com tick limitado e prévia, condicionado a backup/restore e testes; PRs #43/#44 draft. Não liberar G5 nem afirmar homologação de produção.


## Aceite operacional do backup e agendador supervisionado — 13/11/2026

### Evidência operacional anterior

- Operador reportou 12 PASS focal (1,92 s), 514 PASS integral (204,32 s, um warning Starlette conhecido), verify_zero_spend PASS e RECOVERY_INSPECTION saudável. Sem lease, reservas, órfãos, quarentena ou bloqueio de autenticação; expiração OAuth permanece UNKNOWN.
- BACKUP_RESTORE_VERIFIED em 2026-11-13T14:39:05.770805+00:00, arquivo privado `tapi-a6-post605-20261113-113905.sqlite3`, SHA-256 `6b6948294934e9abbfe8edfb6de51c4a53b37fc75cc5bfca247f21b48ef93b9f`, 5.840.896 bytes, 450 ms backup e 71 ms restore descartável. integrity_check/foreign_key_check ok, inventário igual, origem não substituída, parada de escritores atestada. Head 0012, 605 IDs únicos, 10 perfis, 695 snapshots, 12 checkpoints, 33 runs, 1.429 eventos/outbox, zero admissões científicas. Evidência reportada pelo operador, não inspeção independente do DB/arquivo. Não comprova backup pré-migração, restauração da aplicação, recuperação de filas ou RPO/RTO de produção.

### Tick supervisionado (CAP-001, IMP-040/052/165/168/170, suporte CAP-022/IMP-091/144)

- `discovery_scheduler.py` e `scripts/a6_supervised_scheduler.py`: prévia read-only, escolhe entre histórico (coverage) e refresh (recency) usando os planejadores A5; preferências três horas UTC de histórico e quarta de refresh, fallback quando preferida sem elegíveis. Cadência e 3:1 são escolha inicial de engenharia, não ótimo empiricamente demonstrado, nem garantia de distribuição de requisições: quota pode se esgotar antes do refresh. Limites padrão 3 fontes, história 4 páginas de 10 e persistência integral, refresh 2 páginas de 10 e até 12 registros; mesmos custos conservadores de 4 unidades/run. Sem novo schema, API, daemon, instalação de tarefa Windows ou operação externa por padrão.
- Execução explicitamente opt-in com `--execute`, relatório JSON privado exclusivo e flags existentes mais `TAPI_BD_SCHEDULER_ENABLED=1` e `TAPI_META_REQUIRE_TOKEN_EXPIRY=1`. Requer data real de expiração do token (não a do grant); data de acesso aos dados se disponível. Datas declaradas não validam token. Inspeção impede lease/reserva/órfão, quarentena, último A5 não revisado ou auth bloqueada. A5 replana sob lease e repete direitos/quotas/expiração antes das operações; não depende da seleção antiga da prévia. Manter modo supervisionado e backup vigente.
- Claim por tenant/slot horário UTC gravado antes de qualquer execução em domain_events/outbox, lock do tenant, transação e sequência exclusiva. Terminal registra resultado/cycle_key; sucesso não permite repetir o mesmo slot. Sem elegíveis não cria claim nem executa A5. Falha ou interrupção com claim aberta impede novos ticks mesmo em outra hora. Revisão local pelo admin, evento_seq exato da última parada (obter da nova prévia), confirmação de ingestão parada e recuperação A5 resolvida antes de `--acknowledge-stop`. Não há retry/refund nem reuso do slot. A prévia e claim são transações separadas; corrida com operador manual pode impedir A5/consumir slot, não autoriza contornar a lease. Ack exige realmente parar processos; não cancela rede em voo. O latch do scheduler não proíbe A5 manual; não operar rotas simultaneamente. Quarentena deliberadamente bloqueia o scheduler inteiro até resolução técnica. A5 manual continua sujeito aos próprios gates.
- Arquivo JSON exclusivo é criado antes da execução, flush/fsync após resultado; DB e arquivo não são uma transação distribuída. Interrupção pode deixar arquivo vazio/parcial: consultar ledger e inspeção, não repetir automaticamente. A prévia pode ter dados obsoletos em concorrência; uso supervisionado. Campo external_data_accessed=null após tentativa de execução quando não é seguro inferir se houve rede; relatório completo privado contém ciclo e evidências quando retornados. Sem divulgação de token/cursores.
- Validação local: 13 PASS em 0,47s, SQLite temporário com tabelas de eventos/outbox/lock reconstruídas, planejadores/execução/inspeção simulados; módulos e testes conferidos por blob (094b8e3, 2c08586, 811f49a). CLI compilado, dois testes adicionais reais A5 com transporte mock e CLI offline publicados, ainda não executados. Esperado 529 PASS se 514 preservados. PostgreSQL, concorrência entre processos reais, scheduler em operação, recuperação integral de filas e medição de RPO/RTO de produção não validados. Sem merge, chamada Meta, migração, gasto ou alteração do DB operacional nesta implementação; DEC-018 vigente.

```powershell
git pull --ff-only
python -m pytest -q tests/test_discovery_scheduler.py tests/test_discovery_history_a5.py
python -m pytest -q
python scripts/verify_zero_spend.py
python scripts/a5_recover_business_discovery.py
python scripts/a6_supervised_scheduler.py --manifest artifacts/private/bd_manifest_a6_v8.json
```

Manter flags externas desligadas e expirações não inventadas. A última linha é somente prévia: esperar SCHEDULER_PLAN_ONLY, external_data_accessed=false, state=NEVER_RUN se nunca executado, blocker BD_SCHEDULER_TOKEN_EXPIRY_REQUIRED se data ausente (ou BD_META_TOKEN_EXPIRY_REQUIRED se modo obrigatório já ativo); proposed_mode=null quando quota 78/80 permanece. Não executar --execute nesta validação. Não configurar tarefas recorrentes ainda. Se futuramente autorizado tecnicamente, configurar as datas reais no ambiente privado, testar com quota positiva e relatório exclusivo, e manter operador acompanhando. Não reiniciar quota. Procedimento de recuperação do scheduler: após parar todas as rotas de ingestão e resolver falhas via A5 recovery, obter state.event_seq em nova prévia e executar `python scripts/a6_supervised_scheduler.py --acknowledge-stop <EVENT_SEQ> --confirm-all-ingestion-stopped` (login admin local), nunca repetir o slot. Este comando é para parada real, não para teste sobre banco operacional saudável.

Próxima etapa: validação do tick e comparação com capacidade positiva, consolidação ordenada #43→#44 (ambos permanecem draft), expansão de identidades/fontes e admissão científica. Não declarar CAP-001, CAP-022 ou G5-OPS completos.


## Aceite do tick e triagem do corpus científico — 13/11/2026

- Operador: 29 PASS focal (11,13 s), 529 PASS integral (222,43 s, um warning Starlette conhecido), zero-spend PASS. Inspeção saudável sem lease/reservas/órfãos/quarentena, OAuth UNKNOWN. Prévia slot 14:00 UTC, NEVER_RUN, histórico preferido, proposed_mode=null, BD_SCHEDULER_TOKEN_EXPIRY_REQUIRED, quota 78/80 nas duas modalidades. 605 IDs/10 perfis, 50 fontes/12 aprovadas, zero duplicatas/admissões e rede. Aceite da implementação e prévia; não da execução real, nem capacidade positiva. Não reiniciar quota, não inventar datas OAuth.
- Para avançar offline na cadeia de valor, IMP-053/170 (CAP-001) e IMP-043 (qualidade), suporte CAP-003/IMP-064: novo `discovery_corpus_readiness.py` e CLI `scripts/a6_corpus_readiness.py`. O leitor técnico já solicita caption opcional e a persistência de novo conteúdo guarda caption se fornecida; metadata_only não significa ausência de texto. Não se conhece cobertura real das legendas antes do relatório.
- Diagnóstico de inventário metadata_only Instagram por tenant e manifesto: fonte aprovada com grant ativo, referência igual e verificação técnica anterior; formato primário, maturação >=14d, métrica válida e denominador positivo, correlação com run BD concluído e auditado, viewer e fonte esperados, depois presença de legenda não vazia. Contagens mutuamente exclusivas pelo primeiro estágio de bloqueio; CAPTION_AVAILABLE_FOR_ASSESSMENT significa disponibilidade local após filtros, não evidência suficiente nem autorização de IA. Não exporta texto, URL, ID de post, cursor ou token; não classifica audiência, não registra perfis/contextos, não escreve no banco, não coleta dados nem admite posts. Data card canônico existente apresentado separadamente; não confundir contagens de registros metadata_only com corpus científico ou IDs únicos. Registros fora do manifesto entram no total e no bloqueio, não aparecem como fonte do manifesto. O audit_run verifica correlação/contagens e presença de evidência, não revalida digest contra payload Meta ou vincula criptograficamente caption atual; auditoria tem essas limitações. Usa último snapshot válido até o corte; métricas seguem denominador de observação, não histórico de publicação.
- Relatório é diagnóstico corrente, não snapshot transacional global; executar com escritores parados para comparabilidade. Ainda não há política nova de uso de caption para inferência, avaliação automatizada DEC-018, direito multimodal ou registro científico. A próxima implementação deve separar avaliação automatizada de alegação de revisão humana, com evidência e abstenção, sem adulterar CAP-004. O data card atual exige revisão explícita e não deve ser contornado.
- Validação: 13 PASS em 0,05 s no módulo exato e testes puros (eb80ccb/b33962a), sem reconstrução de banco. Um teste de integração A5/CLI/grant revogado publicado, ainda não executado localmente. Esperado 543 PASS integral se 529 preservados. Sem rede, merge, migração, custo, scheduler ativado ou alteração do DB operacional. DEC-018 vigente.

```powershell
git pull --ff-only
python -m pytest -q tests/test_discovery_corpus_readiness.py tests/test_discovery_history_a5.py
python -m pytest -q
python scripts/verify_zero_spend.py
python scripts/a6_corpus_readiness.py --manifest artifacts/private/bd_manifest_a6_v8.json
```

Último comando apenas offline; manter flags externas desligadas, escritores parados e compartilhar saída agregada, nunca DB/legendas. Esperar CORPUS_READINESS_PLANNED, inventário 605/10 se inalterado, soma first_blocking_stage=605, new_scientific_admissions=0, external_data_accessed=false. Número de captions e formatos a medir, não presumir. Nenhum gate liberado. Próximos: diagnosticar resultado, corrigir lacunas de fonte e planejar admissão com evidência automatizada honesta; validação operacional do tick quando quota e credencial permitirem.


## Diagnóstico operacional e ponte de registro/triagem textual — 13/11/2026

- Operador reportou CORPUS_READINESS_PLANNED às 23:38 UTC: 605 IDs únicos/10 perfis; 125 formatos não prioritários; **480** Reels/carrosséis com legenda disponível após todos os filtros. 30 runs concluídos não vazios auditados, zero runs inválidos, zero registros fora do manifesto e zero admissões. Nenhum perfil/contexto registrado; data card canônico exclui 605 por ausência de registro. 12 fontes com escopo técnico correspondente (duas sem registros), 38 candidatas. Não foi enviada a saída da regressão esperada de 543; não afirmar aceite integral anterior.
- CAP-001 IMP-048/053/167/170, suporte CAP-003 IMP-064: `discovery_corpus_bridge.py` e CLI `a6_corpus_bridge.py` usam manifesto e grants existentes, sem nova aprovação institucional. Prévia de cadastro para fontes aprovadas, ativas, tecnicamente verificadas, referência igual, viewer distinto. Registro explícito admin e ingestão parada, transação atômica com lock tenant/grant e evento/outbox por perfil, idempotente; conflito de metadados bloqueia lote, não sobrescreve. Não cria grants, contextos, revisões ou admissão. Setor operacional mapeado por estrato (foodservice=food; beauty=beauty; ecommerce=commerce; financial/accounting=services; demais=other), não porte jurídico; duas fontes vazias podem integrar frame prospectivo. Eventos preservam DEC-018 e hash do manifesto; nenhuma alteração de schema.
- Triagem lexical local determinística `bd-caption-audience-signals.v1` apenas nas captions que passam readiness: sinais explícitos de endereçamento (MEI/microempresa/pequeno negócio), menção isolada ou abstenção por falta de sinal. Regex não reconhece adequadamente negação, ironia, citação, contexto implícito ou toda variedade linguística; até 'não é para MEIs' contém sinal lexical. Nunca é decisão positiva/negativa de targeting, não estima precisão, não cria review e não conta para corpus científico. Evidências por post opcionais em JSON privado exclusivo: content_id, username, SHA-256 da legenda persistida, spans de codepoints Python/rule (máx 20, truncamento sinalizado); não exporta texto, URL ou token. Sem IA externa. Campo de observabilidade audiovisual continua não avaliado; não confundir hash local da legenda com verificação criptográfica do payload Meta.
- Validação: 14 PASS puros em 0,06 s, módulo e teste conferidos por hash 5137c70/303b2a5. Um teste integrado A5/registro/replay/triagem publicado, não executado localmente. Regressão esperada 558 se 543 anteriores preservados. Registro e triagem do DB real ainda não realizados, sem merge, migração, rede, despesa ou liberação de gates. Prévia é diagnóstico corrente, manter escritores parados.
- Próximo: executar prévia com relatório privado, conferir plano de registro e aplicar cadastro local autenticado; construir avaliação contextual por post com abstenção, proveniência e trilha automatizada separada de revisão humana, seguida de critérios de admissão e direitos efetivos. Não chamar os 480 de amostra científica. Scheduler permanece pendente de quota positiva e data OAuth real.

```powershell
git pull --ff-only
python -m pytest -q tests/test_discovery_audience_signals.py tests/test_discovery_corpus_readiness.py tests/test_discovery_history_a5.py
python -m pytest -q
python scripts/verify_zero_spend.py
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_corpus_bridge.py --manifest artifacts/private/bd_manifest_a6_v8.json --report-name "a6-audience-$stamp.json"
```

Esperar AUDIENCE_SIGNALS_PLANNED, assessed_captions=480 se dados e grants inalterados; categorias somam 480, targeting_decisions=0, scientific_admissions=0. Compartilhar somente stdout agregado. Após conferir registro planejado e parar todas as rotas de ingestão, cadastro explícito (login admin local; não nova aprovação institucional):

```powershell
python scripts/a6_corpus_bridge.py --manifest artifacts/private/bd_manifest_a6_v8.json --register-profiles --confirm-all-ingestion-stopped
python scripts/a6_corpus_readiness.py --manifest artifacts/private/bd_manifest_a6_v8.json
```

Esperar 12 novos perfis se grants ainda vigentes e iguais, 0 contextos/revisões/admissões, canonical data card com até 480 técnicamente elegíveis e 0 científicos; aplicar apenas após regressão aprovada. Repetição idempotente. Fazer novo backup após alteração real, com comando de drill existente. Não compartilhar JSON privado por post ou banco.


## Aceite da triagem, diagnóstico de autenticação e piloto contextual — 13/11/2026

- Operador reportou AUDIENCE_SIGNALS_PLANNED às 23:42 UTC, 480 legendas, 7 sinais explícitos (todos Sebrae), 42 menções (36 Sebrae, 5 Contabilizei, 1 ABIHPEC), 431 abstenções. Arquivo privado a6-audience-20261113-204242.json. Nenhuma decisão de targeting/admissão. Plano 12 REGISTER, cadastro falhou INVALID_CREDENTIALS, card posterior confirma 0 perfis/contextos/admissões e inventário inalterado 605/10. Regressões 543/558 não reportadas; não alegar aprovação integral. Falha de senha pode gravar audit/contador; nenhum cadastro confirmado.
- Correção CLI a6_corpus_bridge: não assumir login admin; --admin aceita login existente ou prompt explícito. --inspect-local-admins limitado ao CLI operador OS e SQLite já existente; seleciona somente login, disabled, locked_until por membership admin do tenant; sem hash/senha/token, sem escrita ou redefinição. Não expor stdout de diagnóstico a terceiros; não repetir senha incorreta (lock 15 min após 5 falhas no IdentityStore); reutilizar login/senha já usados no provisionamento, não bootstrap/reset manual.
- CAP-003/IMP-064, CAP-001 IMP-053/170, DEC-017/018: novo adapter `discovery_audience_contextual.py` e CLI `a6_audience_contextual.py`. Reusa E1 LocalGLiNERDecider, EvidenceBundle, checkpoint fixado e validado, sem download, flags offline. Compara candidatos positivo/negativo/abstenção com lexical por matriz 3x3; valida vínculo de hash/fingerprint/modalidade/locator e não promove nenhum resultado a targeting, review ou admissão. Negativo de legenda não exclui post. 6 textos sintéticos cobrem explícito, negação, menção, implícito, institucional e consumidor; smoke de integração não é benchmark científico. Preflight padrão não abre DB/modelo.
- Política existente `decide(instagram_metadata, classify)` permanece deny-default; --execute bloqueia antes de abrir banco/carregar modelo, mesmo com flag. DEC-018 não precisa ser reafirmada, mas leitura metadata não constitui autorização técnica específica de classificação. Nenhuma alteração de policy ou criação de grant fictício. Caminho futuro de execução somente após política efetiva permitir, reusa readiness com grants e manifesto existentes, sem gravação DB, relatório por post privado exclusivo com hash/locator correlacionável e modelo fixado. Sem texto bruto, sem avaliação audiovisual, sem validação independente. Não habilitar operação real agora. Piloto sintético é opcional se checkpoint local já disponível.
- 11 PASS em 0,03 s nos testes puros (blobs 4182ce5/adf5628 verificados); dois testes integrados publicados e não executados localmente. Esperado 571 integral se 558 preservados. Sem merge, migração, chamada Meta, inferência real ou alteração do DB operacional pelo assistente.

```powershell
git pull --ff-only
python -m pytest -q tests/test_discovery_audience_contextual.py tests/test_discovery_contextual_integration.py tests/test_discovery_audience_signals.py tests/test_discovery_corpus_readiness.py tests/test_discovery_history_a5.py
python -m pytest -q
python scripts/verify_zero_spend.py
python scripts/a6_corpus_bridge.py --inspect-local-admins
```

Somente no terminal privado: conferir login admin e estado, não enviar login/senha ou hash ao chat. Se conta desbloqueada e senha conhecida, parar ingestão e executar novamente (prompt login e senha):

```powershell
python scripts/a6_corpus_bridge.py --manifest artifacts/private/bd_manifest_a6_v8.json --register-profiles --confirm-all-ingestion-stopped
python scripts/a6_corpus_readiness.py --manifest artifacts/private/bd_manifest_a6_v8.json
python scripts/a6_audience_contextual.py
```

Esperado cadastro 12/480 técnico/0 científico se grants inalterados; se falhar novamente, parar, não resetar senha diretamente no SQLite. Preflight contextual CONTEXTUAL_READINESS, classification_scope_allowed=false. Após sucesso fazer backup como já documentado. Se checkpoint local previamente validado disponível e flag TAPI_SYSTEM_ONE_ENABLED=1, teste opcional com `--synthetic-smoke --report-name "a6-contextual-synthetic-<stamp>.json"` (TAPI_SYSTEM_ONE_LOCAL_MODEL_DIR aponta para diretório existente fora do projeto). Não executar --execute em base real enquanto policy negar. Próximo resolver escopo técnico efetivo de classificação e contexto de fontes, validar modelo local em smoke e então avaliar corpus, sem simular revisão humana.


### Correção de ergonomia do login — somente senha

Por solicitação do responsável, o CLI `a6_corpus_bridge.py --register-profiles` agora localiza automaticamente o único admin habilitado do tenant no SQLite existente e solicita apenas a senha (getpass); não imprime o login, não tenta autenticar em várias contas e mantém IdentityStore, RBAC, contador de falhas e revogação de sessão. Zero/múltiplos admins habilitados ou conta única temporariamente bloqueada interrompem antes do prompt de senha; --admin explícito continua disponível para ambientes ambíguos ou PostgreSQL. Não faz reset, bootstrap ou mudança de credenciais. Substitui a instrução anterior de prompt de login. Se senha incorreta, parar e não insistir. 6 testes puros executados (0,03s, blobs fe97db0/130fe7c verificados); teste integrado CLI com IdentityStore real e registro simulado publicado, não executado localmente. Esperado 578 integral se 571 preservados. Sem mudança do DB operacional pelo assistente.

```powershell
git pull --ff-only
python -m pytest -q tests/test_local_admin_selection.py tests/test_discovery_contextual_integration.py
python scripts/a6_corpus_bridge.py --manifest artifacts/private/bd_manifest_a6_v8.json --register-profiles --confirm-all-ingestion-stopped
```

Executar registro somente após testes e com ingestão parada; senha exclusivamente no terminal local. Não é nova autorização institucional.


## Registro real de 12 perfis e contexto documental / escopo local — 14/11/2026 UTC

Operador reportou SAMPLING_PROFILES_REGISTERED: 12 novos, 0 anteriores, sessão autenticada, 0 contextos e admissões; data card 01:05 UTC confirma 12 grants ativos/verificados, 480 tecnicamente elegíveis/10 perfis, 125 formatos excluídos, 480 sem contexto, zero excluídos por registro e 0 científicos. Inventário 605/10 inalterado, 30 runs auditados. Setores: serviços 251, outros 136, comércio 57, beleza 33, alimentação 3. Nenhum teste integral novo reportado. Backup pós-registro ainda não confirmado.

CAP-001/IMP-053/167/170 e CAP-003/IMP-064: `discovery_caption_research.py` introduz evento/outbox por fonte, provisionado por admin autenticado com ingestão parada, lock tenant/grants e correspondência de manifesto, grant ativo/verificado, perfil registrado e referências. Contexto documental reproduz estrato, intenção declarada, referências e hipótese de tipo/setor; porte desconhecido, não revisão humana, não post targeting. Escopo técnico específico `offline_bd_caption_candidate_classification` para legendas já persistidas, DEC-018 como referência única; não cria grant de leitura, não modifica policy.py global, não permite mídia/API/publicação/agregação externa. Revogável por fonte (evento específico ou revogação/expiração do grant subjacente); reexecução idempotente, conflito bloqueia lote. Provisão não significa verificação independente de direitos/termos do provedor. Data card preserva contadores científicos e humanos; nova cobertura documental separada, registros com contexto documental mas sem contexto humano passam para exclusão por avaliação pendente. Sem migração.

CLI bridge: --plan-contexts offline; --register-contexts com senha do único admin e ingestão parada; --revoke-context USERNAME explícito somente para revogar. CLI contextual com --manifest verifica todos os escopos locais e exige --confirm-all-ingestion-stopped em --execute, revalida antes de cada inferência e no final; mantém deny global e não usa grant de leitura como autorização isolada. Sem execução real de modelo pelo assistente. Não há atomicidade global de leitura e inferência, manter todos os escritores parados; relatório de candidatos não é revisão nem admissão. Caminho --execute sem manifesto segue bloqueado. Integração simulada publicada, não executada localmente; regressão esperada 579 se 578 preservados. PR draft sem merge.

```powershell
git pull --ff-only
python -m pytest -q tests/test_discovery_history_a5.py tests/test_discovery_contextual_integration.py tests/test_corpus_audit_v52.py
python -m pytest -q
python scripts/verify_zero_spend.py
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_backup_restore_drill.py --output-name "tapi-a6-registered-$stamp.sqlite3" --confirm-all-writers-stopped
python scripts/a6_corpus_bridge.py --manifest artifacts/private/bd_manifest_a6_v8.json --plan-contexts
python scripts/a6_corpus_bridge.py --manifest artifacts/private/bd_manifest_a6_v8.json --register-contexts --confirm-all-ingestion-stopped
python scripts/a6_audience_contextual.py --manifest artifacts/private/bd_manifest_a6_v8.json
```

Executar registro somente após regressão e backup aprovados, escritores parados. Esperar 12 contextos/escopos locais, 0 humanos/admissões, local_caption_scope_allowed=true e classification_scope_allowed=false (negação global preservada). Após checkpoint local verificado e smoke sintético, testar inferência local real com --execute --manifest ... --confirm-all-ingestion-stopped --report-name exclusivo, TAPI_SYSTEM_ONE_ENABLED=1 e --model-dir diretório existente fora do projeto. Não baixar modelo automaticamente nem compartilhar relatórios privados.
