# Plano Único de Implementação — baseline atemporal

**Base atemporal v6.1 — proposta documental.** Requisitos e hipóteses não são declarações de execução. Detalhes originais são parte desta base por remissão obrigatória ao mapa de seções; fatos datados ficam em `04_Snapshots/`.


## Base e invariantes

204 IMP, 543 arestas, 23 CAP, 18 U, 18 DEC, 16 grupos domínio, 28 CT, 28 contratos, 29 inventário de schemas, 207 ISO e 414 U×CAP, 18 lacunas e 7 gates. Preservados IDs, critérios de aceite, dependências, ordem, estimativas originais, única entrega e IMP-131. A estimativa histórica de 1561h não é esforço restante. A fonte original v5.2 tem 15 DEC; incorporamos DEC-016–018 com os campos exatos das matrizes Git sincronizadas. As cinco matrizes Git de 05/11 foram reconstruídas byte a byte e preservadas no snapshot inicial. A matriz vigente conserva os 204 oráculos originais e adiciona vínculos normativos `decision_ids_vigentes` e `regra_vigente`; status originais são explicitamente históricos. O mapa de evidências por tarefa e fases fica no snapshot datado, não altera a especificação. Ausência de evidência em um corte não prova ausência de código. IMP-062 dispensa declarada, não cumprida. Mapear novos experimentos a IMP existentes. Não criar plano paralelo.

## Regra de execução permanente
As 13 matrizes estáveis estão em `03_Plano_Unico/matrizes/`. Os estados e fases A00–A11 do corte inicial estão no snapshot. A fase é um overlay operacional, nunca uma alteração das dependências, aceites ou IDs. Usar o DAG e os bloqueios vigentes, avaliar valor marginal e riscos e reestimar apenas trabalho restante com evidência de capacidade. A tarefa IMP-131 permanece o único aceite final. Não criar backlog paralelo ou alterar precedências por resumo. Qualquer alteração de escopo/contrato/hipótese exige registro de decisão, diff da matriz e verificador. As tarefas IMP-062/CAP-004 são dispensadas por decisão comunicada, nunca cumpridas; ausência de gold independente deve ser revelada. Não bloquear o trabalho autorizado pedindo novamente aprovação institucional genérica. R$0 em desembolso e serviços faturáveis.

## Gates globais
G0-PERMISSIONS, G1-CONTRACT, G2-REPRODUCIBILITY, G3-EVAL, G4-SECURITY, G5-OPS, G6-ISO: definição, tarefas e prova no CSV. Nenhum gate pode mudar só por texto ou status de PR. Consultar registro datado, testes, artefatos e oráculos. O caminho crítico do snapshot inicial é histórico e não uma instrução permanente.
