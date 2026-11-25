# Fluxo de trabalho e organização do repositório

**Norma de desenvolvimento:** [Base Atemporal v6.1](base_atemporal/INTEGRACAO.md), [índice](base_atemporal/00_Indice_e_Protocolo.md) e [Plano Único](../planning/base_atemporal/). O GitHub é fonte de estado operacional, não substituto dos originais privados. A baseline normativa e os snapshots têm funções distintas.

## Branches e PRs — corte histórico de 17/11/2026

As referências a PR #43/#44 abaixo são históricas. Para a situação observada em 24/11 consulte [o novo corte](governance/STATE_2026-11-24.md). Antes de agir, consultar a pilha real no GitHub; não inferir branch ativa por este texto.
- `main`: integração consolidada, Base Atemporal e histórico de incrementos integrados; **não** implica produção homologada.
- [#43 A5](https://github.com/pablo-marchina/stone/pull/43): primeiro incremento pendente, branch `feat/cap001-a5-historical-continuous-20261112`, base main. Manter draft até confirmar os critérios de aceite operacional, backup e autorização explícita de merge.
- [#44 A6](https://github.com/pablo-marchina/stone/pull/44): desenvolvimento ativo, branch `feat/cap001-a6-source-expansion-20261112`, base A5. Manter draft; validar cada incremento no HEAD exato; não mesclar antes da integração da base e dos critérios próprios.
- [#45](https://github.com/pablo-marchina/stone/pull/45): integração exclusivamente documental concluída. Não promove A5/A6.
- Branches antigas: preservar histórico e links; não desenvolver a partir delas por padrão. Inventário inicial em [inventário de branches](repository_inventory_20261117.json); o SHA no inventário é histórico, não HEAD vivo. Branch com PR merged não significa que todo commit foi preservado por ancestralidade (squash/rebase possíveis). Não excluir nem mover refs sem checar dependências, commits únicos e backup.

## Encerramento das propostas históricas
| PR | Disposição e destino |
|---|---|
| #22 | DEC-016 incorporada no #23 e na Base Atemporal. Documento único original permanece na branch pinada. Encerrar sem merge, não atribuir cumprimento científico. |
| #27 e #28 | Propostas alternativas E1.3 consolidadas pelo #29; preservar ambos os heads e seus testes/relatórios. |
| #29 e #30 | Laboratórios E1.3/E1.4 históricos; não integrados ao runtime. A trilha ativa A6 usa experimentos de CTA dirigido (docs/70–72), não equivalência funcional. Reavaliar código, fixtures, ablação e resultados únicos no E-S1-01/A04, sob IMP-026/060/064/065/069/136. Nenhuma promoção de política/modelo por arquivamento. |
| #31 | Protocolo de revisores independentes superado por DEC-018. Preservar contratos e testes de leakage como referência; não executar anotação independente, não inventar revisores, não promover. |
| #32 | DEC-018 consolidada nos #41/45 e docs/53–54 (incluindo reafirmação posterior na A6). Encerrar proposta sem merge; aprovação declarada não equivale a direitos técnicos nem a cumprir >=50. |
| #10 | Plano preliminar já fechado; manter histórico. |
A tabela registra disposição documental, não prova de equivalência de todos os arquivos. Qualquer componente único dos laboratórios pode ser recuperado pelo SHA e avaliado no backlog existente.

## Issues em acompanhamento
- [#6](https://github.com/pablo-marchina/stone/issues/6): conta profissional e permissões efetivas Meta; preservar escopos, quotas e grants por operação. Não repetir aprovação institucional.
- [#19](https://github.com/pablo-marchina/stone/issues/19): corpus dirigido a MPEs (DEC-016), volume, diversidade, elegibilidade e observabilidade; IMP-167/170 e demais tarefas do Plano Único.
- [#8](https://github.com/pablo-marchina/stone/issues/8): CAP-023 Studio, integração com agente e evidências, aceite pendente.

## Procedimento
1. Consultar HEADs remotos e checkout limpo. Seguir a cadeia de bases reais dos PRs abertos; `main → A5 → A6` descreve a etapa inicial, não necessariamente o topo atual. Propagar mudanças de base com fast-forward ou merge sem reescrever histórico; em conflito preservar avanços documentados da branch filha e evidenciar o diff.
2. Executar `python docs/base_atemporal/ferramentas/validar_espelho.py` antes de trabalhar; referenciar IMP/CAP/DEC/CT, evidências, hashes, limitações. Atualizar estado em snapshot datado; alterações normativas exigem decisão e revisão das matrizes.
3. Separar os commits de documentação dos de código. Verificar regressões no HEAD final; não transferir PASS antigo para SHA novo. Sem CI automática paga; `verify_zero_spend.py`, direitos, segurança e backups continuam exigidos.
4. Não promover o código pendente, fechar gates ou publicar dados por sincronização de branches. Aceite integral IMP-131; IMP-062 dispensado conforme DEC-018, não cumprido.

## Estado do corte inicial (histórico, não instrução viva)
Em 17/11 BRT, antes da sincronização, PR #43 em `0aa7d86e6d14531d394c6df06ed2174879b7e373`, A6 em `c85f6d6b7f0ea3774a150621d4553276fcb6a082`. A02.5/6 ainda aguardava 124 focais, backup pós-0015, rehearsal 0016 e procedimento protegido, conforme [registro operacional pinado](https://github.com/pablo-marchina/stone/blob/c1edc85233808caae9951deaee3d5df20d19c38f/docs/74_A00_BASELINE_REGRESSAO_2026-11-17.md). Consultar o HEAD atual antes de retomar.

## Manutenção documental

Seguir [padrão documental](governance/STANDARD.md); rodar o catálogo local junto ao validador existente. Mudança de organização não autoriza merge de código, rebase de branches dependentes ou alteração de gates. Para propagar o padrão, respeitar as bases reais da pilha e revisão do responsável.
