> **Atualização pós-DEC-016:** material histórico de diligência, sem consentimento registrado. O manifesto canônico para novas fontes é `research_source_candidates_v2_20261103.json`; `mpe-source-frame.v1` é legado. O PR de persistência permanece desativado e não atribui elegibilidade científica automaticamente.

# Primeira fonte MPE — diligência documental (03/11/2026)

**Fonte priorizada para revisão:** `@vaicomeroquee`; setor `food`; estrato `food_unverified`.

## Evidência verificada sem consultar Instagram

- A Agência Sebrae Bahia descreveu a chef **Marianna Braga**, seus serviços de gastronomia para eventos desde 2019 e o uso de `@vaicomeroquee` para promoção de serviços. O texto trata o caso no contexto de pequenos negócios: https://ba.agenciasebrae.com.br/cultura-empreendedora/analise-gratuita-do-instagram-ajuda-chef-de-cozinha-a-conquistar-mais-clientes/
- Reportagem de 29/09/2026 reproduz o vínculo entre chef, atividade de buffets e `@vaicomeroquee`: https://n1n.com.br/negocios-na-bahia/113037/instagram-analise-gratuita-sebrae-impulsiona-vendas-chef/
- Essa evidência suporta **identidade histórica do perfil e atividade comercial aparente**. Ela NÃO comprova CNPJ/porte empresarial formal, titularidade atual, conta profissional Business/Creator, conteúdo ainda disponível, dados de audiência, direitos para armazenamento ou autorização de pesquisa.

**Estado:** `review`, não `approved`. Por isso, o manifesto público mantém `size_band=unverified`, nenhuma referência de permissão e zero publicações. Não foi realizada consulta Graph à conta nem coleta de mídia nessa etapa.

## Gate de aprovação ainda pendente

| Controle | Estado |
|---|---|
| Correspondência histórica do handle com negócio citado no Sebrae | Documento público encontrado |
| Identidade/atividade empresarial atual e enquadramento MPE por documento confiável | **Pendente** |
| Tipo atual Instagram Business/Creator e IG ID verificado pela API | **Pendente** |
| Base de uso e retenção dos dados para pesquisa / autorização por finalidade | **Pendente** |
| Referência de aprovação e prova local SHA-256 de documento | **Pendente** |
| Escopo explícito `corpus_metadata_ingest` além de leitura/exportação | **Pendente** |
| Grant administrativo por IG ID e cadastro de corpus por estrato | **Pendente** |
| 1+ Reel/carrossel ≥14 dias com métricas e seguidores positivos | **Pendente** |

## Procedimento seguro quando a fonte for aprovada

1. Registrar em manifesto **privado v2** os campos `status=approved`, `creator_type=mpe_business`, `business_size_class=micro|small`, `business_size_evidence_reference`, `audience_intent`, `audience_rationale_reference`, `approval_reference`, responsável, datas, hash da prova e os três escopos `business_discovery_metadata_read`, `local_research_metadata_export`, `corpus_metadata_ingest`. A prova privada precisa de revisão humana; hash só verifica integridade, **não** direito jurídico.
2. Validar identidade técnica por Business Discovery em consulta delimitada: `scripts/mpe_corpus_pilot.py` continua em modo diagnóstico, sem escrita no banco. Obter IG ID e testar elegibilidade; se retornar zero, manter a fonte com déficit explícito.
3. Criar grant de origem via API administrativa existente `POST /v1/ingestion/grants`, amarrado ao ID IG e **mesmo** `approval_reference`; cadastrar `POST /v1/corpus/profiles` com o mesmo ID, setor de registro legado, estrato e URL da evidência; registrar também `POST /v1/corpus/source-contexts` com o contexto de criador, porte, setor e audiência-alvo correspondente ao manifesto v2.
4. Em ambiente migrado com Alembic 0006 e, apenas após revisão operacional, fornecer `TAPI_MPE_APPROVED_FRAME_PATH` e `TAPI_MPE_APPROVAL_PROOFS_DIR` apontando para documentos privados fora do Git, confirmar `TAPI_OFFICIAL_METADATA_READS=1` e `TAPI_ZERO_BILLING_CONFIRMED=1`. O novo `TAPI_MPE_PERSISTENCE_ENABLED` é **0 por padrão**; habilitar somente quando contrato/restrições forem satisfeitos.
5. Um admin autenticado pode então executar `POST /v1/ingestion/business-discovery/runs` com JSON:

```json
{
  "username": "vaicomeroquee",
  "expected_ig_id": "ID_NUMERICO_VERIFICADO_PREVIAMENTE",
  "run_key": "mpe-pilot-approved-20261103",
  "limit": 5,
  "max_pages": 2
}
```

O exemplo acima **não deve ser executado** com placeholder; é contrato de entrada, não autorização. Uma nova execução usa outra `run_key`; chave repetida é recusada. A operação não recebe mídia simulada, não segue links externos e não chama `/{third_party_id}/media`: ela consulta o nó Business Discovery do perfil de acesso e checa o ID do alvo antes de gravar.

## Controle de procedência e versão

- A ingestão usa as transações, o índice de conteúdo idempotente, o histórico de snapshots e o outbox existentes. `business_discovery_provenance` (migração Alembic `0006_business_discovery_provenance`, após `0005_scientific_corpus`) registra, **por run e post**: ID da fonte, ID da mídia, ligação ao conteúdo, versão Graph, hash do item, hash do lote, referência e hash da prova de autorização, horário de observação.
- Tokens, documentos de aprovação, payloads brutos e URLs de `paging.next` **não** são gravados no ledger.
- O data card v2 separa posts tecnicamente elegíveis dos cientificamente elegíveis: somente uma revisão humana por post, com evidência observável, referência e hash, pode elevar a contagem científica. O novo ledger dá suporte à auditoria da aquisição; não cria posts automaticamente no data card.
- `observed_current_only` indica seguidores **no momento da leitura**, não na data de cada publicação: evitar ranking histórico exato ou afirmação causal.
- **Limitações para revisão antes de operar em produção:** cada item é persistido na mesma transação que seu registro de procedência e snapshot, com rollback conjunto. Entretanto, o lote inteiro pode ter commits anteriores antes de uma falha posterior, exigindo reconciliação de runs parcialmente concluídos. A paginação aninhada fica limitada ao lote; não há checkpoint persistente de Business Discovery, apenas o da ingestão de primeira parte. Não declarar transação de lote completamente atômica nem censo completo.

## Situação do Plano v5.2

IMP-167: no frame v2 a primeira fonte passou de `candidate` a `review` por evidência pública recente, sem autorização. IMP-168: contrato de snapshot preservado em testes. IMP-170: persistência experimental construída sob flags e gates, **sem prova real de elegibilidade e sem execução com Meta**. Resultado atual permanece **0 perfis aprovados e 0 posts reais**, meta de ≥30 perfis e 2.000–5.000 posts pendente.
