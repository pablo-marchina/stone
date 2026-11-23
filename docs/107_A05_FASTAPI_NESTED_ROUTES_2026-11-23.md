# IMP-027 / A05 / A11 — FastAPI >=0.137 roteamento aninhado (23/11/2026)

## Sintoma confirmado no operador Windows

Git HEAD: 5773030bef0284f593e11941633ee681eebbd2c7.
FastAPI 0.165.0 / Starlette 1.10.0, com as quatro importações do worktree corretas.
O diagnóstico offline retornou app.routes=12 e app.router.routes=22, mas o inventário de rotas HTTP que iterava app.routes produzia agent_posts=[] e studio_posts=[]. Dois testes isolados falharam; A11 executou 404 PASS, 2 FAIL, 0 SKIP, de 406 esperados.

Isto é compatível com uma alteração documentada do FastAPI 0.137.0: include_router preserva objetos de roteadores aninhados, em vez de copiar todos os APIRoutes para o nível superior; iterar app.routes não fornece lista plana. Não inferir que handlers desapareceram — os testes reais de API A05→Studio→SVG passaram. Links upstream:
- https://fastapi.tiangolo.com/release-notes/#01370
- https://github.com/fastapi/fastapi/discussions/15791

## Correção na PR #72

- tests/test_a05_import_compilation_gate.py: conserva conferência de proveniência de módulos; agora verifica o inventário HTTP POST *efetivo* via app.openapi()["paths"], criado pelo FastAPI; além disso chama quatro endpoints via ASGI TestClient sem token e exige 401 (não 404), em SQLite in-memory.
- tests/test_studio_signed_route_guard_a05.py: captura o EXATO APIRouter fornecido ao app.include_router; audita todos os POSTs de documentos por dependência de assinatura no endpoint e/ou contexto do roteador; confere o OpenAPI efetivo; insere no SQLite em memória uma referência assinada sintética como ponteiro (não uma licença), autentica um administrador de teste e exige resposta 403 com o motivo STUDIO_SIGNED_REFERENCE_ACTION_RECHECK_REQUIRED para quatro métodos legados.
- scripts/a05_route_inventory_diagnostic.py: preserva o inventário superficial para diagnóstico e também lista rotas POST efetivas do OpenAPI, sinalizando quando o inventário superficial não é plano.
- tests/test_a05_route_inventory_diagnostic.py: mock e contrato de saída alinhados, mantendo segredo e dados fora da saída.

Nenhuma regra de autenticação, PEP, publicação, gasto externo ou gate foi alterada. A contagem alvo do A11 permanece 406, e a correção aumenta o rigor: além da existência de rotas, prova que o ASGI efetivamente as despacha e que mutações legadas de documentos com referência externa ficam bloqueadas em 403.

## Evidência e pendências

**Implementação publicada; validação Windows do SHA novo PENDENTE.** Não classificar os dois testes como PASS, nem declarar A11 verde até execução pelo operador. Após os dois testes PASS, executar o A11 com SHA exato e novo relatório imutável; se a etapa A05/A07 PASS 406/406, os estágios A06/Node/Chrome restantes também precisam terminar com sucesso no mesmo HEAD. Não reduzir o número de testes nem remover verificações.

DEC-008 continua OPEN em segurança operacional; G0–G6, IMP-131 continuam BLOCKED; zero merge ou deploy.
