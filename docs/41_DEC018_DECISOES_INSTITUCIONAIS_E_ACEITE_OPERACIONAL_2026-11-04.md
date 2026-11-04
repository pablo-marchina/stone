# DEC-018 — Atualização de premissas institucionais e aceite (04/11/2026)

**Procedência:** decisões comunicadas pelo responsável do TAPI Stone nesta conversa. Este registro documenta a declaração institucional, mas **não é** cópia de contrato, prova de abrangência jurídica, acesso técnico já testado nem desbloqueio automático de grants. Gate 0B técnico e controles operacionais preservados.

## Decisões informadas

| Assunto | Nova premissa | Consequência |
|---|---|---|
| Escopo | Todas as expansões condicionais foram institucionalmente liberadas. | As 23 capacidades do v5.2 continuam no escopo de desenvolvimento integral; não repetir pedido genérico de aprovação do escopo. |
| APIs e IDs | Acesso institucionalmente liberado; recursos serão fornecidos quando requisitados. | Pedir insumos específicos apenas na integração relevante, com armazenamento local seguro. Não presumir que uma API já foi autenticada ou testada. |
| Fontes e operações | Todas institucionalmente liberadas para uso, segundo o responsável. | A autorização geral declarada deixa de ser pendência de decisão institucional; grants técnicos e identificadores por fonte/ação ainda precisam ser materializados. |
| Uso de terceiros | Foi informado acordo institucional de uso de conteúdo de terceiros com escopo descrito como irrestrito. | Registrar essa declaração; o texto, a abrangência, direitos efetivamente abrangidos e obrigações legais/de plataforma precisam ser conferidos na operação concreta. Acordo institucional não equivale automaticamente a dispensar restrições de terceiros não signatários. |
| Dados Stone | Foi informado acesso e uso liberados institucionalmente. | Projetar integrações com dados internos; extrações, mapeamento, privacidade e testes continuam pendentes. |
| Revisores humanos | Não serão disponibilizados. | Não condicionar o avanço de engenharia à existência de revisores humanos. |
| Ciência | Não haverá validação científica independente. | Não prometer revisão científica independente, gold humano, estimativa científica de precisão/FPR ou promoção com base nesses artefatos. |
| Financeiro | Restrição existente R$ 0, sem revisão informada. | Continuam proibidos desembolsos, serviços faturáveis e campanhas pagas reais. |

## Colisão com o plano original

O Plano Único v5.2 mantém como critério de negócio do núcleo: rubrica de 20 atributos, JSON e evidências por publicação, abstenções e revisão humana de pelo menos 50 publicações.

A indisponibilidade de pessoas e a decisão de não realizar validação independente exigem **mudança formal do critério de aceite**, não permitem marcá-lo como realizado nem reescrever retroativamente o case original. Proposta de substituição institucional de processo:

- Preservar os 20 atributos, modalidade/locator/hash observáveis, outputs estruturados, rastreabilidade, cobertura e abstenção, testes unitários, regressão, integração, adversariais e invariantes.
- Retirar da execução a etapa de duas revisões humanas, arbitragem, 50 publicações revistas e validação independente, registrando-as como **dispensadas por decisão institucional**, não concluídas.
- Usar testes e conjuntos artificiais claramente identificados. Avaliação exploratória com dados reais pode medir volume, cobertura, abstenção, consistência e falhas verificáveis; sem referência independente, não calcular acurácia populacional como se houvesse gold confiável.
- Não converter ausência de CTA na legenda em ausência de CTA no vídeo. Não selecionar GLiNER ou heurísticas para produção só pelo desempenho nos 34 exemplos artificiais.
- Manter os seis entregáveis e as 23 capacidades como metas de implementação, mas documentar divergências entre aceite técnico operacional e exigência científica do documento acadêmico original. Caso esse documento exija a revisão humana para aceite formal, a sua dispensa deve ser incorporada ao termo de aceite aplicável.

## Bloqueios que permanecem

1. **Operação concreta:** identidade do app, tokens/IDs, escopos efetivamente concedidos, vínculo de contas e grants verificáveis por fonte/operação; a futura disponibilização de credenciais não comprova integração já funcionando.
2. **Direitos e conformidade:** operacionalizar, com referência auditável, quais dados/modalidades/contas o acordo informado cobre e quaisquer regras aplicáveis de privacidade, retenção e termos das plataformas. Não usar este registro como token ou autorização técnica genérica.
3. **Implementação:** agente Python/MCP, editor CAP-023/DesignDocument, render, geração de criativos, playbook, ingestão robusta e testes ponta a ponta.
4. **Qualidade:** o laboratório E1.5 permanece um ensaio técnico com revisores fictícios. Validação científica independente não será executada; portanto não haverá alegações científicas independentes.
5. **Custos e governança:** teto de caixa R$ 0; sincronização do pacote integral de matrizes v5.2, rastreabilidade por tarefa IMP e integração dos PRs empilhados #29, #30 e #31.

## Guardas preservadas

Nenhuma alteração automática em config/source_permissions.json, em credenciais, nas flags de ingestão ou no Gate 0B. A política deny-by-default continua até operação concreta tecnicamente comprovada. Este documento **não aprova recursos remunerados** e não promove modelos a produção.

**Natureza do registro:** aditivo DEC-018 de decisões informado pelo responsável, sem alterar a numeração das 15 decisões históricas ou das 204 tarefas do plano v5.2. A reconciliação das 13 matrizes com os novos critérios é trabalho documental pendente.
