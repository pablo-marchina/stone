# CAP-001 / A5 — aquisição histórica e contínua com curadoria incremental

**Data:** 12/11/2026. **Base:** main após merge do [PR #42](https://github.com/pablo-marchina/stone/pull/42) (`d2efe5f`). **Status:** incremento implementado e testado offline; execução real A5 ainda não efetuada. A4 comprovou 39 posts técnicos únicos em 3 fontes, 60 observações reauditadas nos três lotes A4, zero admissões científicas. DEC-016 e DEC-018 continuam aplicáveis.

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
