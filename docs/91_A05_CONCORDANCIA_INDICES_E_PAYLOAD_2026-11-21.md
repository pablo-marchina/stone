# A05 — concordância SQL↔payload no PEP de referências criativas

> Incremento corretivo da Base Atemporal v6.1, sem substituir qualquer CAP, IMP, requisito, decisão ou gate normativo. Nenhuma concessão de direitos e nenhuma homologação de produção.

## Falha de integridade fechada

O PEP independente `CreativeReferencePEP.require_for_atomic_draft` se apoia na função `_source_bound` do registro assinado A05.4 para verificar se uma referência externa está ligada à ingestão e ao conteúdo correto. A implementação anterior conferia a assinatura e o SHA-256 do payload do conteúdo, mas podia deixar passar **divergências em colunas SQL indexadas** que não pertencem ao payload assinado:

1. A coluna `content_items.published_at` podia divergir de `ContentItem.published_at` sem alterar o hash do conteúdo assinado.
2. A coluna `content_items.creator_id` podia passar a apontar para outra linha válida de criador cujo payload JSON ainda declarasse o identificador original. O join do banco seguiria o novo índice, mas a comparação prévia apenas entre os dois payloads serializados continuaria satisfeita.

Ambas as situações têm implicações para rastreabilidade e isolamento de evidência, mesmo que a assinatura Ed25519 do conteúdo original permaneça correta. **Não são provas de exploração real**: são cenários de corrupção/adulteração do banco construídos para garantir comportamento fail-closed.

## Correção

`src/tapi_gate0/creative_reference_registry_a05.py` passa a selecionar as identidades SQL indexadas de criador e data, e a exigir:

- `content.creator_id == content_items.creator_id`;
- `creator.creator_id == creators.id`;
- data de publicação indexada com timezone explícito, idêntica ao timestamp do payload;
- publicação e criação do criador não futuras em relação ao instante da verificação;
- todas as verificações existentes de origem/tenant/conta/SHA, grants técnicos, assinatura, revogação e expiração permanecem intactas.

O retorno negativo continua bloqueando tanto o diagnóstico A05.4 quanto o PEP efetivo, sem promover concessões genéricas.

## Testes e prova

- **4 novos testes** com fixtures de direitos e fontes estritamente fictícios: alteração da data SQL e do criador SQL indexado, verificadas tanto no diagnóstico de registro quanto no PEP independente. Os dois casos do PEP também exigem ausência de evento de autorização de sucesso.
- O teste de criador insere uma linha extra com FK válida e payload do criador original. Assim, a hipótese de discordância SQL↔payload é reproduzível **sem desligar foreign keys**.
- Inspeção estática dos **25 arquivos** do grupo A05/A07 na PR anterior: 199 funções de teste e 66 casos adicionais por parametrização, total esperado 265. Com os 4 testes novos, o A11 agora espera **269 casos**. Esta contagem estática **não é** um resultado pytest.
- **Regressão integral, testes E2E A05/Studio e A11 focal 269 no SHA exato: NOT_RUN**. Nenhuma autorização de produção é inferida. Antes de promover PR: executar o pytest completo, confirmar zeros skips/falhas e revisar os logs sanitizados.

## Verificação necessária

```powershell
git rev-parse HEAD
python -m scripts.a05_python_source_preflight
python -m pytest -q -rs tests/test_creative_reference_registry_a05.py tests/test_creative_reference_pep_a05.py tests/test_a11_focal_evidence_packet.py
python scripts/verify_zero_spend.py
python docs/base_atemporal/ferramentas/validar_espelho.py
```

Depois executar A11 focal e A00 completo **no mesmo SHA**, testes de integridade/concorrência PostgreSQL, A02 Strict, corpus/gold, agentes e CT-STUDIO antes dos gates G0–G6 / IMP-131. Nenhum merge, deploy ou migração operacional foi realizado neste incremento. R$0 é hard stop; DEC-018 permanece vigente.
