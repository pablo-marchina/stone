# Próximas ações do Plano Único — sem entregas separadas

| Ordem por dependência | Ação verificável | Pré-condição | Evidência/saída | Bloqueio |
|---|---|---|---|---|
| 1 | Congelar versão dos documentos-base e identificadores U/CAP/DEC | Nenhuma | `reference/SOURCE_SHA256.json`, `config/traceability.json` | Não |
| 2 | Validar schema da rubrica e resolver ambiguidades com Stone | Manual + decisão formal | JSON Schema/Pydantic, testes negativos | Aprovação semântica externa |
| 3 | Produzir contratos completos, não apenas registries | Protocolo de erros e identidade | OpenAPI, testes CT-01–CT-18 | Parcial |
| 4 | Executar benchmark DEC-010 respeitando teto de R$ 0 | Capacidade/custo do projeto | ADR com evidências | Infraestrutura pendente; teto R$ 0 já aprovado |
| 5 | Criar remote repo novo privado se autorizado e conectar CI | Org/nome/visibilidade | URL repo, pipeline CI verde | Decisão titular pendente |
| 6 | Implementar identidade, authz e source grant verificado | Dono e IAM | Tests positivos/negativos e logs | Decisão externa pendente |
| 7 | Criar esquema relacional/transações/outbox + fixtures sintéticas | Contratos e auth | Migrations/testes de recuperação | Não, local |
| 8 | Coletar posts reais via conector autorizado e construir gold | Grants validados | Dataset card, amostras/insights reais | Gate 0B |
| 9 | Seguir demais tarefas do Plano Único até 22/22 capacidades | Dados, evals e aprovações por ação | Release manifest, ISO, evals | Gates de release |

## Limite

Você pediu **uma única entrega final de produto**. Esta lista é ordem técnica e de liberação de risco, não divide o produto em entregas. Gate0A não libera Gate0B nem substitui aceite integral.


## Ação pendente de criação do GitHub

Repositório GitHub já criado e autorizado: https://github.com/pablo-marchina/stone. Publicar o scaffold via conector sem incluir mídias/dados/segredos não autorizados; ver `docs/15_REPOSITORIO_GITHUB.md`.

## Custos

Teto máximo R$ 0. Instalar/usar somente softwares gratuitos no ambiente disponível. Ações financeiras reais (como anúncios pagos) não podem acontecer com esse orçamento.
