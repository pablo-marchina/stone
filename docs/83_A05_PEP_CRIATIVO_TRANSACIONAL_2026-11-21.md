# A05 → CAP-023 — PEP criativo transacional (incremento técnico)

> **Overlay operacional** da Base Atemporal v6.1, não substitui o Plano Único, as 204 IMP, 23 CAP, 543 dependências, 7 gates e o aceite único IMP-131. Referências: A05, CAP-005, CAP-006, CAP-023; DEC-018. Não aprova direitos de terceiros, avaliação científica, publicação nem produção.

## Mudança funcional

O fluxo `POST /v1/agent/creative-drafts` cria `CreativeSpec` e a primeira versão do `DesignDocument` em uma transação. A URL do serviço só está disponível em modo autenticado; o tenant/actor vêm da sessão revogável. A criação de documentos só é permitida a `admin` e `editor`.

Antes desta implementação, a rota aceitava apenas referências sintéticas locais sem URL externa. Esse comportamento **continua sendo o padrão**. O handoff B2 comum continua restrito a `synthetic_local` com `is_synthetic=True` e sem URL. A rota atômica pode receber, *opcionalmente*, um dicionário `reference_grant_ids` mapeando `content_id` para `grant_id` somente quando um host confiável tiver injetado `CreativeReferencePEP` no servidor.

A presença de IDs de grants na requisição **nunca cria** permissão. A autoridade, sua chave pública e o revision/digest do head de revogação são confiados **exclusivamente ao servidor**, nunca ao cliente. `create_secure_app` oferece a opção `creative_reference_authorities` para um host gerenciado independentemente; `from_environment` não a habilita nem a configura automaticamente.

## Checagens por transação

- Revalida sessão, tenant, ator e papel na mesma conexão SQL; bloqueia sessão e associação em bancos com locks de linha.
- Exige fonte de metadados exata, registro de conteúdo real, digest assinado da representação persistida, grants técnicos de metadados vigentes e registro criativo próprio.
- Verifica assinatura Ed25519 de grant e revocation head pinado a âncora independente, expiração, escopo por origem/tenant/conta/conteúdo, identidade e digest.
- Exige **ambas** as operações `creative_spec_reference` e `studio_draft_reference`. Grant que cobre apenas uma operação é negado.
- Faz locks de autoridade, fonte e conteúdo compatíveis com PostgreSQL para evitar uso concurrente enquanto há revogação, verifica o grant dentro da transação e grava evento de autorização com outbox.
- Se qualquer referência falhar, toda a operação é revertida: nenhuma versão parcial e nenhum recibo de sucesso permanece.
- O documento resultante continua `rights_status=pending_review`, `reference_status=unverified` e `approval_status=draft`. Não há acesso à mídia, geração automática de conteúdo externo, aprovação editorial, exportação publicável ou publicação.

O PEP reutiliza o registro A05.4 como **dados assinados e revogáveis**, mas **não** reutiliza seu retorno `CONTRACT_VERIFIED_DIAGNOSTIC_ONLY` como permissão. Verifica as condições novamente no limite do uso efetivo.

## Persistência e trust

A migração `0017_creative_reference_pep` acrescenta somente três tabelas inicialmente vazias `a054_reference_authorities`, `a054_reference_revocations` e `a054_reference_grants`, com integridade referencial. `downgrade` nega exclusão quando há algum registro de autoridade, grant ou revogação. **Nenhuma migração foi aplicada em banco operacional.**

O procedimento para ambiente real **não está concluído**: precisa de provisionamento externo de chaves públicas e âncoras auditadas, aprovação de grants por operação, rotação/atualização independente de revogação, restauração/backup e teste real de competição de transações em PostgreSQL. Não inventar chaves, assinaturas ou aprovações para passar a verificação.

## Evidências e limitações

- 13 novos cenários no teste `test_creative_reference_pep_a05.py`, 2 em `test_agent_b2.py` e 2 em `test_creative_reference_pep_migration_a05.py`. Nos testes, as chaves, aprovações e fontes são **totalmente fictícias**. **Status no checkout integral do último SHA: NOT_RUN.**
- Reprodução isolada de `0017_creative_reference_pep` no mesmo conteúdo do GitHub, usando Alembic `Operations` em SQLite temporário: upgrade vazio, downgrade vazio e bloqueio de downgrade não vazio **PASS**. Não equivale a ensaio da cadeia Alembic completa, nem a migração em produção.
- Pacote focal A11 tem **207** casos Python A05/A07 **esperados**, não 207 PASS. Executar no HEAD exato, sem relaxar skips.
- O espelho documental Base Atemporal v6.1 foi novamente verificado como íntegro e acíclico (sink IMP-131). Isso é verificação documental, não aceite de capacidades.

## Bloqueios de release

Todas as liberações G0–G6 e IMP-131 continuam **BLOCKED**. O PEP assinado é um elo técnico da arquitetura; não prova licenças reais, elegibilidade do corpus C1, qualidade científica/gold, orquestração dos agentes, render final ou operação contínua. A02 Strict e as avaliações multimodais continuam pendentes. Sem merge, produção, mídia de terceiro ou gasto financeiro; R$0 permanece obrigatório. DEC-018 vigora sem pedir aprovação institucional genérica novamente.

### Testes necessários no checkout completo

```powershell
git rev-parse HEAD
python -m pytest -q -rs tests/test_creative_reference_pep_a05.py tests/test_creative_reference_registry_a05.py tests/test_creative_reference_pep_migration_a05.py tests/test_agent_atomic_draft_a05.py tests/test_agent_b2.py tests/test_a11_focal_evidence_packet.py
python scripts/verify_zero_spend.py
python docs/base_atemporal/ferramentas/validar_espelho.py
```

Após PASS focal, validar A11 focal e A00 full no mesmo SHA, sem herdar PASS de SHAs anteriores. O rollout exige validação de backup/restore/migração e testes de locks no PostgreSQL operacional **antes**, com controles de direitos efetivos e sem provisionamento de gasto.
