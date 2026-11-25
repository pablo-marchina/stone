# Portal documental — TAPI Stone

Este portal é uma visão de navegação, não uma nova fonte de requisitos. A especificação integral privada continua necessária conforme o [protocolo](base_atemporal/00_Indice_e_Protocolo.md) e [guia de adoção](base_atemporal/INTEGRACAO.md).

| Necessidade | Comece por | Tipo Diátaxis |
|---|---|---|
| Entender propósito, escopo e produto | [Documento mestre](base_atemporal/01_Documento_Mestre_Atemporal.md), [contexto editorial](base_atemporal/08_Contexto_Editorial_Stone.md) | Explicação |
| Entender arquitetura e limites | [Arquitetura](base_atemporal/07_Arquitetura_Unificada_Atemporal.md), [mapa de arquitetura](architecture/README.md), [System One](base_atemporal/06_SystemOne_StoneS1_Atemporal.md) | Explicação |
| Entender ciência e pesquisa | [Metodologia](base_atemporal/05_Metodologia_Cientifica_Atemporal.md), [pesquisa](base_atemporal/03_Pesquisa_Tecnica_Atemporal.md), [benchmark](base_atemporal/04_Benchmark_Competitivo_Atemporal.md) | Explicação |
| Consultar decisão | [Registro canônico](base_atemporal/02_Registro_Decisoes_Atemporal.md), [matriz DEC](../planning/base_atemporal/MATRIZ_DECISOES.csv), [DEC-018](53_DEC018_CONFIRMACAO_ALCANCE_E_CRITERIO_REVISAO_2026-11-05.md) | Referência |
| Implementar uma tarefa | [Plano Único](base_atemporal/11_Plano_Unico_Atemporal.md), [backlog](../planning/base_atemporal/BACKLOG_UNICO_IMPORTAVEL.csv), [dependências](../planning/base_atemporal/DEPENDENCIAS.csv), [mapa de fases](../planning/action_2026-11-17/phase_map.json) | Referência |
| Consultar critérios e contratos | [Requisitos](../planning/base_atemporal/MATRIZ_REQUISITOS.csv), [CAP](../planning/base_atemporal/MATRIZ_CAPACIDADES.csv), [CT](../planning/base_atemporal/CATALOGO_TESTES_CT.csv), [contratos](../planning/base_atemporal/CATALOGO_CONTRATOS.csv), [gates](../planning/base_atemporal/MATRIZ_GATE_GLOBAL.csv) | Referência |
| Trabalhar em segurança | [Direitos](02_MATRIZ_DIREITOS_E_POLICY_GATES.md), [segurança](06_SEGURANCA_E_IDENTIDADE.md), [R$0](14_POLITICA_CUSTO_ZERO.md), [fluxo Git](REPOSITORY_WORKFLOW.md) | Referência histórica + regras vigentes na base |
| Reproduzir/registrar incremento | [Guia documental](governance/STANDARD.md), [templates](governance/TEMPLATES.md), [guia local](guides/README.md) | Guia prático |
| Consultar progresso | [Corte de 24/11](governance/STATE_2026-11-24.md), [inventário pinado](governance/inventory_2026-11-24.json) | Histórico |
| Explorar toda a documentação da branch | `python scripts/documentation_catalog.py index` | Referência gerada |
| Cruzar requisitos, CAP, IMP, DEC, CT e gates | `python scripts/documentation_catalog.py graph` | Referência gerada |

Os arquivos numerados na raiz de docs são registros de diferentes épocas: não assumir que título, número ou data lhes confere autoridade normativa. Os links de fontes integrais no espelho podem exigir o ZIP privado. O mapa de fases é overlay operacional e pode não existir em branches antigas; não inventar um plano alternativo.

## Trilhas de desenvolvimento (referências do corte de 24/11)

- A00/qualidade: [regressão inicial](74_A00_BASELINE_REGRESSAO_2026-11-17.md), [frontier A11](104_A11_FRONTIER_VERTICAL_REHEARSAL_2026-11-23.md).
- A01/A02/aquisição e multimodal: [A5](56_CAP001_A5_AQUISICAO_HISTORICA_CONTINUA_2026-11-12.md), [A6](57_CAP001_A6_EXPANSAO_IDENTIFICACAO_2026-11-12.md), [ASR estrito](109_A027_SHARED_AV_STRICT_WER_CONTRACT_2026-11-23.md).
- A04/retrieval: [evidência IMP-071](75_IMP071_EVIDENCIA_FASTPATH_E_LACUNAS_DE_ACEITE_2026-11-20.md), [comparação sintética](78_A04_IMP060_COMPARACAO_SINTETICA_FTS5_2026-11-20.md).
- A05/agente e integração: [ledger protegido](114_DEC008_PROTECTED_AV_RESEARCH_LEDGER_2026-11-23.md), [handoff Studio](116_AGENT_TRACE_STUDIO_HANDOFF_2026-11-23.md).
- CAP-023/demo: [hipóteses editoriais](124_DEMO_EDITORIAL_HYPOTHESES_2026-11-24.md), [Kinetic v4](133_DEMO_SOCIAL_KINETIC_2026-11-24.md).
- A11/aceite: [frontier e exercício vertical](104_A11_FRONTIER_VERTICAL_REHEARSAL_2026-11-23.md); IMP-131 e gates não são liberados por um ensaio local.

Todas as referências acima remetem a evidências de escopo e SHA próprios. Para um tutorial de uso completo e homologado, a cobertura ainda precisa ser avaliada; não declarar que os registros históricos são manuais finais.
