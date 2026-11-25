# Fluxo de trabalho e organização do repositório

## Regra vigente após a consolidação de 24/11/2026

A **main é a única base canônica de integração de desenvolvimento**, não uma release homologada. Consulte o [registro de consolidação](governance/CONSOLIDATION_2026-11-24.md), [inventário de branches](governance/BRANCH_INTEGRATION_2026-11-24.json), [padrão documental](governance/STANDARD.md), [Base Atemporal v6.1](base_atemporal/INTEGRACAO.md) e [Plano Único](../planning/base_atemporal/).

1. Confirmar estado limpo e SHA de origin/main antes de iniciar; criar branch curta por incremento IMP, sem retomar automaticamente branches anteriores.
2. Paralelizar frentes independentes sobre main; explicitar dependências reais, reconciliar conflitos preservando direitos e testes. Não criar novo backlog nem pilha longa sem necessidade.
3. Antes de integração: validar espelho, catálogo, zero-spend, preflight e testes pertinentes no SHA exato; documentar resultados, falhas, limites e vínculos. Regressão integral e gates continuam próprios. Não transferir resultados automaticamente.
4. Abrir PR contra main (ou dependência explícita, quando indispensável); integrar somente com autorização aplicável e preservação do histórico. Sem force-push, exclusão de histórico, CI pago ou automerge que contorne revisão.
5. Manter registro de evidências e snapshots separado de norma. A aprovação institucional comunicada DEC-018 não é reaberta; direitos técnicos, tenant, quotas, segurança e backups continuam exigidos. IMP-131 é aceite indivisível; IMP-062 dispensado, não cumprido.
6. Merge de desenvolvimento nunca autoriza deploy, migração operacional, publicação ou promoção científica.

## Histórico preservado

O [fluxo anterior, pinado no HEAD do merge](https://github.com/pablo-marchina/stone/blob/98a6f8fb8c3b44e86e3dc960684e3b564ecdfc00/docs/REPOSITORY_WORKFLOW.md) registra a pilha antiga, os PRs #43/#44, as disposições das propostas #10/#22/#27–32 e questões #6/#8/#19. Essas referências são históricas e não instruem a retomada de branches. Consultar estado atual de issues e PRs no GitHub. Nenhuma proposta histórica foi reativada por esta consolidação.
