# Benchmark competitivo e referências de produto

**Base atemporal v6.1 — proposta documental.** Requisitos e hipóteses não são declarações de execução. Detalhes originais são parte desta base por remissão obrigatória ao mapa de seções; fatos datados ficam em `04_Snapshots/`.


## Escopo e método

Revisão incremental do benchmark v2 de 22/10; usar a investigação completa, matriz comparativa, níveis de evidência, licenças, estudos e links como referência de consulta obrigatória em 02_Referencias_Integrais. Não afirmar teste direto de concorrentes nesta revisão. Níveis: documentação pública, código inspecionado historicamente, avaliação própria (nenhuma nova). Separar comparação de produtos de benchmark de modelos. Revalidar disponibilidade, licença e preço antes de qualquer adoção.

| Referência | Valor para o TAPI | Limite / adoção |
|---|---|---|
| GetTranscribe | Pesquisa e análise multimodal de concorrentes | Referência funcional mais próxima; não prova paridade |
| Reel Research (fluxomate) | Pipeline aberto de Reels | Scraping/downloading e maturidade histórica; não reutilizar sem licença e termos |
| Snitch | Inteligência de conteúdo e MCP | AGPL no benchmark histórico; avaliar isolamento/reuso |
| Reels Analyzer | Evidência → roteiros | AGPL, atenção à aquisição |
| SocialGPT MCP / ReelRecon | Contratos e integração de ferramentas | Não confundir conector com engine de inteligência |
| InstaSeer | Relatórios por perfil e UX de evidências | Documentação comercial, não teste |
| Rival IQ / Dash Social / Tubular | Comparação social, benchmarks, relatórios | Métricas, licença e acesso proprietários; comparação por tarefas |
| mLabs / Stilingue | Fluxo editorial/social listening em Brasil | Integração, direitos e custos; não presumir acesso gratuito |
| Foreplay | Pesquisa de criativos e anúncios | Paid ads adjacente, não substitui corpus orgânico |
| Canva / Adobe Express | Edição visual, templates e colaboração | Referência de UX a investigar, não implementação/paridade comprovada |
| CapCut / Descript | Timeline e edição audiovisual | Referências de UX a investigar; não copiar ativos/código |
| Valen / Jev / Snap | Interface de decisões tipadas | Benchmark de tecnologia separado; não produto concorrente equivalente |

## Matriz de tarefas comparáveis

| Jornada | Baseline TAPI observada no corte inicial (histórica) | Comparação proposta | Métrica/oráculo |
|---|---|---|---|
| Descobrir e filtrar | A4/A6 metadata oficial | Curadoria, filtros, estratos | Cobertura, erros, direitos, tempo |
| Inspecionar referência | Data Explorer | UX de relatório | Tempo para localizar snapshot e justificativa, zero referência inválida |
| Categorizar | Evidence Lab, ASR/OCR, candidatos | Modelos e pipelines | Campo, observabilidade, risco-cobertura, latência |
| Encontrar padrões | Ranking Explorer | Painéis concorrentes | Reexecução, denominador, contrastes, filtros |
| Gerar brief | B2/preview | Criativos de referência | Fidelidade, originalidade, aderência à marca |
| Editar/exportar | Studio E3–E8 | Canvas/timeline | Undo, versões, paridade, teclado, tempo e memória |
| Operar | RBAC/SSE/vault/jobs | Produtos integrados | Isolamento, revogação, recuperação, qualidade ISO |

Reproduzir comportamento público e casos próprios (clean-room), nunca código restrito, dados de terceiros sem direitos ou contorno de autenticação. Para cada padrão: origem → comportamento observado → requisito existente → oráculo próprio → decisão/rollback. CAP-020, IMP-120/121/149 exigem prova de paridade empírica; consultar evidência datada, sem presumir homologação. Não criar novos compromissos a partir de funcionalidades de marketing. A vantagem candidata é evidência auditável da publicação à peça editável e combinação System One + agente generativo, não alegação de ineditismo mundial.

A shortlist, o plano de leitura, as tabelas detalhadas de soluções, os níveis A/C/D, a auditoria de alegações e os critérios de reuso do benchmark original permanecem integrais na biblioteca. A classificação competitiva deve ser atualizada por tarefa e evidência, sem adotar automaticamente funcionalidades.
