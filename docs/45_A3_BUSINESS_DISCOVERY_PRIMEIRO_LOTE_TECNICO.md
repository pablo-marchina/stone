# A3 — Business Discovery: lote técnico real com trilha de auditoria

Estado: **ingestão real e auditorias executadas pelo operador em 05/11/2026 UTC**,
com 3 publicações novas, segunda execução com 0 conteúdos novos e 3 snapshots
atualizados, e preservação verificada dos 3 snapshots originais. A revisão
técnica incluiu 314/314 testes locais aprovados, Gate 0 e gasto zero aprovados.
Esses resultados **não** constituem admissão ao corpus científico,
autorização para redistribuir mídia ou liberação de produção.

## Por que este fluxo existe

O Instagram técnico `academy_fellow_stone` (IG user ID
`17841459971757521`) confirmou acesso ao `business_discovery` de `sebrae`
(IG user ID `17841403133066329`). A resposta real apresentada pelo operador
inclui 50 posts (07/10 a 04/11/2026), 22 com pelo menos 14 dias em
04/11/2026 à noite, e métricas públicas. O `/{viewer}/media` anterior concluiu
com zero registros porque o perfil técnico tem `media_count=0`.

A rota já existente `/v1/ingestion/business-discovery/runs` **não é substituída**:
ela exige SourceFrame v2, prova local, escopo `corpus_metadata_ingest`, registro
no corpus e contexto. Este incremento oferece **somente** registro de observações
técnicas, mantendo `scientifically_validated=false`, sem atualizar tabelas de
admissão ao corpus. O registro de grant por fonte **não equivale** à verificação
legal de direitos de reutilização de conteúdo.

## Controles

- Meta Graph API versão fixa `v26.0` para esta operação; rota HTTPS de host
  fixo `graph.facebook.com`, sem redirecionamentos ou URLs vindas do provedor.
- `TAPI_OFFICIAL_METADATA_READS=1`, `TAPI_ZERO_BILLING_CONFIRMED=1` e
  `TAPI_BD_TECHNICAL_INGEST=1` obrigatórios, além de OAuth válido no ambiente.
- Grant **ativo e não expirado** para o **ID externo de destino** e tenant
  autenticado. O grant do perfil técnico não substitui o da conta externa.
- Requer `viewer_ig_id != expected_ig_id`, valida usuário e ID retornados.
- No máximo 10 publicações por página, 4 páginas por execução e **3 gravações**
  por execução; trava de cinco reservas de execução/dia/conta já presente no Store.
- Posts elegíveis tecnicamente: idade `>=14d`, imagem, Reels ou carrossel,
  com permalink HTTPS, curtidas/comentários observáveis e seguidores atuais
  positivos. Isso não define seleção científica (rubrica, estratégia e direito).
- A data de seguidores é **atual**, diferente da data histórica de publicação;
  ER é somente descritivo `(likes+comments)/followers`.
- Após a resposta remota, revalida grant e grava `technical_verified_at`
  **somente na fonte externa identificada pela Meta**, sob lock e com rechecagem
  de expiração. Esse marcador não concede elegibilidade científica, revisão
  jurídica, direito de reutilização nem aprovação de produção. Dentro da
  transação de cada post, `_persist_item` retoma bloqueio de grant e expiração.
- Persistência transacional por post: `creators`, `content_items`, `metrics_snapshots`,
  `ingestion_records`, `domain_events`, `event_outbox`; evento adicional
  `business_discovery.metadata_observed` contém run_key, viewer, fonte, post,
  snapshot, hashes SHA-256 de metadados e método de aquisição, sem token/cursor.
- Duplicatas não recriam conteúdo; alterações em métricas geram novo snapshot;
  observações técnicas repetidas têm eventos independentes no próprio run.
- Sem importação de JSON editado como prova oficial. Mocks servem **apenas** para
  testes; no modo `--execute`, o retorno é lido da Meta e gravado na mesma execução.

## Operação PowerShell no Windows (sem expor token)

Partindo de um checkout que contenha este incremento e do banco SQLite
existente utilizado pelo tenant `local-research`, com migrações oficiais já
aplicadas e administrador Stone criado:

```powershell
$env:TAPI_DATABASE_URL = "sqlite:///C:/stone-data/tapi.sqlite3"
$env:TAPI_TENANT_ID = "local-research"
$env:TAPI_META_IG_ID = "17841459971757521"
$env:TAPI_OFFICIAL_METADATA_READS = "1"
$env:TAPI_ZERO_BILLING_CONFIRMED = "1"  # somente após confirmar zero custo real
$env:TAPI_BD_TECHNICAL_INGEST = "1"
$tokenNovo = Read-Host "Novo token Meta" -AsSecureString
$env:TAPI_INSTAGRAM_ACCESS_TOKEN = ([System.Net.NetworkCredential]::new("",$tokenNovo)).Password
Remove-Variable tokenNovo
```

**O token anteriormente publicado no chat deve ser revogado na Meta.** O token
novo não deve aparecer em Git, issue, prompt, screenshot ou comentário.

O administrador deve registrar no **mesmo banco** um grant específico para o
perfil externo, caso ainda não exista. Após login no Stone, usando `$headers`
Bearer da sessão do admin (e `$base="http://127.0.0.1:8000"`):

```powershell
$grant = @{
  platform = "instagram"
  source_account_id = "17841403133066329"
  approval_reference = "DEC-018-fonte-sebrae-metadata-research"  # referência efetivamente aplicável
  expires_at = (Get-Date).ToUniversalTime().AddDays(30).ToString("o")
} | ConvertTo-Json
Invoke-RestMethod -Uri "$base/v1/ingestion/grants" -Method Post -Headers $headers `
  -ContentType "application/json" -Body $grant
```

Esse cadastro não publica nem inclui dados automaticamente no corpus. Se o
backend responder `GRANT_ALREADY_EXISTS`, verifique o grant da fonte no DB,
sem tentar recriar ou reabilitar grants expirados por SQL manual.

Para o primeiro lote (até 3 itens, até 4 requisições oficiais), no mesmo
PowerShell em que as variáveis de ambiente estão configuradas:

```powershell
python scripts/a3_business_discovery_first_batch.py --execute --username sebrae --target-ig-id 17841403133066329 --page-limit 10 --max-pages 4 --persist-limit 3
```

O comando devolve JSON sem token. `BD_TECHNICAL_METADATA_COMMITTED` e
`audit.all_traces_valid=true` com `has_persisted_observations=true` indicam
que os relacionamentos entre posts/snapshots/eventos/outbox foram verificados.
Pode-se auditar novamente, sem OAuth ou chamadas à Meta:

```powershell
python scripts/a3_business_discovery_first_batch.py --audit "RUN_KEY_DO_RESULTADO"
```

Também existem endpoints **admin-only** no backend autenticado:

- `POST /v1/ingestion/business-discovery/technical-runs`: envia o mesmo corpo
  validado de `TechnicalDiscoveryRequest`, com OAuth obtido somente do ambiente
  do Uvicorn; autorização RBAC e flags obrigatórias.
- `GET /v1/ingestion/business-discovery/technical-runs/{run_key}/audit`:
  relatório técnico read-only, delimitado pelo tenant da sessão.

## Critérios de aceite

1. `new_records>0` **ou** `refreshed_records>0` / `duplicate_records>0`,
   com pelo menos um evento de observação rastreável.
2. Origem dos itens `17841403133066329` distinta da identidade técnica
   `17841459971757521` em cada evento de auditoria.
3. Snapshot vinculado ao content ID e audit event; sem tokens, cursores ou
   documento de autorização armazenados nos eventos.
4. `research_corpus_accepted=false`, `scientifically_validated=false`.
5. Segundo run com mesmo item mantém um único `content_item`; métricas
   alteradas geram novo `metrics_snapshot` sem apagar o anterior.
6. Teste de revogação/ausência de grant bloqueia a operação e não faz rede
   se grant está ausente desde o início.

## Evidências de engenharia (não equivalem a uma nova leitura ao vivo)

`tests/test_discovery_technical_a3.py`: transporte HTTP simulado com IDs,
URLs, métricas e timestamps de uma amostra previamente observada; autenticação,
RBAC, persistência, outbox, tenant, mudança de métricas, repetição, bloqueios,
grant revogado e resposta vazia. Não foi utilizado token OAuth real no teste.

 
## Evidências de execução real do operador — 05/11/2026 UTC

| Run | Novos | Atualizados | Auditorias | Rastreabilidade |
| --- | ---: | ---: | ---: | --- |
| `bdmeta-20261105014813-08d8a157` | 3 | 0 | 3 | `all_traces_valid=true` |
| `bdmeta-20261105015021-aba58480` | 0 | 3 | 3 | `all_traces_valid=true` |

Em ambas as execuções: viewer IG `17841459971757521`, source IG
`17841403133066329`, tenant `local-research`, 4 páginas examinadas,
31 posts retornados, 28 recentes excluídos e 3 observações aceitas.
Os três `content_id` mantiveram-se estáveis; os `snapshot_id` da segunda
execução diferem dos originais. Reauditoria posterior da **primeira** execução
comprovou que seus 3 snapshots originais, conteúdos e eventos de outbox
continuavam acessíveis (`all_traces_valid=true`).

Isso demonstra persistência e rastreabilidade nesse cenário, não imutabilidade
formal, nem revisão de direitos, nem inferência causal. A classificação
`NOT_ASSESSED` continua vigente até avaliações científicas independentes,
e `production_approved=false`.

**Regressão local pós-revisão:** 314 testes Python aprovados; Gate 0 e
`verify_zero_spend.py` aprovados. Nenhum token Meta ou credencial é armazenado
neste documento.
