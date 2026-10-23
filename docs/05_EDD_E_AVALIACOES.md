# Estratégia EDD e medição científica — preparação

**Objetivo:** especificar como provar qualidade antes de otimizar componentes, sem confundir fixtures sintéticas com gold de domínio.

## Sets segregados

- `development`: iteração de prompts, SQL, modelos, contratos.
- `validation`: seleção de alternativas e patamares.
- `sealed_test`: único aceite final de modelo/capacidade por ciclo, nunca usado em prompt/RAG ou seleção de hiperparâmetros.

Separar por `creator_id` e deduplicar quase-duplicatas. Amostragem humana de **pelo menos 50 publicações** é requisito formal; suporte por classe, dupla anotação parcial, concordância e intervalos são exigências de engenharia adicionais. Não é possível produzir gold real antes de ter dados de origem autorizada. Nesse intervalo, executar somente fixtures sintéticas de **contratos e bordas**, sem alegar F1 ou grounding real.

## Baselines e avaliações

| Domínio | Baseline | Métrica prevista | Status |
|---|---|---|---|
| Ranking | SQL/aritmética exata `(likes+comments)/followers`, top 10% | Concordância absoluta, cobertura e erro de divisor | DEFINIDO, não executado em posts reais |
| Rubrica | Texto/metadata autorizados + abstenção | Macro-F1/MAE por campo, suporte, observabilidade | PENDENTE GOLD REAL |
| Multimodal | Modalidade adicional sob direito verificado | delta F1, erro temporal, custo, p95 | BLOQUEADO SEM MÍDIA |
| Retrieval | SQL/FTS | nDCG@k/Recall@k, custo, p95 | PENDENTE CORPUS |
| Agente | Resposta determinística por SQL + templates | exatidão, groundedness, trajetória de ferramentas | PENDENTE CORPUS |
| Criativos | Sem fonte vs. com fonte válida | blind pairwise humano, tempo de edição | PENDENTE GUIA STONE |
| Operação | local sem integrações | p95, recuperabilidade, acessibilidade, RBAC | PLANO DEFINIDO |

## Gates

`G0 fonte`, `G1 contratos`, `G2 reprodutibilidade`, `G3 avaliações`, `G4 segurança`, `G5 operação`, `G6 qualidade ISO`. A aprovação global exige todos os gates aplicáveis e a evidência real por capacidade. Métricas aspiracionais não são resultados.

## Primeiro experimento executável

`EXP-G0-SCHEMA`: validar que 20 campos da rubrica existem, que todos os dados externos são negados, que respostas de status não declaram produção e que os schemas candidatos são sintaticamente válidos. `python -m pytest -q`; relatórios de teste local podem ser anexados ao registro de evidência. Isso não valida a rubrica semântica ou a precisão dos modelos.
