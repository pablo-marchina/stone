# TAPI Stone — Creative Studio editável e stack-alvo unificada

**Natureza:** proposta arquitetural registrada a pedido do responsável; **não é implementação concluída nem decisão homologada por benchmark**. Integra a Arquitetura Unificada v5.1 e o Plano Único, sem substituí-los nem criar entregas independentes. **Orçamento de caixa obrigatório: R$ 0**, incluindo licenças, APIs, hospedagem e publicidade; processamento local tem custos físicos/operacionais e depende de hardware disponível.

## 1. Intenção e cobertura

Preservar os seis entregáveis do case: (1) base documentada, (2) ranking, categorização e mapeamento, (3) agente Python e MCP com referências, (4) playbook e >=5 criativos, (5) demonstração executável ponta a ponta, (6) README reproduzível.

Preservar as CAP-001..CAP-022 formais, opcionais, ampliadas e transversais conforme `tapi_plano_unico_consolidado/MATRIZ_CAPACIDADES.csv` de referência. A nova proposta **CAP-023 — Estúdio criativo visual editável** conecta CAP-005, 007, 010, 013, 014, 016, 017, 019 e 022. CAP-023 e as tarefas IMP-163+ são **candidatos**, ainda não inseridos nas matrizes oficiais; a incorporação exigirá atualização atômica de capacidades, backlog único, dependências, ISO 23x9, critérios, contratos, domínio, testes e gates, sem perder as linhas anteriores.

A proposta de aula para ir além — embaixador, collab, piloto, playbook de lojista e painel interativo — é incorporada ao fluxo editorial, sujeita às parcerias/autorizações reais.

## 2. Jornada única do produto

`fontes autorizadas → corpus e qualidade → ranking top 10% + comparação top/restante → rubrica multimodal/50+ revisões → padrões e busca fundamentada → agente analisar/recomendar/gerar_criativo → brief e script → composição visual editável → revisão humana e variantes → exportação → aprovação → publicação orgânica autorizada ou download → mensuração e aprendizado`.

O usuário pode interromper, editar, duplicar, reverter ou exportar antes de qualquer efeito externo. **Prévia de publicação não equivale a previsão de engajamento, entrega real ou publicação feita.** Previsão (CAP-015) só aparece se houver avaliação de calibração; resultados comerciais não podem ser inferidos de curtidas.

## 3. Requisitos funcionais do Creative Studio

- **Formato:** post imagem (feed), carrossel multipágina, story, capa de Reels, vídeo vertical/Reels/YouTube Shorts, variantes A/B, formatos personalizados. As exportações efetivas são compatíveis com as capacidades reais de cada canal.
- **Entrada:** brief, público MPE, segmento, identidade visual autorizada, referências reais, hipótese editorial, CTA, roteiro/legenda, duração, palavras proibidas e restrições de marca.
- **Geração:** primeiro produzir `CreativeSpec` validado; construir `DesignDocument` nativo com camadas editáveis. LLM/VLM não devolve diretamente instruções executáveis arbitrárias; toda geometria, tipo, fonte, cor, mídia e ação passam por validação de schema, direitos e limites.
- **Editor visual:** selecionar, arrastar, redimensionar, girar, agrupar, ordenar camadas, editar texto e tipografia, trocar mídia, alterar fundo, cores, alinhamento, máscaras, grids, guias, safe areas, idioma, dimensões e ordem dos slides; undo/redo, zoom e atalhos. Nunca exigir nova inferência para alteração manual.
- **Vídeo:** storyboard editável, cenas, texto, legendas, clipes autorizados, trilhas autorizadas, entrada/saída, duração, cortes, keyframes e timeline. Um editor temporal completo exige desenvolvimento adicional; não presumir paridade com softwares profissionais.
- **Modos:** geração assistida; controle manual sem IA; regenerar apenas a camada/slide/cena selecionada; aplicar sugestões sem sobrescrever edições; comparação A/B; histórico com restauração.
- **Saídas:** `DesignDocument` versionado (fonte principal), PNG/JPEG/SVG quando compatível, carrossel ZIP e vídeo MP4/WebM mediante renderização disponível, legenda/roteiro/CTA em texto, manifesto de fontes/ativos e pacote de exportação; formatos editáveis em produtos terceiros são opcionais e precisam de adaptadores reais, sem prometer PSD/Canva/Figma nativos.
- **Governança:** marca, direitos de cada recurso, autoria, proveniência, fontes, revisão editorial, aprovação explícita por operação externa, política de retenção/apagamento e imutabilidade das referências analíticas.
- **Compatibilidade:** viewer e editor devem ler o mesmo contrato; preview e exportação precisam de teste visual de equivalência e não podem fingir capacidades indisponíveis.

## 4. Contrato canônico proposto (esboço, não código implementado)

```json
{
  "schema_version": "design-document.v1",
  "document_id": "design.demo",
  "tenant_id": "tenant.demo",
  "creative_version_id": "creative.demo.v1",
  "canvas": {"width": 1080, "height": 1350, "background": "#FFFFFF"},
  "platform_intent": "instagram_feed",
  "pages": [{
    "id": "page.1",
    "duration_ms": null,
    "layers": [
      {"id":"layer.title","kind":"text","x":80,"y":120,"w":920,"h":160,
       "text":"Seu caixa está sob controle?","style":{"font_family":"licensed-font","font_size":72,"color":"#111111"},
       "origin":"ai_proposed","editable":true},
      {"id":"layer.media","kind":"image","x":80,"y":350,"w":920,"h":760,
       "asset_id":"asset.licensed.1","origin":"user_or_authorized","editable":true}
    ]
  }],
  "reference_ids": ["content.ref.1"],
  "rights_status": "pending_review",
  "approval_status": "draft",
  "source_document_version": 1
}
```

IDs acima são **ilustrativos**, não representam dados reais. O contrato definitivo precisa modelar tipos por discriminated union, transformação, propriedades temporais, limites, grupos, assets, hashes, crop, fontes, permissões, audit trail, export profile e migrations. **O JSON é fonte da verdade**, não o raster exportado. Alterações do usuário ficam em versões derivadas, jamais reescrevendo dados observacionais da pesquisa.

## 5. Stack-alvo recomendada (decisão ainda submetida ao DEC/benchmark)

| Camada | Tecnologia-alvo | Motivo e controle |
|---|---|---|
| UI do produto | React + TypeScript + Vite, Tailwind e componentes acessíveis | Compatibilidade com frontend existente; comparar Next.js na DEC-002 com CWV/TCO antes de migrar |
| Estado/API | TanStack Query, Zod, OpenAPI typed client, SSE existente | Dados reais e contratos tipados; WebSocket somente se colaboração simultânea exigir |
| Editor visual estático | **Fabric.js (MIT)** integrado à UI React | Objetos editáveis, manipulação, filtros, serialização JSON e SVG/PNG; benchmarking com React-Konva (MIT) para performance/editor |
| Texto rico | **Lexical (MIT)** | Legenda, roteiro, CTA e comentários editoriais com versionamento |
| Motion/video | **Motion Canvas (MIT) + FFmpeg**; timeline e edição próprias | Prévia e renderização de composições temporais; verificar codec/licenças, paridade preview-export e consumo |
| IA visual | **ComfyUI local** com modelos de pesos e licenças aprovados; fallback templates e assets próprios | Imagem opcional, nunca indispensável; modelos locais requerem GPU/VRAM; distinguir ComfyUI core de nodes pagos |
| VLM | **Qwen3-VL** candidato com licença verificada por peso, mais baseline determinístico atual | Frames/transcrição com avaliação per-field; custos físicos e hardware determinam viabilidade |
| ASR | faster-whisper/Whisper local ou equivalente após comparação | Transcrição permitida e avaliação de WER/Português |
| Agent | LangGraph, checkpoints persistentes, Pydantic + MCP Python SDK v2 (`MCPServer`) | Fluxos com revisão humana, tools restritas, referências imutáveis e testes MCP |
| API backend | **FastAPI/Pydantic/SQLAlchemy/Alembic** existentes | Reaproveitar contratos, identidade, RBAC, auditoria e SSE já implementados |
| Dados transacionais | PostgreSQL local após benchmark/integração real; SQLite local enquanto necessário | RLS/backup/restore não comprovados no estado atual |
| Busca | SQL+FTS inicialmente, **pgvector** se melhora Recall@k; DuckDB+Parquet se analítica off-line justificar | Evitar segundo banco vetorial sem ganho mensurado e sem vazamento de direitos |
| Execuções | outbox e jobs duráveis no Postgres; separar worker de render da API | Isolamento CPU/GPU, filas, retries, idempotência, no duplicated export |
| Assets | filesystem privado com sha256 e manifestos, storage compatível S3 apenas se aprovado sem cobrança | Política de direitos, expiração e URLs não públicas por padrão |
| Evals/ops | pytest, Playwright, vitest, golden visual diffs, OpenTelemetry opcional | Score por campo, traces reais, segurança e ISO 25010/25019 |

**Não selecionar por popularidade:** toda escolha acima é hipótese candidata para DEC e experimento, sem homologação automática. Não adicionar Redis/Temporal/Kubernetes/mais bancos/mais agentes sem necessidade comprovada. Ambição de máximo de tecnologias úteis significa maior cobertura de capacidades reais e interoperáveis, não dependências redundantes.

## 6. Escolhas excluídas por orçamento/licença

- **tldraw SDK**: licença de produção comercial específica; não é opção padrão para requisito R$ 0.
- **Remotion**: distribuição/licença condicionada a tipo e porte de organização e caso de uso; para uso institucional ou de automação comercial pode exigir licença, logo não presumir gratuito.
- **Polotno**: SDK comercial de editor; não presumir uso sem custo.
- **Modelos hosted pagos**, stock media sem licença, TTS/música comercial e render em nuvem sujeito a faturamento: não habilitar.
- FFmpeg pode ser **LGPL ou GPL conforme build/codec**; auditar distribuição e transcodificação.

## 7. Contratos e endpoints candidatos

`POST /v1/studio/projects` (brief+creative+referências → projeto);
`POST /v1/studio/projects/{id}/generate-layout` (gerar documentação por camadas, sem publicação);
`GET /v1/studio/projects/{id}`;
`PATCH /v1/studio/projects/{id}/versions` (JSON schema, ETag/controle de concorrência);
`POST /v1/studio/projects/{id}/render-jobs` (assíncrono, tipo de exportação, orçamento e idempotência);
`GET /v1/studio/render-jobs/{id}`;
`POST /v1/studio/projects/{id}/approve`;
`POST /v1/studio/projects/{id}/export`.
Publicação externa via CAP-017 deve ser **endpoint separado**, desabilitado até permissões específicas, revisão humana e autenticação completa; preview/render não a acionam.

## 8. Modelo de persistência candidato

`creative_projects`, `design_documents`, `design_revisions`, `design_layers` (se necessário), `media_assets`, `asset_rights`, `render_jobs`, `export_artifacts`, `editorial_approvals`, `creative_experiments`, `collaborator_permissions`. Gravação principal versionada do documento pode ser em JSONB e snapshots com checksums; não duplicar tabela de camada até precisar de consultas. Adicionar referências para `creative_version`, `insight`, `content_item`, `source_grant`, `tenant`, `run_event`. URLs externas são desaconselhadas sem allowlist/SSRF guards.

## 9. Testes e regras de aceite obrigatórios

1. Gerar 1 proposta a partir de brief + no mínimo 1 referência real autorizada, sem inventar citação; modo sem fontes deve recusar/fallback explícito.
2. Editar texto, substituir imagem, mover e redimensionar camada, alterar paleta e reordenar slides **sem regeneração de imagem achatada**.
3. Salvar, sair, recarregar e recuperar documento com hash/versão, histórico, undo/redo e teste de isolamento multi-tenant.
4. Exportar mídia visualmente coerente com a prévia (golden snapshots em browser e pipeline), sem perda de conteúdo, fontes ou direitos; vídeo só após renderer validado.
5. Rastrear `brief → insight → posts → creative_version → document_version → render → aprovação`.
6. Não acessar mídia alheia sem direito, não enviar tokens a logs e não disparar publicação/anúncios sem aprovação explícita.
7. Rejeitar overlays com texto ilegível, zonas inseguras, dimensões incorretas, arquivos maliciosos e fontes/ativos sem licença.
8. Avaliar tempo de edição e utilidade com usuário, originalidade e adequação à Stone/MPE; critérios previamente definidos.
9. Zero serviço pago, zero overage, sem pressupor disponibilidade de GPU.
10. Repetir comparativos de bibliotecas, testes de acessibilidade, memória/latência e falhas antes de escolher implementação final.

## 10. Priorização dentro do Plano Único

**P0** contratos de design/editabilidade, assets e direitos + editor visual estático + salvar/carregar/exportar PNG; rastreabilidade até CAP-007.  
**P1** carrossel, branding, variantes, revisão/aprovação, playbook e painel, instrumento de avaliação real.  
**P2** timeline e render de vídeo/Shorts, geração de ativos por modelo local, colaboração, piloto orgânico.  
**P3 condicional** publicação externa autorizada, predição calibrada, CRM/atribuição real, anúncios pagos **permanentemente desabilitados sob teto R$ 0**.

A prioridade depende da viabilidade de fontes, corpus 2–5 mil e validação mínima de 50 posts. Não atrasar as seis evidências acadêmicas por recurso visual opcional nem confundir cronograma acadêmico com obrigação técnica sem autorização institucional.

## 11. Referências externas consultadas, verificáveis

- Fabric.js MIT, serialização e exportação: https://github.com/fabricjs/fabric.js e https://github.com/fabricjs/fabric.js/blob/master/LICENSE
- React-Konva MIT: https://konvajs.org/docs/react/index.html
- Lexical MIT, React: https://github.com/facebook/lexical
- Motion Canvas MIT: https://github.com/motion-canvas/motion-canvas e https://motion-canvas.io/docs/
- FFmpeg licensing: https://ffmpeg.org/legal.html
- ComfyUI local: https://github.com/comfy-org/ComfyUI
- Qwen3-VL 8B licencia Apache-2.0: https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct
- MCP SDK v2 `MCPServer`: https://py.sdk.modelcontextprotocol.io/whats-new/
- LangGraph stateful checkpoints: https://reference.langchain.com/python/langgraph/overview
- pgvector: https://github.com/pgvector/pgvector
- tldraw production license: https://tldraw.dev/community/license
- Remotion conditional license: https://www.remotion.dev/docs/license/pricing
- Meta Instagram API with Facebook Login: https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api
