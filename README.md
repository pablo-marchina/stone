# TAPI Stone — Plataforma unificada (implementação incremental)

> **Situação atualizada em 05/11/2026:** ver [decisões pós-v5.2](docs/51_REGISTRO_DECISOES_POS_V52_2026-11-05.md), [matriz de alinhamento](docs/52_MATRIZ_ALINHAMENTO_FONTES_REPOSITORIO_2026-11-05.md), [DEC-018](docs/53_DEC018_CONFIRMACAO_ALCANCE_E_CRITERIO_REVISAO_2026-11-05.md) e [matrizes sincronizadas](docs/54_SINCRONIZACAO_MATRIZES_V52_DEC018_2026-11-05.md). O piloto oficial Meta A3 registrou **3 posts técnicos reais** e snapshots, mas **zero admissões científicas demonstradas**; o Creative Studio E3–E8 foi integrado até o [PR #40](https://github.com/pablo-marchina/stone/pull/40). Não há homologação de produção, corpus-alvo validado, rubrica multimodal completa ou playbook institucional concluído. Abaixo há seções **históricas de implementação incremental**, que não devem ser interpretadas isoladamente como o estado mais recente.


**Status:** domínio, autenticação, UI autenticada, eventos e conectores de **metadados oficiais** implementados e testados localmente; ainda não é a plataforma completa. **NÃO HOMOLOGADO para produção.** Uma coleta oficial real limitada foi relatada no piloto A3 em 05/11/2026; ver ressalvas no início deste README.

Este pacote materializa as decisões do responsável pelo projeto: **repositório privado** `pablo-marchina/stone` (existente e acessível), **comparar infraestrutura** (decisão aberta), **custo financeiro total R$ 0 (bloqueio obrigatório)**, **aprovação geral de dados e operações declarada pelo solicitante, com grants por conta ainda não registrados e acessos técnicos ainda não validados**, **escopo ampliado aprovado pelo solicitante; autoridade institucional não comprovada**. Segue a Arquitetura Unificada v5.1 e o Plano Único, sem alterar o objetivo de **uma entrega final consolidada**.

> **CAP-001/A4 (06/11):** novo [lote curado Business Discovery](docs/55_CAP001_A4_LOTE_AMPLIADO_BUSINESS_DISCOVERY_2026-11-06.md), com até cinco fontes aprovadas, persistência limitada de até 40 observações por fonte, deduplicação, eventos e cobertura. **Nenhuma nova leitura real foi feita neste desenvolvimento sem credenciais/grants**; os candidatos documentais não são autorização. A execução é opt-in no ambiente do operador.

## O que funciona agora

- API de bootstrap e API segura com identidade, domínio, eventos, UI e conectores oficiais condicionados a autorização específica; nenhum acesso real realizado.
- Política **deny-by-default**: coleção externa só por `/v1/ingestion/runs`, com grant por conta, credencial, autenticação e atestação de custo zero; publicação, CRM e anúncios permanecem inativos.
- Schemas candidatos da rubrica e contratos herdados sem declará-los homologados.
- Testes automáticos de autorização, invariantes e integração leve do bootstrap; CI reproduzível.
- Matrizes de autorização, decisões abertas, protocolo de experimentos de infraestrutura, restrições de gasto, governança de avaliações e registro de pendências.

## Execução local

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
uvicorn tapi_gate0.api:app --host 127.0.0.1 --port 8000
# outra janela: curl http://127.0.0.1:8000/healthz
# curl http://127.0.0.1:8000/v1/gate0/status
```

Não é necessário criar conta na nuvem ou possuir chaves para rodar. `docker compose up --build` inicia apenas a API local; o banco de teste é opt-in com `docker compose -f compose.yaml -f compose.local-db.yaml up --build` e exige `TAPI_DB_PASSWORD` configurado fora do repositório. O endpoint público não deve ser exposto à internet; ele não substitui autenticação/autorização da aplicação final.

## Fluxo seguro de implementação

`Contratos/gold/identidade → pipeline sintético interno → aquisição apenas após autorização → classificação/avaliações → experiência única → homologação operacional`. São **passos internos**, não entregas distintas.

## Situação de aprovação

- **Gate 0A:** *PARCIAL — bootstrap técnico local pronto; definição de identidade de produção, permissões, contratos restantes e decisões tecnológicas pendentes.* Pode iniciar engenharia local limitada.
- **Gate 0B:** *PARCIAL — aprovação geral informada pelo solicitante, mas tokens, acesso técnico e registro de permissão por conta/operação continuam pendentes.*
- **Aceite global da arquitetura:** *NÃO INICIADO*; aprovação de Gate 0 não representa aceite da plataforma.

Comece em `docs/00_MAPA_E_STATUS.md`, depois `docs/01_ACOES_DO_RESPONSAVEL_E_STONE.md`. Os documentos `docs/` não contêm prazos nem divisão de entregas.

## Decisões adicionais do solicitante

- **Custo financeiro máximo: R$ 0**, em todo o produto. Não habilitar integração com serviços que possam gerar faturamento.
- **Escopo ampliado aprovado pelo solicitante**, sem presumir aval institucional nem direitos sobre conteúdo externo.
- **GitHub privado em uso**: `pablo-marchina/stone`; ver `docs/15_REPOSITORIO_GITHUB.md`.
- Os testes automatizados são executados **localmente** com `bash scripts/ci_local.sh`; o workflow GitHub Actions foi movido para exemplo desativado para reduzir risco de custos.
- Ver `docs/14_POLITICA_CUSTO_ZERO.md`, `docs/16_ESCOPO_APROVADO_E_AUTORIZACOES.md` e `docs/17_STATUS_GATE0_ATUALIZADO.md`.

## Domínio e contratos executáveis (synthetic-only)

O pacote possui agora modelos Pydantic da jornada única, persistência SQLite transacional local, autorização por chave de desenvolvimento e endpoints reais do primeiro fluxo, com OpenAPI gerado do código, ranking oficial e linagem até o criativo. **Somente dados `synthetic_local` são aceitos e todas as operações externas continuam bloqueadas.** Consulte [especificação técnica do domínio](docs/18_DOMINIO_E_CONTRATOS_EXECUTAVEIS.md).

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
PYTHONPATH=src python scripts/export_local_openapi.py
```

## Identity, PostgreSQL-compatible persistence, and transactional events (secure mode)

This implementation adds a **separate secure application mode** in the same unified
product. It does not authorize Instagram/YouTube/Stone ingest, publication, ads or CRM.
**Financial budget remains strictly R$ 0.** The initial identity and test corpus are
local; no hosted PostgreSQL service or paid identity provider has been provisioned.

### Installation and migrations (local, no cloud cost)

```bash
python -m pip install -e '.[dev]'
export TAPI_DATABASE_URL="sqlite:////absolute/path/to/local_secure.sqlite3"
python -m alembic upgrade head
python -m tapi_gate0.ops bootstrap-admin --tenant local-research --username admin
# provide a unique 12+ character password at the prompt (never add it to Git)
export TAPI_ALLOW_HTTP_LOOPBACK=1
uvicorn tapi_gate0.secure_api:from_environment --factory --host 127.0.0.1 --port 8000
```

The bootstrap command does not print the password. Authentication uses Argon2id,
revocable random opaque bearer sessions (SHA-256 hashes at rest, 1 hour TTL),
role-based access from durable memberships and composite tenant-scoped FKs.
Use `POST /v1/auth/sessions` to log in; pass `Authorization: Bearer ...` for
other operations. In a deployed environment **HTTPS is mandatory**, without the
loopback flag. Public registration and password reset are deliberately disabled
until their workflows and evaluation are specified.

PostgreSQL candidate: install the optional local driver with
`python -m pip install -e '.[production]'` if available from a free or local
source; set `TAPI_DATABASE_URL=postgresql+psycopg://...` with credentials obtained
from a secrets manager. The same Alembic migration and SQLAlchemy models support
this dialect. PostgreSQL DDL has been compiled, but **no live PostgreSQL
integration, RLS, replication, backup/restore, or production workload test has
been performed yet**. Do not call this a production-homologated deployment.

### Transactional events

Every successful domain write commits its event and event_outbox row in the same
transaction. Read `GET /v1/events?after_seq=N` or connect to
`GET /v1/events/stream` using a bearer token. SSE supports `Last-Event-ID`
replay; keepalive and session validation apply. `EventDispatcher.deliver()`
implements at-least-once processing, bounded attempts and a dead-letter state.
Callbacks **must be idempotent using event_id**; there is intentionally no external
broker or paid messaging service. Concurrent dispatcher leasing, operational
monitoring, PII scrubbing policy and event-retention management remain to be
hardened and tested before production release.

### Validation

```bash
python -m pytest -q
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
# optional: export the secure OpenAPI locally through app.openapi()
```

Local API examples use only `synthetic_local` source. Data access and any
external action stay deny-by-default regardless of user role. Never commit
database files, bearer tokens, passwords, or real third-party content.


## Interface operacional local (sem serviços externos)

O modo seguro também serve `/app/`, um painel autenticado ligado ao endpoint `/v1/ui/overview` e aos eventos SSE reais. Execute o modo seguro conforme `docs/19_IDENTIDADE_PERSISTENCIA_EVENTOS.md` e abra `http://127.0.0.1:8000/app/` no computador local. Os tokens permanecem apenas em memória e todos os dados exibidos vêm do SQLite transacional local. Consulte `docs/20_FRONTEND_OPERACIONAL.md`.

Validação local: `PYTHONPATH=src python -m pytest -q` e `node --test tests/frontend/*.mjs`.

## Pipeline de aquisição oficial e rubrica multimodal conservadora

A camada segura agora registra grants por conta, valida identidade técnica da fonte via APIs
Meta/YouTube, normaliza metadados, aplica classificação parcial evidenciada e persiste
registros/eventos transacionais (migração Alembic 0002). **Desligada por padrão**:
este trecho registra a fase anterior ao piloto A3 de 05/11/2026; consulte a atualização no início do README.
O adaptador opcional de quadros/OCR usa somente mídia local autorizada; áudio e
inferência visual completa permanecem pendentes de validação.
Detalhes, flags, limites e ressalvas de direitos: [aquisição oficial](docs/21_AQUISICAO_OFICIAL_MULTIMODAL.md).
