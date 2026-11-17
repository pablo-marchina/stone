# A00.1 — Baseline e regressão local (17/11/2026)

Plano operacional A00–A11, arquitetura v5.2 + DEC-018, entrega única.
O mapa `planning/action_2026-11-17/phase_map.json` atribui os 204
IMP a exatamente um incremento responsável, sem alterar o DAG,
os critérios de aceite ou as matrizes sincronizadas oficiais.

## Corte anterior à implementação A00.1
- main d2efe5f2ec2ec159801039420b579b50dbf0236d.
- PR #43 draft aberto, não integrado: 0aa7d86e6d14531d394c6df06ed2174879b7e373,
  base main, 34 commits, 20 arquivos alterados, migração 0012.
- PR #44 draft aberto, não integrado: 860226c79ed2dfaab51dc7d648a057080acdcf50,
  base #43 no mesmo SHA, 273 commits, 157 arquivos alterados, sem migração adicional.
  Contagem anterior à adição destes arquivos A00.
- A6: 1065 conteúdos/21 perfis/1169 snapshots reportados, 858 legendas
  primárias, zero admissões científicas demonstradas. Última validação
  focal Evidence Lab: 16 Python PASS/1 configuração incompleta, 2 Node PASS,
  consulta autenticada do caso inicial confirmada depois; teste opt-in
  completo ainda não reportado. UI legível: 7 funções em V8 adaptado,
  não node --test. Regressão completa A6 pendente.
- O script histórico check_gate0 valida 22 CAP do bootstrap, não a
  arquitetura atual. Preservado. verify_zero_spend continua obrigatório.
- Inspeção dos CSV sincronizados pelo assistente: 204 IMP, 23 CAP,
  18 DEC, 7 gates, 543 pares distintos de dependência; referências de
  tarefas a CAP/DEC/gates/IMP válidas; IMP-062 mantém dispensa declarada,
  não cumprimento. Validação completa em Python e DAG no operador pendente.
- Mapa conferido contra Plano de Ação 17/11: 204 tarefas, sem ausências
  ou duplicatas. A00=44, A01=10, A02=13, A03=12, A04=18, A05=10,
  A06=10, A07=21, A08=9, A09=11, A10=21, A11=25.

## Implementação
`scripts/a00_baseline.py`: requer HEAD de 40 caracteres e checkout limpo
antes e depois; inventário de módulos, testes Python/Node, migrações,
árvore Git, versões de dependências e presença das ferramentas. Valida
contagens/IDs, referências das tarefas, DAG acíclico, mapa de fases e
DEC-018; hashes SHA256 dos CSV e do mapa. Não altera matrizes.
Perfis:
- inventory: inventário + check_gate0 e zero_spend, não regressão;
- full: suite pytest tests completa + arquivos rastreados tests/test_*.mjs
  via node --test; OCR local opcional com diretório explícito;
- semantic: nove arquivos de testes semânticos no ambiente tapi-s1,
  não segunda regressão completa nem inferência do checkpoint.
Ambiente filho reduzido: não repassa TAPI_DATABASE_URL, tokens ou flags
operacionais, proxies, PYTEST_ADDOPTS; ativa HF/Transformers offline,
preserva PATH/Conda e variáveis de execução local. Não é sandbox OS:
testes existentes podem usar fixtures, subprocessos e arquivos locais;
não garante isolamento de rede ou filesystem do processo.
Relatórios exclusivos em artifacts/private/<nome>/summary.json,
logs por etapa com SHA256 e JUnit pytest; código 2 em falha, bloqueio,
checkout alterado ou ausência de testes válidos. Skips não são passes;
full_regression_without_skips é distinto de checks_passed.
Não instala deps, não executa os CLIs standalone de benchmark de
modelos, não testa o banco operacional, não faz backup/migração/merge
ou operações externas. Testes de integração locais de fixtures podem
usar FFmpeg/Tesseract. Teste opt-in do triplet Lab não herda configuração,
portanto skip esperado nesse runner; execute separadamente se necessário.
Oito testes novos do runner, ainda não executados pelo assistente.

## Operador Windows
Interromper Uvicorn e quaisquer writers/ingestão antes da regressão.
Na branch A6, atualizar fast-forward; conferir HEAD anunciado no PR.
Se checkout sujo, não descartar alterações, enviar git status.
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$baseline = (git rev-parse HEAD).Trim()
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

conda activate tapi-asr
$env:Path = "C:\Program Files\Tesseract-OCR;C:\Program Files\eSpeak NG;$env:Path"
$env:ESPEAK_DATA_PATH = "C:\Program Files\eSpeak NG"
python scripts/a00_baseline.py --expected-head "$baseline" --profile full --report-name "a00-full-$stamp" --tessdata-dir "C:\Models\tapi\tessdata-fast-4.1.0"

conda activate tapi-s1
python scripts/a00_baseline.py --expected-head "$baseline" --profile semantic --report-name "a00-semantic-$stamp"
```
Enviar os dois JSONs de stdout. Se falha, consultar logs no diretório
privado indicado (não anexar segredos/DB). Não repetir modelos
Whisper/GLiNER/Qwen nem apagar arquivos para obter PASS.
Se ambos executados e revisados, A00.2 reconciliar resultados,
A00.3 usar a ferramenta existente a6_backup_restore_drill com
confirmação de writers parados, A00.4 revisão/merge só mediante
autorização aplicável. A01 consulta read-only pode avançar em paralelo
após preflight e análise de regressões; sem alterar DB até backup.
Nenhum gate global liberado. A00.1 em IMPLEMENTADO_NAO_TESTADO no
corte deste documento. A00, A01–A11 não declarados homologados.

## A00.2 — regressão reportada pelo operador (19:16, 17/11/2026)
Commit f69e70ff7a913a672b7e22915a9100f39cd29e5c, árvore
c8b32215221869d161afc02a49cea7bc868d9ddc, ambos perfis limpos.
91 módulos Python, 87 arquivos Python de testes, 3 Node, 12 migrações.
Matrizes e mapa A00–A11 conferidos pelo runner, sem alteração.
- full tapi-asr, Python 3.11.18: 907 testes, 899 PASS, 7 FAIL,
  1 SKIP (triplet opt-in do Evidence Lab, removido intencionalmente
  da configuração filha), 0 erros JUnit; pytest exit 1 em 211,529s.
  Node exit 0, Gate0 histórico exit 0, zero-spend exit 0.
  Relatório a00-full-20261117-191639, pytest.log SHA256
  332e591c0cf3d5684a1218ca8b3818bfd0f7455f85d41b7544c80180c0779123.
- semantic tapi-s1, Python 3.11.18: 189/189 PASS em 3,594s,
  Gate0/zero-spend exit 0. Relatório a00-semantic-20261117-191639,
  pytest.log SHA256 8606315a9b960942ccd094ee267330d1269f4372a2639fb9bb6fb3d2960b7bf1.
  Não somar os 189 aos 899: suíte sobreposta.
- Ambiente asr sem torch/GLiNER/transformers; ambiente s1 sem
  Pillow/faster-whisper/ctranslate2/onnxruntime, como provisionado.
  Nenhuma causa das sete falhas é identificável apenas pelos
  resumos agregados; não presumir dependência ou regressão específica.
  Não reexecutar toda a suíte antes de examinar diagnósticos.
- A00.1 execução confirmada; A00.2 em investigação; PRs continuam
  Draft, A00.3 backup/restore e A00.4 integração não executados.
  Não homologar nenhuma capacidade/gate por estes testes.

### Diagnóstico incremental
Runner passa a incluir failed_tests (identidades, não traceback)
e SHA256 do XML em novos relatórios. Novo a00_inspect_report
lê relatório histórico sem executar testes ou escrever arquivos,
confere os hashes dos logs, contagens JUnit e, se registrado,
hash do XML. Nos dois relatórios anteriores o XML não tinha digest
prévio: o novo hash é observação atual, não atestação de integridade
histórica. Os identificadores parametrizados podem incluir valores;
revisar antes de compartilhar. Quatro testes novos, pendentes execução.
```powershell
git pull --ff-only
conda activate tapi-asr
python -m pytest -q tests/test_a00_baseline.py tests/test_a00_inspect_report.py
python -m scripts.a00_inspect_report --report-name "a00-full-20261117-191639"
Get-Content "artifacts/private/a00-full-20261117-191639/pytest.log" -Tail 160
```
Enviar identidades das falhas e trechos relevantes (remover segredos
se presentes). Conservar relatório original; a próxima correção
depende dos sete diagnósticos. Não liberar media/produção, não
baixar modelos, não alterar DB nem merge.

## A00.2 — diagnóstico e correções das sete falhas (17/11/2026)
Operador e2a2255: 12/12 testes do runner/inspetor PASS em 0,42s.
a00_inspect_report recuperou os 7 testes com falha e confirmou hashes
dos logs; summary SHA256 83a1047e4b316af92ffa606a43539b40c74252bc7df418aa1e9a4e418481ba40,
JUnit SHA256 c63634089ea6dc81fe8e0150a18ca3c133a1beee9f93be6f3e438dca999d491d
observado posteriormente, sem digest prévio. Regressão original
permanece 899 PASS / 7 FAIL / 1 SKIP (commit f69e70f).

### Causas verificadas no traceback e código
- Quatro falhas em test_discovery_corpus_ingestion: fixture recente
  de 02/11 tornou-se madura em 17/11. new_records=2, esperado 1.
  Corrigidos timestamps de fixtures para NOW-30d e NOW-2d; nenhum
  ajuste ao sampler de produção, grants ou critérios de admissão.
- Duas falhas em test_discovery_technical_a3: capture de 04/11
  usava datas fixas; um dos dois posts recentes já ultrapassou 14d.
  Preservados os valores originais de captura e seus intervalos;
  replay desloca os timestamps pelo delta a partir de CAPTURE_AS_OF
  (05/11 01:16 UTC) para NOW. Não representa nova observação real.
- Uma falha em test_studio_e6: MP4 local criado e recuperado com
  hash correto; assert de cache esperava no-store, API explicitamente
  retorna private, no-store e middleware preserva private. Atualizado
  contrato do teste sem enfraquecer proteção. Verificações posteriores
  de duração, streams, isolamento e revogação ainda precisam rodar.
- Novos testes de fronteira para ambos os leitores: exatamente 14d
  é tecnicamente elegível; 14d menos 1s ainda é recente. MockTransport,
  relógio de referência explícito, nenhuma chamada real. Não conferir
  admissão científica à elegibilidade técnica.
- Cinco commits de correção: a9a22e2, 621a73e, def2706, 2811073,
  71ff4fa. Somente arquivos de teste, sem alteração de produção.
  Não executados pelo assistente.

### Próxima validação
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr
$env:Path = "C:\Program Files\Tesseract-OCR;C:\Program Files\eSpeak NG;$env:Path"
$env:ESPEAK_DATA_PATH = "C:\Program Files\eSpeak NG"
python -m pytest -q tests/test_discovery_corpus_ingestion.py tests/test_discovery_technical_a3.py tests/test_studio_e6.py tests/test_a00_baseline.py tests/test_a00_inspect_report.py
if ($LASTEXITCODE -ne 0) { throw "Regressao focal falhou; nao executar full" }
$baseline = (git rev-parse HEAD).Trim()
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a00_baseline.py --expected-head "$baseline" --profile full --report-name "a00-full-$stamp" --tessdata-dir "C:\Models\tapi\tessdata-fast-4.1.0"
```
Estimativa de inventário da suíte: 913 testes (907 anteriores +4
do inspetor +2 de fronteira), com 1 skip opt-in esperado. Confirmar
contagens reais, não presumir PASS. Suíte semântica anterior 189/189
no f69e70f; não alterada, mas resultado não certifica novo HEAD.
A00.2 permanece aguardando regressão; A00.3 e merges não executados.
Nenhum DB operacional alterado, download de modelos ou gates liberados.

## A00.2 — regressão corrigida confirmada pelo operador
HEAD 23142eb81481792a203009c2a633624f183cf5b9, árvore
ca4b65ce03a07ce13d411aeffe14195d67dc66b6.
47/47 testes focais PASS em 15,13s; full 913 coletados,
912 PASS / 0 FAIL / 0 ERROR / 1 SKIP em 136,401s (runner).
Skip é test_operator_actual_triplet_when_configured, intencional.
Node, Gate0 histórico, zero-spend PASS; checkout inalterado.
Relatório a00-full-20261117-193122; pytest.log SHA256
3d72dd8ad849c6f083641741e1ccdd5cfe257d44daec1793354d711c51eeb1b7,
JUnit SHA256 d94b137c482af57a4f5c2a667d9edc11bb42548fd7a2cffb6c503fa6d6d996e5.
91 módulos, 88 arquivos Python de teste, 3 Node, 12 migrações.
A00.2 concluído para esse HEAD. Sem homologação global, DB operacional
não testado pela suíte, sem merge. Aviso de depreciação Starlette/httpx
não bloqueante; preservar e avaliar em manutenção, sem upgrade casual.

## A00.3 — backup/restore lógico aprimorado (IMP-144 parcial)
Reutilizado discovery_backup + script a6_backup_restore_drill.
Versão tapi-sqlite-backup-drill.v2 compara schema, contagens,
integrity_check, foreign_key_check, Alembic 0012 e SHA256 lógico
por tabela, nos três bancos (snapshot da origem, backup e restore
descartável). Multiset de hashes de linhas tipadas, incluindo NULL,
BLOB, texto, int e float; mantém duplicatas e não depende da ordem.
Não retorna conteúdo, credenciais ou hashes individuais de linhas.
Preflight de espaço: 2x page_count*page_size + 64MiB, no volume
do destino; não é reserva nem garantia contra concorrência de disco.
Sem sobrescrita; source mode=ro; restore nunca sobre original.
Cópia contém todos os tenants e dados privados, não enviar o arquivo.
A verificação depende da declaração de todos os writers parados;
não é lock distribuído e não afere RPO/RTO de produção. Complexidade
de hashes é O(n log n) por tabela, memória proporcional às linhas.
3 testes novos (alteração mesmo count, multiset e espaço).
A00.3 implementado, backup real pendente. Sem migrations.

## A01.1/2 — início independente read-only
Novo corpus_inventory.py e duas rotas GET autenticadas:
 /v1/corpus/inventory
 /v1/corpus/inventory/{content_id}
Escopo admin/researcher/service, igual ao data-card existente.
Cruza ingestion_records, profiles, grants, content, creators; tenant
vem da sessão, grant ativo/tecnicamente verificado reavaliado a cada
requisição, identidade payload/índice validada, registros ambíguos
recusados. Apenas metadados externos registrados; não inclui fixtures
nem C2/C3/C4. Não afirma admissão C1, reauditoria do manifesto/traces,
autorização de mídia ou ranking. Busca handle/ID, filtro formato,
plataforma, perfil, setor, paginação até 100, snapshots históricos
válidos ordenados e paginados. Sem legenda em texto, URL, arquivo ou
payload bruto. Limites defensivos 10k registros e 20k snapshots por
consulta, sem truncamento silencioso. Lista é inventário atual,
não snapshot estável entre páginas; contagem excluída refere-se
apenas às linhas do join. Sem alterações de schema ou banco,
no-store privado. 3 testes com DB descartável e mocks de dados;
ainda não executados pelo assistente. UI Data Explorer não integrada.
Mapeamento incremental IMP-010/012/053/082, sem concluir critérios
originais; IMP-082 depende também de ranking/links/QA.
Nenhuma tarefa oficial ou gate promovido.

### Operador: validar backup e serviço, sem nova coleta
Interromper todos os writers (Uvicorn, agendador, ingestão,
render workers, scripts que persistem). Usar URL e tenant
operacionais existentes, sem criar banco ou mudar grants.
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr
python -m pytest -q tests/test_discovery_backup.py tests/test_corpus_inventory.py tests/test_a00_baseline.py tests/test_a00_inspect_report.py
python scripts/verify_zero_spend.py
```
Se testes PASS, confirmar configuração:
```powershell
if ([string]::IsNullOrWhiteSpace($env:TAPI_DATABASE_URL)) { throw "Reconfigure a URL do banco existente" }
$env:TAPI_TENANT_ID = "local-research"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_backup_restore_drill.py --output-name "a00-baseline-$stamp.sqlite3" --confirm-all-writers-stopped
```
Esperar BACKUP_RESTORE_VERIFIED e logical_table_contents_match=true.
Depois do backup, executar inspeção somente leitura, sem expor
legendas ou IDs no stdout:
```powershell
python -c "import os,json; from tapi_gate0.discovery_local_db import validate_existing_database_url; from tapi_gate0.sa_store import engine_for; from tapi_gate0.corpus_inventory import list_inventory,InventoryFilter; e=engine_for(validate_existing_database_url(os.environ['TAPI_DATABASE_URL'])); r=list_inventory(e,os.environ['TAPI_TENANT_ID'],InventoryFilter(limit=100)); print(json.dumps({k:v for k,v in r.items() if k!='items'} | {'page_items':len(r['items']), 'page_with_snapshot':sum(x['latest_snapshot'] is not None for x in r['items'])})); e.dispose()"
```
Enviar resultados dos testes e JSONs (não copiar o banco).
Sem repetir benchmark ou alterar dados. Próximo: A00.4 revisão
PRs (merge só com autorização) e A01.3 Data Explorer integrado.
