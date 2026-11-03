# Execução do Plano Único v5.2 — incremento 01 (30/10/2026)

**Branch:** `feat/ingestion-pagination-v52-20261030`  
**Base:** `b484eda4f9575c7917027a094da320e1c1949715` (`main`)  
**Status:** código e testes adicionados; **testes locais e operação com APIs reais ainda NÃO executados/homologados nesta revisão**.

## Relação com o Plano Único

- **IMP-165 (PARCIAL):** página de mídia Instagram com cursor, exclusivamente no host oficial. Nenhuma URL `paging.next` é seguida. A recuperação da página seguinte exige `resume=true`, estado anterior persistido e novo `run_key`.
- **IMP-166 (PARCIAL):** piso de `min_age_days=14` antes da persistência, com contagem separada de itens recentes; o ranking já tinha seu próprio filtro de idade. Estratégias de coortes e auditoria da população ainda pendentes.
- **IMP-163 (PARCIAL):** registro de alterações e verificação local de integridade do ZIP do Plano v5.2.
- **IMP-168 (NÃO CONCLUÍDA):** o novo checkpoint não equivale a refresh de snapshots; os dados de posts já persistidos ainda não são atualizados.
- **IMP-164 (BLOQUEADO EXTERNAMENTE):** Meta OAuth/grants não comprovados; não ativar ingestão real sem teste de autorização.
- **IMP-167/IMP-170 (PENDENTES):** descoberta autorizada de perfis, amostra real e data card ainda não implementados.

Os rótulos acima registram avanço **nesta branch**, não alteram automaticamente os status da matriz oficial nem atribuem aprovação institucional.

## Contratos implementados

`IngestionRequest` recebe `resume: bool = false` e `min_age_days: int = 14..3650`. `IngestionResult` acrescenta `excluded_too_recent` e `next_page_available`. Chamadas existentes mantêm o comportamento de primeira página. O modo YouTube não aceita `resume`, porque ali a coleta ainda usa IDs explícitos de vídeos autorizados.

A tabela `ingestion_page_checkpoints` é criada pela migração Alembic `0003_ingestion_page_checkpoints`. Ela armazena apenas o cursor opaco por tenant/plataforma/conta, conclusão e horário. Nunca persiste tokens ou uma URL de paginação.

**Fluxo esperado:** (1) confirmar direitos, OAuth, guardas financeiros e grant; (2) executar primeira página; (3) examinar `next_page_available`; (4) executar nova requisição com `resume=true` e novo `run_key`; (5) repetir até `false`. Reexecutar com `resume=false` reinicia a leitura da primeira página, sem duplicar os posts já presentes.

## Avaliações adicionadas

`tests/test_ingestion_cursor.py` cobre: cursor retornado em página anterior, persistência de checkpoint, segundo lote por retomada, final da paginação, descarte de post com menos de 14 dias, rejeição de cursor com URL, ausência de checkpoint e contrato YouTube. Todos os provedores são simulados.

**Execução exigida antes do merge:**

```bash
python -m pip install -e ".[dev]"
python -m alembic upgrade head  # com TAPI_DATABASE_URL de SQLite temporário configurada
python -m pytest -q
node --test tests/frontend/*.mjs
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
```

Verificar também downgrade/upgrade de 0003 em um banco de teste existente na revisão 0002. Não executar em produção sem backup e validação.

## Bloqueios e limitações explícitos

1. **Sem rede real:** nenhum token foi gerado, acessado ou armazenado; as flags de leitura continuam OFF por padrão.
2. **Controle de volume:** continuam 10 posts por requisição e 5 execuções/conta/dia. A paginação não resolve, por si só, a meta de 2.000–5.000 publicações.
3. **Retomada ainda manual:** o cliente deve enviar `resume=true`; não existe agendador, lock de exclusividade por conta ou reprocessamento automático de jobs.
4. **Sem refresh de métricas:** deduplicação preservada, mas snapshot de interações não é atualizado por uma nova leitura do mesmo post.
5. **Sem comparação inferencial validada:** a presença de mais páginas não prova permissão para ranking entre contas ou representatividade da amostra.
6. **Dependência externa:** autorização Meta, permissões por conta, licenciamento e política de uso continuam bloqueios independentes do código.

## Sincronização do backlog — pendência

O Plano v5.2 integral fornecido à conversa foi conferido localmente, com todos os 15 caminhos listados em `CHECKSUMS_SHA256.txt` aprovados. SHA-256 do ZIP de origem: `0dbb51bf18a75734fcb2121373590bfc1ba3ae5cd729aff9a4dcb537491aa04d`.

**Ainda não foram sincronizados no GitHub os 13 CSVs + manifesto/checksums da v5.2.** A síntese em `docs/24_...` não substitui esses arquivos. Essa sincronização continua como primeira pendência documental e deve preservar os IDs históricos.

## Próxima execução técnica

Auditar a migração e os testes; implementar `IMP-168` (refresh versionado de snapshots), bloqueio contra corrida de dois jobs por conta e métricas de cobertura; completar `IMP-164` assim que o administrador Meta concluir as ações de autorização. Não iniciar descoberta externa fora dos direitos concedidos.

## Atualização — IMP-168 e verificações locais (30/10/2026)

**Implementado nesta branch (pendente de suite E2E):**

- Em vez de descartar toda publicação conhecida, `_persist_item` grava um novo `metrics_snapshots` quando os valores de curtidas, comentários, seguidores ou visualizações mudam; mantém os snapshots anteriores e usa identificador novo.
- Releituras sem mudanças permanecem `duplicate_records`; atualizações ficam em `refreshed_records` também no ledger persistido `ingestion_runs`.
- Atualizações emitem `ingestion.metrics_refreshed`, com versão monotônica baseada na versão máxima anterior, e outbox transacional; métricas não observadas não apagam valores históricos.
- A migração `0003` inclui `ingestion_runs.refreshed_records` e checa a existência da coluna, pois a revisão `0002` utiliza a definição corrente da tabela.
- Novos testes: `tests/test_ingestion_snapshot_refresh.py` e `tests/test_ingestion_migration_v3.py`.

**Testes realmente executados localmente no ambiente de análise:** dois smoke tests **isolados** com SQLAlchemy/Alembic e SQLite em memória, usando uma réplica da definição de tabela e a lógica da revisão `0003`. Foram aprovados: (1) upgrade/downgrade com ledger anterior preservado e (2) instalação cujo schema antigo já contém a coluna adicionada. Isso **não é execução da suíte do repositório**.

**Bloqueio para homologação:** o ambiente de execução local não possui checkout do repositório privado e não consegue resolver o host GitHub para `git clone`; a conexão do GitHub permite leitura/escrita de arquivos e PRs, mas não disponibiliza o checkout diretamente à sessão Python. Para cumprir o pedido de testes completos, é necessário um ZIP do conteúdo da **branch do PR #11**, sem `.env`, tokens, senhas, arquivos de banco real ou credenciais, enviado ao chat. Nenhuma permissão de API Meta/YouTube é necessária para os testes offline. Até receber os arquivos ou obter outro acesso local autorizado, os testes de integração permanecem `NAO_EXECUTADO`.

**Próximo gate:** rodar `pytest`, frontend Node, migrar 0002→0003 e base limpa por Alembic real, revisar idempotência, concorrência de ingests e `run_key`, corrigir falhas, atualizar PR. Não fazer merge ainda.

## Validação final em checkout local (03/11/2026)

**Fonte local:** ZIP da branch fornecido no chat, extraído em área temporária sem arquivos `.env` nem credenciais reais. Esta seção **substitui** o bloqueio de checkout/testes descrito acima; a suíte agora foi executada de fato.

**Falha inicial real:** `pytest` apresentou `175 passed, 2 failed`. Ambas as falhas vinham do versionamento histórico das migrações: `0001` criava tabelas de ingestão registradas dinamicamente no `metadata` atual; `0002` tentava criá-las novamente.

**Correção feita e testada:** revisão `0001` restringida ao conjunto fixo de 13 tabelas de domínio e identidade originais; revisão `0002` congela a estrutura dos três objetos históricos de ingestão, sem dependência do esquema atual. Assim, `0003` adiciona checkpoint e contador de refresh. Incluído `path_separator=os` no `alembic.ini` para compatibilidade com Alembic atual.

**Resultados executados localmente:**
- `PYTHONPATH=src python -m pytest -q` → **178 passed, 0 failed**, sem warnings.
- `node --test tests/frontend/*.mjs` → **3 passed, 0 failed**.
- `PYTHONPATH=src python scripts/check_gate0.py` → **aprovado**.
- `PYTHONPATH=src python scripts/verify_zero_spend.py` → **aprovado**.
- `PYTHONPATH=src python -m compileall -q src migrations tests` → **aprovado**.
- Alembic real SQLite: base vazia → `head` (0003), base 0002 → 0003, rollback 0003 → 0002, novo upgrade; sem perda do registro de execução anterior.
- Teste `test_migrated_schema_persists_new_and_refreshed_metric_snapshots`: banco realmente migrado, um post criado, uma alteração de métricas gerando segundo snapshot e uma releitura idêntica sem duplicação.

**Evidência formal da IMP-168:** `evidence/acquisition/refresh_contract_tests.json`. O critério de aceite da tarefa (histórico, denominador, `observed_at`, sem reescrever métricas anteriores) está comprovado **em SQLite com provider mock**.

**Fronteiras ainda não homologadas:** PostgreSQL real, corrida de ingestões concorrentes, acesso Meta/YouTube real, coleta de múltiplos perfis e desempenho em volumes de milhares de posts. O módulo externo continua desativado por padrão e o custo zero foi verificado. O PR deve passar por revisão antes do merge na `main`.
