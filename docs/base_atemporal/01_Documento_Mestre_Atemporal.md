# Documento mestre — TAPI Stone × Inteli Academy

**Base atemporal v6.1 — proposta documental.** Requisitos e hipóteses não são declarações de execução. Detalhes originais são parte desta base por remissão obrigatória ao mapa de seções; fatos datados ficam em `04_Snapshots/`.


## 1. Propósito e escopo

Case institucional original: projeto individual de quatro semanas, entrega presencial prevista para 25/11/2026 (marco histórico fixo). A pergunta central é quais características de conteúdo, formato e criador aparecem entre as publicações de alto engajamento **voltadas a MPEs**, e como transformá-las em criativos úteis para a Stone. Público: lojistas, prestadores de serviço e autônomos. O Impulso Stone é o contexto editorial de impacto; o empreendedor é também usuário final de um playbook educativo. Não identificar audiência individual como MPE com base somente em perfil, nem exigir que quem publica seja MPE. Criadores, educadores, instituições financeiras, fintechs, marcas e organizações do nicho podem integrar a amostra mediante evidências e direitos.

O PDF original indica kickoff em 26/10; a Aula 1, lida na Biblioteca (32 páginas, p.1), informa 28/10. Entrega 25/11 em ambos. Data realizada não confirmada por ata. A proposta original §4.1 menciona LangGraph, mas §8 diz que nenhuma tecnologia é obrigatória. Preservar LangGraph como candidato prioritário a validar por contrato e benchmark, não inferir exigência exclusiva de stack. A Aula 1 p.23 reconhece riscos e incompatibilidades dos scrapers com os termos; a política ativa continua rota oficial autorizada.

## 2. Compromissos institucionais e evidências

| Entregável | Conteúdo / oráculo de aceite | CAP |
|---|---|---|
| Base documentada | Fonte, licença, período, volumes, perfis, critérios, lacunas, proveniência; referência 2.000–5.000 posts, 30+ perfis, idade ≥14 dias | 001 |
| Mapeamento | ER normalizado, top decil, 20 campos, frequências e criadores, exemplos reais, limitações | 002–004, 008, 012 |
| Agente | analisar/recomendar/gerar_criativo, referências reais, Pydantic, função Python e MCP, erros/abstenção | 005,006,009 |
| Playbook | Padrões e ao menos 5 propostas originais com gancho, roteiro, legenda, CTA, links e ressalvas | 007,010,014,023 |
| Demonstração | Jornada executável real de análise, referência, criativo e justificativa; sem dados inventados | 005,006,022,023 |
| README | Método, arquitetura, execução, resultados, limitações e evolução | 022 |

Base prevista até fim da primeira semana (marco original); volume é referência e não garantia de representatividade. Sete critérios originais: qualidade/documentação da base; coerência técnica; rigor da categorização; aplicabilidade; riscos/vieses; reprodutibilidade; apresentação. Pesos não publicados. DEC-018: ≥50 revisões humanas do case original foram dispensadas por decisão comunicada pelo responsável (04/11), não executadas, instrumento externo não anexado. Não há revisores independentes nem validação científica independente; usar avaliação de engenharia e declarar limitações. Aprovação editorial de publicação, se um dia autorizada, é controle operacional distinto, não revisão científica.

## 3. Escopo ampliado, níveis e restrições

Nível mínimo da Aula 1: coleta/ranking, legenda + thumbnail, playbook. A tabela do PDF §3 descreve multimodalidade leve com thumbnail ou frames, transcrição e VLM; preservar a diferença de formulação entre as duas fontes, sem eliminar a ambição recomendada. Recomendado: frames, transcrição, rubrica completa e referências. Avançado: contraste top/restante, RAG e comentários. CAP-001–007 núcleo; 008–014 opcionais (contrastes, RAG, avaliação de criativos, comentários, segmentação, calendário, lojista); 015–019 fora do case, condicionais (predição, produção final, publicação, anúncios, CRM); 020–022 transversais (benchmark, adaptatividade, qualidade/live); 023 Creative Studio adicional, aprovado pelo responsável. Aula 1 p.30: embaixador, collab, piloto orgânico 1–2 peças, playbook lojista e painel. Não converter extras em requisito institucional. Produção final audiovisual não é obrigação original; o editor agrega valor sem substituir o playbook. Publicação, anúncios, CRM e qualquer acesso não autorizado continuam bloqueados. Nenhum gasto, cobrança automática, cartão ou quota faturável. Custos locais de CPU/GPU/disco/energia mensuráveis.

## 4. Quatro conjuntos independentes

C1: corpus externo de conteúdo dirigido a MPEs, único denominador do ranking externo. C2: diagnóstico de Instagram próprio Stone, janelas e métricas específicas. C3: anúncios pagos históricos, seleção de extremos; CTR/alcance/impressões não equivalem a ER ou conversão. C4: contexto qualitativo/voz de marca e hipóteses editoriais. Não combinar universos, nem cruzar título aproximado como chave. IDs ig_media_id/ad_id/creative_id e janela/placement/timezone necessários. Engajamento, intenção e conversão são distintos. CTA e texto de comentário são proxies, não lead registrado. Leads, CPL, CPA e conversões indisponíveis = desconhecido.

## 5. Dados e análise

Separar candidato documental, identidade técnica, autorização por conta/operação, observação técnica, post dirigido a MPEs, observabilidade por campo e validação. `source_frame.v2` considera creator_type, audience targeting e evidências, business_size_class (inclusive unknown/not_applicable), follower_band, setor, formato, idade, paid_status e grants. O tamanho econômico não decorre de seguidores. Usar data card com contagens e motivos por fonte, estrato e modalidade. Guardar observação de seguidores no instante de coleta. ER=(likes+comments)/followers; excluir ausentes ou denominador zero, nunca imputar; top 10% com regra de arredondamento/desempate e coorte/as_of. Idade ≥14 dias reduz imaturidade, não garante estabilização. Comparação top/restante requer rótulos em ambos, denominadores e controle de criador. Não inferir causalidade.

## 6. Rubrica e agente

Preservar 20 campos: tipo_post; duracao_faixa; formato_video; hook_primeiros_3s; tipo_hook; forca_hook_0a10; tema_principal; tem_rosto; criador_e_empreendedor_real; prova_social; texto_na_tela; legenda_tamanho; ritmo_cortes_0a10; tom; usa_linguagem_regional; clareza_mensagem_0a10; tem_cta; tipo_cta; oferta_ou_beneficio_explicito; elementos_top5. JSON fixo; envelope auxiliar de observabilidade, fontes e hash/locators. Não inferir ausência no vídeo a partir de legenda. Pontuações exigem âncoras. Campos desconhecidos e não aplicáveis distintos. A audiência MPE é uma decisão separada dos 20.

Entrada formal do agente: `mode` ∈ analisar/recomendar/gerar_criativo; `query`; `segment` opcional; `filters` opcional. Saída: `findings`, `reference_posts`, `creatives`, `confidence_flag`, `explanation`; validação Pydantic. Referências contêm IDs/links/snapshots e categorias reais quando autorizadas. Sem suporte suficiente, abster/collect_more_evidence. Criativos contêm gancho, roteiro, legenda e CTA originais, vinculados a evidência e hipóteses, não copiar criativos de terceiros. Expansão visual: CreativeSpec → DesignDocument → revisões → render → aprovação da versão exata → export. O usuário edita sem IA; sugestões de IA são patches validados e reversíveis.

## 7. Critérios internos e visão de produto

U01 DSR/rigor; U02 operação real; U03 quantitativo válido; U04 EDD; U05 adaptatividade medida; U06 frontend/live; U07 melhores escolhas mediante benchmark; U08 pesquisa sistematizada; U09 avanço útil; U10 funcionalidades; U11 qualidade E2E; U12 opcionais; U13 extras condicionais; U14 ISO; U15 eficiência de recursos; U16 absorção da pesquisa; U17 clean-room; U18 dados úteis/autorizados. Texto integral e oráculos na matriz `MATRIZ_REQUISITOS.csv`. Nenhum U pode ser apagado por replanejamento. O produto é monólito modular com workers e uma jornada única. Stone-S1 é hipótese integrada a CAP-003/005/021/022, não modelo existente. Roteador decide quando regras, modelos de decisão ou LLM/VLM agregam valor; autorização nunca é decidida por IA.

## 8. Fonte de verdade e continuidade
O GitHub e os relatórios operacionais são evidência do as-is, nunca nova especificação por implicação. Consultar o snapshot identificado e o HEAD/PRs atuais antes de desenvolver. As exigências de prazo do case permanecem históricas, não são um relógio móvel. Preservar a ambição completa e avaliar dependências e recursos sem recortar escopo. A DEC-018 vigora no escopo comunicado até alteração/revogação expressa; não solicitar novamente aprovação institucional genérica. Direitos técnicos efetivos por fonte, finalidade, ativo, ação, retenção e licença seguem obrigatórios. Ver registro normativo e índice de precedência.

## Anexo normativo de compatibilidade: rubrica e contrato institucional
### A. Rubrica integral de categorização multimodal (Mestre original §7)

**[FONTE — pp. 5–6, §6.2]** O modelo VLM/LLM deve retornar **JSON fixo**. Existem oito grupos e 20 campos de classificação; os nomes são preservados abaixo.

| Grupo | Campos | Categorias explicitadas no TAPI |
|---|---|---|
| Formato | tipo_post; duracao_faixa; formato_video | tipo_post: reels, carrossel, imagem, short; formato_video: talking head, tutorial, bastidores, antes/depois, humor/esquete, depoimento, lista/dicas, trend |
| Gancho | hook_primeiros_3s; tipo_hook; forca_hook_0a10 | tipo_hook: pergunta, promessa, dor, número, polêmica, curiosidade |
| Tema | tema_principal | vendas, finanças, marketing, atendimento, gestão, motivação, ferramentas/maquininha, história de empreendedor |
| Pessoas | tem_rosto; criador_e_empreendedor_real; prova_social | Sem valores fechados descritos para esses campos |
| Texto e edição | texto_na_tela; legenda_tamanho; ritmo_cortes_0a10 | Sem categorias fechadas para legenda_tamanho |
| Linguagem | tom; usa_linguagem_regional; clareza_mensagem_0a10 | tom: informal, técnico, inspiracional, humorístico |
| Conversão | tem_cta; tipo_cta; oferta_ou_beneficio_explicito | tipo_cta: comentar, salvar, link na bio, DM, seguir |
| Síntese | elementos_top5 | Cinco principais elementos identificados |

**Campos terminados em 0a10:** notas numéricas de zero a dez. O PDF não define âncoras detalhadas ou categorias adicionais. Não inventar defaults como se fossem requisitos originais.


### B. Contrato da ferramenta e requisitos do agente (Mestre original §9)

### 9.1 Entrada formal do TAPI

| Campo | Tipo lógico sugerido | Situação |
|---|---|---|
| mode | enum: analisar, recomendar, gerar_criativo | [FONTE] |
| query | texto: pergunta ou objetivo | [FONTE] |
| segment | texto/enum opcional de público ou setor | [FONTE] |
| filters | objeto opcional de plataforma, período e tamanho de perfil | [FONTE] |

### 9.2 Saída formal do TAPI

| Campo | Significado | Regra de qualidade sugerida |
|---|---|---|
| findings | Características recorrentes e frequências | Mostrar contagens e denominadores |
| reference_posts | Links, métricas e categorias das publicações usadas | IDs e URLs devem existir na base |
| creatives | Gancho, roteiro, legenda e CTA, com fontes | Vincular referências a cada criativo |
| confidence_flag | Aviso de sustentação por poucas publicações | Definir critério operacional documentado |
| explanation | Explicação em linguagem natural | Separar evidências de inferências |

**[FONTE]** Entradas e saídas validadas com Pydantic; execução registrada; integração por função Python e servidor MCP. **[ANÁLISE]** Configurar respostas coerentes por modo: `analisar` pode retornar `creatives=[]`; `gerar_criativo` não deve omitir evidências de suporte.

### 9.3 Regras sugeridas para `confidence_flag`

**[PENDENTE]** O documento exige o campo, mas não define sua regra. **[ANÁLISE]** Adotar níveis descritivos com limiares definidos após verificar distribuições da amostra. Considerar número de posts, diversidade de autores, percentuais de dados ausentes e concordância na classificação. Não chamar esse indicador de probabilidade estatística se ele for uma heurística.

### 9.4 Testes do agente

- Consulta quantitativa: resultado coincide com query determinística para o mesmo filtro.
- Referência: todo `reference_post` possui ID, URL e métricas rastreáveis.
- Criativo: contém gancho, roteiro, legenda e CTA e não reproduz indevidamente texto de terceiros.
- Incerteza: informa baixa base amostral e ausência de mídia em vez de alucinar.
- Contrato: rejeita modos inválidos, filtros incoerentes e JSON fora do schema.
- Execução: logs e parâmetros permitem entender qual informação levou à resposta.


Os títulos e categorias acima são transcrição do Documento Mestre original; seu §7.2 de revisão humana permanece histórico e é superado operacionalmente por DEC-018.
