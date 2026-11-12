# CAP-001 / A4 — lote ampliado de observações técnicas Meta Business Discovery

**Corte:** 06/11/2026. **Escopo:** seleção explícita de fontes, coleta oficial limitada, persistência, deduplicação e relatório de cobertura. **Status atualizado em 12/11/2026:** código e testes offline implementados; três execuções reais no ambiente autorizado do operador reportadas com sucesso, incluindo lote de três fontes, reauditoria local e refresh sem duplicação. Ver seção de evidência operacional ao final. O banco privado não foi inspecionado diretamente nesta revisão.

**Precedência:** [DEC-016](33_DEC016_IMPLEMENTACAO_FONTE_ELEGIBILIDADE_DATA_CARD_V2.md), [DEC-018](53_DEC018_CONFIRMACAO_ALCANCE_E_CRITERIO_REVISAO_2026-11-05.md) e [A3 técnico real](45_A3_BUSINESS_DISCOVERY_PRIMEIRO_LOTE_TECNICO.md). A4 **não** é revisão independente nem inclusão científica automática.

## Entrega técnica do incremento

- `src/tapi_gate0/discovery_batch.py`: manifesto Pydantic versionado `tapi-bd-technical-batch.v1`, seleção explícita de até **cinco fontes aprovadas por lote**, limite de **quatro páginas por fonte** (dez registros/página), persistência de até **40 observações por fonte** — frente ao limite A3 de três — e limite agregado de **20 solicitações** oficiais por lote. Configuração padrão mais conservadora: três fontes, até quatro páginas e **12 observações por fonte**.
- `scripts/a4_business_discovery_curated_batch.py`: `--plan` é offline e padrão. `--execute` exige todos os flags A3, OAuth Meta, tenant, banco existente, viewer IG, **relatório JSON privado**, ID de fonte verificado e grant vigente, com `approval_reference` igual ao manifesto. Não cria grants, não descobre perfis por conta própria e não usa cobrança.
- `TechnicalDiscoveryService` A3 é reutilizado sem alterar persistência: posts de `ingestion_records`, conteúdo, métricas imutáveis por snapshot, eventos de proveniência e outbox com transação por item. IDs persistidos seguem estáveis, repetição de posts não os duplica, e alteração de métricas acrescenta snapshot. Um ID de mídia Meta já atribuído a **outra fonte** no mesmo tenant é tratado como conflito, sem duplicação silenciosa.
- Relatório `tapi-bd-technical-coverage.v1`: por perfil — fonte, estrato, registros novos, métricas atualizadas, duplicatas sem alteração, páginas e itens retornados, itens recentes, hashes e referências a snapshots. Global — contagens consolidadas, itens técnicos únicos no DB antes/depois, número de perfis observados e déficit de observabilidade; nunca apresenta cobertura técnica como satisfação da meta **científica** de 30 fontes/2.000 posts.
- Grant ausente/expirado ou inconsistente em qualquer fonte selecionada bloqueia **antes da primeira solicitação externa**. O grant de cada fonte é rechecado imediatamente antes de seu run e novamente dentro do pipeline A3, inclusive antes da persistência. Erro de fonte interrompe as seguintes; o relatório do lote registra apenas códigos seguros.

## Fonte selecionada ≠ fonte autorizada

O manifesto público [`evidence/acquisition/bd_batch_candidate_manifest_v1.json`](../evidence/acquisition/bd_batch_candidate_manifest_v1.json) contém **seis candidatos documentais** (Sebrae e cinco perfis de pesquisa anterior), todos com `status=candidate`. Só o identificador do Sebrae foi observado no piloto A3; **não atribuímos IDs não verificados aos outros perfis**. Não há aqui declaração de novos grants ou de direito de reutilização. O tipo/porte do criador não serve de critério de exclusão: a elegibilidade científica depende da **publicação dirigida a MPEs**, com evidência observável (DEC-016).

Para ativar uma fonte individualmente no **manifesto privado**, é necessário confirmar: (1) `username` e `expected_ig_id` oficiais, (2) estrato e referência de intenção MPE, (3) escopo técnico de metadados e expiração, (4) aprovação efetivamente registrada em `ingestion_source_grants` sob **o mesmo tenant, conta e referência**. Ajustar `status=approved`, informar `approval_reference`, `audience_rationale_reference`, `expires_at` (UTC) e `allowed_operations=["business_discovery_metadata_read"]`. Uma string `approved` em JSON, sozinha, não configura o grant nem substitui as condições da API ou eventuais direitos editoriais.

### 1. Prévia sem rede

```powershell
python scripts/a4_business_discovery_curated_batch.py `
  --manifest evidence/acquisition/bd_batch_candidate_manifest_v1.json
```

A saída inicial esperada é **6 candidatos, 0 selecionados, 0 chamadas externas**. Faça uma cópia não versionada da lista em `artifacts/private/bd_manifest_approved.json` antes de atribuir qualquer aprovação real. O diretório `artifacts/private/` está no `.gitignore`.

### 2. Execução real — somente no ambiente do operador autorizado

No mesmo terminal/DB do piloto [A3](45_A3_BUSINESS_DISCOVERY_PRIMEIRO_LOTE_TECNICO.md), configurar os valores efetivos **via ambiente protegido**, não em arquivos do Git: `TAPI_DATABASE_URL`, `TAPI_TENANT_ID`, `TAPI_META_IG_ID`, `TAPI_INSTAGRAM_ACCESS_TOKEN`, `TAPI_OFFICIAL_METADATA_READS=1`, `TAPI_ZERO_BILLING_CONFIRMED=1` e `TAPI_BD_TECHNICAL_INGEST=1`. Validar primeiro as quotas e condições gratuitas aplicáveis. O token nunca deve aparecer em PR, log, arquivo de cobertura ou CLI.

```powershell
python scripts/a4_business_discovery_curated_batch.py `
  --manifest artifacts/private/bd_manifest_approved.json `
  --execute `
  --batch-key bdbatch-operador-20261106-01 `
  --max-sources 3 --page-limit 10 --max-pages 4 --persist-limit 12 `
  --report artifacts/private/bd_a4_20261106_01.json
```

**Não copiar o `batch-key` em uma segunda execução:** o ledger protege contra reuso acidental. O arquivo de relatório deve ter nome novo a cada execução e é criado com permissão de arquivo restrita. Os limites podem chegar a cinco fontes e 40 registros por perfil, respeitadas as quotas, os contratos e a disponibilidade da API.

O resultado é JSON privado. Verificar `status`, `sources[].audit_all_traces_valid`, `evidence[].metadata_sha256`, `evidence[].snapshot_id`, `coverage.unique_technical_posts_added` e a concordância com as linhas reais do banco. **Só então** registrar volume novo na matriz de execução. O lote deve terminar com `scientific_admissions_from_batch=0` e `production_approved=false`; promover um item ao corpus científico exige avaliação separada dos direitos, observabilidade e critérios de elegibilidade.

## Critérios de aceite e verificação

| Critério | Evidência disponível neste PR | Limitação |
|---|---|---|
| Seleção de fontes | Manifesto privado aprovado necessário, validações de schema, IDs únicos e referências/grants iguais | Candidatos públicos não estão aprovados |
| Deduplicação e refresh | Teste SQL para duas fontes com 4 conteúdos, segunda coleta produz 0 novos, 1 snapshot atualizado e 3 itens inalterados; conflito do mesmo media ID entre fontes é bloqueado | Dados de teste com transporte simulado |
| Ampliação | Teste com cinco registros sintéticos persistidos no **SQLite de teste**; antigo limite A3 era 3 | Não é uma nova coleta Meta real |
| Proveniência | Auditoria de eventos, snapshots, outbox, hashes e run keys; nenhuma credencial/cursor armazenado | Hash é integridade local, não assinatura Meta |
| Limites e bloqueios | Preflight de todos os grants, validação de janela/flags, limite 5×4, stop-on-error | Sem medição de quotas Meta em ambiente real |
| Cobertura | Contagens por origem e total de registros técnicos únicos no banco antes/depois | Não prova representatividade/validade científica |
| Dados reais novos | **36 novos registros técnicos reportados em três lotes de 12/11/2026; 24 refreshes** | Três fontes reais; banco privado não inspecionado diretamente nesta revisão |

**Nota:** a referência científica de 2.000–5.000 posts e pelo menos 30 perfis continua pendente. O lote A4 é operacionalmente limitado para segurança e não pretende atingir essa meta em uma execução.

## Evidência operacional reportada pelo operador — 12/11/2026

Prévia offline: manifesto SHA-256 `b506a6e3cd4513a1a1c41c13ef82cbaa0654f0a9b0c7d4fa804bfdc475dd74b0`; 1 fonte selecionada de 6 candidatas (Sebrae, `17841403133066329`); limites 4 páginas, 10 itens/página, 12 observações. O endpoint de prontidão havia retornado `READY_FOR_BOUNDED_PREFLIGHT` sem bloqueios.

| Evidência | Lote 1 | Lote 2 |
|---|---:|---:|
| Batch key | `bdbatch-20261112-103410` | `bdbatch-20261112-103638` |
| Run key | `bdbatch-20261112-103410-01` | `bdbatch-20261112-103638-01` |
| Status | BATCH_COMPLETED | BATCH_COMPLETED |
| Páginas examinadas | 4 | 4 |
| Itens retornados | 32 | 32 |
| Excluídos por idade | 20 | 20 |
| Observações elegíveis | 12 | 12 |
| Registros novos | 12 | 0 |
| Refresh de métricas | 0 | 12 |
| Duplicatas inalteradas | 0 | 0 |
| Posts técnicos únicos antes/depois | 3 → 15 | 15 → 15 |
| Reauditoria read-only: observações | 12 | 12 |
| Reauditoria: all_traces_valid | true | true |
| Reauditoria: has_persisted_observations | true | true |
| Admissões científicas | 0 | 0 |

**Conclusão restrita:** a repetição real preservou a cardinalidade dos posts e registrou refresh de métricas nas 12 observações. A implementação compara likes, comments, follower_count e views; o resumo não identifica qual campo mudou. Não afirmar que todos os posts ganharam curtidas ou comentários. As 24 observações dos dois runs não são 24 posts únicos.

**Limites da evidência:** transcrição dos resumos de CLI/JSON e da reauditoria executada pelo operador, não inspeção independente do banco, dos JSON completos ou dos payloads Meta. Não anexar tokens, dados privados ou payloads. O teste multifonte real continua pendente; testes simulados cobrem múltiplas fontes, mas não o comportamento live. A referência científica de 30 perfis/2.000–5.000 posts não foi atingida; `production_approved=false`. Esta evidência não libera gates globais, não autoriza novas fontes e não substitui a revisão final do diff.

## Primeiro lote multifonte real — 12/11/2026

Evidência reportada pelo operador após registro e verificação dos grants de Stone e Ton no tenant local, além do grant Sebrae preexistente. IDs identificados via Business Discovery oficial: Stone `17841401947908402`, Ton (`seliganoton`) `17841426444024285`; Sebrae RN `17841401897470679` identificado mas **não selecionado**. Não há autorização implícita para a fonte reserva.

Batch `bdmulti-20261112-104658`, `BATCH_COMPLETED`, 3 fontes, limites 4 páginas × 10 itens e 12 observações por fonte. Resultado: 9 páginas, 79 itens retornados, 43 recentes excluídos, 36 observações elegíveis, 24 registros novos, 12 refreshes, 0 duplicatas inalteradas ou do provedor; cobertura técnica 15 → 39 posts únicos nas três fontes.

| Fonte | Run key | Novos | Refreshes | Posts únicos após | Observações reauditadas | Trilhas válidas |
|---|---|---:|---:|---:|---:|---|
| Sebrae | `bdmulti-20261112-104658-01` | 0 | 12 | 15 | 12 | true |
| Stone | `bdmulti-20261112-104658-02` | 12 | 0 | 12 | 12 | true |
| Ton | `bdmulti-20261112-104658-03` | 12 | 0 | 12 | 12 | true |

Todos os runs: `BD_TECHNICAL_METADATA_COMMITTED`; reauditorias read-only: `completed`, `all_traces_valid=true`, `has_persisted_observations=true`. Três lotes A4 totalizam 60 observações (36 novas + 24 refreshes), além de três posts únicos do piloto A3, sem admissão científica automática. Cobertura não exaustiva e não comparável à referência científica. A base do lote não representa todos os posts de todas as fontes nem uma amostra representativa; Stone e Ton são do mesmo grupo.

**Aceite operacional multifonte reportado**. Não houve acesso independente ao DB ou ao relatório integral nesta revisão. A prova não testa conflito concorrente entre fontes em produção, nem valida direitos independentemente, CI ou os gates científicos. A revisão de código identificou que a verificação cross-source ocorre antes da persistência, sem restrição de unicidade global entre contas; não assumir segurança para execuções concorrentes entre fontes. Manter execução serial por tenant até tratar/testar concorrência. Revisão final e regressão ampliada pendentes antes do merge.

## Revisão de fechamento — 12/11/2026

- Correção de concorrência: `_persist_item` obtém lock transacional por tenant antes do lock por fonte e revalida propriedade do media ID Instagram na mesma transação de conteúdo, snapshot e outbox. Aplica-se a todos os caminhos de ingestão que usam o store. O precheck A3 permanece como bloqueio antecipado, não é a única defesa. Conflito retorna `BD_CROSS_SOURCE_MEDIA_ID_CONFLICT`.
- Novo teste com barreira força duas threads a ultrapassarem o precheck antes da persistência: exatamente um registro, um snapshot, um run completado e um conflito. Teste em SQLite de arquivo. A implementação utiliza locks SQL, mas não foi executada contra PostgreSQL nesta rodada. Execuções multifonte continuam seriais por tenant para evitar que contagens before/after misturem lotes concorrentes.
- Regressão focada: 63 PASS; complementar: 139 PASS. Suíte completa Python disponível: **371 PASS** (38,85 s; o processo de ferramenta atingiu seu limite de tempo, mas o log final do pytest mostrou 371 passed). `verify_zero_spend.py` PASS, `check_gate0.py` estrutura local verificada, Gate 0B global bloqueado. Snapshot local do código baseado em `79bb017`, comparado com a base `e5bc4a3` (alterações PR41 documentais e sincronização de plano), sobreposto com blobs A4 correspondentes aos hashes do PR; arquivos de correção e teste conferidos por SHA. Não é CI remota nem homologação do banco operacional.
- A4 aceito como incremento de engenharia; não implica liberação de produção, admissão científica, cobertura exaustiva ou cumprimento de CAP-001 integral. A5 deverá utilizar checkpoints específicos Business Discovery, não os cursores da ingestão first-party, e orquestração serial.
