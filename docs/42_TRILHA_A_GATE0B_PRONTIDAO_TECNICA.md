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
