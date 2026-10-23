# Camada de identidade, persistência e eventos — implementação

**Status: implementação de código com testes locais aprovados.** Não implica implantação homologada em produção nem autoriza dados externos.

## Decisões arquiteturais aplicadas

- Identidade first-party, usuários com credenciais **Argon2id**, sessões bearer aleatórias (48 bytes codificados), token armazenado somente como SHA-256, TTL de 1 hora, logout revogável, lockout após cinco falhas por 15 minutos.
- Bootstrap inicial de admin exclusivamente por CLI offline (senha via terminal; sem endpoint de registro público), membros criados apenas por `admin` do tenant; papel é resolvido **do banco a cada requisição**.
- Papéis `admin/researcher/annotator/editor/viewer/service`, autorização explícita por rota e verbo; criação e consulta condicionadas ao tenant derivado da sessão, nunca à URL ou body. Todas as operações externas permanecem negadas mesmo para `admin`.
- Repositório unificado com SQLAlchemy Core, tabelas com FK compostas `(tenant_id,id)` para relacionamentos e Alembic versionado. SQLite é backend gratuito de testes locais; mesmo esquema SQLAlchemy compila para PostgreSQL, porém **PostgreSQL de verdade ainda não foi testado**. No startup normal, migração não é aplicada automaticamente.
- Evento de domínio gravado na mesma transação da escrita; outbox de entrega com confirmação, tentativas limitadas e estado de dead letter. O consumidor interno tem semântica **at-least-once**, não exatamente uma vez; callbacks devem deduplicar por `event_id`.
- `GET /v1/events` oferece paginação por `seq`, `GET /v1/events/stream` usa SSE com cursor `Last-Event-ID` e revalidação de sessão; eventos contêm metadados sintéticos mínimos.
- HTTP não-TLS é negado no modo seguro, exceto quando explicitamente ativado para loopback local.

## Procedimento de bootstrap gratuito

```bash
python -m pip install -e '.[dev]'
export TAPI_DATABASE_URL="sqlite:////absolute/path/to/secure.sqlite3"
python -m alembic upgrade head
python -m tapi_gate0.ops bootstrap-admin --tenant local-research --username admin
export TAPI_ALLOW_HTTP_LOOPBACK=1
uvicorn tapi_gate0.secure_api:from_environment --factory --host 127.0.0.1 --port 8000
```

Para testar PostgreSQL (sem contratar serviços), usar instância PostgreSQL **local já disponível**, instalar driver livre `psycopg[binary]` via extra `.[production]` e migrar com `alembic upgrade head`; verificar isolamento, transações, retry, backup/restore e carga antes de liberar a implantação.

## Avaliações executadas localmente

`python -m pytest -q`, `python scripts/check_gate0.py`, `python scripts/verify_zero_spend.py`, migração Alembic em SQLite e exportação do OpenAPI. Registro de testes remotos: **não executados** porque GitHub Actions não foi ativado (orçamento R$ 0).

## Lacunas antes da homologação operacional

1. Executar integração real com PostgreSQL e testar drivers/migrações sem rede, falhas de transação, concorrência e segurança.
2. Planejar e validar RLS no PostgreSQL como defesa adicional (o isolamento atual é aplicativo + chaves compostas).
3. Testar backups/restauração e plano de recuperação, políticas de retenção/exclusão de sessões e eventos.
4. Implementar leasing de jobs e idempotência por consumidor para processamento em múltiplos workers; a outbox atual atende teste local de consumidor único.
5. Definir operação de recuperação segura de credenciais, MFA/SSO quando apropriado e gestão de segredos em ambiente de execução autorizado.
6. Autorizações de fontes, aprovação institucional e integrações reais permanecem pendentes. Publicação de mídia paga em R$ 0 permanece inviável.

**Aceite desta ação:** código, contratos e testes locais; **não** aceite de toda arquitetura e **não** homologação de produção.