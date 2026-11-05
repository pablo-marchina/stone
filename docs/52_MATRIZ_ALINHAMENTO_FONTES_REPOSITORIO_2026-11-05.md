# Matriz de alinhamento — fontes do TAPI, arquitetura, Plano Único e repositório

**Auditoria de referência:** 05/11/2026. **Branch auditada:** `main`, commit `79bb0173c90cbc993481bf1e959154adf796a5de`.  
**Objetivo:** identificar **o que a fonte exige/projeta**, **o que o repositório comprova** e **o que permanece pendente**, evitando que descrições antigas continuem sendo lidas como status atual.  
**Registro de decisões relacionado:** [51_REGISTRO_DECISOES_POS_V52_2026-11-05.md](51_REGISTRO_DECISOES_POS_V52_2026-11-05.md). A DEC-018 está formalizada no âmbito de decisão do responsável em [53](53_DEC018_CONFIRMACAO_ALCANCE_E_CRITERIO_REVISAO_2026-11-05.md), e as matrizes sincronizadas são explicadas em [54](54_SINCRONIZACAO_MATRIZES_V52_DEC018_2026-11-05.md).

## 1. Inventário e precedência das fontes

A fonte institucional não é substituída por textos de metodologia, benchmark, arquitetura ou PR. Os pacotes externos abaixo foram fornecidos ao projeto para esta reconciliação; **não presumir que seus bytes estão publicados em `main`**. Os fingerprints identificam a versão examinada, não concedem autorização de uso.

| Camada | Fonte fornecida | Função documental | Artefato próximo no repositório | Relação/limite |
|---|---|---|---|---|
| F0 — normativa | `Proposta de TAPI_Stone_Inteli_Academy (1).pdf` | Objetivo, rubrica, avaliação, limites e entregáveis oficiais | `docs/03_...`, `07_...`, `09_...`, `23_...` | Fonte de exigência; confirmar eventuais decisões formais posteriores |
| F1 — referência | `TAPI_Stone_Documento_Mestre_Referencia.md` | Interpretação fiel, diferenças entre `[FONTE]`, `[ANÁLISE]`, `[PENDENTE]` | `docs/09_ORIGENS_REFERENCIAS_E_LIMITES.md` | Apoio, não contrato institucional |
| F2 — ciência/pesquisa | `TAPI_Stone_Pesquisa_Revisada_Expandida_v2_2026-10-22.md`, `TAPI_Stone_Benchmark_Projetos_Solucoes_Similares_REVISADO_v2_2026-10-22.md`, `TAPI_Stone_Metodologia_Cientifica_Engenharia_Produto_REVISADA_v2_2026-10-22.md` | Métodos, benchmarking, riscos de plataformas, EDD, ISO | `docs/05_...`, `11_...`, `12_...` | Hipóteses e protocolos, não resultado validado |
| F3 — arquitetura base | `TAPI_Stone_Arquitetura_Pacote_Final_Consolidado_2026-10-22.zip` (v5.1) | Visão de produto unificado, contratos e matrizes iniciais | `docs/23_ARQUITETURA_UNIFICADA_REVISADA_V5_2_2026-10-30.md` | A arquitetura v5.1 **continua vigente nas partes não alteradas**, mas não está toda reproduzida textualmente no repo |
| F4 — revisão | `TAPI_Stone_Arquitetura_Revisada_v5_2_Changelog_2026-10-30.md` | CAP-023, separação evidência/brief/editor, novas tarefas e testes | `docs/23_ARQUITETURA_UNIFICADA_REVISADA_V5_2_2026-10-30.md`, `docs/22_...` | Texto proposto em 30/10; várias capacidades passaram a ter implementação após essa data |
| F5 — execução | `TAPI_Stone_Plano_Unico_Implementacao_v5_2_2026-10-30.zip` | 23 CAP, 204 IMP, 15 DEC, 7 gates, 28 CT, 13 matrizes CSV + manifesto | `docs/24_PLANO_UNICO_IMPLEMENTACAO_V5_2_2026-10-30.md` | **Resumo versionado no Git**; matrizes CSV do pacote externo **não são, por isso, automaticamente o baseline de status em Git** |
| F6 — revisão contextual | `auditoria_integral_impulso_stone_2026-11-03.md`; `TAPI_Stone_Revisao_Conceitual_Metodologica_Auditoria_Impulso_v3_2026-11-03.md` | Separação C1–C4, correção da unidade amostral, limites de Ads/Instagram | `docs/30_...`, `33_...`, código `mpe_sources.py`/`scientific_corpus.py` | Não converter relatórios Stone em amostra orgânica, nem CTR em leads |
| F7 — execução auditável | PRs GitHub integrados até #40 e arquivos em `main` | Presença de código, testes declarados, limitações | `src/`, `tests/`, `migrations/`, `docs/33_...`–`50_...` | Prova de engenharia localizada; não prova aceite científico, jurídico ou operacional |

### Fingerprints SHA-256 das principais fontes externas fornecidas

```text
778404c2a14e8f3c303bd42cdb47093cfe982ddc67fcb0522dab46db36869495  Proposta de TAPI_Stone_Inteli_Academy (1).pdf
759c9e2645ed7f8416037e412b3f9bc53ea57f91b901a22f0c6cc58ad92fc102  TAPI_Stone_Arquitetura_Pacote_Final_Consolidado_2026-10-22.zip
d24e212118e899f8cc98dd550f6c0f690fcb7a369553f018bbab055ebc19d8df  TAPI_Stone_Documento_Mestre_Referencia.md
a5767382211f82ca29d32cc7affa87d9be2d51c70081d7c169d30280be351665  TAPI_Stone_Pesquisa_Revisada_Expandida_v2_2026-10-22.md
d3713cc7601cab0c0073c81e87d9c8628875784e016c364891d5fa5cd89c3960  TAPI_Stone_Benchmark_Projetos_Solucoes_Similares_REVISADO_v2_2026-10-22.md
28bbf497a5b761219ee1ca82f49371cb1ddef522a7daaeef479c9c79d7f9ae1c  TAPI_Stone_Metodologia_Cientifica_Engenharia_Produto_REVISADA_v2_2026-10-22.md
ab9651300d0f289df51f21a2158aa08bfebbf20db223baa23dde40ba09a91b60  TAPI_Stone_Arquitetura_Revisada_v5_2_Changelog_2026-10-30.md
0dbb51bf18a75734fcb2121373590bfc1ba3ae5cd729aff9a4dcb537491aa04d  TAPI_Stone_Plano_Unico_Implementacao_v5_2_2026-10-30.zip
391e56555eaf5e17e69635ad074586a97ef92fed5801a60d89d3791b19fb0a92  TAPI_Stone_Revisao_Conceitual_Metodologica_Auditoria_Impulso_v3_2026-11-03.md
864030f5402a4587462a05fd0afb4b0f838372e9ad15aba6b71a78f444d5525c  auditoria_integral_impulso_stone_2026-11-03.md
```

## 2. Critério de leitura da implementação

- **IMPLEMENTADO_PARCIAL:** funcionalidade identificada no código, mas sem todos os requisitos do plano/aceite.
- **IMPLEMENTADO_LOCAL:** operação concreta relatada em teste ou uso limitado e verificável por arquivo/PR; não é produção.
- **TESTADO_SINTETICO:** testes/mocks/fixtures não são dados científicos.
- **EXECUCAO_REAL_REPORTADA:** operador registrou chamada oficial e observações reais; não equivale a inferência científica validada.
- **NAO_COMPROVADO_NA_AUDITORIA:** não se encontrou evidência suficiente nesta revisão para declarar funcionalidade pronta. **Não significa prova de inexistência em todo o código.**
- **BLOQUEADO/CONDICIONAL:** requer autorização, avaliação, permissão, dados, infraestrutura ou liberação própria.
- **HISTORICO:** documento fiel à época, mas superado por PR posterior; deve conter aviso e referência ao corte atual.

## 3. Rastreabilidade do núcleo institucional (CAP-001…007)

| CAP | Exigência nas fontes | Evidência localizada em `main` | Estado de produto | Gap de aceite |
|---|---|---|---|---|
| **001** Coleta/base | Instagram principal; YouTube complementar quando permitido; 2–5 mil posts/≥30 perfis como referência; idade ≥14 dias; origem, direitos, qualidade | `connectors.py`, `mpe_sources.py`, `corpus.py`, `scientific_corpus.py`, `docs/45_...`, PRs #23/#33/#36 | IMPLEMENTADO_PARCIAL + EXECUCAO_REAL_REPORTADA | Somente **3 posts técnicos reais** relatados em 05/11, zero posts demonstrados como cientificamente admitidos; volumetria/diversidade não atendida |
| **002** Ranking | `ER=(likes+comments)/followers`, top 10% por base declarada; recortes, qualidade do denominador | `agent_evidence_e1.py`, contratos e store SQL; `docs/43_...` | IMPLEMENTADO_PARCIAL | Sem ranking científico reproduzível sobre corpus elegível e observável de escala adequada |
| **003** Rubrica | 20 campos fixos, evidência multimodal/temporal e JSON tipado | `domain.py`, `classification.py`, `system_one_e1.py`, `system_one_e12.py`; PRs #24–26 | IMPLEMENTADO_PARCIAL / TESTADO_SINTETICO | Sem classificação audiovisual integral comprovada em posts reais autorizados; GLiNER é laboratório textual |
| **004** Revisão | TAPI original: ≥50; DEC-018: dispensa de revisores humanos e validação científica independente comunicada pelo responsável | `scientific_corpus.py`, docs/53 e PR #32 | ALTERACAO_DE_ACEITE_DECLARADA_NAO_CUMPRIDA_LITERALMENTE | As 50 revisões não ocorreram; não produzir pseudo-gold nem apresentar dispensa como cumprimento do PDF original |
| **005** Agente | Modos `analisar/recomendar/gerar_criativo`, ferramentas, evidência e justificativa | `agent_evidence_e1.py`, `agent_evidence_b2.py`, `agent_api_e1.py`; PR #34 | IMPLEMENTADO_PARCIAL | Sem LangGraph final, geração original fundamentada completa, testes E2E dos três modos |
| **006** Integração | Função Python tipada + MCP; retorno com findings/references/creatives/confidence/explanation | `agent_mcp_b2.py` (MCP stdio, três ferramentas), contratos B2 | IMPLEMENTADO_LOCAL / PARCIAL | Ferramentas e protocolo não representam ainda paridade com contrato final de saída nem servidor MCP/cliente homologados |
| **007** Playbook/criativos | ≥5 criativos com gancho, roteiro, legenda, CTA, fontes e contexto Stone | `creative-spec.v1` via B2, Studio C2–E8, edição/exportação | IMPLEMENTADO_PARCIAL | Faltam cinco criativos originais sustentados por pesquisa real, playbook final e avaliação editorial |

**Regra:** posts técnicos, perfis candidatos, peças de Meta Ads e observações sintéticas **não** podem ser somados para declarar cumprimento do volume científico.

## 4. Rastreabilidade das capacidades expandidas

| CAP | Estado verificável até o corte | Evidência / condição |
|---|---|---|
| 008 — contraste top/restante | NÃO COMPROVADO NA AUDITORIA | Requer rótulos no restante da base, não apenas top; sem dados não há lift válido |
| 009 — RAG/busca híbrida | PARCIAL (retrieval estruturado B2) | Embeddings/híbrido e ganho versus SQL não avaliados |
| 010 — avaliação de criativos | NÃO COMPROVADO NA AUDITORIA | Não confundir editor/patch com avaliação de qualidade editorial |
| 011 — comentários/intenção | NÃO COMPROVADO NA AUDITORIA | Direito, cobertura e texto de comentários ainda dependentes da fonte |
| 012 — segmentos | PARCIAL no quadro amostral | Nenhuma inferência setorial consolidada em corpus validado |
| 013 — calendário | NÃO COMPROVADO NA AUDITORIA | Necessita evidência temporal e recomendações apoiadas na amostra |
| 014 — playbook de lojistas | NÃO COMPROVADO NA AUDITORIA | Público/linguagem diferenciados a validar |
| 015 — predição | CONDICIONAL e fora do case | Não é entrega obrigatória; exige decisão explícita de extensão |
| 016 — produção final de imagem/vídeo | IMPLEMENTADO_PARCIAL (raster, ZIP, render local de rascunho) | Exportação funcional em escopo limitado ≠ peça final aprovada |
| 017 — publicação automática | BLOQUEADO | Nenhuma evidência de permissão e release para publicação externa |
| 018 — campanhas pagas | BLOQUEADO | Teto de gasto R$0; não ativar |
| 019 — CRM/leads | BLOQUEADO/CONDICIONAL | Dados internos e conversões efetivas indisponíveis; proxies não são leads |
| 020 — pesquisa competitiva | DOCUMENTADO | Pesquisa e benchmark externos disponíveis; nenhuma homologação de fornecedor alegada |
| 021 — adaptação/roteamento | NÃO COMPROVADO NA AUDITORIA | Requer benchmark contra baseline simples e replay |
| 022 — qualidade/ISO/live trace | IMPLEMENTADO_PARCIAL | RBAC, outbox, SSE, testes e gates; sem auditoria ISO ou release |
| 023 — Creative Studio | IMPLEMENTADO_LOCAL / PARCIAL AVANÇADO | PRs #35/#37–40, APIs de versões, canvas, páginas, vídeo, áudio, FFmpeg, 720p; sem produção editorial homologada |

## 5. Desvios documentais concretos e providências

| Local | Afirmação histórica/inconsistência | Evidência posterior | Tratamento recomendado |
|---|---|---|---|
| `README.md` cabeçalho e seção de aquisição | Afirma que nenhuma coleta externa real ocorreu | PR #36, `docs/45_...`: duas execuções reais e 3 registros técnicos | Corrigir cabeçalho e qualificar seção histórica; linkar este snapshot |
| `docs/00_MAPA_E_STATUS.md` | Fala de **22 CAP/12 DEC**, anterior ao v5.2 | Plano v5.2: **23 CAP/15 DEC/204 IMP** | Aviso de histórico; índice para 51/52, manter decisões de origem |
| `docs/17_STATUS_GATE0_ATUALIZADO.md` | Gate 0B totalmente bloqueado e nenhum grant externo | Grants técnicos e piloto A2/A3; DEC-018 ainda pendente de formalização no PR #32 | Distinguir gate global de permissão por fonte/operação; não marcar G0B aprovado |
| `docs/16_ESCOPO_APROVADO_E_AUTORIZACOES.md` | `source_use_grants=NONE` e `operation_grants=NONE` como realidade atual | PR #33 e #36 mostram grants técnicos específicos e leitura limitada | Manter como registro histórico; diferenciar grants locais efetivos de direitos institucionais |
| `docs/23_ARQUITETURA_...v5_2` | CAP-023 e coleta real aparecem como não implementados em 30/10 | PRs #35–40 e #36 em 05/11 | Inserir adendo datado, **sem reescrever** a comparação histórica v5.1→v5.2 |
| `docs/24_PLANO_UNICO_...v5_2` | Plano é especificação, não estado do software; CSVs externos não sincronizados | Código pós-v5.2 e tarefas realizadas parcialmente | Link para matriz por evidências; futura sincronização dos CSVs com validador e sem reenumerar |
| `docs/30_...MPE...` | Descreve zero persistência e frame histórico v1 | `docs/33_...`, `docs/45_...` e PR #36 | Preservar cronologia, adicionar aviso para snapshot atual |
| `docs/43_TRILHA_B_...` | A seção B1 inicial registra MCP pendente | O próprio arquivo inclui seção B2 e PR #34 integrado | Ler B1 como histórico e B2 como incremento; agente completo segue pendente |
| PR #32 / `docs/41_DEC018...` | Documento proposto para decisão institucional | PR **aberto**, arquivo **não existe na `main`** | Não citá-lo como registro aprovado/versionado na main |
| PRs #27–31 | Experimentos/diagnósticos System One mais novos | PRs abertos e empilhados | Não incorporar números/funcionalidades na `main` antes de merge/QA |

## 6. Restrições que devem permanecer invariantes

1. **Fidelidade:** TAPI original e decisões verificáveis da instituição prevalecem na definição do aceite; planos de expansão não o revogam.
2. **Corpus:** `mpe_targeted` é atributo do **conteúdo**, não porte do autor, nem prova da composição real da audiência.
3. **Fontes:** C1 externo, C2 Instagram Stone, C3 Ads e C4 contexto editorial não devem compartilhar denominadores/identificadores sem vínculo real.
4. **Métricas:** `ER` oficial é descritiva; followers atuais são snapshot e não necessariamente os da publicação; CTR ≠ lead e visualizações ≠ impressões.
5. **Observabilidade:** nem legenda nem thumbnail isolados comprovam hook temporal, ritmo de cortes ou música; ausência é `unknown/not_observable`, nunca evidência fabricada.
6. **Direitos:** token e grant de API, permissão de persistência, processamento de mídia, redistribuição e publicação são operações distintas, com regras próprias.
7. **Design:** evidência e classificações originais são imutáveis em sua versão; `DesignDocument` editável e export são camadas derivadas.
8. **Segurança:** tenant/RBAC, idempotência, revogação, hashes, versionamento e `deny-by-default`; testes em SQLite isolado não são migração aprovada do banco de operação.
9. **Custos:** R$0; nada que gere despesa, campanha ou publicação é ativado implicitamente.
10. **Testes:** o PR #40 registra 358 testes Python e 7 Node sobre árvore publicada, mas **nenhum status de CI remoto** foi encontrado neste corte; quatro testes Python E8 ficaram fora do diff.

## 7. Política para alinhamento contínuo

- Qualquer PR de mudança de escopo, fonte, política, métrica, contrato ou aceitação deve atualizar **51 (decisões)** e **52 (matriz)**, associando SHA, diff e prova de teste; um PR puramente técnico atualiza os componentes atingidos.
- Estados **por capacidade** precisam indicar fonte, condição, commit, teste e gate; não converter a matriz histórica `NAO_IMPLEMENTADO` para `CONCLUIDO` em lote.
- Em divergência, abrir `DEC-XXX` ou ADR correspondente, sem silenciar a divergência. Não marcar direitos/aceite como resolvidos com base apenas em uma declaração.
- A sincronização agora inclui **quatro matrizes completas de capacidades/tarefas/decisões/gates e `DEPENDENCIAS.csv` no Git**, além dos deltas versionados e gerador determinístico em `planning/v5_2/audit_2026-11-05/` e `scripts/sync_plano_v52_audit.py`. Os **13 CSVs completos** constam do ZIP gerado nesta conversa; os outros oito não modificados permanecem disponíveis no ZIP, sem alegar que foram todos versionados individualmente. Conferir [docs/54](54_SINCRONIZACAO_MATRIZES_V52_DEC018_2026-11-05.md).
- O produto segue **uma entrega única** e não uma sequência de entregáveis independentes; as fases são gates internos.

## 8. Checklist verificável no próximo corte

- [x] Referências da arquitetura v5.2, decisão DEC-016, laboratório DEC-017, agente B2, A3 e Studio E3–E8 identificadas em Git.
- [x] Piloto A3 descrito com 3 publicações técnicas e ressalva explícita de não admissão científica.
- [x] Separação do material Stone (C2–C4) em relação ao corpus externo (C1) documentada.
- [x] PR #32 e #27–31 tratados como abertos, sem antecipar efeito na `main`.
- [x] DEC-018 documentada como dispensa de revisão humana **confirmada pelo responsável** (não requisito cumprido); confirmação documental institucional independente não disponível neste corte.
- [x] Commitados **quatro CSVs integrais**, o arquivo das **543 dependências**, seus deltas, manifesto e gerador reprodutível.
- [ ] Comprovar universo científico representativo, 20 atributos observados/avaliados, agente de três modos e cinco criativos.
- [ ] Rodar suíte e CI com HEAD exato, integrar testes E8 ausentes, verificar backup/migrações do banco real, E2E, direitos e release.

**Observação final:** este documento **não certifica completude** de cada linha de código do projeto; usa as evidências rastreadas na `main` e os PRs conhecidos até o SHA do corte.
