# Trilha A — Gate 0B técnico por conta (incremento A1)

**Estado:** mecanismo de diagnóstico e testes de segurança implementados; não é liberação automática de todas as operações, nem concessão de grants. A autorização institucional geral está informada como formalmente concedida (DEC-018, PR #32).

## Implementado

- Novo contrato `TechnicalReadiness` em `src/tapi_gate0/gate0b_technical.py`, somente para leitura oficial de metadados de **uma conta**.
- O endpoint existente `GET /v1/ingestion/connections/{platform}/{account_id}` agora retorna `BLOCKED`, `READY_FOR_BOUNDED_PREFLIGHT` ou `PREVIOUSLY_VERIFIED_RECHECK_REQUIRED`, com razões de bloqueio.
- Consulta o grant do banco filtrado pelo tenant autenticado; não aceita prova ou escopo fornecido na própria requisição.
- Rejeita grant ausente, vencido/desabilitado, referência vazia, token ausente, chave de leitura OFF e ausência de confirmação de custo zero. Não revela tokens.
- Um histórico `technical_verified_at` nunca libera automaticamente novo acesso: exige nova confirmação.
- A política de fonte histórica em `src/tapi_gate0/policy.py` continua deny-by-default. O endpoint relata prontidão para **tentar** o preflight; não altera autorização de publicação, publicidade, CRM nem mídia.

## Verificar no checkout do PR

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_gate0b_technical.py tests/test_gate0_policy.py
python -m pytest -q
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
git rev-parse HEAD
```

## Próxima implementação de A2

Conectar autorização técnica confiável às operações efetivas com enforcement por account/tenant/operation/expiry, auditoria, revogação e decisão coerente entre `policy.py` e `IngestionStore.run`, sem confiar em JSON editável. Atualizar verificadores de Gate 0B para validar operações **específicas**, não apagar 72 registros PENDING de uma vez. Preparar pré-voo Meta com ID/token fornecido por canal seguro no momento da integração.

**Este incremento não executou API externa, não promoveu Gate 0B ao estado global PASS e não alterou o orçamento R$ 0.**



## Incremento A2 — grants revogáveis e primeira leitura Meta

Implementado no mesmo PR:

- Criação do grant agora gera `ingestion.grant.created` no ledger `domain_events` e `event_outbox`; a revogação administrativa `POST /v1/ingestion/grants/{platform}/{account_id}/revoke` desabilita a conta, gera `ingestion.grant.revoked` e é irreversível nesse registro (novo grant exige fluxo explícito).
- A ingestão revalida grant depois da resposta da API e antes de marcar `technical_verified_at`. Cada persistência possui lock sobre a linha do grant, além da verificação de expiração.
- `scripts/a2_meta_first_batch.py` é um runner para **um único lote oficial delimitado** (1 a 3 publicações retornadas); nunca cria grants automaticamente nem exibe segredos/legendas. Verifica custo zero, grant ativo e credencial local. `--execute` é obrigatório.
- `tests/test_gate0b_a2.py` cobre criação/revogação e auditoria, isolamento e bloqueio do runner sem pré-requisitos. Atualizada expectativa do teste legado de eventos para incluir auditoria de criação.

### Comandos de verificação local no HEAD do PR

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_gate0b_technical.py tests/test_gate0b_a2.py tests/test_official_ingestion.py
python -m pytest -q
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
git rev-parse HEAD
```

### Primeiro lote Meta real (não executado nesta sessão)

O operador deverá fornecer **somente ao ambiente local seguro** `TAPI_DATABASE_URL`, `TAPI_TENANT_ID`, `TAPI_META_IG_ID` (IG ID, não Page ID), `TAPI_INSTAGRAM_ACCESS_TOKEN`, `TAPI_OFFICIAL_METADATA_READS=1` e `TAPI_ZERO_BILLING_CONFIRMED=1`. O administrador deve ter previamente criado um grant ativo por `POST /v1/ingestion/grants` para esse IG ID. Verificar política de quotas do fornecedor e custo financeiro antes de ativar os switches.

```powershell
python scripts/a2_meta_first_batch.py
# Somente após grant, autenticação, quota e custo zero localmente verificados:
python scripts/a2_meta_first_batch.py --execute --limit 3
```

A saída sanitizada deve conter `BOUNDED_OFFICIAL_READ_COMPLETED`, `run_key`, contagens de novos/duplicados/recentes e `metadata_only=true`. `new_records=0` pode ser um resultado honesto caso a amostra tenha apenas mídias recentes. **Ainda não há primeira leitura Meta real comprovada neste PR.** Nenhuma operação de publicação, vídeo ou publicidade é habilitada.
