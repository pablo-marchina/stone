# Gate 0 — Mapa e status

> **Este documento é um snapshot histórico do Gate 0 anterior ao Plano v5.2.** Os números **22 CAP / 12 DEC** descrevem o planejamento inicial. O pacote v5.2 contém **23 CAP / 15 DEC / 204 IMP**, e o repositório avançou até o PR #40. Consulte o [registro de decisões](51_REGISTRO_DECISOES_POS_V52_2026-11-05.md) e a [matriz atual](52_MATRIZ_ALINHAMENTO_FONTES_REPOSITORIO_2026-11-05.md). O histórico abaixo é preservado para auditoria.


## Objetivo único

Preparar a implementação **de uma plataforma única** de inteligência e operação de conteúdo TAPI Stone. Cobertura de planejamento: 22 capacidades (7 formais, 7 opcionais, 5 ampliações externas e 3 transversais), 18 critérios da metodologia, 12 decisões de tecnologia. Não transformar isso em entregas separadas; a liberação continua sendo única e integral, subordinada a gates globais.

## Decisões expressas pelo responsável

| Tema | Escolha | Interpretação executável |
|---|---|---|
| Repositório | Novo | Scaffold local pronto; repositório GitHub privado `pablo-marchina/stone` criado pelo usuário e acesso confirmado |
| Infraestrutura | Comparar | Manter DEC-010 aberto; executar microbenchmark antes de contratar |
| Orçamento | R$ 0 obrigatório | Teto total e por operação R$ 0; nenhuma cobrança automática |
| Permissões de fontes | Pendente | Todos os grants de fontes/ações externas = PENDING, fail closed |
| Autoridade de aprovação | Pendente | Escopo expandido aprovado pelo solicitante; aprovação institucional, jurídica e dos dados não comprovadas |

## Semântica de estados

- `LOCAL_PREPARED`: estrutura e testes locais existem; não significa homologação de contrato.
- `SPECIFIED`: especificação escrita; avaliação ou operação ainda não testada.
- `PENDING_EXTERNAL`: exige decisão/comprovante de terceiros.
- `BLOCKED`: integração não disponível e não ativável no bootstrap.
- `VALIDATED`: somente após execução e evidência com commit+artefato.

## Veredito

**Gate 0A: parcial.** Está permitido desenvolver localmente componentes sem uso de fontes/recursos externos.
**Gate 0B: bloqueado.** Coleta de posts de terceiros, mídia, comentários, publicação, publicidade paga e dados Stone/CRM não podem ser acionados.
**Plataforma integral: não implementada.** A conclusão dependerá do Gate Global da arquitetura, não da presença deste pacote.
