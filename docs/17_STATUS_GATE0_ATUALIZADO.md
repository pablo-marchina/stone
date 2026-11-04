# Estado do Gate 0 após identificação do remoto

| Item | Estado |
|---|---|
| Escopo expandido | Aprovado pelo usuário; homologação institucional pendente |
| Desembolso aprovado | **R$ 0**, bloqueio absoluto |
| GitHub remoto | `pablo-marchina/stone`, **privado**, escrita confirmada via conector |
| Hospedagem de produção | Não selecionada; infraestrutura paga não permitida |
| Dados e mídias | Permissões pendentes; operações externas negadas por padrão |
| Gate 0A | **Parcial:** base técnica pronta, decisões de identidade, contratos e infraestrutura ainda abertas |
| Gate 0B | **Bloqueado** por permissões externas |
| Release final | **Não comprovado**; arquitetura completa não implementada |

Não confundir o commit do bootstrap com a entrega integral do TAPI Stone.


## Atualização institucional confirmada — 04/11/2026 (DEC-018)

O responsável confirmou que **todas as expansões, fontes, operações, dados Stone, termos e direitos necessários — inclusive uso de terceiros — foram formalmente autorizados pela instituição**. APIs/IDs e credenciais estarão disponíveis quando solicitados. **Não haverá revisores humanos nem validação científica independente**. O restante da tabela acima é histórico do bootstrap inicial, anterior a esta decisão.

| Critério Gate 0B | Nova leitura |
|---|---|
| G0B-01: autorização institucional e operações externas | **RESOLVIDO institucionalmente** |
| G0B-02: fontes × operações | **RESOLVIDO quanto à aprovação formal**; provisão de IDs/escopos/grants técnicos ainda pendente |
| G0B-03: termos, retenção e direitos multimodais | **RESOLVIDO quanto à aprovação institucional formal comunicada**; aplicação técnica das condições pertinentes ainda pendente |

**Gate 0B técnico não foi liberado automaticamente.** `config/source_permissions.json` conserva 72 registros PENDING, `src/tapi_gate0/policy.py` continua deny-by-default e nenhuma operação real passa sem identidade, credencial, permissão efetiva, grant vinculado, limite de custos e teste. Essa pendência é **técnica/operacional**, não falta de nova aprovação institucional. Não solicitar novamente um acordo genérico ou deliberação sobre fontes/termos para avançar.

O requisito histórico de 50 revisões humanas deve ser **dispensado/substituído no aceite formal**; os testes sintéticos não são validação científica. Custos continuam R$ 0. Ver [DEC-018](41_DEC018_DECISOES_INSTITUCIONAIS_E_ACEITE_OPERACIONAL_2026-11-04.md).
