# Contratos executáveis e domínio canônico — TAPI Stone

**Status:** implementado e testado **somente em ambiente local com registros sintéticos**. Não implica aprovação de operação em produção. O produto continua uma única arquitetura, sem separação em plataformas para funcionalidades opcionais.

## Escopo desta implementação

O modelo tipado abrange identidade/organização, conexões, criadores, conteúdo, snapshots de métricas, rubrica, evidência, rankings, insights, criativos, publicações, campanhas, conversões, experimentos, avaliações, runs e eventos. A versão inicial da persistência SQLite mantém entidades que participam do primeiro fluxo operacional, com chaves relacionais e eventos atômicos. Outros DTOs estão disponíveis para desenho e validação, **não** como integrações funcionais.

A interface OpenAPI é **gerada do código FastAPI/Pydantic** e armazenada em `contracts/openapi.local.json`. Nunca confundir os 23 esquemas candidatos de governança da arquitetura com contratos completos dos endpoints. Esse arquivo OpenAPI representa apenas as rotas implementadas.

### Contratos HTTP operacionais em modo local protegido

| Operação | Resultado | Regra essencial |
|---|---|---|
| `POST /v1/creators` / `GET /v1/creators/{id}` | Criador tipado | Apenas `synthetic_local`; tenant obtido da chave local |
| `POST /v1/content` / `GET /v1/content/{id}` | Conteúdo tipado | Criador deve existir no mesmo tenant e fonte |
| `POST /v1/content/{id}/metrics` | Snapshot imutável | Contagens não negativas, timestamps com timezone, FK e IDs únicos |
| `POST /v1/content/{id}/assessments` | Rubrica e evidência tipadas | 20 campos, sem atributos afirmados sem evidência |
| `GET /v1/content/{id}/assessments/latest` | Última avaliação | Não confundir `null`, `false` e `not_observable` |
| `POST /v1/analyses/rankings` | Ranking, top 10% e contagens de exclusão | ER oficial exato, idade mínima e snapshots por as-of |
| `POST /v1/insights` / `GET /v1/insights/{id}` | Insight com referências | Não aceita causalidade não comprovada |
| `POST /v1/creatives` / `GET /v1/creatives/{id}` | Rascunho editorial | Referências devem fazer parte do insight |
| `GET /v1/creatives/{id}/lineage` | Criativo → insight → conteúdos | Resolve todas as referências no mesmo tenant |
| `GET /v1/events` | Eventos de domínio com sequência | Eventos gravados na transação da alteração |
| `GET /v1/domain/catalog` | Catálogo do domínio | Distingue capacidades operacionais e não implementadas |
| `POST /v1/policy/check` | Decisão local de autorização | Não transforma um arquivo JSON em permissão |

Rotas `/v1/collections`, `/v1/publications`, `/v1/campaigns`, `/v1/crm/conversions` possuem contrato de entrada e retorno **403 obrigatório**. São intencionalmente inoperantes, não placeholders anunciados como integração.

### Como executar os testes e usar a API

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
PYTHONPATH=src python scripts/export_local_openapi.py

# somente terminal local; não publicar em rede externa
export TAPI_LOCAL_DOMAIN_ENABLE=1
export TAPI_LOCAL_DOMAIN_KEY='substituir-por-chave-local-aleatoria-com-pelo-menos-32-caracteres'
export TAPI_LOCAL_DB=.local/domain.sqlite3
uvicorn tapi_gate0.api:app --host 127.0.0.1 --port 8000
```

A interface de documentação estará em `http://127.0.0.1:8000/docs`, apenas quando a API local for explicitamente habilitada. Envie a chave por header `X-TAPI-Local-Key`. O tenant do único principal local é **`local-research`**. Não faça commit do banco, da chave ou de arquivos `.env`.

### Exemplo de criação local

```bash
curl -X POST http://127.0.0.1:8000/v1/creators \
  -H "X-TAPI-Local-Key: $TAPI_LOCAL_DOMAIN_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"local-research","creator_id":"sample-1","origin":"synthetic_local","handle":"exemplo-sintetico"}'
```

Nenhuma dessas operações faz chamadas para Instagram, YouTube, Stone, CRM, provedores de modelos ou serviços pagos.

## Invariantes verificadas

- Identificador de tenant conferido contra o principal autenticado; nunca vem apenas do parâmetro recebido.
- Registros de fontes externas são negados **antes** da persistência; publicar, campanhas, CRM e coleta não são executados.
- SQL parametrizado, FK e unicidade por tenant, mutações em transação, outbox de eventos atômicos e ordenação de cursor.
- Métricas de seguidores preservam data de medição; denominador zero e idade insuficiente produzem contagens de exclusão.
- Fórmula do TAPI `(likes+comments)/followers`; ordenação exata como fração, `ceil(n * 0,1)` para top decil e desempate estável por ID. É uma **regra operacional proposta para empates e arredondamentos**, não foi homologada pela Stone.
- Todo valor de rubrica afirmado precisa de evidência; atributos temporais exigem vídeo com timestamp; alegação de empreendedor real requer prova externa, `null` não vira `false`.
- Rascunhos criativos não podem citar conteúdo que não sustente o insight relacionado.
- Testes EDD cobrem autenticação, isolamento lógico, direitos, falhas, integridade, métricas, temporalidade e linhagem.

## Limites e decisões pendentes

1. **Autorização:** dados reais de Instagram/YouTube/Stone e ações externas permanecem bloqueados. Aprovação de escopo expandido pelo solicitante não é concessão de direitos sobre terceiros.
2. **Identidade:** header de chave forte é **exclusivamente ferramenta de desenvolvimento local**; produção exigirá sistema de autenticação, RBAC/ABAC e isolamento testado para múltiplos tenants.
3. **PostgreSQL:** SQLite é o backend local de referência com custo R$ 0; migração para PostgreSQL não está feita e dependerá de benchmark de custo, durabilidade e operação gratuita.
4. **Rubrica:** `duracao_faixa` e `legenda_tamanho` têm categorias operacionais ainda não homologadas; rótulos sintéticos não medem F1.
5. **Ranking:** dados de uma única fonte, não agregados entre plataformas; análise observacional não prova causalidade; rubricas ainda precisam ser revisadas em pelo menos 50 posts autorizados.
6. **Escopo ainda não operacional:** publicação, campanha, CRM, produção audiovisual, roteamento de modelos, multimodal real, FastMCP, LangGraph, frontend real, estatística avançada, 22/22 capacidades integradas e SLOs. O catálogo explicita esse estado.
7. **Rastreabilidade:** a outbox local é gravada transacionalmente, porém não há broker, política de entrega remota ou SSE em produção.
8. **Orçamento:** nenhuma execução pode gerar cobrança; chamadas a provedores e campanhas pagas não estão habilitadas.

## Procedimento de verificação e repetição

- `python -m pytest -q` executa os testes antigos e os novos.
- `PYTHONPATH=src python scripts/export_local_openapi.py` gera o contrato diretamente da implementação.
- `python scripts/check_gate0.py` e `python scripts/verify_zero_spend.py` preservam as regras do Gate 0.
- `contracts/openapi.local.json` é artefato de inspeção, não documentação homologada de todas as 22 capacidades.

**Não chamar isto de produção:** somente o subconjunto local tipado/persistente, protegido por chave de desenvolvimento, passou nos testes. A aplicação completa permanece em desenvolvimento e terá apenas uma entrega final de produto.
