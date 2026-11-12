# CAP-001 / A5 — aquisição histórica e contínua com curadoria incremental

**Data:** 12/11/2026. **Base:** main após merge do [PR #42](https://github.com/pablo-marchina/stone/pull/42) (`d2efe5f`). **Status:** incremento implementado e testado offline; dois ciclos históricos reais A5 reportados em 12/11/2026, com retomada nas três fontes, 197 media IDs únicos e auditorias válidas. Refresh real independente também reportado com sucesso; recuperação auditada ainda pendente. A4 comprovou 39 posts técnicos únicos em 3 fontes, 60 observações reauditadas nos três lotes A4, zero admissões científicas. DEC-016 e DEC-018 continuam aplicáveis.

## Arquitetura e decisões

- `history`: consulta Business Discovery a partir do cursor privado por tenant/fonte/viewer/referência de grant, sem retomar a partir de uma página truncada. Limite de persistência igual a páginas × itens/página. O cursor só avança após todas as persistências e auditoria correlacionada, na mesma transação que conclui o run. A4 antigo não gerou checkpoint histórico: a primeira passagem A5 começa no topo e deduplica os registros existentes.
- `refresh`: nova leitura a partir do topo, intervalo padrão 24h por fonte, sem tocar no checkpoint histórico. Não é uma varredura completa dos posts antigos; perfis com alta frequência podem ter publicações que amadurecem fora da janela de quatro páginas. A cobertura de refresh deve ser avaliada e estendida em um incremento posterior.
- Migração Alembic 0012: `bd_history_checkpoints` (cursor restrito, hashes de cursores visitados, run, páginas e escopo) e `bd_cycle_leases` (um ciclo A5 por tenant). Não registra cursor em relatório, stdout ou Git. Cursor ausente/última página parcial significa `frontier_unconfirmed`, nunca exaustão comprovada.
- Fila ordenada por última aquisição histórica/refresh, com novas fontes primeiro, até 5 fontes, 4 páginas/fonte e 40 observações/fonte no histórico; 20 solicitações máximas por ciclo. Refresh limitado a 12 observações/fonte. Contagem global no DB distingue registros, media IDs únicos e perfis técnicos, não corpus científico.
- Orçamento conservador por dia UTC: até 80 páginas reservadas por tenant, debitando 4 por reserva Instagram inclusive A3/A4, concluída, falha ou reservada. Também continuam 5 reservas por fonte/dia. É um **limite local**, não confirmação de limite, cobrança ou disponibilidade da Meta. A5 possui lease contra sobreposição de ciclos A5, não contra chamadas manuais simultâneas de outros entrypoints: não executar A3/A4/ingestão first-party em paralelo com A5 no mesmo tenant.
- Por padrão a CLI só lê o DB local e valida manifesto; nenhuma chamada Meta. `--execute` requer os flags anteriores, mais `TAPI_BD_CONTINUOUS_ENABLED=1`, credencial e relatório privado novo. Sem serviços pagos, scraping, download de vídeo, publicação ou API automática de criação de grants.
- Falhas interrompem as seguintes fontes no lote; último run falho/reservado deixa a fonte fora da fila até revisão. A5 não implementa ainda reset auditado de cursor inválido/expirado, recuperação de lease órfão ou renovação de grant. Nunca remover registros ou locks automaticamente, nem editar grants/cursores diretamente. Se houver crash, interromper agendamento e inspecionar run/lease antes de retomar. Não confundir itens já gravados antes de uma falha de run com checkpoint avançado.

## Expansão de fontes

O arquivo [bd_a5_candidate_expansion_20261112.json](../evidence/acquisition/bd_a5_candidate_expansion_20261112.json) contém seis candidatos documentais adicionais. O operador já tem um manifesto privado de 9 fontes (3 aprovadas, 6 candidatas). A expansão prevista é 15 fontes registradas, mantendo **apenas as três autorizações atuais**; o arquivo público nunca contém grants.

| Candidato | Evidência de identificação/finalidade | Limitação |
|---|---|---|
| nuvemshop | Site oficial de e-commerce para pequenos empreendedores, comunicado de 2015 com handle; conteúdo educacional e loja online | Identidade atual não verificada via Meta |
| contaazul | Página institucional oficial com link Instagram e gestão para micro/pequenos negócios | Perfil e posts não verificados via Meta |
| abraselnorn | Página oficial Abrasel RN com Instagram e orientação a empresários de alimentação | Associação regional; verificar relevância MPE por post |
| abraseloestepotiguar | Página oficial Abrasel regional Oeste Potiguar, com Instagram | Mesmo grupo associativo; evitar superrepresentação |
| abihpecoficial | Página institucional da ABIHPEC identifica perfil e audiência B2B/B2C | Intenção MPE incerta |
| sediturmav | Prefeitura de Mato Verde identifica Instagram na página Sala Mineira do Empreendedor | Intenção do perfil incerta; não confundir serviço municipal com audiência exclusiva |

As URLs exatas constam do JSON. Nenhum ID Meta é inventado para estes seis candidatos. A consulta de identificação oficial só pode ocorrer se a finalidade estiver autorizada. O intake offline rejeita aprovações na lista pública, handles/IDs conflitantes e não altera decisões do manifesto privado.

Meta operacional de expansão (não desenho amostral validado): buscar diversidade entre instituições, meios de pagamento/finanças, gestão/contabilidade, marketing/e-commerce, alimentação, beleza, comércio e outros serviços. Registrar origem documental, data de consulta, estrato, intenção e limitações. Priorizar novos grupos independentes em vez de multiplicar filiais de Sebrae/Stone/Abrasel. Passar candidato → identificação oficial → justificativa de finalidade → autorização específica vigente → grant administrativo → manifesto aprovado → lote. Rejeitar perfil cujo público não seja MPE; se incerto, não admitir posts no corpus por inferência do perfil. O frame aceita até 100 entradas; 30 fontes efetivamente observadas e 2.000–5.000 posts ainda não foram atingidos.

## Operação local — primeira validação A5

Manter backup do banco existente (preferir API de backup SQLite; não copiar arquivo SQLite ativo arbitrariamente). Parar workers e Uvicorn antes da migração. Não executar `init-db` ou `bootstrap-admin` novamente. Usar a mesma URL, tenant e viewer do A4.

```powershell
git fetch origin
git switch feat/cap001-a5-historical-continuous-20261112
git pull --ff-only
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "src"
$env:TAPI_DATABASE_URL = "sqlite:///C:/stone-data/tapi.sqlite3"
$env:TAPI_TENANT_ID = "local-research"
$env:TAPI_META_IG_ID = "17841459971757521"
python -m alembic current
# Após backup verificado, somente no DB local correto:
python -m alembic upgrade head
python -m alembic current
```

A cabeça esperada na branch A5 é `0012_bd_history_checkpoints`. Não use essa migração na main antiga antes da revisão A5.

```powershell
python scripts/a5_expand_source_frame.py `
  --base artifacts/private/bd_manifest_multifonte_v1.json `
  --candidates evidence/acquisition/bd_a5_candidate_expansion_20261112.json `
  --output artifacts/private/bd_manifest_a5_v1.json

python scripts/a5_business_discovery_cycle.py `
  --manifest artifacts/private/bd_manifest_a5_v1.json `
  --mode history --max-sources 3 --max-pages 4 --daily-request-budget 80
```

A prévia local não exige token; a saída inclui fontes deferidas (candidatas, grants, quotas, falha pendente), seleção e cobertura total. A data de expiração real de cada grant pode impedir o lote; não preencher validade fictícia ou recriar grant ativo. Primeiro validar a prévia e quotas gratuitas.

Execução explicitamente autorizada, após a prévia:

```powershell
# Somente se as condições de acesso e R$0 estiverem confirmadas:
$env:TAPI_BD_CONTINUOUS_ENABLED = "1"
$env:TAPI_BD_TECHNICAL_INGEST = "1"
$env:TAPI_OFFICIAL_METADATA_READS = "1"
$env:TAPI_ZERO_BILLING_CONFIRMED = "1"
# Token válido por ambiente protegido; nunca em Git, log ou argumento.
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a5_business_discovery_cycle.py `
  --manifest artifacts/private/bd_manifest_a5_v1.json `
  --mode history --max-sources 3 --max-pages 4 --daily-request-budget 80 `
  --execute --report "artifacts/private/a5-history-$stamp.json"
```

Repetir com **nome de relatório novo**, dentro das quotas, para demonstrar retomada. Verificar `tenant_coverage_before/after`, `batch.sources[].history_checkpoint_status`, novos registros, reauditorias e zero admissões científicas. Não compartilhar cursores ou JSON privado completo. Um modo `refresh` pode ser planejado/executado com os mesmos argumentos, `--mode refresh --refresh-hours 24`. A CLI é apropriada para invocação periódica por agendador local (sem sobreposição), mas não instala tarefa nem roda em segundo plano por si. Credenciais devem ser providas por mecanismo seguro do operador; não salvar token em arquivo de tarefa. O primeiro aceite deve ser manual, com reauditoria.

## Critérios para fechar A5

1. Migração 0012 no DB do operador após backup; prévia local sem rede.
2. Dois ciclos históricos reais por fonte, cursores retomados e sem saltos por truncamento; relatório não expõe cursores e histórico é imutável por refresh.
3. Refresh real separado, auditoria válida e contagem sem duplicação; orçamento real da Meta verificado.
4. Exercitar recuperação auditada de falhas/cursor expirado/lease órfão antes de agendamento contínuo sem supervisão. PostgreSQL concorrente e cobertura de refresh de alta frequência permanecem sem validação.
5. Expandir fontes específicas autorizadas para 30+ com diversidade; coletar 2.000+ posts técnicos sem prometer prazo, depois aplicar mecanismo separado de admissão científica. Não equiparar a meta técnica à científica.

A 10 itens/página e 80 páginas reservadas/dia, o teto aritmético é de 800 itens retornados/dia, não de novos posts. Os 1.961 posts técnicos restantes exigiriam no mínimo 50 runs de 40 novos registros (limite idealizado, sem exclusões ou duplicatas), condicionado ao volume disponível, grants, estabilidade dos cursores, quotas e termos. Não programar chamadas para atingir o teto automaticamente sem validação real.

**Validação:** 10 novos testes A5; regressão A3/A4/A5, ingestão, corpus e migrações: 77 PASS; suíte completa Python reconstruída: **381 PASS** (40,74 s). Os 77 estão incluídos nos 381. `verify_zero_spend.py` PASS e `check_gate0.py` estrutura local verificada; Gate 0B global permanece bloqueado. Código testado offline em SQLite de arquivo, transporte simulado, blobs conferidos contra o GitHub. Sem nova leitura Meta, CI remota ou prova de PostgreSQL. Sem admissão científica ou produção.


## Primeira execução histórica real reportada — 12/11/2026

Prévia no ambiente do operador: manifesto `a1e61806a5b9a57f307f0c0b129fe6f59a63666a7930ecaae90ceb668ef18717`, 15 fontes, 3 aprovadas, 12 deferidas por SOURCE_NOT_APPROVED, 39 media IDs distintos, zero conflitos entre fontes. Orçamento local reservado antes do ciclo: 20/80 páginas. A prévia foi read-only e sem rede.

Ciclo `a5history-20261112141205-e3d3524b`, status BATCH_COMPLETED: 12 páginas, 120 itens retornados, 43 excluídos por idade, 77 elegíveis, 38 novos e 39 refreshes, 39 → 77 registros e media IDs únicos, 3 fontes. Todos os checkpoints reportados como continuation_available.

| Fonte | Run key | Novos | Refreshes | Observações reauditadas | Páginas | Checkpoint |
|---|---|---:|---:|---:|---:|---|
| Sebrae | a5history-20261112141205-e3d3524b-01 | 5 | 15 | 20 | 4 | continuation_available |
| Ton | a5history-20261112141205-e3d3524b-02 | 13 | 12 | 25 | 4 | continuation_available |
| Stone | a5history-20261112141205-e3d3524b-03 | 20 | 12 | 32 | 4 | continuation_available |

Reauditoria de todos os runs: completed, all_traces_valid=true, has_persisted_observations=true. Zero admissão científica, production_approved=false, cobertura não exaustiva. Orçamento conservador esperado após o ciclo: 32/80, sujeito à próxima prévia. A prévia e o ciclo bem-sucedido evidenciam disponibilidade das tabelas no DB operacional; backup e saída exata Alembic não foram fornecidos. Fonte: resumos CLI e reauditoria reportados pelo operador, não inspeção independente do DB/JSON integral. Não registrar cursores privados. Segundo ciclo deve confirmar avanço de pages_examined e last_run_key; refresh deve preservar o checkpoint. Sebrae pode atingir a quota de cinco reservas diárias após a segunda execução histórica, portanto não forçar refresh se deferido. PR permanece draft.


## Segunda execução histórica real e prova de retomada — 12/11/2026

Ciclo `a5history-20261112141401-2ccaaea7`: BATCH_COMPLETED, mesmo manifesto SHA-256 `a1e61806a5b9a57f307f0c0b129fe6f59a63666a7930ecaae90ceb668ef18717`. Prévia: três fontes autorizadas selecionadas, 12 candidatas deferidas, orçamento conservador 32/80. Foram consultadas 12 páginas, retornados 120 itens, zero excluídos por idade, 120 elegíveis e **120 novos**, zero refreshes ou duplicatas. Cobertura do tenant: 77 → 197 registros técnicos e media IDs distintos, três fontes, zero duplicatas entre fontes. Zero admissões científicas e produção não aprovada.

| Fonte | Run key | Novos | Total técnico acumulado | Observações reauditadas | Páginas cumulativas | Checkpoint |
|---|---|---:|---:|---:|---:|---|
| Sebrae | a5history-20261112141401-2ccaaea7-01 | 40 | 60 | 40 | 8 | continuation_available |
| Ton | a5history-20261112141401-2ccaaea7-02 | 40 | 65 | 40 | 8 | continuation_available |
| Stone | a5history-20261112141401-2ccaaea7-03 | 40 | 72 | 40 | 8 | continuation_available |

Todos os runs BD_TECHNICAL_METADATA_COMMITTED; reauditorias read-only completed, all_traces_valid=true, has_persisted_observations=true. Consulta local reportada aos checkpoints confirma avanço 4 → 8 páginas e last_run_key do segundo ciclo nas três fontes, sem divulgar cursores. Dois ciclos históricos A5: 197 observações reauditadas, 158 novos registros e 39 refreshes. Rendimento do segundo ciclo (120 novos/120 retornados) não é garantia de ciclos futuros. Evidência operacional fornecida pelo operador; sem inspeção independente do banco, dos payloads ou dos relatórios integrais.

**Aceite de retomada histórica real reportado.** Orçamento conservador esperado 44/80 após o ciclo. Sebrae atingiu, segundo o histórico informado, cinco reservas diárias; validar a próxima prévia e não contornar a quota. Próximo teste: refresh de fontes elegíveis (esperadas Stone/Ton), com comparação integral dos checkpoints localmente antes/depois, sem publicar cursores ou referências privadas. Recuperação auditada de falhas e agendamento ainda pendentes; PR permanece draft. Meta de 30 fontes e 2.000–5.000 posts não atingida, nem comparável automaticamente à base científica.


## Refresh real independente do histórico — 12/11/2026

Ciclo `a5refresh-20261112141559-2ef847d8`: BATCH_COMPLETED, manifesto SHA-256 `a1e61806a5b9a57f307f0c0b129fe6f59a63666a7930ecaae90ceb668ef18717`. Prévia selecionou Ton e Stone; Sebrae deferido corretamente por BD_BATCH_DAILY_SOURCE_QUOTA_REACHED, 12 candidatas por SOURCE_NOT_APPROVED. Orçamento local antes do ciclo 44/80 páginas reservadas, teto de 8 requisições e 24 observações. Resultado: 5 páginas, 47 retornados, 23 recentes excluídos, 24 elegíveis, zero novos, 24 refreshes, zero duplicatas. Cobertura 197 → 197 registros e media IDs únicos, 3 fontes, zero duplicatas entre fontes.

| Fonte | Run key | Novos | Refreshes | Observações reauditadas | Trilhas válidas |
|---|---|---:|---:|---:|---|
| Ton | a5refresh-20261112141559-2ef847d8-01 | 0 | 12 | 12 | true |
| Stone | a5refresh-20261112141559-2ef847d8-02 | 0 | 12 | 12 | true |

Ambos BD_TECHNICAL_METADATA_COMMITTED, reauditoria completed, all_traces_valid=true, has_persisted_observations=true. Operador comparou SHA-256 da serialização ordenada de todas as linhas de bd_history_checkpoints no tenant antes/depois: CHECKPOINTS_PRESERVADOS: TRUE. Não divulgar cursores, referências privadas ou os hashes integrais. Orçamento conservador esperado após refresh: 52/80, sujeito à próxima prévia. A5 acumula 221 observações reauditadas, 158 novas e 63 refreshes, base de 39 → 197 registros técnicos únicos. Zero admissões científicas, sem produção. Aceite operacional do refresh independente reportado, não inspeção independente do banco privado. Recuperação auditada de falhas, cursor expirado e lease órfão, revisão final e agendamento permanecem pendentes; não ativar execução contínua não supervisionada. Backup/migração exatos e quotas efetivas do provedor não foram independentemente verificados.


## Recuperação administrativa offline — 12/11/2026

Implementada em `src/tapi_gate0/discovery_recovery.py` e `scripts/a5_recover_business_discovery.py`. Inspeção sem argumentos é somente leitura; alterações exigem administrador autenticado e confirmação explícita de que **todos** os processos de ingestão estão parados. Uma falha permanece registrada como `failed` e continua consumindo a reserva diária. O reconhecimento administrativo só libera a seleção futura se as demais condições de grant, manifesto, quota e escopo forem satisfeitas. Reinício histórico é opcional, apenas para o último run histórico falho, e remove o checkpoint da fonte (sem remover posts, reservas ou evidências), registrando o run e páginas anteriores no evento de auditoria. Lease órfão exige chave exata, idade mínima de 30 minutos e ausência de reservas não pertencentes ao ciclo; reservas abandonadas tornam-se `failed`, sem liberação de quota. Eventos e outbox são transacionais. Não há retry automático nem chamada Meta na recuperação.

Inspeção no ambiente do operador, após atualizar a branch: `python scripts/a5_recover_business_discovery.py`. Não provoque falhas ou leases órfãos na base operacional saudável. Os cenários destrutivos foram testados apenas em banco temporário SQLite com transporte simulado. Registre backup e não execute recuperação com outras rotas de ingestão em paralelo; a confirmação operacional de parada não é prova automática de inexistência de processos. A serialização de lease/recovery é por tenant e somente no fluxo A5. Não há teste PostgreSQL real, CI remoto ou inspeção independente do banco do operador.

Regressão local: 27 PASS nos testes A4/A5/recovery; 385 PASS na suíte Python completa (39,81 s); `verify_zero_spend.py` PASS. Cinco blobs de código/teste publicados e comparados por hash com a cópia testada. Nenhuma nova chamada externa ou alteração da base do operador. Manter PR em draft até revisão final, inspeção operacional somente leitura, evidência de backup/migração e autorização explícita para merge. Agendamento permanece desligado; expansão de fontes e admissão científica continuam pendentes.


## Inspeção operacional pós-recovery — 12/11/2026

Operador executou `python scripts/a5_recover_business_discovery.py` após atualização da branch. Resultado reportado: `{"status":"RECOVERY_INSPECTION","lease":null,"latest_a5_blocked_runs":[],"reserved_runs":0,"external_data_accessed":false}`. Inspeção somente leitura aprovada; nenhuma recuperação necessária, sem mutações de checkpoint. Não constitui exercício real de recuperação de falha nem inspeção independente do DB. Na revisão de 12/11, GitHub reportou PR integrável, mas nenhuma execução PR-triggered, status de CI ou review formal foi encontrada no head anterior `4d64655`. A assinatura do fluxo administrativo CLI foi conferida contra IdentityStore.login/resolve/revoke. Permanecem pendentes evidência de backup/migração, regressão verificável no checkout final e autorização explícita de merge. Manter agendamento desligado e execução serial supervisionada; 197 posts técnicos, 221 observações A5 e zero admissões científicas. Não há necessidade de repetir coleta para fechar a inspeção.


## Regressão no Windows e correções de portabilidade — 12/11/2026

O operador reportou 373 PASS, 12 falhas e um warning, com verificação de gasto zero PASS. Dez falhas Studio E6/E7 por ausência de Pillow (`PIL`), uma falha do preflight por flags reais herdados (`CREDENTIAL_MISSING` em vez de `OFFICIAL_READS_DISABLED`), uma falha da prévia A5 por erro genérico anterior à conexão (`A5_INVALID_MANIFEST_OR_LIMITS`). A causa exata desta última não é demonstrada pelo log; hipótese de portabilidade/validação de URL SQLite. Corrigimos a construção de caminho do fixture com `as_posix()`, escrita UTF-8 explícita, guard compartilhado com `make_url` para os dois CLIs A5, diagnóstico separado `A5_DATABASE_INVALID_OR_MISSING` e novo teste de arquivo SQLite ausente sem criação. `test_cli_defaults_to_no_network` neutraliza ambos os flags por monkeypatch, sem alterar as proteções do preflight. Pillow (`>=11,<13`) também passa a integrar o extra `dev`; o extra `local_render` permanece. Nenhum teste removido ou convertido em skip.

Regressão local Linux com `TAPI_OFFICIAL_METADATA_READS=1` e `TAPI_ZERO_BILLING_CONFIRMED=1` e sem credencial real: 39 PASS focal; **386 PASS** completa (40,27 s), `verify_zero_spend.py` PASS. Sete blobs conferidos com a cópia testada. Não afirmar correção Windows confirmada até reexecução do operador. Atualizar branch, instalar `python -m pip install -e ".[dev,local_render]"` e executar testes sem credenciais reais e com flags de ingestão desligados. O warning Starlette não é a causa das falhas. Nenhuma alteração na base operacional, coleta Meta, merge ou agendamento. Backup/migração anterior continua não confirmado pelo operador.
