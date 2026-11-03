# IMP-167 — viabilidade de Instagram Business Discovery

**Data da evidência:** 2026-11-03. **Escopo:** preparação e amostragem de perfis profissionais selecionados. **Estado:** acesso ao **perfil** comprovado com Meta real; leitura de **mídia de terceiros** e paginação em campo aninhado ainda não comprovadas na Meta.

## Evidência real confirmada pelo responsável

- Aplicativo Meta **TAPI Stone**, autenticação **Instagram API with Facebook Login**, conta de acesso `academy_fellow_stone` (IG ID `17841459971757521`).
- Meta Graph API Explorer v26.0: permissões `instagram_basic`, `instagram_manage_insights`, `pages_read_engagement`, `pages_show_list` concedidas.
- A consulta de teste `GET /17841459971757521?fields=business_discovery.username(instagram){username,followers_count,media_count}` retornou sucesso e conta profissional `@instagram` com ID `17841400039600391`, quantidade de seguidores e contagem de publicações.
- **Não usar o perfil `@instagram` como parte automática do corpus MPE**: foi apenas uma verificação de permissão e do endpoint. A conta de acesso não retornou mídias próprias em `GET /17841459971757521/media`.

## Matriz de operações

| Operação | Estado | Dependência / garantia |
|---|---|---|
| Perfil da conta autenticada | Comprovado pela Meta real | ID e username confirmados, seguidores próprios=0 |
| `business_discovery.username` — dados básicos | **Comprovado pela Meta real** | `instagram_manage_insights` confirmado no token |
| `business_discovery.username` — mídias e contagens | **Pendente de teste real** | Pré-voo opt-in, formatos Reels/carrosséis, campos que podem faltar |
| Paginação nested `media.limit().after()` | **Testado com mocks, não com Meta real** | Cursor opaco, até 3 páginas, sem seguir URL externa |
| Direitos, retenção e inclusão no corpus científico | **Não autorizados automaticamente** | Revisão de uso por fonte, grant por conta/finalidade, políticas de retenção e acesso |
| Descoberta de 30+ perfis MPE | **Não executada** | Matriz estratificada por faixa/setor, aprovação de perfis e diversidade |
| 2.000–5.000 publicações elegíveis | **Não atingido** | Denominador positivo, 14+ dias, direitos e qualidade suficientes |
| Captura de mídia, arquivos, anúncios ou publicação | **Bloqueada / fora do escopo** | Proibido inferir direitos a partir de metadados públicos |

## Ferramenta de pré-voo (sem persistência)

Arquivos: `src/tapi_gate0/business_discovery.py`, `scripts/business_discovery_preflight.py` e `tests/test_business_discovery_preflight.py`.

A ferramenta exige usuário profissional alvo explicitamente selecionado e referência documental **não secreta** de aprovação de uso. O token permanece exclusivamente em variável de ambiente, a conexão é TLS com `graph.facebook.com` e caminhos fixos, não há scraping, download, gravação nem URL de `paging.next`. Quotas: `limit` entre 1 e 10, `max_pages` entre 1 e 3, por padrão 1 página de 3 mídias, e as flags já existentes de leitura/custo R$0.

```powershell
python scripts/business_discovery_preflight.py --execute --target PERFIL_PROFISSIONAL_APROVADO --approval-reference pesquisa-validada-2026 --limit 3 --max-pages 1
```

**Nota de autorização:** `--approval-reference` registra a declaração operacional para pré-voo e **não substitui** evidências contratuais, legais ou avaliação de conformidade. O programa não grava nem concede grant. Um perfil profissional consultável pela API não é automaticamente apropriado para o corpus.

## Critérios e limitações

O probe contabiliza Reels/carrosséis, outros formatos, IDs duplicados, idade mínima 14 dias, métricas não retornadas, timestamps inválidos e denominadores de seguidores não positivos. **Followers** é uma medição do momento da consulta, não número histórico de seguidores na data de publicação. O valor `reported_media_count` da API não pode ser equiparado a publicações elegíveis.

Ao testar na Meta real, o endpoint com campos aninhados pode rejeitar alguns campos ou a sintaxe de cursor dependendo da versão/API/conta. O projeto usa `graph.facebook.com/v23.0`; o Explorer que confirmou o perfil usou `v26.0`. Até validar a compatibilidade, o conector é **experimental**, não uma rotina homologada para coleta em produção.

## Evidências de teste

- `PYTHONPATH=src python -m pytest -q tests/test_business_discovery_preflight.py` → **8 aprovados** (mock).
- `PYTHONPATH=src python -m pytest -q` → **185 aprovados** em checkout local do ZIP de ingestão, após aplicação das duas migrações históricas já corrigidas na `main`; não é teste de todo o conteúdo atual da `main`.
- `node --test tests/frontend/*.mjs` → **3 aprovados**.
- Gate 0 e invariantes custo zero → **PASS**.
- Arquivos Python novos foram sincronizados ao GitHub com hash de conteúdo idêntico ao checkout testado.

**Próxima decisão:** executar pré-voo real de um alvo profissional selecionado, observar limites de mídia e revisar permissões/direitos antes de implementar qualquer persistência. Não declarar IMP-167 ou IMP-170 concluídas.
