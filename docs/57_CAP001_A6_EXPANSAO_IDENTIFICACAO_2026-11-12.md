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
