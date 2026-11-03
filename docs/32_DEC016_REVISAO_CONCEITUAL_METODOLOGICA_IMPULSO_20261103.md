# DEC-016 (PROPOSTA) — Revisão conceitual e metodológica do TAPI após evidências Impulso Stone

**Data:** 03/11/2026  
**Estado:** `PROPOSTA_PENDENTE_DE_APROVACAO` — não altera o case oficial, escopo acordado no kickoff, flags, direitos nem contagens reais.  
**Referências:** `Proposta de TAPI_Stone_Inteli_Academy (1).pdf` §§2–6; `TAPI_Stone_Documento_Mestre_Referencia.md` §§1–5; `TAPI_Stone_Metodologia_Cientifica_Engenharia_Produto_REVISADA_v2_2026-10-22.md` §§0–5; `TAPI_Stone_Arquitetura_Revisada_v5_2_Changelog_2026-10-30.md` §§4–9; Plano Único v5.2; auditoria `auditoria_integral_impulso_stone_2026-11-03.md` (revisão de quatro páginas de Instagram Insights e 26 slides Meta Ads).

## 1. Erro de domínio encontrado

O case original pesquisa **publicações direcionadas a micro e pequenos empreendedores** — inclusive as publicadas por criadores, educadores, bancos/fintechs e marcas do setor —, e não exclusivamente publicações **de autoria de empresas juridicamente MPEs**. Audiência-alvo classificada por conteúdo não é audiência real comprovadamente composta de MPEs.

O schema `src/tapi_gate0/mpe_sources.py` hoje exige `size_band=micro|small` e `size_evidence_reference` de **toda** fonte aprovada. O `corpus.py` e o frame atual acentuam perfil/estrato de setor empresarial. Isso bloqueia perfis de especialistas/instituições que podem integrar legitimamente o universo oficial. O primeiro negócio priorizado (`@vaicomeroquee`) pode continuar como piloto de uma subamostra, mas não redefinir todo o corpus.

**Decisão proposta:** introduzir `source_frame.v2` e anotação de elegibilidade por conteúdo, distinguindo:
- `creator_type`: `mpe_business`, `independent_creator`, `educator_expert`, `financial_institution`, `fintech`, `sector_brand`, `sector_organization`, `other`;
- `content_audience`: `mpe_targeted`, `uncertain`, `not_mpe_targeted`, com evidência e status de revisão;
- `business_size_class` (micro/small/medium/large/unknown/not_applicable) **não universal**;
- `follower_band` (tamanho de audiência e instante observados, distinto de porte da empresa);
- `mpe_sector_context`, `content_topic_segment`, `format`, `platform`, `publication_age`, `paid_status`, `source_use_scope`, `sampling_stratum`, `observed_at`.

Direitos continuam exigidos por operação e finalidade. Essa proposta NÃO libera leitura não permitida nem autoriza persistência automática.

## 2. Evidências Stone que devem ser separadas do corpus externo

| Camada | Documento e unidade | Valor para TAPI | Não inferir |
|---|---|---|---|
| `C1_external_corpus` | Posts e perfis externos dirigidos a MPEs | Ranking oficial, rubrica, top10 e recomendações | 6 posts do alvo técnico `@instagram` não são corpus MPE |
| `C2_stone_instagram` | Relatório Instagram de `@impulsostone`; agregados 90 dias e ranking 180 dias | Perfil de audiência, temas, formatos, contexto editorial | 626.036 views não são 213.179 pessoas nem impressões Ads; 93,9% não seguidores ≠ MPEs |
| `C3_stone_paid_ads` | Deck Meta Ads, fevereiro–outubro 2026; campanhas/anúncios/criativos | Hipóteses sobre copy, CTA e distribuição paga | CTR ≠ leads; alcance de campanhas não é aditivo; não há spend, volume de leads, CPL/CPA |
| `C4_stone_brand_context` | Tom de voz, cinco pilares e referências a cinco parceiros | Condições de geração e avaliação editorial | Parceiros citados não têm impacto individual mensurado |

**Indicadores PDF reportados:** 626.036 visualizações na última captura (outra captura: 626.409), 213.179 visualizadores, 3.692 seguidores, +1.813 saldo; 93,9% views de não seguidores, Reels 52,5%, Stories 32,7%, Posts 14,7%, audiência feminina 70,5%, idades 35–54 somam 47,5%. As bases exatas de demografia e o número de posts por formato não foram fornecidos.

**Meta Ads:** duas campanhas principais 680.111 e 641.500 impressões somam 1.321.611 exibições, não alcance único. O deck seleciona dez fichas melhores e seis piores; uma arte reaparece sob outro posicionamento. O ranking por impressões contém linhas fora de ordem. O exemplo do setor beleza com 10.877 engajamentos e alcance 10.891 não significa que quase todas as pessoas interagiram (eventos podem se repetir). Há criativos com CTA explícito mas CTR baixo, contrariando uma generalização simplista. Dados são de contexto histórico, não experimento causal.

## 3. Métrica oficial: preservar, não substituir

- **Desfecho case:** `ER=(likes+comments)/followers`; selecionar top 10% com filtros/denominador/snapshot/empate/versão declarados.
- **Referência amostral:** 2.000–5.000 posts de 30+ perfis; publicações >=14 dias; Instagram Reels/carrosséis principal; Shorts complementar. `2k–5k` aparece como **volume de referência** no case — registrar déficit sem redefinir secretamente como regra de aprovação.
- `followers_observed_now` é medida na data de leitura, **não** na publicação; usar `followers_measured_at`, ressalvas temporais e análise de sensibilidade.
- Não somar CTR de anúncio, impressões, views, alcance ou engajamentos a taxas de seguidores. Definição de `engagement` e tipo de `click` ainda faltam.
- Ausência de dados financeiros/comerciais é `unknown`, **não zero**. Presença de CTA/um comentário não é lead observado.
- Comparações top/restante são opcionais no case, mas metodologicamente úteis **somente** quando a base de comparação também tiver anotações. Clusterizar por criador, analisar heterogeneidade por estrato/período e declarar inferência não causal.

## 3.1 Bloqueio de conteúdo observável no Business Discovery atual

O método `BusinessDiscoveryProbe._fields` e o sampler `mpe_evidence.py` **não solicitam `caption`, thumbnail, frames, áudio ou transcrição**. Os campos efetivamente coletados identificam fonte/ID, URL, tipo, data, curtidas, comentários e seguidores, permitindo apenas elegibilidade **técnica de idade/métricas**. Eles **não demonstram** por si que o conteúdo da publicação é dirigido a MPEs, nem permitem classificar campos da rubrica multimodal que dependem de visualizar o post.

Antes de contar um post no corpus de pesquisa, separar três estados:
- `technical_metrics_eligible`: formato, idade, ID e métricas verificáveis;
- `research_content_eligible`: conteúdo direcionado a MPEs comprovado por anotação/evidência autorizada;
- `rubric_observable`: campos da rubrica com modalidades realmente acessíveis, os demais marcados `not_observable`.

O uso de legendas, thumbnails, transcrições ou frames requer rota tecnicamente compatível e revisão específica de direitos. Não presumir que Business Discovery, por ter retornado seis mídias técnicas de @instagram, libera análise semântica/audiovisual de terceiros.

## 4. Rubrica, hipóteses e avaliação

**Preservar como núcleo:** 20 campos JSON/Pydantic, pelo menos 50 publicações revisadas por humanos, agente com modos `analisar|recomendar|gerar_criativo`, Python+MCP, playbook com >=5 propostas vinculadas a referências reais, demo e README. Multimodal só quando mídia/legenda autorizada estiver de fato observável: rótulos `observed|not_observable|not_applicable`. Não atribuir nota de ritmo/cortes ou rosto com texto isolado.

As peças Stone formam **hipóteses exploratórias e pós-hoc**, não evidência causal, por exemplo:
1. convites participativos vs outro CTA;
2. conteúdo prático (precificação, pós-venda, gestão) vs mensagens amplas;
3. alinhamento setorial, história real e calendários;
4. presença de CTA vs sua clareza/contexto;
5. diferença entre o mesmo tema em público/objetivo/placement distintos.

Exigir amostra não selecionada pelo resultado, comparação com baseline, divisão por criador/creative para evitar leakage, observabilidade e revisão humana da utilidade à Stone. Pilares do PDF: educação financeira; gestão/vendas; histórias reais; especialistas; comunidade. Podem virar `StoneBrandContext`, mas não substituir silenciosamente campos da rubrica oficial.

## 5. Dicionário de métricas e linkage obrigatórios para fonte interna

Criar contratos candidatos `metric_dictionary.v1`, `stone_historical_source_card.v1`, `editorial_context.v1`. Cada observação deve ter entidade, plataforma, `metric_name`, definição nativa, `value`, unidade, `window_start/end`, `observed_at`, filtros, paid-status, granularidade e qualidade da medição.

Para cruzar post `@impulsostone` com anúncio, solicitar IDs `ig_media_id`, `ad_id`, `creative_id`, placement, datas e definição da métrica. A coincidência de título — “Empreendedor(a)...”, “Festa Junina”, “Vendeu? E agora?” — não autoriza um JOIN nem o cálculo de impacto. Materiais Stone são **referências secundárias internas**; não transformar slides em registros brutos ou gold.

## 6. Impacto proposto no plano e na implementação

| Prioridade | IDs afetados | Critério de revisão |
|---|---|---|
| P0 | CAP-001, IMP-164–167, DEC-005, U18 | Novo contrato de público/creator, direitos por operação; testes positivos para criador/fintech voltado a MPEs e negativos para conteúdo fora do tema |
| P0 | CAP-002, IMP-166/168, U03 | ER oficial + top10 reproduzível; incerteza do denominador contemporâneo, paid_status, variações 14/30/60d |
| P0 | CAP-001/008, IMP-170 | Data card distinto para fontes relevantes, autorizadas, posts elegíveis, anotados e revisados; não equiparar candidatos a corpus |
| P0 | CAP-003/004, U04 | 20 campos, >=50 revisões, evidência por campo, negativos e `not_observable` |
| P0 | PR #20, G0-PERMISSIONS | Manter draft/flag OFF; antes do merge revisar semântica, direitos, lotes parciais, RBAC, checkpoints e testes em main |
| P1 | CAP-005/006/007, U11/U16 | Cinco criativos rastreáveis, consistência com marca Stone, linguagem e afirmações proporcionais ao suporte |
| P1 | CAP-019/022; IMP-154 | Contexto histórico Stone e métricas internas versionadas, sem fundir bases |
| P2 | CAP-023, mídia paga/publicação/CRM opcionais | Não travar núcleo, não executar efeitos externos sob R$0 sem autorização |

**Não mudar aqui:** `MATRIZ_REQUISITOS.csv`, `MATRIZ_CAPACIDADES.csv`, `BACKLOG_UNICO_IMPORTAVEL.csv` ou schema produtivo sem decisão aprovada. Após a revisão, versionar as matrizes preservando IDs e status históricos; nenhum post real ou permissão pode ser fabricado.

## 7. Gates e prova mínima desta revisão

- Documento fonte e seu hash/versionamento, classe de evidência e limites.
- Testes do schema de fontes com criadores/bancos/fintechs, MPE produtora e conteúdo irrelevante; nenhuma inclusão baseada só em followers ou em porte empresarial.
- Data card e ranking reproduzíveis no mesmo snapshot, com faltantes e estratos.
- Avaliação humana >=50 sobre posts reais elegíveis, não sobre as 16 peças selecionadas como melhores/piores.
- Agente retorna referências verdadeiras, recusa claims sobre leads/ROI quando essas métricas não existem, gera >=5 criativos para a marca e esclarece incerteza.
- Corpus atual continua **0 posts reais**; PDF/PPTX não contam como corpus.

## 8. Decisões pendentes

1. Confirmação formal do recorte `conteúdo direcionado a MPEs` versus eventuais orientações posteriores do kickoff.
2. Classificador e evidência para conteúdo direcionado a MPEs e seleção dos estratos.
3. Direitos de uso/retensão/redistribuição dos materiais internos Stone e disponibilidade de exportações oficiais por ID.
4. Definição institucional de tolerância do volume de referência e critérios de aceite.
5. Liberação real da persistência de terceiros **somente após** correção semântica e revisão de riscos.

**Conclusão:** a auditoria da Stone reforça valor editorial e complementa o contexto, mas o TAPI deve permanecer um sistema de inteligência de conteúdo dirigido a MPEs. Corrigir primeiro o universo e a medição; só depois expandir coleta e persistência.
