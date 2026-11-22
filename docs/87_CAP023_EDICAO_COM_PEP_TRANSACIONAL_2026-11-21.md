# CAP-023 / A05 — Edição de rascunhos com direitos revalidados na transação

> Overlay técnico, **não** substitui a Base Atemporal v6.1, o Plano Único, as 23 CAP, os 204 IMP, as 543 dependências, os CTs ou G0–G6/IMP-131. Nenhuma licença real é conferida pelo código, e esta PR não autoriza produção.

## Lacuna fechada

A PR #51 registrava o vínculo entre documento e grant criativo e oferecia uma operação manual de rechecagem. Ela ainda não aplicava o resultado **no instante da edição**. Assim, um grant poderia estar revogado depois da rechecagem, e uma rota antiga continuaria editando o documento sem verificar a revogação no mesmo commit.

O incremento introduz:

1. `StudioStore.patch_text_layer(..., connection=..., reference_authorizer=...)`: recebe uma transação de banco gerenciada pelo servidor; se o documento estiver vinculado a grants externos, exige um callback confiável **dentro da transação de escrita**. A operação sem callback falha com `STUDIO_SIGNED_REFERENCE_RECHECK_REQUIRED`. Documentos sintéticos continuam usando a API de edição legada.
2. `recheck_document_references(..., connection=...)`: reutiliza a conexão aberta, bloqueia a linha da versão corrente em bancos com `SELECT FOR UPDATE`, valida evidências, bindings, grants e revogação e audita o resultado **na mesma transação**. Não produz certificado persistente de direitos futuros.
3. `POST /v1/agent/creative-drafts/{document_id}/text-patches`: endpoint autenticado admin/editor que exige `If-Match` e `expected_version`. Revalida todas as referências no instante da ação, executa a edição CAS e insere a nova versão sob a mesma transação. Qualquer erro na validação, ETag, versão ou camada aciona rollback, inclusive da auditoria de rechecagem.
4. `router_for_studio`: todos os métodos POST legados com `document_id` deixam de modificar documentos com grants externos vinculados. Essas operações não possuem ligação transacional com o PEP; retornam `STUDIO_SIGNED_REFERENCE_ACTION_RECHECK_REQUIRED` (403). Leituras e edições de documentos sem bindings permanecem disponíveis, nos limites preexistentes.

Este desenho não presume que uma rechecagem positiva anterior autorize uma nova ação. O novo endpoint comprova, quando homologado, **apenas a elegibilidade para uma edição interna de texto naquela transação**. Não altera `rights_status=pending_review`, `approval_status=draft`, `publication_allowed=false` e não permite mídia externa, aprovação editorial ou publicação.

## Exemplo de requisição (sem grant ou identidade fictícios)

```text
POST /v1/agent/creative-drafts/<document_id>/text-patches
Authorization: Bearer <sessao-valida-do-servidor>
If-Match: <etag-atual-do-documento>

{"expected_version":1,"page_id":"page.1","layer_id":"headline","text":"Texto editado"}
```

A requisição usa os grants vinculados à própria versão do documento e a âncora confiável do host, nunca chaves ou grants fornecidos pelo operador. O endpoint não recebe parâmetros para contornar a validação PEP.

## Escopo e limites

- As operações legadas de geometria, páginas, restauração e edição via `/v1/studio/documents/{id}` estão **bloqueadas** para documentos com referências assinadas enquanto não integrarem rechecagem na própria transação. A proteção é no roteador HTTP e na edição de texto do `StudioStore`. Chamadas internas fora dessas rotas ainda devem adotar a mesma fronteira; a auditoria de todos os caminhos internos não foi concluída.
- Renderização e exportação possuem contratos próprios de assets e direitos, **não** recebem aprovação implícita via referência criativa. É necessário provar revalidação por ativo e operação no instante de uso.
- Concorrência real com revogação, locks PostgreSQL, migrações 0017/0018 no banco de staging e restauração de backup continuam pendentes.
- O PEP em produção permanece desativado por padrão e depende de âncoras independentes verdadeiras e grants efetivos por operação. Os testes criam somente licenças fictícias locais.

## Testes e estado de evidência

- **9 novos casos** em `tests/test_creative_reference_pep_a05.py` e `tests/test_agent_atomic_draft_a05.py`: edição assinada positiva, rollback após revogação, bloqueio da rota antiga de texto e páginas, ETag obrigatória e inválida, PEP host ausente, rollback de auditoria após erro de camada e compatibilidade sintética e registro da tabela de vínculos no `StudioStore` independente.
- O pacote A11 Python A05/A07 passou de 240 para **249 casos esperados**. **249 NÃO É resultado de execução.** O check de hashes inclui agora `studio_e1.py`, `studio_api.py` e os novos limites do agente.
- Foi executado **um ensaio isolado de 3 casos FastAPI** demonstrando que dependências adicionadas ao `APIRouter` antes dos decorators bloqueiam mutações com `document_id` e preservam GETs e documentos sintéticos. Não é prova E2E da aplicação.
- No checkout integral do HEAD atual, a nova suíte focal, A11 e A00 ainda estão **NOT_RUN**. Não usar testes de commits anteriores como PASS para este SHA.

Validar no HEAD exato em checkout íntegro e ambiente privado:

```powershell
git rev-parse HEAD
python -m pytest -q -rs tests/test_creative_reference_pep_a05.py tests/test_agent_atomic_draft_a05.py tests/test_studio_e1.py tests/test_a11_focal_evidence_packet.py
python scripts/verify_zero_spend.py
python docs/base_atemporal/ferramentas/validar_espelho.py
```

Depois executar A11 focal 249, A00 full no **mesmo SHA** e testes nativos PostgreSQL/Windows sem relaxar direitos, skips, ASR Strict ou G0–G6. Sem merge, migrations reais, deploy ou gasto nesta PR.
