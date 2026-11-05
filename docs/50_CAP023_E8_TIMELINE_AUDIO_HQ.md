# CAP-023 E8 — timeline visual, áudio embutido autorizado e renderização de qualidade superior

**Referência:** Arquitetura Final Consolidada + atualização v5.2, Plano Único, sequência de implementação CAP-023 E3→E4/E5→E6→E7→E8. Este documento relata um incremento do **mesmo** Creative Studio, não cria arquitetura ou plano paralelo.

**Base de integração:** PR #39 (sobre #38, que depende do #37), mais o incremento E7 do pacote `stone_cap023_e7_video_multifaixa_workers_2026-11-05.zip`. O checkout de testes deste incremento é histórico B2+C2+E3–E8, e **não** inclui A2/A3 remotamente incorporados à `main`. **Não usar os testes locais como prova de CI no HEAD remoto exato.**

## Implementação E8

### 1. Timeline visual (continuação IMP-187/188)

- `studio_timeline_e8.js` integra a tela já existente em `/app/studio.html`.
- Cenas proporcionais à duração, faixa de overlays, edição de narração, texto, duração, keyframes de posição/opacidade e transições por formulário validado.
- Reordenação de cenas por arrastar/soltar **e** por `Alt+Seta`; os clips são reindexados por `start_ms` e gravados em **nova versão** via API existente `POST /v1/studio/storyboards/{id}/timeline`.
- IDs de MP4 e PNG são vinculados de forma explícita às cenas antes de enfileirar um job. Os IDs vinculados na UI são **temporários até criar o job**; o manifesto do job gravado pelo backend é o registro durável. O storyboard v1 continua referenciando o documento e as cenas, sem mutação oculta de mídias.
- Upload MP4, upload WAV PCM, atestação de PNG, controle por cena de trim e áudio embutido, faixas WAV, seleção de qualidade, status e download autenticado do rascunho. Nenhuma URL externa de mídia é aceita. Os tokens não são colocados em URLs.
- A interface **enfileira** jobs, mas não inicia um worker automaticamente: o operador executa `scripts/studio_advanced_render_worker.py --once` com as flags necessárias.

### 2. Direitos específicos de áudio de origem

- `UploadVideoSource` continua exigindo prova local de direitos de vídeo, validade e atestação do operador. Um MP4 com áudio é rejeitado por padrão, mantendo o comportamento da E7.
- A admissão de **um único stream AAC embutido** (1–2 canais, 8–48 kHz) exige `embedded_audio_rights_attested=true` **e** `embedded_audio_evidence_reference` específica, nunca inferidas da autorização do vídeo.
- A migração Alembic `0011_studio_source_audio_hq_e8` acrescenta `has_embedded_audio`, `embedded_audio_rights_status` e `embedded_audio_evidence_reference` aos ativos de vídeo.
- `SceneInput.include_source_audio=true` e `source_audio_gain_percent` demandam atestação ainda ativa, verificada no enfileiramento, no worker e antes de fornecer o arquivo produzido. `POST /v1/studio/video-sources/{asset_id}/embedded-audio/revoke` revoga apenas áudio, sem reativar/revogar implicitamente o vídeo.
- O áudio incluído é extraído localmente por FFmpeg, restrito ao mesmo segmento `trim_start_ms`/duração da cena; convertido para PCM 16 kHz mono e misturado na timeline com as faixas WAV adicionais, com soma saturada. **Até quatro faixas simultaneamente cadastradas, contando cada áudio de fonte utilizado.**
- Nenhum áudio é extraído de vídeo de terceiros sem essa prova específica. A atestação é a declaração administrativa do operador, **não** auditoria externa dos direitos.

### 3. Qualidade superior com custo zero

| Perfil | Resolução | FPS | Duração máxima | Ativação |
| --- | --- | --- | --- | --- |
| `preview_540p` | 540×960 | 12 | 15 s | padrão E7 |
| `quality_720p` | 720×1280 | 24 | 6 s | `TAPI_E8_HQ_ENABLED=1` |

As dimensões **não** são valores arbitrários fornecidos pelo usuário. A lista permitida e os limites são revalidados no enfileiramento e na execução. O perfil superior usa x264 local com CRF 18, áudio AAC a 160 kb/s e FFmpeg local; frames são gravados progressivamente em diretório temporário para reduzir o consumo de RAM. As transições reabrem apenas frames de borda. Nenhuma geração remota, cobrança ou publicação é realizada. O rótulo **`RASCUNHO - NAO PUBLICAR`** permanece visível nos dois perfis.

## Validação executada no checkout local histórico

- `341 passed` — Python, incluindo 9 testes E7 e 4 testes E8 com FFmpeg real, sincronização do áudio embutido, perfil 720p/24 FPS, hash, revogação e rejeições.
- `7/7` testes Node: os 3 herdados + 4 do módulo da timeline.
- Chromium real + FastAPI in-process: storyboard de duas cenas, edição e keyframes, drag/drop real, versões, ativo PNG autorizado e job em fila, sem erros JS.
- Alembic `upgrade head` em SQLite efêmero alcançou `0011_studio_source_audio_hq_e8`; colunas verificadas.
- `check_gate0.py` executado e retornou **estrutura local verificada**; `verify_zero_spend.py` PASS. Isso não equivale a aprovação científica nem produção.
- Testes **não** executados no HEAD exato da sequência #37/#38/#39+E7 da `main`. Nenhum PR foi mesclado como resultado da validação histórica.

## Protocolo de integração (ordem obrigatória)

1. Com acesso ao repositório, confirmar HEADs remotos de #37, #38 e #39, preservando `main` e evitando sobrescrever trabalho local.
2. Fazer checkout exato da branch do **PR #39**, validar todas as suítes desse HEAD, inclusive A2/A3, executar Alembic 0007→0009 em SQLite isolado, `check_gate0.py`, `verify_zero_spend.py`, Node e QA do navegador. Sem CI configurado, registrar commit SHA e logs reais.
3. Aplicar o patch **E7** e depois o **E8** com `git apply --check`/`git apply`. Rodar regressão completa, E7/E8, migração 0010→0011 em cópia isolada, FFmpeg e QA. Registrar o novo SHA.
4. Revisar, integrar os PRs 37→38→39 sobre a `main` na ordem de dependência. Integrar E7/E8 apenas depois de sua revisão independente, sem alterar a arquitetura original.
5. Manter produção, publicação, permissões científicas e quaisquer gastos externos desativados até seus gates próprios.

## Limitações mantidas

- A timeline ainda não é um editor audiovisual profissional com waveform, thumbnails de vídeos, persistência de vínculos por cena **antes** da fila, trims com precisão de frame e prévia real no navegador. É uma base visual funcional para criação de jobs versionados e autorizados.
- Sem 1080p, sem escalonamento de workers, sem armazenamento externo nem execução automática; 720p é um primeiro perfil de qualidade superior ao protótipo 540p.
- Não há prova de eficiência sob carga ou auditoria integral WCAG. Foram realizados testes funcionais e um teste de navegador isolado.

### Comando de validação segura no Windows

No repositório clonado que possua acesso ao GitHub e dependências de desenvolvimento já instaladas:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate_e8_on_pr39_exact.ps1 `
  -E7Patch 'C:\CAMINHO\stone_cap023_e7_advanced_video_2026-11-05.patch' `
  -E8Patch 'C:\CAMINHO\stone_cap023_e8_timeline_audio_hq_2026-11-05.patch'
```

O script verifica o SHA remoto, cria um worktree isolado, usa SQLite próprio, não acessa a Meta e executa os testes. Não faz merge nem apaga o worktree automaticamente. **Essa validação deve ser executada por quem tem o checkout privado atual: não foi executada neste ambiente.**
