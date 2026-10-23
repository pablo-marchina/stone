# Critérios para sair do Gate 0

| Item | Evidência que libera | Estado |
|---|---|---|
| Repositório remoto | Nome, titular e visibilidade definidos; GitHub privado ainda não criado; CI local em vez de workflow faturável | PENDENTE_REMOTO |
| Infraestrutura | Teto R$ 0 definido; benchmark de alternativas sem cobrança e trade-offs a executar | ORCAMENTO_OK_INFRA_ABERTA |
| Contratos funcionais | Schemas definitivos request/response/error, Python/REST/MCP, testes negativos | PENDENTE |
| Auth e isolamento | Identidade/roles, política de tenant e mecanismos de verificação | PENDENTE |
| Avaliação | Baseline local executado; plano gold e holdout pré-registrado | PARCIAL |
| Fontes | Matriz de permissões e direitos validada por responsável legítimo | PENDENTE |
| Aprovação ampliação | Escopo expandido aprovado pelo solicitante; autoridade institucional sem comprovação | PARCIAL |
| Operação externa | Aprovação por ação/conta, permissões OAuth, salvaguardas e auditoria | BLOQUEADA |

**Gate0A não exige que Gate0B seja liberado** para começar engenharia local com dados sintéticos. Gate0B será verificado para cada fonte e operação, sem autorizar implicitamente as demais. Nenhum dos dois representa aceite do release final de 22 capacidades.
