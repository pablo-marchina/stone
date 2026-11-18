# Pesquisa técnica consolidada — atualização e agenda

**Base atemporal v6.1 — proposta documental.** Requisitos e hipóteses não são declarações de execução. Detalhes originais são parte desta base por remissão obrigatória ao mapa de seções; fatos datados ficam em `04_Snapshots/`.


## 1. Método e base preservada

A pesquisa v2 (22/10) examinou preprint Understanding Virality, estudos Instagram/YouTube, APIs, segurança, multimodalidade, estatística, agentes e Stone. A evidência é histórica: os links e versões de outubro não são afirmações de atualidade. Seu texto integral é parte da referência obrigatória em `02_Referencias_Integrais`. Pesquisa externa desta atualização concentra-se nos modelos de decisão e embeddings; licenças, quotas, política de armazenamento e versões de API devem ser revalidadas antes de uso. Classificar evidência como paper, documentação primária, alegação de fornecedor, código observado, execução reportada ou hipótese.

## 2. Aquisição e conformidade

Instagram Business Discovery oficial é candidato operacional e já teve execução histórica documentada para metadados e legenda opcional. A rota deve respeitar termos, grants, limites e versão Graph; não presumir acesso a vídeo ou comentários de terceiros. YouTube Data API v3 é complementar; antes de ativar, verificar quotas atuais, regras de armazenamento/refresh, agregação entre proprietários, métricas derivadas, classificação Shorts, acesso a captions e direitos de mídia. Não reutilizar a recomendação yt-dlp do PDF como permissão. Não usar scraping em violação de termos. Repositórios de ferramentas de scraping são fontes de padrões clean-room, não autorização. Dados Stone C2–C4 não pertencem ao corpus externo.

## 3. Evidência científica e multimodal

Understanding Virality fornece inspiração para rubrica audiovisual/engajamento, não validade externa em MPEs brasileiras. Multi-Pop estuda heterogeneidade de criadores; Getting the Recipe Right motiva combinações; VidHalluc alerta para erros temporais e alucinações. Os estudos observacionais não comprovam causalidade. Comparar extração determinística, ASR, OCR, VLM e decisão tipada por campo. Priorizar FFmpeg/ffprobe, Silero VAD, faster-whisper Medium e Tesseract Best como baselines experimentais locais (resultados no catálogo). VLM Qwen3-VL-2B teve avaliação reprovada no snapshot de referência; não promover sem nova evidência. Alternativas: CLIP/SigLIP, DINO, V-JEPA para embeddings visuais/temporais, ainda não testadas no TAPI. Uma imagem não comprova contexto temporal, identidade profissional ou ausência de CTA. Áudio convertido em texto perde prosódia e informação acústica.

## 4. System One e modelos de decisão

| Candidato | Evidência / proposta | Limite |
|---|---|---|
| GLiNER2.5-multi-Decide | 287M, encoder textual multilíngue, model card Apache-2.0; já experimentado | Benchmark fornecedor em inglês; cobertura PT-BR TAPI insuficiente |
| Valen-Decision-1.5 | Fornecedor disponibiliza 0.8B/2B/4B/9B/27B, texto/imagem/vídeo, choice/noul/score/bbox, pesos e código SFT | 0.8B/2B candidatos; runtime GGUF custom documenta texto/imagem, vídeo deve ser verificado por runtime; não confundir código Apache-2.0 com licença de pesos/dados |
| Jev | Referência de interface tipada, não confundir com JEPA | Acesso e custo/termos não comprovados; sem envio de conteúdo real |
| SubQ Snap | Modelo de decisão texto/imagem de contexto longo; v1.2 anunciada 11/11 | Serviço comercial, lançamento v1.0 anunciava cobrança; bloqueado R$0 sem comprovação de não faturamento |
| Laya Multilingual | Candidato de comparação textual | Identidade exata/checkpoint/licença/benchmark ainda a confirmar; não instalar por nome |
| Clef / variantes | Candidatos mencionados na análise anterior | Não revalidados nesta rodada; não tratá-los como disponíveis/adequados |
| BERTimbau/BERTabaporu | Encoders PT-BR para classificação e intenção | Necessitam dados e avaliação de domínio; não garantem transferência para Instagram |

Valen 1.5: documentação do fornecedor em https://valen-team.github.io/docs/valen/ e https://github.com/Valen-Team/Valen (09–10/11), card https://huggingface.co/Valen-Team/Valen-Decision-1.5-0.8B-GGUF (Q8_0 cerca de 830 MB de arquivo, não RAM total). Transformers exemplo usa CUDA; ONNX CPU e runtime GGUF próprio candidatos. Não executar `trust_remote_code=True` sem auditoria, pinagem e ambiente restrito. SubQ Snap: https://subq.ai/introducing-subq-snap e https://subq.ai/subq-snap-1-2. GLiNER: https://huggingface.co/fastino/GLiNER2.5-multi-Decide. Métricas anunciadas não equivalem a desempenho no TAPI. Não confundir SubQ LLM original (contexto longo) com Snap (decisões), nem Jev com JEPA (representação latente).

## 5. Retrieval e treinamento

E5 multilingual (https://arxiv.org/abs/2402.05672) oferece small/base/large; BGE-M3 (https://arxiv.org/abs/2402.03216) é candidato denso/esparso/multivetorial; comparar baseline TF-IDF/FTS, vetorial exata e RRF/rerank. Índice de mil posts não exige serviço vetorial gerenciado. Verificar licença do checkpoint e direito de gerar/armazenar embeddings e revogar derivados. Separar relevância, performance e qualidade de evidência; reranking não altera ranking ER. Avaliar consultas com relevância de referência explicitada, diversidade e fidelidade das citações.

Destilação: Hinton et al., https://arxiv.org/abs/1503.02531; weak supervision e Snorkel, https://arxiv.org/abs/1711.10160; calibração Guo et al., https://arxiv.org/abs/1706.04599. Pseudorrótulos de professores não são gold. Comparar LogReg/SVM/CatBoost/MLP multi-head sobre encoders congelados antes de LoRA. Não usar métricas de engajamento para classificar rubrica nem treinar com dados sem direito explícito. BERTimbau e BERTabaporu: localizar revisão oficial e dataset/license antes de treinamento. Distinção entre intenção de contato e conversão obrigatória.

## 6. Agentes, software e produção

LangGraph candidato para orquestração de ferramentas e checkpoints; MCP B2 no corte inicial usava JSON-RPC stdio, versão 2024-11-05, três ferramentas. Comparar SDK MCP atual com adapter, autenticação/contratos/tenant e avaliação adversarial. SQL/Python produz estatísticas, LLM sintetiza sem inventar. System One seleciona decisões tipadas; System Two planeja e gera. Open-source não significa licença compatível nem custo zero de operação. React/Vite, PostgreSQL/pgvector, OTel, Fabric/Konva, Motion Canvas, FFmpeg e ComfyUI são candidatos sujeitos ao benchmark. Usar dependências locais já comprovadas como baseline e reduzir complexidade; não impor Kubernetes, broker ou GPU paga.

## 7. Agenda de decisões

DEC-005 direitos; DEC-006 retrieval; DEC-007 modelos; DEC-008 agente; DEC-017 decisões tipadas. Gate técnico/legal precede comparação. Congelar hardware, dados, splits, checkpoints, prompts e thresholds; medir p50/p95, RSS/VRAM, disco, throughput, energia, cobertura, erro, latência end-to-end e custo de treinamento/preprocessamento. Adotar somente ganho comprovado com rollback. Ver Stone-S1 e catálogo. A pesquisa v2 integral é referência obrigatória, inclusive bibliografia, auditoria de quotas, políticas e limitações; o benchmark competitivo é separado. O registro de cada inferência, download e resultado pertence a snapshots e catálogos datados.

## Regra permanente de pesquisa
Nenhuma ficha de modelo, versão, licença, preço ou quota histórica constitui verificação atual. Antes de decisão/uso, revalidar documentação primária e registrar data, versão, licença de código e pesos, hardware, escopo de dados, custo, resultados e lacunas. Reusar todos os detalhes de pesquisa v2 que não conflitem com DEC-016–018. Modelos são candidatos substituíveis; a função de decisão tipada permanece.
