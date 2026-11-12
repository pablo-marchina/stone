# DEC-018 — decisão institucional comunicada, permissões operacionais e mudança do critério de revisão humana

**Corte:** 05/11/2026 · **Registro de autoridade:** declaração explícita do responsável pelo projeto em 04/11/2026, preservada no [PR #32](https://github.com/pablo-marchina/stone/pull/32).  
**Status de governança:** `CONFIRMADA_PELO_RESPONSAVEL`. **Status documental externo:** `INSTRUMENTO_INSTITUCIONAL_NAO_ANEXADO_A_AUDITORIA`.  
**Escopo:** projeto unificado Stone/Impulso Stone, arquitetura v5.1 + revisão v5.2, Plano Único, pesquisa observacional, Studio e operações ampliadas.  
**Precedência:** o TAPI original continua registrado integralmente; esta DEC documenta a **mudança de aceite comunicada**, sem alegar que um requisito dispensado foi realizado.

## Decisão confirmada e seu alcance

O responsável comunicou em 04/11/2026 que:

1. A instituição concedeu aprovação **formal e abrangente** para as expansões, fontes, operações, termos e direitos necessários ao projeto, incluindo conteúdo de terceiros e os dados disponibilizados pela Stone.
2. Contas, APIs, permissões técnicas e identificadores efetivos serão disponibilizados sob demanda; **aprovação declarada não substitui credencial, escopo API, autorização de conta ou capability técnica**.
3. **Não haverá revisores humanos nem validação científica independente.** Isso abrange a exigência original de amostragem de ≥50 publicações anotadas manualmente com concordância entre avaliadores.
4. O projeto continua restrito a **R$ 0 em desembolsos e serviços faturáveis**; não há execução automática de publicidade paga nem contratação implícita de serviços.

**Natureza da confirmação:** trata-se de manifestação direta do responsável, aqui incorporada à governança do projeto e ao planejamento. Esta auditoria **não recebeu para leitura** o contrato, autorização escrita individual de fornecedor ou documento institucional externo que especificaria todas as condições; não afirmar auditoria independente desses instrumentos. **Não é necessário nem permitido no fluxo interno do projeto pedir nova confirmação desta decisão ao responsável.** A aprovação institucional é permanente para o escopo comunicado, até eventual revogação ou alteração expressa. Ver regra operacional abaixo.

## Consequência para o requisito original ≥50

| Aspecto | TAPI original | Decisão do responsável (04/11) | Registro e aceite |
|---|---|---|---|
| Revisão humana da rubrica | Validação de **pelo menos 50 publicações** e concordância com referência humana | **Dispensada**, pois não haverá anotadores humanos | `ALTERACAO_DE_CRITERIO_DEC018`; **não `CUMPRIDO`**, não gerar revisores fictícios |
| Gold e validação independente | Etapa recomendada na metodologia científica e exigência de revisão no case | Não executar validação científica independente | Relatar `scientifically_validated=false` até que outra evidência legítima exista; usar teste estrutural, funcional e de consistência como avaliação **de engenharia** |
| Qualidade da classificação | Rubrica fixa de 20 atributos e observabilidade por modalidade | Mantida | Abstenção por falta de áudio/frames, checks de schema e provenance, avaliações determinísticas sem alegar concordância humana |
| Relevância do corpus MPE | Conteúdo dirigido a MPEs; revisão de elegibilidade prevista no desenho científico | Direitos institucionalmente comunicados, mas sem revisores independentes disponíveis | Não inferir relevância apenas por perfil; usar evidência observável e regras rastreáveis; classificar cobertura como `NAO_VALIDADA_INDEPENDENTEMENTE` |
| Declaração de conformidade institucional | Critério original de ≥50 | Mudança comunicada | Não alegar conformidade literal com o PDF até haver instrumento institucional acessível que documente a substituição; expor divergência no relatório final |

**Decisão operacional:** a tarefa `IMP-062` será registrada como `DISPENSADO_POR_DEC018_DECLARADA_NAO_CUMPRIDO` nas matrizes sincronizadas. Isso **não** altera seus IDs, remove seus vínculos ou apaga a descrição histórica. Gates de avaliação permanecem **não liberados** para operação final enquanto outros critérios do produto estiverem pendentes. Testes sintéticos, modelos locais e métricas de engenharia podem ser executados, **não substituem** a revisão humana como se fosse realizada.

## Gate 0B — distinção entre decisão e execução

- **G0B-01 institucional:** `APROVACAO_COMUNICADA_PELO_RESPONSAVEL`; evidência externa adicional não examinada nesta revisão.
- **G0B-02 fonte/operação:** requer credencial válida, escopo efetivo, tenant e grant específico; existe piloto real Meta A3 **restrito** ao Sebrae com 3 posts técnicos, sem incorporação científica automática.
- **G0B-03 termos/direitos:** aprovação institucional comunicada; aplicações específicas devem continuar obedecendo condições de API, direitos de mídia e atestações por recurso/uso. Upload, análise audiovisual, armazenamento e redistribuição não são a mesma operação.
- **G0B-04 release:** não liberado. Produção, publicação externa, campanhas, CRM e serviços com custo não são ativados pela DEC-018.

Uma declaração de aprovação não modifica automaticamente `policy.py`, `config/source_permissions.json`, tokens, aprovações editoriais ou feature flags.

## Relação com outras decisões e artefatos

- [DEC-016](33_DEC016_IMPLEMENTACAO_FONTE_ELEGIBILIDADE_DATA_CARD_V2.md): relevância do **post** para MPEs e medição da elegibilidade separadas do porte do criador.
- [DEC-017](35_DEC017_E1_SYSTEM_ONE_LAB.md): System One/GLiNER local experimental, não substitui revisão científica.
- [A3 Meta](45_A3_BUSINESS_DISCOVERY_PRIMEIRO_LOTE_TECNICO.md): prova técnica restrita de leitura oficial, snapshots e rechecagem de grant.
- [Plano Único v5.2](24_PLANO_UNICO_IMPLEMENTACAO_V5_2_2026-10-30.md): o requisito original não é reescrito retroativamente; `DEC-018` entra como decisão adicional vinculada às tarefas.
- [Registro pós-v5.2](51_REGISTRO_DECISOES_POS_V52_2026-11-05.md) e [matriz de alinhamento](52_MATRIZ_ALINHAMENTO_FONTES_REPOSITORIO_2026-11-05.md): evolução e provas.
- [PR #32](https://github.com/pablo-marchina/stone/pull/32): registro anterior da declaração, **ainda aberto** em 05/11. Este adendo deve evitar divergências ou estados contraditórios ao consolidá-lo.

## Política de evidência após DEC-018

- Usar `PROPOSTO`, `IMPLEMENTADO`, `TESTADO_SINTETICO`, `EXECUCAO_REAL_REPORTADA`, `CI_VERIFICADO` e `HOMOLOGADO` sem misturá-los.
- **Sem revisão independente:** não publicar F1/MAE como precisão científica comprovada sobre o público Stone; não simular anotadores, não mascarar a ausência com rótulos de IA.
- Validar por contratos, fixtures negativas, consistência determinística, provas técnicas de proveniência, comportamento seguro, segregação, direitos por operação, testes integrados e limitações explícitas.
- O projeto continua sujeito às sete gates globais da entrega única; nenhuma dispensa equivale a liberação operacional automática.

**Registro final:** decisão do responsável confirmada e aplicada ao plano de execução **como dispensa declarada**; verificação documental de instrumento institucional externo **não foi realizada**; execução literal das 50 revisões **não ocorreu**.


## Regra operacional reafirmada pelo responsável — 12/11/2026

O responsável reafirmou expressamente que a aprovação já foi concedida e determinou a eliminação de solicitações repetidas de aprovação em todo o projeto. A DEC-018 é a referência institucional única para todas as atividades dentro do escopo comunicado, sem novos formulários, declarações, datas de validade artificiais, arquivos de autorização por lote ou interrupções por confirmação genérica. Não solicitar novamente aprovação institucional para expansão documental, identificação, aquisição e demais atividades já abrangidas.

Distinguir a decisão institucional de mecanismos técnicos: autenticação, tokens e permissões reais do provedor, identidade da fonte, escopos de operações, grants técnicos auditáveis e revogáveis, limites de requisições, custo zero, segregação de tenant e preservação de dados. Esses mecanismos não são novos pedidos de aprovação institucional; devem ser operacionalizados com o menor atrito possível, reutilizando DEC-018 como referência quando aplicável. Não inventar uma data de expiração institucional, não simular um grant, não tratar uma identificação como prova de acesso a mídia e não contornar bloqueios efetivos do provedor. Não confundir DEC-018 com habilitação automática de publicação externa, contratação de serviços ou comprovação científica.

A6: a identificação de candidatos usa diretamente a referência DEC-018, o manifesto, os handles explícitos, o viewer e o administrador autenticado. Retirados o arquivo IdentityScope, seus campos de referência/validade e o prompt correspondente. A6.3 deverá reconciliar identidades e preparar grants técnicos por fonte sem solicitar outra aprovação institucional. A decisão é orientação transversal para todas as próximas implementações. Não altera retrospectivamente as evidências já registradas, nem comprova instrumento externo independente.
