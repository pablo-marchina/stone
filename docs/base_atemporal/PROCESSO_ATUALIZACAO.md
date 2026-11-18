# Como manter a base atemporal

## Regra de mudança
1. Identificar o fato ou requisito alterado e sua autoridade. Abrir fonte exata, registrar hash/commit/data/escopo e o status de evidência. Nunca atualizar número antigo sem novo snapshot.
2. Se for apenas progresso, criar snapshot novo, preservar o anterior e atualizar `LATEST_SNAPSHOT.json` após revisão; não editar núcleo. Distinguir `codigo_verificado`, `execucao_reportada`, `teste_reexecutado`, `nao_observado`, `aceite`.
3. Se decisão altera requisito, contrato, escopo ou metodologia, registrar DEC/alteração (não usar IDs já existentes para nova decisão), atualizar núcleo, matriz, vínculos, oráculos, mapa de conflito e manifesto. Retain a versão anterior. Não promover candidato por conversa ou PR sem decisão. Revalide licenças/quotas/APIs antes de uso, não transforme literatura em verdade atual.
4. Para novo experimento, registrar hipótese vinculada a IMP/CAP, referência (fixture/programática/pseudo/independente indisponível), dados, split/seed, hashes, configuração, oráculo pré-registrado, custo, resultado positivo e negativo e limitação. Nunca falsificar teste ou ajustar holdout após resultado. Não pedir nova aprovação institucional genérica; verificar direitos efetivos.
5. Para alterações no plano, preservar IDs e aceitar somente diff explícito; 204/543 são baseline de referência, não impedimento eterno a uma expansão deliberada. Toda mudança exige DAG válido, fechamento único IMP-131 e rastreabilidade CAP/U/DEC/CT/ISO/gates.
6. Antes de substituir contexto ativo, executar `python validar_base.py`, conferir relatório e manter cópia da release. Integração GitHub deve ser branch documental revisável, sem alterar código, dados ou CI faturável.

## Snapshot novo
Use `06_Integracao_GitHub/coletar_snapshot_local.py` para registrar árvore/commit local e hashes de documentos rastreados sem rede ou mutação. O operador deve complementar status remoto de PRs, dados, testes, migrações e grants por evidência, sem incluir conteúdo sensível. Snapshot do checkout não prova operação. Compare HEAD e refs com GitHub por ferramenta autorizada antes de agir. O script não gera conclusões ou promove gates.
