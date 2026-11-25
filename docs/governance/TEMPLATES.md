# Templates de documentação

Copiar a estrutura apropriada; preencher apenas fatos conhecidos. Não criar IDs concorrentes com o Plano Único.

## Registro de incremento / evidência

```markdown
# Título
- Data/corte e fuso:
- Classe: histórica
- IMP / CAP / U / DEC / CT / gates: (IDs oficiais ou NAO_APLICAVEL + motivo)
- Branch / PR / SHA de origem:
- SHA efetivamente testado / blobs verificados:
- Estado de implementação: planejado | implementado | parcial
- Evidência: sintética | reportada | observada | reproduzida | não avaliada
- Verificação: PASS | FAIL | SKIP | NOT_RUN
- Ciência: não avaliada / não validada / evidência legítima específica
- Operação/autorização: escopo e limites
## Alteração e comportamento
## Comandos, ambiente, resultados e artefatos (hash, local autorizado)
## Falhas, skips, limitações e riscos
## Próxima ação (IMP existente)
```

## ADR (visão de uma decisão existente, ou proposta formal)

```markdown
# DEC-xxx — título
- Estado: proposta | aberta | confirmada | substituída
- Fonte canônica / registro / matriz:
- Data e autoridade:
## Contexto e restrições
## Alternativas e critérios
## Evidência e protocolo comparável
## Decisão (ou não decidida)
## Consequências, riscos e rollback
## Vínculos IMP/CAP/U/CT e decisões substituídas
## Gatilho de reavaliação
```

Não atribuir ID novo sem mudança de governança. A ficha não substitui a matriz DEC nem o detalhe integral.

## Guia prático / tutorial

```markdown
# Objetivo executável
- Tipo: guia | tutorial
- Escopo, versão e pré-requisitos:
- Autorização efetiva e ambiente:
## Entrada e procedimento
## Resultado esperado e como verificar
## Falhas comuns, recuperação e rollback
## Limitações, referências canônicas e última verificação
```

## Snapshot de estado

```markdown
# Corte YYYY-MM-DD
- SHA(s), branch(es), PR(s), origem e fuso:
- Escopo de observação (Git, execução local, relatório do operador):
## Fatos verificados e fatos reportados (separados)
## Resultados e limites por frente
## Bloqueios e próxima ação
## Evidências/manifestos autorizados (sem dados privados)
```

Usar o coletor existente da Base Atemporal para snapshots privados; um resumo público interno ao Git não substitui os recibos.
