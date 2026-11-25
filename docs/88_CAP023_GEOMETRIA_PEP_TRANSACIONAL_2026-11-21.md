# CAP-023 — edição geométrica com PEP por operação

> Incremento de código da Base Atemporal v6.1, empilhado sobre PR #52. Não é substituto dos critérios CAP, CT ou do Plano Único, e não aprova G0–G6/IMP-131.

## O que foi integrado

- `StudioCanvasStore._change` agora recebe opcionalmente uma conexão/transaction gerenciada pelo servidor e um callback de autorização. Quando um documento tem `studio_reference_bindings` externos, a mutação no kernel **exige** o callback na mesma transação. Sem callback, falha fechada com `STUDIO_SIGNED_REFERENCE_RECHECK_REQUIRED`. A regra abrange **canvas e páginas** que usam `_change`, inclusive chamadas internas fora do HTTP.
- `StudioCanvasStore.move` propaga os parâmetros confiáveis de transação e autorização para a implementação comum, mantendo as APIs existentes disponíveis para documentos sem grants externos.
- Novo `POST /v1/agent/creative-drafts/{document_id}/geometry` (admin/editor, bearer do tenant, `If-Match`, CAS de versão), que faz `recheck_document_references` e a alteração geométrica **na mesma transação**. Fonte/grant revogados ou evidência inválida abortam atualização e auditoria.
- As rotas legadas de `/v1/studio/documents/{id}/...` continuam bloqueadas para documentos com grants externos; a proteção está registrada **antes** das declarações `@router`. O teste `test_studio_signed_route_guard_a05.py` verifica o grafo de dependências real do FastAPI, detectando se o registro for deslocado para depois das rotas.
- Resposta continua com `rights_status=pending_review`, `approval_status=draft`; a edição não permite publicação, geração de mídia, exportação autorizada ou alteração de escopo do grant.

## Testes adicionados

- 5 cenários de grants assinados fictícios: geometria positiva/versão/ETag, revogação, ETag ausente ou inválido, rollback de auditoria se a camada estiver ausente e chamada direta ao `StudioCanvasStore` sem PEP.
- 1 teste do caminho sintético local, sem autoridade externa.
- 1 teste adicional que examina as dependências efetivamente anexadas aos endpoints legados no FastAPI.
- **A11 focal esperado:** 256 casos do grupo A05/A07. É uma expectativa de coleta, **não** 256 PASS.

### Evidência executada

Foi validada localmente a semântica do FastAPI em um aplicativo mínimo que registra a guarda **antes** de dois endpoints POST e um GET: POST de documento assinado bloqueado, POST de página assinada bloqueado, POST sintético permitido e GET de documento assinado permitido. Também foi reproduzido que anexar o `Depends` depois da criação das rotas não as protege, mas **o Stone já o registra antes**, portanto não foi demonstrado bypass na PR #52.

**Checkout completo do commit, suíte de integração, A11 focal, A00 full e PostgreSQL: NOT_RUN**. A execução direta de `git clone` do repositório privado falhou por falta de resolução DNS do host neste ambiente; isso não representa falha dos testes do Stone. Não há comprovante CI do GitHub nesta branch. Nenhuma migração operacional ou deploy executado.

### Comandos de validação no HEAD exato

```powershell
git rev-parse HEAD
python -m pytest -q -rs tests/test_creative_reference_pep_a05.py tests/test_agent_atomic_draft_a05.py tests/test_studio_signed_route_guard_a05.py tests/test_studio_e1.py tests/test_studio_e4.py tests/test_a11_focal_evidence_packet.py
python scripts/verify_zero_spend.py
python docs/base_atemporal/ferramentas/validar_espelho.py
```

Avançar para A11 focal e A00 full **apenas no mesmo SHA**, depois testes PostgreSQL de locks/revogação e prova de rights reais por operação. Faltam autorização por ação para imagens, páginas, restore, export, render e publicação, mais A02 Strict, corpus científico, agentes e avaliações. A arquitetura integral e os gates seguem bloqueados. R$0 e DEC-018 permanecem invariantes.
