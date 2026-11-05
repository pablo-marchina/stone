# CAP-023 — E6: render local autorizado, IA fundamentada e qualidade

**Fonte de produto:** Arquitetura Final Consolidada v5.1 + evolução v5.2. **Fonte de sequência:** Plano Único v5.2, na continuidade das tarefas IMP-184/185/186/187/188 e preparação da IMP-189. **Decisões posteriores** são respeitadas sem afirmar aprovação científica, publicação ou direitos de terceiros por inferência.

**Dependência de código:** PR #38 (E4/E5), empilhado sobre PR #37 (E3). Nenhuma mudança na arquitetura-alvo nem no plano.

## 1. Render audiovisual local: piloto explícito, limitado e auditável

- `studio_render_e6.py`: serviço de renderização de **vídeo MP4 de rascunho** em fila persistente, backend SQLite/PostgreSQL por SQLAlchemy e histórico imutável de transições de estado (`queued`, `running`, `succeeded`, `failed`, `canceled`, `retried`). `process_next` é chamado explicitamente pelo operador e utiliza **FFmpeg local**, sem chamadas externas, publicação ou serviços pagos.
- O vídeo é composto de **1 a 4 stills PNG** já carregados no tenant, ordenados e temporizados por `studio-storyboard.v1`, com transições `cut`. Áudio é **opcional**: WAV RIFF PCM16 mono 16 kHz, até 30s, armazenado em banco, validado por hash e submetido ao FFmpeg como arquivo temporário controlado.
- Marca visível `RASCUNHO - NAO PUBLICAR` incorporada ao MP4; saída restrita a **360×640**, **8 fps**, **até 20 segundos**, **8 MiB**, timeout FFmpeg de **45s**. A arquitetura integral poderá usar workers de alta fidelidade e transições mais ricas posteriormente; este incremento não as declara prontas.
- Protocolo estrito: somente bytes de PNG/WAV validados, `subprocess.run` com lista fixa de argumentos sem shell, sem URLs de rede, `TemporaryDirectory` descartável, hashes de arquivos, limite de CPU e saída, nenhuma credencial em linha de comando ou log.
- O operador deve ativar as flags **`TAPI_LOCAL_RENDER_ENABLED=1`** e **`TAPI_ZERO_BILLING_CONFIRMED=1`** depois de verificar que FFmpeg e a máquina local não têm cobrança. O endpoint web apenas enfileira; o worker não roda automaticamente.
- Job inclui versão do storyboard e manifesto SHA-256 dos assets. Antes de efetivar o resultado o worker revalida direitos, expiração, integridade e ausência de cancelamento; o download revalida direitos novamente.

## 2. Direitos por ativo — além do booleano de upload C2

- `POST /v1/studio/assets/draft-render-rights` exige **admin**, ativo PNG pertencente ao tenant, `rights_attested=true`, referência concreta e validade futura. Não é verificação jurídica automática: `independently_verified=false`.
- `POST /v1/studio/assets/{asset_id}/draft-render-rights/revoke` registra revogação; a operação futura e o download do artefato tornam-se bloqueados.
- `POST /v1/studio/audio/wav` exige **admin**, bytes WAV estritos, referência e validade. Não são aceitos MP3, SVG externo, URLs remotas nem conversão arbitrária.
- Histórico de atestações/revogações em `studio_render_rights_events`. Não colocar títulos de propriedade intelectual, tokens Meta ou textos externos sem autorização na base de fontes do corpus.

## 3. Propostas de edição fundamentadas em evidência

- `studio_evidence_edits_e6.py`: `POST /v1/studio/documents/{id}/evidence-edits/preview` exige `content_id` e `snapshot_id` reais existentes no **mesmo tenant**, com associação correta e referência já vinculada ao `DesignDocument`.
- O preview carrega observação real (não sintética), hash do snapshot, ETag da versão e diff da alteração, marcados como **evidência descritiva não validada cientificamente**. Não executa o texto de legendas como instrução, não gera recomendações por LLM e não promove classificação por inferência.
- `apply` exige `operator_confirmed=true`, `preview_sha256` e CAS da versão. Inserção de `studio_evidence_edit_events` e nova revisão do documento ocorre **na mesma transação SQL**; `draft`, `pending_review`, `unverified` continuam preservados.

## 4. Qualidade, desempenho e acessibilidade

- UI C2: botão de navegação por camada com estado `aria-pressed`, foco teclado, canvas com setas (10 px, Shift+seta 1 px), feedback no `role=status` e alternativa aos gestos de ponteiro.
- Testes `tests/test_studio_e6.py`: bloqueio de flags, recusa de grant ausente/revogado, idempotência de estados, áudio inválido, worker FFmpeg real e verificação `ffprobe`, download autenticado por tenant, edição vinculada ao snapshot e registro de proveniência atômico.
- Script `scripts/e6_browser_accessibility_performance_qa.py`: Chromium sem rede externa, acesso por teclado e p95 local de 40 consultas simples de documento. **Não** substitui auditoria WCAG 2.2, revisão com leitores de tela, nem testes de carga, throughput e infraestrutura real.

## 5. Migração e execução local

`migrations/versions/0009_studio_local_render_e6.py` depende de `0008_studio_storyboards` e adiciona sete tabelas. Migração foi validada em SQLite isolado. **Faça backup consistente do banco real e verifique `python -m alembic current` antes de `upgrade head`**.

Instale em ambiente local autorizado o FFmpeg e a dependência opcional `pip install -e '.[dev,local_render]'`; não faça download automático por CLI.

```powershell
$env:TAPI_DATABASE_URL = 'sqlite:///C:/stone-data/tapi.sqlite3'
$env:TAPI_TENANT_ID = 'local-research'
$env:TAPI_LOCAL_RENDER_ENABLED = '1'
$env:TAPI_ZERO_BILLING_CONFIRMED = '1'
# Após backup e verificação explícita das migrações:
python -m alembic upgrade head
# Após criar um job via API autenticada, executar no máximo um job:
python scripts/studio_local_render_worker.py --once
```

```powershell
python -m pytest -q tests/test_studio_e6.py
python -m pytest -q
node --check src/tapi_gate0/web/studio.mjs
node --test tests/frontend/test_events.mjs
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
```

## 6. Estado honesto e próximos marcos

**Implementado neste incremento:** worker local FFmpeg para still PNG + áudio PCM, manifestos e auditorias; grant por ativo revogável; edição estruturada vinculada a evidências reais; smoke acessível por teclado e benchmark mínimo; migração 0009.

**Ainda não implementado:** timeline audiovisual com vídeo-fonte e trilha de áudio segmentada, transições complexas, animação real de keyframes, edição por modelo IA real, aprovação jurídica independente, filiação científica ao corpus, worker de produção com reprocessamento de leases abandonadas, monitoramento distribuído, acessibilidade WCAG auditada, transcodificação escalável/alta resolução ou publicação. Nenhuma operação paga/externa foi habilitada.

**Limitação de validação:** a suíte local roda no snapshot exato de PR #38 nos arquivos do Studio, mas o checkout histórico não incorpora os commits A2/A3 presentes em `main`. É obrigatório reproduzir a suíte no HEAD remoto resultante antes de merge e homologação. Os testes de operador/Meta não foram repetidos aqui.
