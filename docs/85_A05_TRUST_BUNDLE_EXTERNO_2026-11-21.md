# A05 / CAP-023 — bootstrap de âncoras públicas independentes

> Incremento operacional da Base Atemporal v6.1. Este documento **não** concede direitos, licenças, acesso a provedores, homologação científica nem liberação de G0–G6 / IMP-131.

## Comportamento

O `from_environment()` agora pode fornecer uma coleção de `TrustedReferenceAuthority` ao `CreativeReferencePEP` usando um **arquivo JSON público, imutavelmente pinado por SHA-256** e armazenado fora do checkout. Nenhuma configuração implica **default deny** para referências externas. Configuração parcial ou inválida provoca erro genérico de inicialização, não fallback permissivo.

É obrigatório que o host gerenciado independentemente provisione **todos** estes parâmetros (não preencher com dados fictícios para uso real):

```text
TAPI_CREATIVE_REFERENCE_PEP_ENABLE=1
TAPI_CREATIVE_REFERENCE_TRUST_FILE=/caminho-absoluto-fora-do-repo/public-trust.json
TAPI_CREATIVE_REFERENCE_TRUST_SHA256=<sha256-exato-dos-bytes-do-arquivo>
```

O caminho acima é **ilustrativo**, não um arquivo existente. O arquivo é só de leitura, máximo 64 KiB, sem links simbólicos finais, e não pode estar dentro do repositório. Em sistemas POSIX, deve pertencer ao usuário do serviço, sem permissões de grupo/outros. Em Windows, ACLs são responsabilidade do host; o digest pinado continua obrigatório. O carregador rejeita JSON com chaves duplicadas, escopos repetidos, campos inesperados, plataformas fora de Instagram/YouTube, chaves públicas inválidas e revisions ou digests malformados.

Contrato do documento (campos com valores **sintáticos ilustrativos**, não utilizar como autoridade):

```json
{
  "schema_version": "tapi-creative-reference-trust-bundle.v1",
  "authorities": [
    {
      "tenant_id": "TENANT_ID_VERIFICADO",
      "platform": "instagram",
      "issuer_id": "ISSUER_ID_INDEPENDENTE",
      "public_key_b64": "BASE64_DA_CHAVE_PUBLICA_ED25519",
      "min_revocation_revision": 1,
      "revocation_claims_sha256": "SHA256_DE_64_HEXADECIMAIS"
    }
  ]
}
```

Os valores acima são marcadores **incompletos** para demonstrar a estrutura; o carregador os rejeitará até receber valores reais e válidos. **Não** armazenar chaves privadas no JSON ou no Git. A aprovação institucional DEC-018 permanece vigente, sem necessidade de reaprovação genérica; a autorização independente de fonte/ação e os requisitos técnicos do provedor continuam necessários.

## Limites de segurança

- A presença do trust bundle apenas permite ao servidor **verificar** grants assinados já registrados. Nenhum grant é criado, assinado, renovado ou aprovado pelo bootstrap.
- O PEP também verifica fonte, tenant, conteúdo, digest, sessão revogável, roles, grant técnico, `creative_spec_reference`, `studio_draft_reference` e estado de revogação com pin independente **dentro da transação**.
- O documento gerado é sempre um **rascunho**, não aprovado para exportação ou publicação em produção.
- Provisionamento de autoridade real, grants reais, rotação do head de revogações, backup/restore, migração 0017 e lock de PostgreSQL precisam de ensaio e revisão operacionais separados.
- A aplicação mantém custo financeiro absoluto R$0 e não dispara acesso externo nem publicação.

## Evidência e próximos gates

`tests/test_creative_reference_trust_a05.py`: 16 cenários de política de arquivo **PASS em teste isolado de componente no ambiente desta implementação**, com stub de dataclass de autoridade. O código do carregador foi comparado caractere a caractere por comprimento/checksum ao publicado na branch. O teste isolado **não** prova as importações completas da aplicação.

`tests/test_creative_reference_trust_startup_a05.py`: dois testes adicionais verificam o encaminhamento na inicialização, mas **ainda NOT_RUN no checkout completo**. A11 focal espera agora 225 casos do grupo A05/A07; número esperado não significa testes aprovados. Testar `verify_zero_spend.py`, espelho da Base v6.1, A11 focal e A00 full no **mesmo commit** antes de integrar qualquer PR.

**Estado:** código em PR draft; 0/7 gates liberados, IMP-131 bloqueado, nenhuma migração operacional ou deploy. Próximo trabalho: execução E2E no checkout nativo, provisionamento independente, revogação operacional e integração integral com o ciclo de vida do Studio.
