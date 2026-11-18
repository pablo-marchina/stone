# Protocolo científico e de engenharia de produto

**Base atemporal v6.1 — proposta documental.** Requisitos e hipóteses não são declarações de execução. Detalhes originais são parte desta base por remissão obrigatória ao mapa de seções; fatos datados ficam em `04_Snapshots/`.


## 1. Design Science Research e avaliação

DSRM: identificar problema/motivação; definir objetivos e métricas; projetar/desenvolver artefato; demonstrar em ambiente autorizado; avaliar; comunicar resultados e limitações. O artefato é a plataforma integrada. U01–U18 e oráculos integrais preservados nas matrizes. Engenharia baseada em evidências: para cada DEC formular pergunta, pesquisar com string/data/critérios de inclusão/exclusão, comparar fontes primárias, registrar risco de viés, shortlist e baseline, pré-registrar métrica/limiar/pesos, medir mesmo workload/hardware, Pareto custo/qualidade e rollback. Clean-room: observar comportamento público, não copiar código/ativos sem licença nem contornar controles.

DEC-018 substitui no plano interno a revisão humana independente por avaliação de engenharia com referências declaradas. Não falsificar anotadores, F1 sobre gold inexistente ou afirmar conformidade literal. Revisão editorial operacional de peça/publicação é distinta. Testes de usuário externos só se legitimamente disponíveis; sem eles, utilidade medida por oráculos de tarefa e checklist, não preferências humanas fabricadas.

## 2. Perguntas e hipóteses preservadas

RQ1 original v2: sobrerrepresentação de atributos no topo vs restante; v3 separa descritivo (central) de contraste opcional. RQ2 v2: estabilidade por criador/formato/estrato. Para evitar colisão de IDs, registrar os aliases v3 RQ1–RQ5 como RQv3-1 (frequências), -2 (contrastes), -3 (robustez), -4 (transferência editorial), -5 (contexto Stone). RQv3-4 adaptada à DEC018: checklist e provas de rastreabilidade, utilidade humana não comprovada.

| ID v2 | Hipótese | Experimento e condição |
|---|---|---|
| H1 | Texto+imagem melhora classificação vs texto | Mesma evidência quando comparar arquiteturas; ablação para modalidades; F1 por campo só com referência nomeada |
| H2 | Frames+transcrição melhoram atributos temporais vs thumbnail | Mídia autorizada; janela 0–3 s, temporalidade e erro |
| H3 | Recuperação híbrida supera SQL/filtros ou somente semântica | Query congelada; Recall@k/nDCG/MRR, p95 e direitos |
| H4 | Geração grounded supera sem referências | Brief pareado, exatidão de links e claims; sem avaliação cega independente |
| H5 | Roteamento adaptativo mantém/melhora qualidade/custo | Política fixa vs adaptativa; risco-cobertura, latência, custo total |
| H6 | Visualização de evidências melhora eficiência | Tarefas com/sem interface; medir se possível, não inventar SUS |
| H7 | Plataforma reduz tempo de briefing sem perder qualidade | Comparação real com fluxo Stone somente se disponível |

Extensões H1.a, H2.a, H3.a, H4.a, H5.a/b/c, H-INT.a, H6.a, H7.a na matriz de hipóteses. São subexperimentos, não substituem H1–H7 nem novos compromissos institucionais. Hipóteses EH-01–07 de marca separadas. Não renumerar IDs.

## 3. Protocolo observacional C1

População: posts direcionados a MPEs, não apenas produzidos por MPEs; formato Reels/carrossel prioritário, Shorts complementar sob política. Unidade primária publicação, cluster criador; medir distribuição por criador/estrato, categoria e janela. Definir seleção, atividade 12 meses, follower bands pequenos/médios/grandes (Aula 1: ≤10k, 10–100k, grandes; fixar fronteira não sobreposta), tipo de criador e setor independentes de porte econômico. Diferenciar relevância documental, identidade, grant, observação e elegibilidade por post. Registrar também negativos explícitos, desconhecido, motivo de ausência e paid_status unknown. Não selecionar apenas top posts para amostragem de contraste. Snapshots, timestamp e versão de fórmula; referência de volume 2–5 mil/≥30, déficit explícito. Estimar estabilidade de métricas, não presumir idade 14d suficiente.

ER=(likes+comments)/followers observado; exigir contadores válidos e >0 seguidores, manter ausentes como ausentes. Unidade de ranking por plataforma, universo, período, as_of. Usar top ceil(0,10*n) como regra proposta documentada como regra candidata no snapshot A6 e desempate determinístico com aviso de empate; documentar variante oficial. Frequências sobre top com n posts, n criadores, proporção observada/desconhecida. Contraste: diferença de prevalências e lift P(cat|top)/P(cat|base) só se ambos conjuntos avaliados; reportar denominadores, não converter desconhecido em negativo. Sensibilidade a falta de dados (limites sob hipóteses explícitas), idade 14/30/60, top 5/10/20%, exclusão criador dominante, intraperfil e ponderação por criador, formatos, estratos, paid_status, período. Jaccard de top conjuntos na população comparável, leave-one-profile-out. Bootstrap por criador quando clusters permitirem; não tratar posts do mesmo criador como independentes. Corrigir múltiplas comparações, pré-registrar análise, separar descobertas post-hoc e confirmatórias. Calcular poder com efeito e ICC quando dados permitirem; não prometer representatividade. Nenhum efeito causal ou conversão inferido de ER, CTR, views ou comentários.

## 4. Rubrica, observabilidade e referências

Manter exatamente os 20 campos do PDF. Envelope: observed/candidate, not_observable, not_applicable, uncertain/abstain e measurement_only separado; manter compatibilidade com enum real do código (mapeamento explícito, não alterar schema sem migração). Registrar modalidade, timecode/ROI/spans, hash, snapshot, modelo/revisão, método, motivo, rights_reference e evidência. Hook 0–3 s exige janela, CTA ao longo do vídeo, scores 0–10 exigem âncoras definidas; ritmo medida de cortes ≠ score. Alegação de prova social ≠ fato verificado; rosto ≠ empreendedor real. Não usar engajamento como feature para classificar conteúdo. `mpe_targeted` separado. Medição de performance e classificação têm universos distintos.

Níveis de referência: (a) fixture sintética/autorais com oráculo conhecido; (b) dados programáticos/metadados mensuráveis; (c) pseudorrótulos/model consensus; (d) avaliação real de cobertura/consistência sem verdade de referência; (e) referência independente legítima, indisponível sob DEC018. Relatar métricas conforme nível, não somar níveis. Separar splits por criador/tempo e deduplicar quase-clones/campanhas; congelar teste, ajustar apenas dev; dataset card, manifesto, versão de checkpoint e licença. Sem gold humano novo, F1/MAE em fixture mede apenas fixture, em pseudorrótulo mede fidelidade ao professor; concordância não comprova verdade. Calibração Brier/ECE depende de referência adequada; confiança não calibrada deve ser marcada. Avaliar cobertura e risco seletivo por campo e grupo, erro em desconhecido, falsos positivos em negativos, estabilidade ordem de alternativas, contradições e abstenção; não afrouxar gate para elevar cobertura.

## 5. Evaluation-Driven Development e experimentos

Pirâmide: schema/contrato; unitários positivos/negativos; integração DB/API/MCP e segurança; testes de modelo por campo e ablações; E2E jornada, browser/acessibilidade; carga/recuperação/ops; aceite institucional. Usar mesmo corpus, hardware, orçamento, versões e seeds. Pré-registrar alvo de não inferioridade e ganho antes de executar; sem pesos arbitrários pós-resultado. PASS de benchmark pequeno não é produção. Preservar resultados FAIL; não repetir para encontrar resultado conveniente. Pseudorrótulo e teacher/student: incluir máscara por campo, confidências e evidência, evitar ensinar atributos sem modalidade; medir custo de extração, treino, inferência, fallback e armazenamento, propagação de erros e drift. Direitos de treino distintos de processamento e retenção. Roteador só promove decisões com gate e rollback, nunca altera policy.

## 6. Qualidade ISO e operação

ISO/IEC 25010:2023: adequação funcional, eficiência de desempenho, compatibilidade, capacidade de interação, confiabilidade, segurança da informação, manutenibilidade, flexibilidade e safety. Matriz 23×9 (207) e 414 U×CAP preservadas, oráculos originais. ISO 25019, 25012/5259, NIST AI RMF e OWASP como referências, não certificação. Riscos: vazamento tenant, SSRF, XSS, prompt injection, cadeia de suprimentos, falhas de revogação, exposição de segredo, custos, deriva, falsa causalidade. Negação por padrão; verificar grant por ação/campo/finalidade/tenant/asset/revisão, expiração/revogação, quotas e armazenamento. Não expor raw dados privados no GitHub. Jobs idempotentes com leases/fencing, retry limitado, DLQ, cancelamento, backup e restore verificado, SLO/RPO/RTO medidos. RBAC e HTTPS fora loopback; logs redigidos; export e aprovação versão exata; sem publicação ou campanha automática.

## 7. Regras de liberação e evidência

G0-PERMISSIONS, G1-CONTRACT, G2-REPRODUCIBILITY, G3-EVAL, G4-SECURITY, G5-OPS, G6-ISO. O estado de cada gate é consultado no registro de execução mais recente; por padrão não liberado. G0 bootstrap histórico não prova gate global. `release_manifest` deve identificar commit/árvore, contratos, versões, datasets/rights, métricas, testes, riscos, migrações/backup, políticas, custos, approvals, rollback e pendências. IMP-131 único aceite final. A00–A11 são sequência de engenharia, não entregas separadas. Não trocar evidência por contagem de testes.

## 8. Templates operacionais

Pré-registro: id, H/RQ, decisão/IMP, pergunta, referência e tipo, população, amostra, splits/seed, candidatos e baseline, inputs observáveis, métricas, critérios de aceitação e parada, hardware/custo, direitos/licença, riscos, resultado e interpretação, artefato/hash. Insight: coorte/as_of, denominador posts/criadores, contagens/unknowns, estimando, intervalo/limites, referência verificável, confusores e claim permitido. DEC: alternativas, fontes, gates, protocolo, resultados/Pareto, decisão, rollback, revalidação. Evidência de teste: SHA código, ambiente, comando, execução real ou reportada, contagem/pass/fail/skip, logs privados digest, escopo e limitação. O protocolo original v2 e revisão v3 preservam detalhes e referências históricas; em conflito, esta consolidação proposta resolve por DEC-016–018 e separação de estados.

## Anexo: patamares históricos de engenharia a preservar e reavaliar
### 5.4 Gates quantitativos **propostos, NÃO oficiais**

| Gate | Métrica e patamar inicial proposto | Exigência de evidência |
|---|---|---|
| G0 Fonte | 100% dos fluxos ativos com permissão/retenção documentadas | Approval register e matriz fonte × uso |
| G1 Dados | 100% IDs rastreáveis; nenhum valor numérico negativo; ausência de campos críticos medida, não ocultada; duplicatas resolvidas | Suite de testes e relatório de cobertura por fonte |
| G2 Rubrica | 100% JSON validável; 0 atribuições assertivas a campos `nao_observavel`; mínimo formal de 50 revisões | Gold e relatório por campo; meta inicial macro-F1 >=0,80 nos campos-chave, **sujeita a piloto** |
| G3 Evidência | 100% IDs citados existem na base; 100% de cálculos de referência conferidos com SQL | Testes exatos por consulta |
| G4 Recuperação | Recall@5 >=0,85 inicialmente em gold relevante, condicionado a baseline; p95 observado | Comparação de índices e consultas |
| G5 Agente | 100% modos/schema válidos; nenhuma consulta SQL inventada; groundedness >=0,95 em conjunto avaliado | Testes de trajetória, verificação automática e auditoria humana |
| G6 Produto | P95 de consulta tabular <2s em carga-alvo proposta; streaming de estado inicial <3s quando infraestrutura permitir; UX e acessibilidade testadas | k6/Playwright, baseline de carga explícito |
| G7 Produção | 0 vulnerabilidades críticas abertas; backup/restore e rollback testados; autenticação/segregação; incidentes e alertas instrumentados | Relatórios operacionais e teste de recuperação |

**Atenção:** patamares acima são hipóteses de engenharia, não métricas atingidas nem requisitos da Stone. Sem volume, hardware e usuários reais não é correto declarar SLO final. Portões podem ser mais rigorosos para dano crítico e ajustados via processo registrado **antes** de examinar o holdout. Ausência de evento negativo em poucos testes não prova risco zero.



Os nomes G0–G7 acima são **camadas de avaliação da metodologia v2**, não IDs de gates globais da arquitetura v5.2. Usar os sete IDs G0-PERMISSIONS a G6-ISO como autoridade de release. Na linha G2, referência ≥50 dispensada por DEC-018; na linha G5, auditoria humana independente não executável. Metas macro-F1, Recall@5 e groundedness dependem de referência declarada: em fixtures ou pseudorrótulos não provam qualidade científica real. Nenhum limiar é aprovado automaticamente por este anexo. As demais metas continuam candidatos pré-registráveis, sem inventar SLO de produção.

## Operacionalização da rubrica e contratos
Conforme doc 07, bins de duracao_faixa e limites de legenda_tamanho não foram fixados formalmente; não inventar enums, definir e versionar decisão antes de pontuar. `elementos_top5` admite até cinco quando há evidência; não preencher cinco obrigatoriamente por fabricação. Scores exigem âncoras comportamentais documentadas; a recomendação histórica de manual humano e concordância é limitada pela DEC-018, sem fingir validação humana. Envelope por campo inclui origem, modalidade, evidência, timestamp/ROI, observabilidade, modelo/prompt/versão, motivo de abstenção, e anotador somente se realmente existente. Conforme doc 03, `source_use_grant` não substitui contrato completo de endpoint; cada capacidade precisa request/response/error, validações cruzadas, ACL/tenant, idempotência, exceções, volume, versão, telemetria e testes positivos/negativos, com paridade OpenAPI/Pydantic/MCP. Não considerar placeholder capacidade operacional.
