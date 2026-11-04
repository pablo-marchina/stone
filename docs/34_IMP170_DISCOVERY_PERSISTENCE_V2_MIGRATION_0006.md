# IMP-170 — Adaptação Business Discovery ao contrato DEC-016 (PR #20)

**Estado:** código experimental, não habilitado para coleta nem persistência real.  
**Branch-base:** `main` após o PR #23; Alembic `0005_scientific_corpus` → `0006_business_discovery_provenance`.

## Motivação e semântica

O TAPI estuda **publicações direcionadas a MPEs**, não somente conteúdo de empresas legalmente MPEs. A aquisição por Business Discovery só obtém metadados oficiais limitados; ela **não** observa conteúdo multimodal e **não** classifica automaticamente um post como `mpe_targeted`.

A rota `POST /v1/ingestion/business-discovery/runs` grava exclusivamente uma **amostra técnica de metadados** para posterior revisão, usando `ResearchSourceEntry` (frame `tapi-source-frame.v2`). Um manifesto legado `mpe-source-frame.v1` é rejeitado nesse caminho. A revisão científica é registrada depois por `POST /v1/corpus/content-reviews`, com evidência observada, referência e SHA-256.

## Gates antes de qualquer leitura da Meta

1. `TAPI_MPE_PERSISTENCE_ENABLED=1` apenas com revisão expressa; configuração padrão permanece **0**.
2. `TAPI_OFFICIAL_METADATA_READS=1` e `TAPI_ZERO_BILLING_CONFIRMED=1`, token mantido fora do repositório.
3. Manifesto **privado** v2 com fonte `approved`, aprovação não expirada, justificativa de audiência da fonte e escopos `business_discovery_metadata_read`, `local_research_metadata_export` e `corpus_metadata_ingest`. Uma hipótese `audience_intent=mpe_targeted` **não** aprova posts individualmente.
4. Prova de aprovação local íntegra (SHA-256), e grant administrativo ativo do IG ID com o mesmo `approval_reference`.
5. Perfil previamente registrado no corpus com estrato e referência correspondentes. Em `corpus_profiles.sector` (campo legado), `finance` e `cross_sector` do v2 usam `other`; o setor científico integral é preservado em `corpus_source_research_contexts`.
6. Contexto científico registrado por `POST /v1/corpus/source-contexts`, com `creator_type`, `business_size_class`, `sector_context`, `audience_intent` e justificativa exatamente compatíveis com o manifesto aprovado.
7. Migrações `0005_scientific_corpus` e `0006_business_discovery_provenance` previamente aplicadas.

**Não habilitar em dados reais antes da revisão de autorização, termos Meta, LGPD, retenção e recuperação de lotes parcialmente concluídos.** Hash documental não é uma base jurídica automática.

## Procedimento técnico em ambiente aprovado

Depois da verificação prévia do ID do Instagram da fonte e de criar grant, cadastro, contexto e manifesto privado com aprovação:

```http
POST /v1/ingestion/business-discovery/runs
Authorization: Bearer <TOKEN_DO_ADMIN>
Content-Type: application/json
```

```json
{
  "username": "PERFIL_APROVADO",
  "expected_ig_id": "ID_IG_VALIDADO",
  "run_key": "coleta-piloto-v2-exemplo-001",
  "limit": 5,
  "max_pages": 2
}
```

Isto é um **exemplo de contrato**, não um comando pronto para operar nem permissão de acesso. A consulta lê `business_discovery.username(...)` a partir do viewer profissional, valida ID e nome do alvo e usa cursor aninhado com limites curtos. Uma `run_key` já usada não é reaproveitada.

## Saída e trilha de evidência

A resposta `DISCOVERY_TECHNICAL_METADATA_COMMITTED` indica apenas registros técnicos, com `scientifically_eligible_posts_created=0` e `scientific_review_required=true`. Cada post técnico tem content ID estável, snapshots de métricas não sobrescritos e uma linha de procedência com hash do item, hash da leitura, referência/hash do documento de autorização e instantes de aquisição. **Uma linha não implica que a publicação foi rubricada, validada cientificamente ou liberada para redistribuição.**

A migração `0006_business_discovery_provenance` depende de `0005_scientific_corpus`. A gravação de um item e sua procedência é atômica por item, mas o **lote completo ainda pode sofrer falha parcial** e não possui checkpoint durável para cursor Business Discovery. Não considerar uma execução falha como lote completo. O histórico de YouTube, a ingestão de primeira parte e a métrica oficial de ER não são modificados.

## Cobertura exigida para revisão

- Fonte v1 bloqueada; fonte v2 não autorizada, sem scope de escrita, grant, cadastro ou contexto bloqueada antes da rede.
- Produto em status `OFF` por padrão; `@instagram` continua excluído do corpus.
- Fonte v2 do tipo fintech com `sector_context=finance` e `business_size_class=not_applicable` permitida mediante seus próprios grants.
- Primeira leitura cria registro técnico e ledger; releitura inalterada não duplica; mudança de métricas cria snapshot; falha no ledger reverte o item.
- Após leitura, data card v2 mostra `technically_eligible_instagram_posts > 0` e `scientifically_eligible_instagram_posts = 0`; revisão humana mock separada pode elevar a segunda contagem.
- Migração 0006 deve subir, descer até 0005 e reaplicar sem remover o contexto científico.

**Situação de dados externos:** nenhum perfil aprovado e nenhum post científico real no banco. Todos os testes do PR são offline, com dados fictícios.