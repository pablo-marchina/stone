# CAP-023 E7 — vídeo-fonte, timeline multifaixa, keyframes e worker recuperável

**Referência vinculante:** Arquitetura Final Consolidada v5.1 + ampliação v5.2, decisões posteriores e tarefas do Plano Único. **Pré-requisito técnico:** E6 (PR #39), que depende do PR #38 e do #37. E7 continua o MESMO Creative Studio; não cria um produto paralelo.

## O que foi implementado

- **Vídeo-fonte:** upload local e opt-in de bytes MP4, no máximo 7 MiB; somente H.264/YUV420p, até 1080×1920, 30 segundos, **uma faixa de vídeo sem áudio embutido**, inspecionado com `ffprobe`; atestação de direitos por vídeo (com referência, validade e revogação) e SHA-256 por tenant. Não há upload de URL nem download remoto. Cada cena recebe ou um PNG com direitos ativos ou um vídeo MP4 com `trim_start_ms` e corte limitado à duração da cena.
- **Multifaixa:** até quatro ativos WAV PCM16 mono/16 kHz já autorizados pelo E6, com início em milissegundos, ganho percentual e mixagem determinística com saturação. Não aceita MP3, áudio embutido do vídeo ou streaming. O áudio final é codificado AAC localmente.
- **Keyframes animados:** cada overlay textual existente em `studio-storyboard.v1` agora interpola X, Y e opacidade entre keyframes por frame. Texto é rasterizado com Pillow, jamais incorporado como expressão livre do FFmpeg.
- **Transições:** acrescentado `crossfade` e `transition_ms` ao contrato `TimelineClip` (corte continua padrão). O blend é aplicado nos frames próximos da fronteira sem modificar a duração da timeline nem liberar pistas não autorizadas. Transições ficam limitadas a 100–500 ms e à metade do tempo disponível em cada cena.
- **Qualidade:** raster vertical de rascunho 540×960, 12 FPS, H.264 CRF22 e AAC 128kbps; marca visível `RASCUNHO - NAO PUBLICAR`. Limites do piloto: quatro cenas, duração total até 15s e vídeo final até 18 MiB. **Isso não é render de produção em 1080×1920**.
- **Recuperação:** nova fila `studio_e7_render_jobs` com `queued/running/succeeded/failed/canceled`, lease aleatório por tentativa, expiração de 480s, recuperação no próximo `--once` após crash, no máximo três tentativas, CAS por token impedindo que worker antigo confirme artefato. Cancelamento e revogação de direitos bloqueiam persistência e download. Eventos append-only gravam transições de estado e revogações.

## APIs novas (todas exigem Bearer e tenant autenticado)

| Endpoint | Papel | Objetivo |
|---|---|---|
| `POST /v1/studio/video-sources/mp4` | admin | Upload e atestação explícita do MP4 local |
| `POST /v1/studio/video-sources/{asset_id}/revoke` | admin | Revogar direitos do vídeo |
| `POST /v1/studio/advanced-render-jobs` | admin/editor | Enfileirar storyboard + cenas + até 4 WAVs |
| `GET /v1/studio/advanced-render-jobs/{job_id}` | autenticado/tenant | Consultar status |
| `POST /v1/studio/advanced-render-jobs/{job_id}/cancel` | admin/editor | Cancelar sem publicar |
| `POST /v1/studio/advanced-render-jobs/{job_id}/retry` | admin/editor | Reenfileirar falha antes de 3 tentativas |
| `GET /v1/studio/advanced-render-artifacts/{artifact_id}` | autenticado/tenant | Download condicionado aos direitos ativos |

Nenhuma API processa FFmpeg no request HTTP; somente o CLI opt-in faz render. `TAPI_LOCAL_RENDER_ENABLED=1`, `TAPI_ZERO_BILLING_CONFIRMED=1` e **nova flag** `TAPI_E7_VIDEO_RENDER_ENABLED=1` são necessárias para operar. **Não habilitar em produção ou sem orçamento comprovadamente R$ 0.**

### Exemplo limitado de job

```json
{
  "job_id": "job.e7.local",
  "storyboard_id": "story.e7",
  "storyboard_version": 2,
  "scenes": [
    {"scene_id":"scene.1","video_asset_id":"mp4.EXEMPLO","trim_start_ms":300},
    {"scene_id":"scene.2","image_asset_id":"asset.EXEMPLO","trim_start_ms":0}
  ],
  "audio_tracks": [
    {"asset_id":"audio.EXEMPLO","start_ms":0,"gain_percent":75},
    {"asset_id":"audio.OUTRO","start_ms":450,"gain_percent":50}
  ]
}
```

IDs são ilustrativos e devem ser substituídos pelos IDs reais **do mesmo tenant**, com direitos atestados e válidos. A versão do storyboard é fixada no manifesto.

## Migração e operação segura

**Não execute `upgrade head` no banco de coleta real sem backup consistente e `alembic current`.** A nova migração `0010_studio_multitrack_e7` depende de `0009_studio_local_render_e6` e cria quatro tabelas e índice de fila. Em teste SQLite isolado, `alembic upgrade head` foi concluído até a revisão 0010.

```powershell
$env:TAPI_DATABASE_URL = 'sqlite:///C:/stone-data/tapi.sqlite3'
$env:TAPI_TENANT_ID = 'local-research'
$env:TAPI_LOCAL_RENDER_ENABLED = '1'
$env:TAPI_E7_VIDEO_RENDER_ENABLED = '1'
$env:TAPI_ZERO_BILLING_CONFIRMED = '1'
# Somente após backup, migrações e criação de job pelos endpoints autenticados:
python scripts/studio_advanced_render_worker.py --once
```

O worker não se inicia sozinho e não roda em polling; cada chamada processa no máximo um job da fila do tenant. As tentativas interrompidas voltam à fila quando o lease expira; não há checkpoint de codificação parcial nem preservação de frames intermediários.

## Testes realizados neste incremento

- `tests/test_studio_e7.py`: render MP4 real com `ffmpeg`/`ffprobe`; duração, 540×960, trilha AAC; corte de vídeo; múltiplos WAV; interpolação de keyframes; limite de transição; direitos revogados; crash/lease expirado; exaustão de tentativas; cancelamento; token de worker obsoleto; auth/tenant; formatos e recortes inválidos.
- Suíte Python integrada local: **337/337 pytest PASS no checkout local histórico B2+C2+E3–E7**; deve ser repetido no HEAD remoto completo A2/A3/B2/C2+E3–E7.
- `node --test tests/frontend/test_events.mjs` 3/3 PASS; `node --check src/tapi_gate0/web/studio.mjs` PASS.
- `check_gate0.py` **estrutura local verificada**, não Gate 0B global nem homologação; `verify_zero_spend.py` PASS.
- SQLite migrado em banco isolado até 0010, sem alterar a base real do operador.

## Lacunas que permanecem

Ainda faltam UI visual de trim/mixer/keyframes com prévia responsiva, leitura dos áudios embutidos em vídeo-fonte quando autorizada, sincronização por timecodes profissionais e múltiplos canais, efeitos avançados, 1080×1920/30fps, recuperação parcial por fragmentos, scheduler multiworker distribuído, sandbox OS/containers para demuxers FFmpeg, monitoramento e testes de carga real. Esse MVP é um **worker de rascunho local com controles verificáveis**, não autorização de publicação, uso científico ou produção.
