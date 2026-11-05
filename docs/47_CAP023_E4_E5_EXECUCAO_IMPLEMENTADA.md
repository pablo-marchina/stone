# CAP-023 — incremento E4/E5 — IMP-182, 183, 184, 185, 187, 188

**Fonte obrigatória:** Arquitetura Unificada Consolidada v5.1 + extensão v5.2 + decisões posteriores. O Plano Único v5.2 determina os IDs e a sequência de implementação. Este incremento continua o Creative Studio C2/E3; não substitui a arquitetura nem altera decisões.

## Escopo realizado

### IMP-182 — histórico/versionamento

- Histórico transacional de `DesignDocument` já existente, preservado; comparação autenticada de duas versões com `from_version` e `to_version`, campos alterados, valores antes/depois e ETag da versão.
- ETag forte SHA-256 por documento JSON tipado, retornada em criação/leitura/edição, com cabeçalho `Cache-Control: no-store`. Escritas com `If-Match` **quando fornecido** retornam HTTP 412 em divergência; `expected_version` mantém a detecção CAS de lost update (409) inclusive em clientes antigos. Não declarar `If-Match` obrigatório para integrações legadas.
- UI com autosave de texto por debounce (800 ms), no `blur` e quando a página fica oculta, preservação de alteração não salva após erro e recuperação limitada de rascunho textual em `sessionStorage` por tenant/documento e 24h. Não grava tokens em storage. Em caso de conflito, nunca sobrescreve automaticamente a versão remota. A gravação antes de encerramento abrupto do processo **não é garantida**; esse limite não deve ser ocultado.
- Retorno a uma versão histórica cria um novo snapshot, sem recuperar aprovação editorial nem direitos automaticamente. Undo/redo na sessão permanece sem recomputar análises.

### IMP-183 — carrossel multipágina

- Mantém edição, duplicação, exclusão e reordenação por botões/drag-drop de 1 a 10 páginas no modelo canônico. IDs únicos, page-local layer operations e verificação de tenant/role/version no servidor.
- QA em Chromium real, usando UI e backend FastAPI in-process com interceptação de requisições: **drag-and-drop HTML5 real** de aba para outra, seguido de snapshot validado. Não foi simulação de callback. Não equivale a teste com pessoas nem auditoria WCAG integral.

### IMP-184 — primeira exportação local

- Um mesmo renderer de canvas desenha a prévia e os PNG/JPEG locais; SVG é gerado de nós tipados, escapando conteúdo textual e incorporando imagem validada como data URI PNG (sem scripts/links externos).
- ZIP multipágina sem dependências externas (método STORE, CRC32 válido, até dez páginas), `manifest.json` com IDs, versão, formato, dimensão, SHA-256 de cada arquivo e estado de aprovações.
- Exportação cooperativa no browser com snapshot fixo da versão e limite de tamanho; não existem jobs server-side, FFmpeg, filas distribuídas, nem política de retries/cancelamento de render remoto. **IMP-184 está parcial**, não completa todos os critérios de aceite do plano.
- Todos os documentos atuais têm `rights_status=pending_review` e `approval_status=draft`. Arquivos derivados são marca-d'água **RASCUNHO - NAO PUBLICAR**; não há aprovação ou publicação implícita.
- QA em Chromium com paridade **pixel a pixel** entre a prévia canvas sem seleção e PNG da página; JPEG foi decodificado por Pillow; SVG inspecionado contra script; ZIP aberto com `zipfile.testzip()`, 3 páginas 1080×1350 e hashes recalculados. Critérios gráficos avançados (fontes substituídas, qualidade perceptual SVG, áudio, safe areas de vídeo, perfis de cor) ainda não testados.

### IMP-185 — proposta estruturada, não IA em produção

- API de proposta **apenas de texto**, com whitelist de campos, prévia determinística, `preview_sha256` vinculado a documento/versão/tenant e confirmação explícita do operador antes do patch.
- Preserva origem `untrusted_model` como metadado de solicitação, sem executar conteúdo do modelo nem consultar modelos externos. Não há geração por LLM neste incremento. Testes verificam recusa de hash alterado, versionamento obsoleto, acesso cross-tenant e ausência de auto-aprovação.
- UI oferece prévia e aceite manual; o texto não é aplicado antes do clique de confirmação.

### IMP-187/188 — contratos persistentes de storyboard/timeline

- Novo contrato `studio-storyboard.v1` com cenas textuais, locators para documento de design local, duração, overlays de texto, keyframes `x/y/opacity`, ordem e cortes `cut`. O tempo é limitado (até 180s totais, máximo 12 cenas).
- API autenticada: `POST /v1/studio/storyboards`, `GET /v1/studio/storyboards/{id}`, `GET /versions/{version}`, `POST /timeline`; tenant e usuário derivam da sessão, bloqueio de duplicidade, edição obsoleta e sobreposição de clipes.
- Persistência com snapshots imutáveis, `edited_by` e `created_at` na migração Alembic `0008_studio_storyboards`, encadeada após `0007_studio_e1`.
- O storyboard nasce de um `DesignDocument` real do mesmo tenant e registra versão de origem fixa. A UI inicia um storyboard textual e apresenta IDs/contagem/duração.
- `audio_status=not_implemented`, `render_status=not_implemented`, `rights_status=pending_review`, `approval_status=draft`. Não há corte de vídeo real, mixagem, decodificação, FFmpeg, render de MP4, licenças ou publicação. **IMP-187/188 estão parciais**, não concluem as capacidades audiovisuais finais.

## Evidências executadas

- `PYTHONPATH=src python -m pytest -q` → **324 testes PASS** no checkout local de integração B2+C2+E3+E4+E5.
- `node --check` nos arquivos JS, 3 testes Node → PASS.
- QA Playwright/Chromium offline → drag/drop real, paridade do PNG, JPEG, SVG, ZIP e hashes SHA-256 → PASS.
- Migração Alembic SQLite limpo → `0008_studio_storyboards (head)`.
- `check_gate0.py` → PASS **estrutural**, não liberação final; `verify_zero_spend.py` → PASS.
- Os testes executados são locais, baseados em checkout B2+C2 histórico com alterações incrementais: **não** equivalem a CI da branch remota #37 + toda a `main` A2/A3/B2/C2.
- Nenhuma credencial Meta, dados de produção ou conteúdo privado externo foram utilizados.

## Próximos critérios técnicos do Plano Único

1. Reproduzir suíte sobre o HEAD remoto exato de PR #37, incluindo integração A2/A3; ajustar PR e integração após revisão.
2. Executar testes de navegador em Chrome/Firefox e com usuários reais (acessibilidade, DnD por teclado, persistência após recuperação de rede).
3. Completar IMP-184 com worker assíncrono, paridade SVG e imagem de referência, limites de memória por página, direitos por ativo e jobs canceláveis.
4. Completar IMP-185 com proposta a partir do agente devidamente fundamentado, guardrails de injeção, múltiplos patches e preview de alterações geométricas.
5. Expandir IMP-187/188 para upload autorizado de mídia/audio, timeline multicamada, cortes, transições, legendas e render audiovisual sob DEC-014, IMP-189 e direitos aplicáveis.
6. Aplicar `0008` **somente** após backup consistente do banco usado pelo operador e confirmação de migrations até `0007`.

## Comandos de validação no Windows

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m pytest -q
node --check src/tapi_gate0/web/studio.mjs
node --check src/tapi_gate0/web/studio_export_e4.js
node --test tests/frontend/test_events.mjs
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
python -m alembic current
# Executar upgrade head APENAS após backup e conferência do histórico do banco.
```
