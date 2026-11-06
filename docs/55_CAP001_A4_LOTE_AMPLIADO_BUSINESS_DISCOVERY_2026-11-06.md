# CAP-001 / A4 — lote ampliado de observações técnicas Meta Business Discovery

**Corte:** 06/11/2026. **Escopo:** seleção explícita de fontes, coleta oficial limitada, persistência, deduplicação e relatório de cobertura. **Status:** código e testes offline implementados; **nenhuma nova chamada Meta efetuada neste PR**, pois o ambiente de implementação não possui token, viewer ID, banco/tenant operacional nem grants consultáveis. Não declarar números reais novos até executar o comando autorizado.

**Precedência:** [DEC-016](33_DEC016_IMPLEMENTACAO_FONTE_ELEGIBILIDADE_DATA_CARD_V2.md), [DEC-018](53_DEC018_CONFIRMACAO_ALCANCE_E_CRITERIO_REVISAO_2026-11-05.md) e [A3 técnico real](45_A3_BUSINESS_DISCOVERY_PRIMEIRO_LOTE_TECNICO.md). A4 **não** é revisão independente nem inclusão científica automática.

## Entrega técnica do incremento

- `src/tapi_gate0/discovery_batch.py`: manifesto Pydantic versionado `tapi-bd-technical-batch.v1`, seleção explícita de até **cinco fontes aprovadas por lote**, limite de **quatro páginas por fonte** (dez registros/página), persistência de até **40 observações por fonte** — frente ao limite A3 de três — e limite agregado de **20 solicitações** oficiais por lote. Configuração padrão mais conservadora: três fontes, até quatro páginas e **12 observações por fonte**.
- `scripts/a4_business_discovery_curated_batch.py`: `--plan` é offline e padrão. `--execute` exige todos os flags A3, OAuth Meta, tenant, banco existente, viewer IG, **relatório JSON privado**, ID de fonte verificado e grant vigente, com `approval_reference` igual ao manifesto. Não cria grants, não descobre perfis por conta própria e não usa cobrança.
- `TechnicalDiscoveryService` A3 é reutilizado sem alterar persistência: posts de `ingestion_records`, conteúdo, métricas imutáveis por snapshot, eventos de proveniência e outbox com transação por item. IDs persistidos seguem estáveis, repetição de posts não os duplica, e alteração de métricas acrescenta snapshot.
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
| Deduplicação e refresh | Teste SQL para duas fontes com 4 conteúdos, segunda coleta produz 0 novos, 1 snapshot atualizado e 3 itens inalterados | Dados de teste com transporte simulado |
| Ampliação | Teste com cinco registros sintéticos persistidos no **SQLite de teste**; antigo limite A3 era 3 | Não é uma nova coleta Meta real |
| Proveniência | Auditoria de eventos, snapshots, outbox, hashes e run keys; nenhuma credencial/cursor armazenado | Hash é integridade local, não assinatura Meta |
| Limites e bloqueios | Preflight de todos os grants, validação de janela/flags, limite 5×4, stop-on-error | Sem medição de quotas Meta em ambiente real |
| Cobertura | Contagens por origem e total de registros técnicos únicos no banco antes/depois | Não prova representatividade/validade científica |
| Dados reais novos | **Não executados neste ambiente** | Pendente de token Meta válido, grants e banco do operador |

**Nota:** a referência científica de 2.000–5.000 posts e pelo menos 30 perfis continua pendente. O lote A4 é operacionalmente limitado para segurança e não pretende atingir essa meta em uma execução.
