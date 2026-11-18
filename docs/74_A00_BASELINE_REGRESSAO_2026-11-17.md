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

## A00.3 / A01 — retorno de testes e Data Explorer integrado
Operador: 29 PASS / 1 FAIL (30 testes), zero-spend PASS.
Falha test_inventory_pagination_filters_and_snapshot_history:
snapshot escolhido likes=10, esperado 20. Os testes de backup
passaram; backup operacional ainda não foi reportado.
Causa provável: resolução do relógio em gravações consecutivas
gera observed_at igual; ordenação existente usa snapshot_id como
desempate determinístico, que não expressa ordem de criação.
O traceback não contém timestamps/IDs; empate original não
comprovado. Não mudar seleção por quantidade de curtidas.
Fixture agora usa relógio injetado, tempos distintos no passado
e grants temporalmente coerentes. Novo teste força empate e
confirma política comum observed_at DESC, snapshot_id DESC.
API informa snapshot_order e latest_snapshot_timestamp_tie;
nenhuma mudança na ordem do ranking, ingestão ou DB. Ordenação
causal por evento/versionamento é trabalho futuro caso necessário;
não inferir ordem cronológica em empate.

A01.3 parcial (IMP-081/082): inventory.mjs integrado ao Dashboard
existente, sem nova página/login, token em memória. Link âncora
Data Explorer, carregamento após login admin/researcher/service,
filtros allowlist plataforma/formato/setor/conta/handle ou ID,
25 itens por página, detalhes e snapshots paginados, estado vazio,
erro, negado, carregamento e limpeza no logout. Resposta obsoleta
descartada por epoch e sessão. Proteção adicional no wrapper api:
401 de token anterior não revoga sessão mais nova. Sem HTML
arbitrário, texto de legenda, player, links externos, ranking,
admissão ou novas operações. Zero diferente de indisponível.
Empate temporal indicado no detalhe. Não há promoção de
metadados para evidência científica. 1 novo teste Python,
4 Node; não executados pelo assistente. UI não verificada no browser.
Sem migrações, escrita operacional ou merge.

### Próxima validação
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr
python -m pytest -q tests/test_discovery_backup.py tests/test_corpus_inventory.py tests/test_a00_baseline.py tests/test_a00_inspect_report.py
node --test tests/test_inventory_ui.mjs tests/test_evidence_lab_ui.mjs
node --check src/tapi_gate0/web/main.mjs
node --check src/tapi_gate0/web/inventory.mjs
python scripts/verify_zero_spend.py
```
Esperado 31 Python, 11 Node nos dois arquivos. Se qualquer
falha, preservar logs; não executar backup se testes falharem.
Com todos os testes PASS e writers parados, executar o backup v2
e consulta agregada conforme comandos anteriores. Só depois
reiniciar Uvicorn local com configuração existente, abrir /app/,
login habitual, clicar Data Explorer, selecionar detalhes e
testar filtros/paginação/logout. Validar contagens reais, não
assumir que todos os 1065 registros têm grant atual/registro.
A00.3 aguarda execução real, A00.4 revisão/merge pendente,
A01.4 ligação de avaliações/evidências, A01.5 contrato compartilhado,
A02 autorização por ativo continuam pendentes.

## A01.3 — consulta real do operador; A01.4 — rubrica histórica integrada
Operador reportou Data Explorer autenticado às 19:47 de 17/11:
1065/1065 registros visíveis, 0 exclusões após join, 25 linhas
na primeira página, métricas e maturação exibidas. Confirma
listagem real no browser; detalhes, filtros, paginação, logout,
testes focais do HEAD 95c301e e backup operacional v2 ainda não
foram reportados. Não presumir PASS nem admissão científica.
A01.4: corpus_rubric_read.py projeta somente avaliação histórica
rubric-v1 / deterministic-text-metadata-v1 / caption-metadata-baseline
no detalhe do inventário, usando o mesmo tenant e grant vigente.
Valida identidade payload/índice, timestamp e correspondência
do ID legado ao fingerprint de legenda atual. Fingerprint
truncado é vínculo de consistência, não atestação criptográfica
independente de valores. Não executa classificador, revalidação
semântica ou nova inferência. Limite 100 avaliações por publicação;
somente uma baseline correspondente é selecionada. Todos os 20
campos presentes; candidatos permitidos tipo_post (confere valor),
tema_principal, tem_cta e tipo_cta (par consistente), apenas
metadado/legenda e locador correspondente, sem retornar locador
bruto, legenda, notes ou mídia. Outros campos observados fora
do escopo são retidos; não observável vira abstenção, não falso.
Nenhuma alteração em rubrica persistida. Não expõe avaliações
posteriores de relatórios privados, não reaudita manifesto/trace
nem verifica direitos por ativo. UI em detalhes da publicação,
20 campos, contadores e razões traduzidas; compartilhamento de
vocabulário com Lab sintético, não mistura datasets.
3 testes Python novos e 1 Node novo; pendentes execução.
A01.4 parcial; integração de relatórios grounded e envelope
persistente A01.5 ainda pendentes. Sem schema, escrita, modelo,
mídia, gastos ou merge.
Validação: repetir somente focal backup/inventory/baseline/inspector
(34 Python esperados), Node inventory/evidence (12 esperados),
zero-spend. Confirmar backup operacional v2 antes de iniciar servidor.
No Data Explorer abrir Detalhes de uma publicação; conferir 20
campos, estado e versão, não assumir cobertura sem o resultado.
Preservar o relatório de backup, não compartilhar SQLite.

## A01.4 — QA detalhes reais e detecção de contrato ausente
Operador consultou content.efbb8e73b8552157e7fef7,
empreendedorasdabelezagb: imagem, setor beleza, grant vigente até
17/12, 1 snapshot, 35 likes/1 comentário/65432 seguidores, views
indisponíveis. Identidade, permissões e histórico exibidos.
Rubrica não apareceu no conteúdo copiado. Não foi informado HEAD,
versão dos módulos carregados ou resposta HTTP; não presumir
causa confirmada. A API a6d5947 retorna stored_rubric mesmo sem
avaliação compatível; frontend anterior a esse corte não exibe.
Nova revisão identifica build A01-RUBRIC-2 no título e versiona
URLs de main/inventory/evidence_lab/CSS. Frontend distingue
stored_rubric ausente, contrato incompatível e resultado válido
com 20 campos (inclusive todos não avaliados). Contadores são
conferidos contra estados; não apresenta promoção canônica.
Teste Node adicional simula clique real, API antiga e rubrica
válida sem avaliação, pendente execução. Não alterada política,
API, dados ou autenticação. Diagnóstico read-only por conteúdo
pode imprimir schema e contagens sem valores, locadores ou legenda.
Reiniciar servidor após git pull, Ctrl+F5 e login. Verificar
marcador A01-RUBRIC-2, consultar detalhes do mesmo post. Se ainda
falhar, comparar saída local get_inventory_item e resposta HTTP.
Não iniciar nova inferência nem repetir benchmarks. Backup v2 e
focal anterior continuam aguardando confirmação; não presumir PASS.

## A01.4 — rubrica histórica verificada no navegador; A01.5 — replay grounded
Operador confirmou painel histórico de content.efbb8e73b8552157e7fef7:
20 campos, 3 candidatos (imagem, tem_cta=true, tipo_cta=link na bio),
17 abstenções, 0 medições/0 não avaliados; deterministic-text-metadata-v1,
17/11 10:54. Não implica acurácia semântica. Publicação imagem fora
da população primária do piloto de 858 legendas.

A01.5: corpus_caption_replay.py opt-in vincula manifesto e três relatórios
privados por nome/digest SHA256, checkpoint fixado e tenant/viewer.
Reutiliza report_rows/evidence_tier/revalidate_row, reauditoria readiness
inteira e escopo antes/depois no startup; campos disjuntos, partição exata,
benchmark rubric gates recalculados. Não reexecuta modelo nem presume
assinatura/atestação das predições. Hashes locais fixam bytes escolhidos
pelo operador, não atestam sua origem. Limite de leitura 8 MB por arquivo,
mesmo leitor privado do Lab sintético. Falha no opt-in impede startup;
sem configuração, aplicação histórica funciona normalmente.
Na consulta, somente loopback/tenant/roles de pesquisa e grant vigente;
escopo DEC018 e ausência de ingestão ativa rechecados, snapshot atual
(ID + hash do payload) e legenda (hash) vinculados ao replay. Alteração
ou revogação retém resultado; reauditoria de traces ocorre no startup,
não a cada GET. Sem texto de legenda, locadores, offsets, dados brutos,
player, novas inferências, gravação, promoção científica ou ranking.
UI A01-REPLAY-1 apresenta estrato de audiência, medida de caracteres,
quatro campos experimentais e proveniência em painel separado. Prova
social/oferta são alegações textuais, não fatos verificados; abstenção
não significa negativo. 3 testes novos de wiring (mocks), Node ajustado;
execução pendente. Testes de revalidação de relatórios existentes devem
ser reexecutados. Backup operacional v2 e regressão focal ainda sem
comprovação; não declarar A00.3 concluído.

### Configuração do operador (somente arquivos existentes)
Com servidor e ingestão parados, validar testes e backup conforme acima.
```powershell
$env:TAPI_CAPTION_REPLAY_TENANT = "local-research"
$refs = @{
  MANIFEST = "bd_manifest_a6_v10.json"
  AUDIENCE = "a6-grounded-v10-20261117-112228.json"
  TOPIC_CTA = "a6-rubric-pilot-20261117-121219.json"
  PROOF_OFFER = "a6-rubric-proof-offer-20261117-140542.json"
}
foreach ($key in $refs.Keys) {
  $path = Join-Path "artifacts/private" $refs[$key]
  if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Arquivo ausente: $key" }
  [Environment]::SetEnvironmentVariable("TAPI_CAPTION_REPLAY_${key}_NAME", $refs[$key], "Process")
  [Environment]::SetEnvironmentVariable("TAPI_CAPTION_REPLAY_${key}_SHA256", (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant(), "Process")
}
if ([string]::IsNullOrWhiteSpace($env:TAPI_META_IG_ID)) { throw "Restaurar viewer IG existente, sem divulgar ID/token" }
$env:TAPI_ALLOW_HTTP_LOOPBACK = "1"
python -m uvicorn tapi_gate0.secure_api:from_environment --factory --host 127.0.0.1 --port 8000
```
Não iniciar coleta em paralelo. Abrir Reels/carrossel no Data Explorer;
imagem anterior deve mostrar fora da população, não negativo. Se startup
bloqueado por partição/snapshot/escopo, preservar diagnóstico, não substituir
por dados inventados e não repetir piloto automaticamente. Desativar replay
com Get-ChildItem Env:TAPI_CAPTION_REPLAY_* | Remove-Item e reiniciar.
Próximo: ranking exploratório e contrato durável de evidência; A02 direitos
por ativo antes de mídia real. Nenhum merge.

## A01.5 — replay real confirmado; A04.1/2 — Ranking Explorer
Operador consultou content.f08418609d2869cd089cf0 (anatex, Reels),
271 likes/22 comentários/788287 seguidores; snapshot 17/11 11:10.
Rubrica histórica 1 candidato e 19 abstenções; replay semântico
retornou consenso semântico, legenda 70 caracteres, 858 registros
reauditorados às 20:07 e quatro abstenções. Confirma startup e leitura
real dos relatórios configurados, não acurácia nem cobertura geral de
UI. A01.5 fluxo operacional verificado; testes recentes e backup v2
não reportados. Contrato durável e A01.6 integral ainda pendentes.

A04.1/2 parcial (IMP-057/059/064/082): corpus_ranking_read.py reusa
summarize, analyze_editorial, analyze_rubric e caption_features.
GET /v1/corpus/inventory/ranking exige roles de pesquisa, loopback,
replay tenant correspondente, escopo DEC018 e ingestão ociosa.
Cada consulta/página reaudita toda a partição atual via readiness,
confere join/grants e snapshots válidos do inventário, vínculo de
fonte, legenda, snapshot ID e hash de payload contra replay.
Se qualquer linha estiver ausente, nova, duplicada ou incompatível,
409 (não gerar ranking parcial). Não é lock transacional distribuído;
operar com writers de ingestão parados. Sem cache ou nova inferência.
ER exato Fraction, desempate por content_id, top ceil(n/10), dois
coortes técnico/semântico, rank global preservado na paginação,
min 10 posts para intraperfil, Jaccard e leave-one-profile-out.
Contrastes de quatro campos global/intraperfil e limites por
missingness, não IC; candidato textual não fato. Sem admissão,
causalidade, recomendações ou alteração do ranking canônico.
UI A04-RANKING-1: seção autenticada Ranking Explorer, consulta sob
demanda, seleção coorte/top ou todos, 25/página, contadores, ER,
estratos, top intraperfil/sem cobertura, botão Evidências abre o
mesmo detalhe do Data Explorer. Contrastes e proveniência recolhíveis.
Logout limpa dados e descarta respostas obsoletas. Não retorna
legendas, mídia, paths privados ou dados de outro tenant.
5 testes Python novos (4 ranking +1 rota) e 4 Node; não executados
pelo assistente. Validar UI e conferir com relatório V10 anterior:
técnico 858/top86, mediana 0,037614%; semântico 439/top44,
mediana 0,03323%. Não assumir igualdade antes de executar.

### Operador
```powershell
git pull --ff-only
git rev-parse --short HEAD
conda activate tapi-asr
python -m pytest -q tests/test_corpus_ranking_read.py tests/test_corpus_caption_replay.py tests/test_corpus_inventory.py tests/test_discovery_rubric_contrasts.py tests/test_discovery_editorial_descriptive.py tests/test_discovery_backup.py
node --test tests/test_ranking_ui.mjs tests/test_inventory_ui.mjs tests/test_evidence_lab_ui.mjs
python scripts/verify_zero_spend.py
```
Se todos PASS, executar backup v2 se ainda pendente, writers parados,
conservar configuração do replay e iniciar servidor. Ctrl+F5, login,
Ranking Explorer, consultar técnico top 10%, semântico top 10%, abrir
Evidências, testar paginação/contrastes/logout. Reportar totais e
medianas, sem enviar relatórios privados. Próximos: fechar A00.3/6
com evidência, A02 direitos por ativo, LangGraph e contrato durável.
Sem merge, schema, gasto, mídia ou gate global liberado.

## A04.2 — ranking técnico reproduzido; A02.1 — PDP de direitos por ativo
Operador reportou Ranking Explorer A04-RANKING-1: técnico 858 posts,
21 perfis, top 86, mediana ER 0,037614%, mediana do top 1,307124%,
Jaccard 0,306569. Paridade nos seis indicadores com V10 anterior.
Intraperfil 850 posts/19 perfis, sem empate no corte. Primeira página
25 linhas; contraste e proveniência disponíveis recolhidos. Não confirma
ranking semântico, expansão de detalhes, paginação, logout ou testes
automatizados. A00.3 backup real v2 continua sem evidência reportada.
A04.2 fluxo técnico verificado, IMP-082 parcial. Sem admissão científica.

A02.1 parcial (IMP-044/054/045): asset_rights.py introduz PDP local
sem I/O. Contratos Pydantic imutáveis e extra=forbid: identidade exata
(tenant, plataforma, conta, publicação, content_id, asset_id, modalidade,
SHA256 de bytes), grant assinado Ed25519 com hash da prova de aprovação,
triplas explícitas operação/finalidade/campo, início/fim/retenção.
Operações download, retain, process, derive, display, export, publish.
Nada de combinar listas de campos e finalidades independentemente.
Âncora de confiança fornecida somente pelo host confiável, não pelo
request; chave pública e escopo tenant/plataforma. Estado de revogação
assinado, janela máxima 15 min, revision e digest exatamente iguais
à referência aceita da autoridade, revogação de grant, asset ou fonte.
Sem âncora/assinatura/estado/escopo válido, deny. Requer relógio confiável.
Formato JSON determinístico versionado, não RFC8785. Hash da prova não
verifica mérito jurídico; requer autoridade legítima e evidência real.
require_asset_rights é preflight para PEP futuro, não credencial.
Dependência opcional rights_local (cryptography>=44,<48), sem serviço pago.
Sem cryptography, assinatura não é verificável, fail-closed.
Testes usam chaves efêmeras sintéticas, não são grants reais. 24 casos
esperados incluindo parametrizações; execução pendente. Não instalar
chave de fixture na operação. Não criar autorização real a partir de
JSON editável, flag de ambiente, grant de metadados ou hash de arquivo.

Limites: ainda não existe registry durável/provisionamento de autoridade,
verificação de documento de aprovação, atualização atômica do piso de
revogação, source grant runtime conectado, PEP de bytes, retenção física,
revogação em cascata ou jobs. Janela de revogação 15 min é escolha de
engenharia inicial e não garantia de revogação imediata. As entradas
legadas policy.decide e inspect_approved_local_media permanecem deny
para mídia externa; nenhuma nova rota de autorização ou migração.
A02.1 IMPLEMENTADO_PARCIAL_NAO_TESTADO; próximos: validar PDP, obter
backup v2 antes de migration 0013/registro durável, PEP por operação,
proveniência de derivados e testes de revogação. Não alterar DEC018,
solicitar de novo autorização institucional ampla ou habilitar mídia
sem evidências técnicas específicas. PRs ainda draft, sem merge.

### Operador: focal e backup
```powershell
git pull --ff-only
conda activate tapi-asr
python -c "import cryptography; print(cryptography.__version__)"
python -m pytest -q tests/test_asset_rights.py tests/test_corpus_ranking_read.py tests/test_corpus_caption_replay.py tests/test_corpus_inventory.py tests/test_discovery_backup.py
node --test tests/test_ranking_ui.mjs tests/test_inventory_ui.mjs tests/test_evidence_lab_ui.mjs
python scripts/verify_zero_spend.py
```
Se cryptography não estiver instalado, instalar somente dependência
local opcional (pip install "cryptography>=44,<48") antes dos testes.
Skips criptográficos não equivalem a PASS; não gerar chave operacional.
Após aprovação, parar todos os writers e realizar backup v2:
```powershell
$env:TAPI_TENANT_ID = "local-research"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_backup_restore_drill.py --output-name "a00-baseline-$stamp.sqlite3" --confirm-all-writers-stopped
```
Enviar saída dos testes e backup (não arquivo SQLite). Não executar
nova coleta, modelo, mídia ou merge. Somente após backup validado
avançar em migração operacional; código de registry pode ser testado
em banco descartável antes disso.

## A00.3 e A02.1 — execução aprovada; A02.2 registro durável
Operador HEAD 216e45f: cryptography 47.0.0 instalado; 54 Python PASS
(11,72s, aviso de depreciação Starlette/httpx), 17 Node PASS, sem
skips, zero-spend PASS. Inclui PDP, ranking, replay, inventário e backup.
A02.1 núcleo testado, não homologação de operações reais.
Backup v2 a00-baseline-20261117-202744.sqlite3, capturado
2026-11-17T23:27:45.453296+00:00, SHA256
 da5fb2a122843d78580f0b2561cda1cde810c5709e81cbac35278f2c259aa67b
(10039296 bytes; backup 297ms, restore 234ms), schema 0012,
integrity/foreign_key ok, equivalência lógica todas as tabelas,
restore descartável, writers parados declarados. 1065 conteúdos,
21 perfis, 1169 snapshots, 1065 avaliações, 2455 eventos/outbox,
5 documentos/5 versões Studio, zero admissão científica. A00.3 concluído
para essa captura; não mede RPO/RTO produção. Preservar backup privado.

A02.2 parcial IMP-044/045/054/137: asset_rights_registry.py,
migração 0013_asset_rights_registry (aditiva, três tabelas vazias).
Autoridades identificadas por tenant/plataforma/emissor, fingerprint
chave pública, revisão e hash do estado; histórico de revogação assinado
append-only via serviço; grants vinculados ao content_id, IDs e digest.
Trust anchor independente fornecido pelo host confiável, não pelo
banco/HTTP; pin exato da cabeça evita uso enquanto host/DB discordam.
Provisão requer snapshot assinado correspondente ao pin; registro de
grant exige digest de evidência verificada pelo host e vínculo de fonte
ativa, técnica e payload de conteúdo; não verifica documento jurídico.
Avanço de revogação CAS + transação, revisão crescente, listas cumulativas,
sem regressão temporal, idempotência sob pin atual. Eventos e outbox
atômicos, payload mínimo. Decisão lê registro, assinatura, estado e
fonte a cada chamada. Não é credencial, não é PEP para bytes, não é lock
que abranja operação de mídia. Sem chaves reais, sem write HTTP, sem
provisionamento automático, sem migração operacional executada. Registro
não guarda chaves privadas. Host deve persistir pin externo por escopo
antes de qualquer uso; recuperação e rotação de chave ainda sem fluxo
operacional. Revogação física/cascata, retention worker e storage pendentes.
Downgrade permitido apenas com as três tabelas vazias, nunca apagar
auditoria existente. Backup v2 agora reconhece 0012/0013 e exige tabelas
correspondentes à revisão. Migração/schema registrados para fixtures.
7 testes novos, incluindo teste real Alembic e bloqueio de downgrade
não vazio. Não executados pelo assistente. A00.4 integração ainda pendente.

### Ensaio antes de migração real
Com writers parados, atualizar e validar:
```powershell
git pull --ff-only
conda activate tapi-asr
python -m pytest -q tests/test_asset_rights.py tests/test_asset_rights_registry.py tests/test_discovery_backup.py
python scripts/verify_zero_spend.py
```
Se PASS, rodar ensaio somente sobre backup fixado (sem usar URL live):
```powershell
python -m scripts.a02_migration_rehearsal --backup-name "a00-baseline-20261117-202744.sqlite3" --backup-sha256 "da5fb2a122843d78580f0b2561cda1cde810c5709e81cbac35278f2c259aa67b" --tenant "local-research"
```
Esperar A02_MIGRATION_REHEARSAL_VERIFIED, tabelas antigas e hashes
preservados (exceto versão Alembic), 3 novas vazias, integridade/FK,
downgrade vazio restaura estado, backup inalterado, banco real não acessado.
Script usa subprocesso Alembic com URL da cópia temporária e ambiente
filho reduzido; sem sandbox OS. Se falha, preservar diagnóstico.
Não rodar upgrade operacional ainda; próxima etapa validar ensaio e
regressão completa, depois upgrade com backup recente confirmado,
PEP/armazenamento privado e jobs duráveis. Nenhum merge, gate ou mídia.

## A02.2 — registro e ensaio aprovados; A02.3 — cofre local de bytes
Operador HEAD 1e963c7: 46/46 Python PASS em 6,90s, zero-spend PASS.
Ensaio A02_MIGRATION_REHEARSAL_VERIFIED no backup fixado
 a00-baseline-20261117-202744.sqlite3 (SHA da5fb2a122843d78580f0b2561cda1cde810c5709e81cbac35278f2c259aa67b):
0012→0013, 39 tabelas antigas preservadas (exceto controle Alembic),
3 novas vazias, schema legado e integridade confirmados, downgrade
vazio verificado, backup inalterado, DB operacional não acessado.
A02.2 testado em fixtures e cópia real; operação permanece 0012.

A02.3 parcial (IMP-040/044/045/047/054/122/123/126/137/145/146):
asset_vault.py é biblioteca de host confiável, não endpoint de produção.
Recebe bytes previamente adquiridos legitimamente, nunca URL/path de
origem. Exige grant retain antes de validar/escrever; process e retain
antes e depois de leitura. Reavalia via registry real. Identidade exata
inclui tenant/plataforma/fonte/post/ativo/digest; AAD inclui emissor,
fingerprint da chave pública, grant, MIME e identidade. Nome interno
SHA256 do AAD; sem dedup entre grants/tenants. AES-256-GCM nonce aleatório
por envelope, chave de 32 bytes fornecida externamente, sem persistir
chave ou texto claro em disco. Hash e tamanho (40 MB) conferidos antes
da retenção e após descriptografia. Allowlist de MIME e cabeçalhos
JPEG/PNG/MP4/WebM/WAV: preflight superficial, não decodificação completa
nem garantia contra mídia maliciosa. Escrita temporária criptografada,
fsync e publicação sem sobrescrita via hardlink; falha em filesystem
incompatível. Rechecagem do grant e limpeza de novo objeto em falha.
Read retorna bytes apenas ao caller confiável; nenhum player, download,
export, derivação, publicação ou subprocesso. Sem permissões cruzadas.
POSIX exige diretório sem group/other; Windows depende de ACL aplicada
pelo operador (não validada automaticamente). Não é sandbox OS; races
com processos do mesmo privilégio e janela depois do retorno de bytes
não são resolvidas. Sem recuperação de staging após crash, índice
durável de objetos, quotas totais, rotação de chaves, purge automático,
linhagem de derivados, PEP de inferência ou backup do vault. Backup SQLite
não inclui bytes. Nenhuma configuração real de chave/diretório/autoridade.
Legacy inspect_approved_local_media continua deny. 12 testes de vault
+1 integração com registry assinado, pendentes execução; testes usam
bytes sintéticos apenas (cabeçalhos, não mídia decodificável).
Decisão de engenharia: AES-GCM e teto 40 MB inicial coerente com adapter
legado; não é limite institucional. Sem nova migração nem DB live write.

### Próxima validação
```powershell
git pull --ff-only
git status --short
conda activate tapi-asr
python -m pytest -q tests/test_asset_vault.py tests/test_asset_rights.py tests/test_asset_rights_registry.py tests/test_discovery_backup.py
python scripts/verify_zero_spend.py
```
Se PASS, regressão integral do novo HEAD com writers parados:
```powershell
$env:Path = "C:\Program Files\Tesseract-OCR;C:\Program Files\eSpeak NG;$env:Path"
$env:ESPEAK_DATA_PATH = "C:\Program Files\eSpeak NG"
$baseline = (git rev-parse HEAD).Trim()
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a00_baseline.py --expected-head "$baseline" --profile full --report-name "a02-full-$stamp" --tessdata-dir "C:\Models\tapi\tessdata-fast-4.1.0"
```
Não executar upgrade operacional até revisar regressão e verificar backup
atual. O ensaio já aprovado não precisa ser repetido sem mudança na
migração. Próximo: upgrade 0013 vazio com preflight/backup recente e
verificação pós-migração, índice/linhagem de objetos, retenção e revogação
em cascata, PEP antes/durante/depois de inferência. Sem merge ou mídia.

## A02.3 — reconciliação das falhas de diagnóstico do vault
Operador HEAD 88f8e83: 59 coletados, 57 PASS / 2 FAIL em 9,24s;
zero-spend PASS. Falhas test_tamper_wrong_key_and_no_overwrite e
test_envelope_binding_rejects_copied_object_under_other_grant:
AUTHENTICATION_FAILED esperado, OBJECT_UNAVAILABLE obtido.
Causa verificada no código: AssetRightsDenied herda PermissionError,
que herda OSError; _read capturava a exceção de segurança lançada
após InvalidTag e traduzia como indisponibilidade de arquivo. Ambos
os acessos foram negados, sem evidência de bytes liberados. Asserções
posteriores do primeiro teste (adulteração e não sobrescrita) não
executadas naquela rodada. Não alterar testes originais para aceitar
código genérico. 75b056c: restringe tratamento de OSError à leitura
filesystem, preserva AssetRightsDenied explícito; validação do
header, autenticação GCM e hash fora do handler. Não muda algoritmo,
chave, grant, escopo nem entrada operacional.
8220adb: cinco casos novos distinguem envelope curto/header inválido,
GCM válido mas digest divergente, PermissionError real de I/O e
objeto ausente. Verificam não sobrescrita e causa da exceção de I/O.
6fccdf6: inclui cryptography na proveniência do runner A00.
64 testes focais esperados, sem skips; novos testes não executados
pelo assistente. Próxima validação: repetir exatamente a suíte focal
asset_vault/asset_rights/asset_rights_registry/discovery_backup;
zero-spend e, somente se PASS, full baseline do novo HEAD conforme
comandos anteriores. A02.3 não fechado até nova execução. Ensaio 0013
já aprovado, código de migração inalterado; upgrade operacional ainda
pendente de regressão e backup recente. Não avançar PEP de mídia
com regressão aberta. Sem I/O operacional, migration, merge ou gastos.

## A02.3 — regressão integral PASS; A02.4 — upgrade controlado e linhagem
Operador HEAD 76a9bc8316dca83b746728d58893f5d6db0c1790,
árvore b45279bff937015c3614d8b465e3ccd29b3d8b95: focal 64/64 PASS
em 9,11s; zero-spend PASS. Full a02-full-20261117-204437,
980 coletados / 979 PASS / 0 FAIL / 0 ERROR / 1 SKIP intencional
(test_operator_actual_triplet_when_configured), pytest 232,743s,
Node/Gate0 histórico/zero-spend PASS, checkout inalterado.
pytest.log SHA256 7626e13de51c280fcfe71e468b10ed34376d4893e8cfe68a747dd7b175b2d9c6,
JUnit SHA256 5bbc85f5903dbf956f9079074bf98c7106366f47bdbef22126a305f76d00101b,
Node log SHA256 af25bfc6c5f01c1057b2be19c2fc71d46202c393587e1f03699a3fbae5bdfe5f.
98 módulos, 94 Python test files, 5 Node, 13 migrations, cryptography 47.0.0.
A00.2 atualizado para esta baseline; vault testado, sem mídia real.

A02 upgrade: scripts/a02_operational_upgrade.py exige HEAD limpo fixado,
flag explícita --apply-0013 e declaração de writers parados. SQLite existente
sem redirecionamento, tenant existente, revisão 0012. Cria backup v2 novo
(exclusivo, verificado com restore descartável), preserva backup original.
BEGIN IMMEDIATE no banco alvo; confere inventário/hashes contra novo backup
antes de DDL. Alembic usa conexão fornecida, sem abrir outra conexão;
DDL e verificação de schema/valores/FK/3 tabelas vazias na mesma transação.
Se falha antes do commit, rollback; após commit, verificação read-only.
Falha pós-commit não implica rollback; manter writers parados e inspecionar.
Não restaura banco automaticamente, não concede direitos, não inicia mídia.
4 testes novos: sucesso, rollback após DDL real, mudança pós-backup, falta de
attestation/DB inexistente. Ainda não executados pelo assistente. Alteração
em migrations/env.py é apenas caminho opcional conexão fornecida; cadeia
0013 inalterada. Testes em cópias descartáveis antes do upgrade real.

A02.4 parcial: asset_lineage.py define referências imutáveis de objeto
retido e artefato derivado, digest, grant, emissor, MIME, método/run, pais,
retention deadline. ID do objeto recalculado com serialização compartilhada
do vault (sem mudar formato v1). Plano puro de invalidação transitiva por
asset_id (todos os grants correspondentes), artifact_id e expiração,
rejeita pais ausentes, IDs duplicados, tenant cruzado, ciclos, derivação
que antecede pai ou retenção além do pai. Limite 20k nós, até 64 pais;
nenhum I/O, exclusão física ou autorização. 5 testes novos, pendentes.
Índice SQL, eventos de invalidação, purge, integração dos PEPs e jobs ainda
pendentes. Contrato de linhagem não substitui checagem de permissões.

### Operador — testes e upgrade explícito
Com servidor, agendador e todos os writers parados:
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr
python -m pytest -q tests/test_a02_operational_upgrade.py tests/test_asset_lineage.py tests/test_asset_vault.py tests/test_asset_rights.py tests/test_asset_rights_registry.py tests/test_discovery_backup.py
python scripts/verify_zero_spend.py
```
Esperado 73 testes focais, sem skips. Se PASS e quiser aplicar 0013, usar
URL operacional existente e tenant local-research, não trocar DB:
```powershell
$env:TAPI_TENANT_ID = "local-research"
$baseline = (git rev-parse HEAD).Trim()
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python -m scripts.a02_operational_upgrade --expected-head "$baseline" --backup-name "a02-pre0013-$stamp.sqlite3" --confirm-all-writers-stopped --apply-0013
```
Esperado A02_OPERATIONAL_MIGRATION_VERIFIED, 39 tabelas antigas preservadas,
3 novas vazias, backup_restore_verified, legacy_logical_contents_match,
media_enabled=false. Se BLOCKED, não reiniciar nem repetir upgrade às cegas;
inspecionar revisão e backup. Após sucesso, novo backup 0013 e smoke
Dashboard/Ranking/Evidence real, sem nova coleta. Regressão full da
baseline 76a9bc8 já aprovada; novo HEAD ainda focal pendente. Sem merge.

## A02.2 — migração operacional confirmada; A02.4 — índice persistente
Operador HEAD fff9bdf3fb982bb496755cfed74bdbf3335f67fb:
73/73 focal PASS (15,38s), zero-spend PASS. Upgrade 0012→0013
A02_OPERATIONAL_MIGRATION_VERIFIED, backup a02-pre0013-20261117-205535.sqlite3
SHA256 da5fb2a122843d78580f0b2561cda1cde810c5709e81cbac35278f2c259aa67b,
39 tabelas preservadas, 3 novas vazias, schema/hashes lógicos/FK ok,
1065 posts únicos, 21 perfis, 0 duplicatas, 0 grants reais, mídia bloqueada.
Backup novo idêntico em bytes ao anterior; 0013 operacional confirmado.

A02.4: asset_lineage_index.py e migration 0014_asset_lineage.
Uma tabela privada de metadados (não bytes/derivados brutos), PK
(tenant,node_id), tipo asset/derived, finalidade research_analysis ou
studio_creation, referência validada, tombstone monotônico. SQLite
somente; BEGIN IMMEDIATE serializa mutações e preflight. Registro de
raiz exige grant retain, vínculo de fonte/identidade/issuer/key, prazo
contido no grant. Registro de derivado exige pais ativos da mesma
finalidade, grafo válido, permissão derive exata de todos os ativos
ancestrais, retenção limitada pelos pais. Idempotência sem sobrescrita;
tombstone nunca reativado. Preflight exige finalidade e campo compatíveis,
reconsulta retain e operação pedida para cada raiz; retorna somente status,
não payload nem credencial. Metadados não comprovam presença de bytes
ou autenticidade de derivados; host confiável e PEP completo pendentes.
Invalidação administrativa por IDs exatos, expiração, propagação
transitiva e eventos/outbox atômicos, versões 1/2. Reconciliação de
revogação assinada por escopo tenant/plataforma/emissor/grant/asset/source,
pin atual e janela válida. Separada do avanço do registry: erro no índice
não pode reverter revogação. Preflight nega direitos revogados mesmo
antes da reconciliação. Ainda sem consumer automático, purge físico,
retention worker, jobs, integração de leitura/outputs ou chaves reais.
Não invalida corpus legado de metadados/captions. Nenhum arquivo removido.
0014 cria tabela vazia; downgrade não vazio proibido. Backup reconhece
0014 com correspondência de schema. Rehearsal aceita --lineage para
0013→0014 (somente cópia). 5 novos casos focais esperados (3 lifecycle,
1 parametrização rehearsal, 1 downgrade); outros checks estendidos.
Não executados pelo assistente. Operacional permanece 0013.

### Operador — testes e backup pós-0013
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr
python -m pytest -q tests/test_a02_operational_upgrade.py tests/test_asset_lineage.py tests/test_asset_vault.py tests/test_asset_rights.py tests/test_asset_rights_registry.py tests/test_discovery_backup.py
python scripts/verify_zero_spend.py
```
Esperado 78 testes. Com todos os writers parados e PASS:
```powershell
$env:TAPI_TENANT_ID = "local-research"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$name = "a02-post0013-$stamp.sqlite3"
$report = python scripts/a6_backup_restore_drill.py --output-name "$name" --confirm-all-writers-stopped | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $report.status -ne "BACKUP_RESTORE_VERIFIED") { throw "Backup falhou" }
$report | ConvertTo-Json -Depth 8
python -m scripts.a02_migration_rehearsal --backup-name "$name" --backup-sha256 "$($report.backup_sha256)" --tenant "local-research" --lineage
```
Esperado 42 tabelas anteriores preservadas, 1 nova vazia, rollback em
cópia verificado; não aplicar 0014 operacional ainda. Próximo: fechar
rehearsal, integração de purge/index e jobs, upgrade protegido 0014.
Nenhuma execução real de mídia nem merge.

## A02.4 — linhagem testada; upgrade 0014 e descarte offline
Operador HEAD a62bdcdb48b1dd8138ac276bcc5c71f0ab702037:
78/78 testes focais PASS em 20,20s; zero-spend PASS. Backup pós-0013
 a02-post0013-20261117-210509.sqlite3, 10067968 bytes,
SHA256 166368b144a7a843924f12ded1b4d6316a18d4a796035f4962b36c640c0b1a89,
backup/restore 250/172ms, integridade/FK/conteúdo lógico OK.
1065 conteúdos/21 perfis/1169 snapshots/1065 avaliações/2455 eventos,
5 documentos Studio; 3 tabelas de direitos vazias, 0 grants reais,
0 admissões científicas. Rehearsal 0013→0014 PASS, 42 tabelas
preservadas, 1 nova vazia, downgrade vazio verificado, backup intacto,
sem acesso operacional. DB live permanece 0013.

Novo incremento: a02_operational_upgrade aceita --apply-0014 (mutuamente
exclusivo com --apply-0013), mesma proteção de backup recente e
BEGIN IMMEDIATE/DDL/checks/rollback, transição fixa 0013→0014.
4 casos adicionais por parametrização dos testes já existentes.
asset_discard.py: função offline trusted-host para descarte de exatamente
um envelope do vault, com índice e registry compartilhando engine,
attestation de todas as leituras/escritas do vault paradas. Somente raiz
com tombstone e cadeia de eventos registro/invalidação íntegra; verifica
ID canônico, path derivado, arquivo regular sem links/reparse points,
tamanho e cabeçalho v1; sem descriptografar bytes. Rejeita arquivo
corrompido ou reintroduzido após recibo; revisão manual nesses casos.
Remove entrada de diretório e registra evento versão 3 + outbox,
preserva tombstone. Se crash após unlink antes do commit, retry registra
already_absent sem alegar remoção por aquela execução. Sem atomicidade
DB/FS, sem prova de erasure, sem garantia contra processo com mesmos
privilégios; host deve fornecer o diretório correto. Não remove cópias,
backups, staging órfão ou payloads derivados. 4 testes novos (fixtures).
Sem CLI de purge real, consumer automático ou integração operacional.
A API do vault primitivo ainda não aplica tombstones; não habilitar PEP
real até integração obrigatória de índice/vault/jobs. Próximo: acesso
indexado, jobs e reconciliação automática. 86 testes focais esperados,
novos 8 casos ainda não executados pelo assistente.

### Operador: testes e upgrade 0014
Com todos os processos de escrita parados:
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr
python -m pytest -q tests/test_a02_operational_upgrade.py tests/test_asset_lineage.py tests/test_asset_vault.py tests/test_asset_rights.py tests/test_asset_rights_registry.py tests/test_discovery_backup.py
python scripts/verify_zero_spend.py
```
Somente após PASS, explicitamente no banco operacional correto:
```powershell
$env:TAPI_TENANT_ID = "local-research"
$baseline = (git rev-parse HEAD).Trim()
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python -m scripts.a02_operational_upgrade --expected-head "$baseline" --backup-name "a02-pre0014-$stamp.sqlite3" --confirm-all-writers-stopped --apply-0014
```
Esperar A02_OPERATIONAL_MIGRATION_VERIFIED, 42 tabelas antigas, 1 nova
vazia, hashes e schema legado OK, mídia bloqueada. Se BLOCKED, manter
writers parados e não repetir automaticamente. Nenhum purge real a
executar. Não realizar merge ou nova coleta. Full anterior 76a9bc8;
regressão integral e smoke pós-0014 ainda pendentes.

## A02.4 — migração 0014 operacional; PEP de bytes indexados
Operador HEAD d3c52d27370db9e9a7b793b41671cc465e85c02c:
86/86 focal PASS (23,63s), zero-spend PASS. Upgrade operacional
0013→0014 A02_OPERATIONAL_MIGRATION_VERIFIED, backup
 a02-pre0014-20261117-212100.sqlite3 SHA256
166368b144a7a843924f12ded1b4d6316a18d4a796035f4962b36c640c0b1a89,
42 tabelas anteriores preservadas, 1 nova vazia, schema/hashes/FK
integridade OK, 1065 únicos/21 perfis/0 duplicatas, 0 grants reais,
mídia bloqueada. 0014 operacional. Descarte testado em fixtures.

Novo asset_indexed_vault.py: IndexedAssetVault exige AssetRightsRegistry
real e AssetLineageIndex com o mesmo engine SQLite. Retenção confere
bytes/identidade/MIME/hash e registra reserva de metadados antes de
publicar envelope, depois BEGIN IMMEDIATE, ref exata, finalidade,
tombstone, tempo e grant retain antes/durante/depois da escrita.
Leitura recebe tenant/object_id/finalidade, resolve ref persistida,
verifica retain+process antes/depois da leitura e tamanho final;
retorna bytes apenas a host confiável. Serializa contra atualização
SQLite de revogação/index, não mantém lock após retorno. Métodos públicos
primitivos retain/read_for_processing com AssetRightsRegistry real
negam INDEX_REQUIRED. Primitivas privadas permanecem para adapter e
fixtures; não é sandbox Python ou OS, não protege contra host malicioso.
Tombstone administrativo impede leitura e nova retenção mesmo se grant
continua ativo; metadados ativos sem bytes não equivalem a retenção
completada, leitura nega, retry exige ref idêntica. Não há atomicidade
DB/FS; reserva permite localizar envelope após crash, staging recovery
continua pendente. Root correto/ACL/chave/autoridade são responsabilidade
do host; nenhum host real configurado. Não é PEP de inferência, não
conecta mídia, não entrega payload derivado, não cria grant.
5 novos testes de integração real-registry em fixtures e testes existentes
adaptados para usar o novo caminho (mantêm assert de revogação e descarte);
91 focal esperados, pendentes execução. Sem alteração de schema.

### Operador
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr
python -m pytest -q tests/test_a02_operational_upgrade.py tests/test_asset_lineage.py tests/test_asset_vault.py tests/test_asset_rights.py tests/test_asset_rights_registry.py tests/test_discovery_backup.py
python scripts/verify_zero_spend.py
```
Se PASS, rodar full baseline com Tesseract/eSpeak como anteriormente;
1007 coletados esperados (1006 PASS, 1 opt-in Lab skip), não presumir PASS.
Com writers parados, backup pós-0014 verificado antes de próximo schema.
Depois smoke Dashboard/Ranking/Evidence com configuração anterior.
Próximo incremento A02.5/6: fila durável, leases fencing, retries,
cancelamento, dedup/quotas, integração com reconciliação de revogação,
PEPs de inferência/commit/derivados. Não executar nova migração, purge
real, coleta ou merge. Nenhum gate global liberado.

## A02.4 — cofre indexado validado; A02.5/6 — fila durável local
Operador HEAD c4a0aeacfae75cc4fbaa0f3a5e25a2f6fe9ee815,
árvore 2cc17ceae004642a173068d1715422add23191e8: focal 91/91 PASS
(30,96s); zero-spend PASS. Full a02-full-20261117-212954,
1007 coletados / 1006 PASS / 0 FAIL / 0 ERROR / 1 SKIP opt-in
Evidence Lab real, pytest 240,031s, Node/Gate0/zero-spend exit 0,
checkout inalterado. pytest.log SHA256
9f19238a68d3d90d317c93f92bccc660dcec12ef55930e020ca278068e152632,
JUnit SHA256 0a59410a8f503ae10e12f4ee61604144de138197880e85fbad6b17fd48cab370,
Node SHA256 a4d45e945af14b78cac2152fb8bedc18bc7f11093d1b7a6394d3db6be6d209fa.
102 módulos, 96 Python test files, 5 Node, 14 migrations.
Backup pós-0014 a02-post0014-20261117-213407.sqlite3,
SHA256 6308ce588545eac9ea975872e059ac504d6d42ae520ea027c1b8d00e6a120a62,
10076160 bytes, backup 218ms/restore 188ms, schema/FK/integridade e
hashes lógicos preservados, 1065 conteúdos/21 perfis/1169 snapshots/
1065 assessments/2455 eventos, 5 Studio docs, quatro novas tabelas
rights/lineage vazias, zero admissão, 0014. A00.2/3 atualizados para
esta captura, não RPO/RTO produção. Smoke UI pós-0014 não reportado.

A02.5/6 parcial: asset_jobs.py, migração 0015_asset_jobs (duas tabelas
vazias asset_processing_jobs e asset_processing_attempts). Biblioteca
SQLite trusted-host, sem rota/worker, sem bytes/payload/modelo.
Spec imutável por tenant/object_id/finalidade/processor/method_version/
configuration_sha256; hash ID determinístico, dedup inclusive terminal.
OCR/ASR-VAD/VLM/temporal com modalidade e campo de derivação explícitos.
Enqueue, claim, heartbeat, finish verificam root ativo, retain+process+
derive exatos, fonte/grant/pin vigentes, na transação BEGIN IMMEDIATE.
Leases com fence aleatório e tentativa persistida; receipt de hash
somente, não artefato verificado nem publicação. Estado queued/running/
cancel_requested/completed/failed/canceled; tentativa até 3, backoff
15s/30s para retry, lease inicial 120s, heartbeat limitado a deadline
900s da tentativa; worker obsoleto/expirado não pode renovar/concluir.
Cancelamento queued imediato; running mantém slot até ack ou expiração,
nega finish. Ack é declaração de worker confiável, não kill. Clock
regressivo detectado por updated_ms; relógio confiável necessário.
Limites iniciais de engenharia: 100 pendentes por tenant, histórico
20k/tenant e 50k global, 1 lease ativo global, 50 tentativas/tenant/dia
UTC e 100 globais/dia UTC. Reserva por tentativa, inclusive falha/timeout,
sem reembolso; ledger durável, eventos/outbox transacionais.
Limites de reservas/leases NÃO garantem CPU/RAM/tempo de subprocesso,
concorrência física ou kill de processos órfãos. Fencing protege recibos;
worker supervisor ainda precisa confirmar cessação de execução antiga,
controlar recursos e revalidar direitos durante inferência e commit.
Reconcile_invalidated explícito cancela queued e solicita cancel running
com tombstone/expiry; deny atual independe de reconciliação. Sem consumer
automático, não confundir chamada de biblioteca com job em execução.
Status read-only sem fence; claim entrega fence somente ao worker host.
A configuração hash não comprova bytes de modelo; PEP de execução e
validação de configuração/artefato pendentes. Sem chaves/autoridade reais,
sem derivação, persistência de payload ou processamento. Não alterar
corpus/ranking; nenhum gate. 10 novos testes de fila + 1 parametrização
rehearsal; 102 focal esperados. Não executados pelo assistente.
Backup reconhece 0015, valida presença de ambas tabelas; downgrade vazio
apenas; ensaio --jobs 0014→0015 em cópia descartável do backup fixado.
Não aplicar 0015 operacional até focal e rehearsal PASS; código de
upgrade protegido ainda não aceita 0015. Próximo: supervisor/PEP de
execução, finalização de derivados sob fence e direitos, quotas reais,
consumer/reconciliação e smoke operacional, depois LangGraph.

### Operador — focal e ensaio 0015
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr
python -m pytest -q tests/test_a02_operational_upgrade.py tests/test_asset_lineage.py tests/test_asset_vault.py tests/test_asset_rights.py tests/test_asset_rights_registry.py tests/test_discovery_backup.py
python scripts/verify_zero_spend.py
```
Esperado 102 focal sem skips. Se PASS:
```powershell
python -m scripts.a02_migration_rehearsal --backup-name "a02-post0014-20261117-213407.sqlite3" --backup-sha256 "6308ce588545eac9ea975872e059ac504d6d42ae520ea027c1b8d00e6a120a62" --tenant "local-research" --jobs
```
Esperado 43 tabelas antigas preservadas, 2 novas vazias, schema/hashes
legados intactos, downgrade vazio verificado, backup inalterado,
operational_database_mutated=false, media_enabled=false.
Não repetir full anterior sem necessidade, não executar upgrade live,
não iniciar coleta ou mídia e não gerar grants fictícios. Sem merge.

## A02.5 — fila e ensaio aprovados; supervisor sintético e finalização fenced
Operador HEAD 28be6c0e9ce574438f03ce0d0d543069f0fe5e71:
102/102 focal PASS em 46,08s, zero-spend PASS. Rehearsal 0014→0015
sobre a02-post0014-20261117-213407.sqlite3 SHA256
6308ce588545eac9ea975872e059ac504d6d42ae520ea027c1b8d00e6a120a62:
43 tabelas preservadas, duas novas vazias, schema/hash/integridade,
downgrade vazio e backup inalterado verificados. DB operacional 0014.

Upgrade protegido aceita --apply-0015, transição explícita 0014→0015
com backup recente e rollback; quatro novos casos parametrizados.
AssetJobQueue.check_lease verifica fence, prazo, direitos vigentes e
retorna spec/ref somente para host confiável. finish_reference recebe
bytes limitados a 1 MB, deriva digest e ID determinístico, registra
referência com pai exato, método, run e retenção limitada ao pai,
confere novamente lease/direitos e relógio e finaliza na mesma transação
SQLite. Falha tardia reverte referência, job e outbox. Status
reference_only, payload_persisted=false, scientific_evidence=false.
Não armazena, valida semanticamente ou disponibiliza o payload;
nenhum worker real usa este método. Não é prova de resultado científico.

asset_supervisor.py: probe somente sintético, exige processor temporal,
method synthetic-supervisor-v1, hash do código fixo, identidade/hash/
MIME/tamanho do fixture MP4 de 12 bytes; não aceita mídia externa.
Lê fixture pelo cofre indexado, subprocesso Python direto -I -S,
stdin/stdout pipe, shell=False, ambiente reduzido SystemRoot/WINDIR,
sem arquivo plaintext, stdout esperado exato e digest do recibo.
Checa lease/direitos antes do spawn, polling a cada 250ms quando I/O
permite, depois da saída e antes de finish; timeout monotônico 15s,
kill + wait do filho direto em erro. Sem heartbeat porque probe curto;
sem retry automático, caller reconcilia/cancela ou aguarda expiração.
Não há isolamento OS, limite efetivo CPU/RAM, garantia de deadline
quando I/O/DB bloqueia, supervisão de árvore de processos nem recuperação
segura de órfãos após crash do host. Filho fixo não cria descendentes;
nenhum modelo ou mídia externa executado. Antes de produção exigir
worker supervisor com controle de árvore/recursos, storage criptografado
de derivados, validação de payload/model/config, trust host operacional
e grants reais. 8 novos casos (3 referência/5 probe), mais 4 migration
parametrizados; 114 focal esperados, não executados pelo assistente.

### Operador — focal e upgrade 0015
Com todos os writers parados:
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr
python -m pytest -q tests/test_a02_operational_upgrade.py tests/test_asset_lineage.py tests/test_asset_vault.py tests/test_asset_rights.py tests/test_asset_rights_registry.py tests/test_discovery_backup.py
python scripts/verify_zero_spend.py
```
Após 114 PASS sem skips, no banco existente local-research:
```powershell
$env:TAPI_TENANT_ID = "local-research"
$baseline = (git rev-parse HEAD).Trim()
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python -m scripts.a02_operational_upgrade --expected-head "$baseline" --backup-name "a02-pre0015-$stamp.sqlite3" --confirm-all-writers-stopped --apply-0015
```
Esperar A02_OPERATIONAL_MIGRATION_VERIFIED, 43 preservadas, 2 novas
vazias, hashes/schema/FK ok, 1065 únicos/21 perfis, mídia false.
Se BLOCKED, manter writers parados e inspecionar; não repetir às cegas.
Sem novo full necessário neste incremento, último c4a0aea. Após upgrade,
backup pós-0015, smoke real UI pendente e próximos PEPs. Não gerar grants,
rodar mídia externa, coleta ou merge. Nenhum gate global liberado.

## A02.5 — 0015 operacional; armazenamento criptografado de derivados
Operador HEAD 5bcc0c8e78c6eb9eb877970c63a80209e7370962:
114/114 focal PASS em 50,07s, zero-spend PASS. Upgrade operacional
0014→0015 A02_OPERATIONAL_MIGRATION_VERIFIED, backup
 a02-pre0015-20261117-215927.sqlite3 SHA256
6308ce588545eac9ea975872e059ac504d6d42ae520ea027c1b8d00e6a120a62,
43 tabelas antigas preservadas, 2 novas vazias, schema/hashes/FK/
integridade OK, 1065 únicos/21 perfis/0 duplicatas, zero grants reais,
mídia bloqueada. 0015 operacional, supervisor sintético e finalização
reference_only testados. Full anterior c4a0aea.

Novo asset_derived_payloads.py: biblioteca trusted-host SQLite, sem
endpoint, worker ou modelo real. DerivedPayloadStore exige chave
aleatória externa 32 bytes dedicada aos derivados, não persiste chave;
key_id fingerprint com domínio separado. AES-256-GCM nonce aleatório,
AAD liga ref completa, spec/config, tentativa, key_id e pai exato.
Finish exige lease/fence e direitos retain/process do pai, derive do
campo e retain explícito do campo derivado (não inferido do derive).
Ciphertext, metadados de linhagem, recibo digest e outbox na mesma
transação; recheck do lease, relógio, pai e direitos antes de concluir.
Leitura interna exige purpose/campo, pai único, recibo completed com
reason encrypted_payload, tentativa/spec/run/digest exatos, retain e
process explícitos do derivado além dos direitos do pai; valida AEAD,
comprimento/hash e recheck antes de retornar bytes. Referência sem
payload não é legível. Bytes opacos não comprovam correção semântica.
Nenhum conteúdo enviado à UI, exportado, publicado ou usado em ranking.
Limites iniciais: 1 MB por payload; 100 MB ciphertext/tenant e 500 MB
global; quota lógica do ciphertext vivo, não limite físico do DB/WAL/
backup. Purge explícito apenas após tombstone, zera ciphertext na linha
ativa e mantém recibo/metadados/evento; idempotente. Não é secure erasure
nem descarte de backups, WAL, páginas antigas, cópias ou buffers em RAM.
Sem rotação, provisionamento/gestão de chave operacional, integração
automática de purge, validação de resultados de cada processor, proteção
contra host malicioso ou garantia de revogação após entrega de bytes.
Nova migração 0016_asset_derived_payloads (uma tabela vazia, FKs
composite para lineage/jobs e unique por job), downgrade não vazio
bloqueado inclusive registros purgados. Backup reconhece 0016 e BLOBs
já suportados no fingerprint. Rehearsal --payloads 0015→0016.
9 testes de storage + 1 parametrização rehearsal, 124 focais esperados,
não executados pelo assistente. Fixtures sintéticas, sem real grants.
Supervisor de árvore, limites reais CPU/RAM e isolamento de processo
continuam pendentes. Operacional ainda 0015, sem ativar mídia externa.

### Operador — focal, backup pós-0015 e ensaio 0016
Com writers parados:
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr
python -m pytest -q tests/test_a02_operational_upgrade.py tests/test_asset_lineage.py tests/test_asset_vault.py tests/test_asset_rights.py tests/test_asset_rights_registry.py tests/test_discovery_backup.py
python scripts/verify_zero_spend.py
```
Após PASS sem skips:
```powershell
$env:TAPI_TENANT_ID = "local-research"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$name = "a02-post0015-$stamp.sqlite3"
$report = python scripts/a6_backup_restore_drill.py --output-name "$name" --confirm-all-writers-stopped | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $report.status -ne "BACKUP_RESTORE_VERIFIED") { throw "Backup falhou" }
$report | ConvertTo-Json -Depth 8
python -m scripts.a02_migration_rehearsal --backup-name "$name" --backup-sha256 "$($report.backup_sha256)" --tenant "local-research" --payloads
```
Esperado 45 tabelas antigas preservadas, 1 nova vazia, downgrade vazio,
backup inalterado; não executar 0016 live antes de revisão. Próximo:
upgrade 0016 protegido, supervisão de execução local com limites reais,
contratos tipados de resultados e integração de adapters em fixtures.
Não criar chave/grant real, mídia, coleta ou merge. Smoke UI pós-0014/
0015 ainda não reportado; próxima full após consolidar A02. Sem gates.

## A02.5/6 — preflight integrado e upgrade 0016 protegido (incremento de engenharia)

Base documental v6.1 validada (espelho e pacote integral PASS local).
HEAD de partida 8fcc554f5ea550796ada7b60d4bccf1877757d2d; nenhum novo
resultado do operador após 114 focais/0015, 124 casos anteriores pendentes.
IMP-040/044/045/054/126/137/145/178; relacionados CAP-001/009/016/021/022/023,
DEC-018, G0/G1/G4/G5. Sem alterar backlog, critérios, direitos ou gates.

- Novo `scripts/a02_payloads_preflight.py`: checkout limpo e SHA exato,
  validador documental, Gate0 legado, zero-spend e suite focal com JUnit
  (sem skips/erros/falhas; mínimo 128, total esperado 138 no HEAD deste
  incremento). Child env reduzido sem credenciais nem DB operacional.
  Somente após PASS, backup read-only do SQLite existente em 0015,
  confirmação de writers parados, restore descartável, rehearsal 0016
  e relatório privado exclusivo. Não aplica migração nem abre mídia.
- `--apply-0016` exige preflight do mesmo HEAD e SHA256 do summary,
  valida hashes de logs/JUnit/backup, reconta JUnit e checa a transição.
  Relatório é evidência local, não assinatura/attestation externa.
  Cria outro backup fresco e repete rehearsal nele antes de BEGIN IMMEDIATE;
  preserva rollback, comparação integral de schema/conteúdo, integridade,
  FKs, verificação pós-commit e proibição de restore sobre banco live.
- Quatro casos de upgrade 0016 parametrizados + dois casos negativos
  (rehearsal bloqueado e CLI sem preflight) + oito testes de report.
  Oito testes novos de contrato do report executados em cópia isolada
  byte-idêntica dos dois arquivos: 8 PASS. Não executada a suite focal
  completa nem os testes de migração do checkout; DNS GitHub no container
  indisponível, banco/backup operacional não disponíveis. Não transferir
  resultados de outros SHAs. Nenhum avanço operacional declarado.

### Operador: validar primeiro, sem aplicar
Com todos os writers interrompidos (inclusive dashboard, workers, scheduler):

```powershell
git pull --ff-only
git status --short
conda activate tapi-asr
$env:TAPI_TENANT_ID = "local-research"
$head = (git rev-parse HEAD).Trim()
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python -m scripts.a02_payloads_preflight --expected-head "$head" --report-name "a02-payloads-$stamp" --backup-name "a02-post0015-$stamp.sqlite3" --confirm-all-writers-stopped
```

Esperar A02_PAYLOADS_PREFLIGHT_VERIFIED, 138 focais esperados sem skips,
45 tabelas preservadas, 1 nova vazia, downgrade vazio e backup inalterado.
Enviar resumo agregado (sem DB/credenciais/logs privados), incluindo SHA e
report_name/report_sha256. Se BLOCKED, não executar upgrade; inspecionar.
Após revisão do resultado, o procedimento de upgrade aceita explicitamente
`--apply-0016 --preflight-report <nome> --preflight-sha256 <sha256>` e novo
`--backup-name`, com mesmos HEAD/writers parados; não executar agora.
Próximos incrementos: supervisor de árvore, orçamento real CPU/RAM,
contratos de processor/payload, adapters sintéticos e smoke UI. Sem grants,
chaves reais, modelo, mídia externa, merge, liberação de gate ou gasto.


## A02.5/6 — 0016 operacional e supervisor Windows v2 (18/11)
Operador, HEAD f6189c22ace68e29f32383cf2eaa6bcf783d0a76:
138/138 focal PASS, 82,699s, zero skips/falhas/erros; JUnit SHA256
ba93974475c48d15e2a4dcd61b24c993e2cae5e1ed493136f621a9fec5b003e7.
Espelho 32/32, Gate0 e zero-spend PASS. Preflight
a02-payloads-20261118-102133 SHA256
fb8dbcbb1e1117d10090b596a2adbe3b47255d47f2d8dcd7fd9cc18e128e555b.
Backup pós-0015 e novo backup pré-0016
a02-pre0016-20261118-103827.sqlite3 SHA256
382bd6c4d66c0cd4acf2c41f4be40e43ad797aca0bfd082e436142f0dd02f0f4;
restore e rehearsal PASS, 45 tabelas preservadas, uma nova vazia.
A02_OPERATIONAL_MIGRATION_VERIFIED 0015→0016, schema, conteúdo, FK e
integridade OK; 1065 registros/1065 únicos/21 perfis/0 duplicatas;
zero grants, mídia false. Evidência reportada pelo operador.
Ambiente tapi-asr original incompleto; tapi-asr-recovery Python 3.11.18,
36 versões recuperadas, pip check/imports PASS, FFmpeg/FFprobe 8.1,
Tesseract 5.4/eSpeak 1.52; pip-freeze/conda-explicit/environment.yml
privados salvos. Aviso Conda sobre pacotes pip não equivale a falha.
Identidade byte a byte não garantida; full regression após recuperação.

### Novo incremento: kernel Job Object para fixtures, IMP-040/044/045/123/137
Base integral validada localmente, 190 hashes/204 IMP/543 dependências.
`asset_windows_job.py`: Windows x64 CPython; job nomeado por sessão
Local\\TAPI.Stone.A02.Synthetic.v2, criação exclusiva falha se ocupado;
handle não herdável, sem breakaway flags, KILL_ON_JOB_CLOSE. Usa handle
do filho Popen (não PID para atribuir/matar); confirma limites por
QueryInformationJobObject. Limites iniciais apenas de fixture: 128 MiB
de memória virtual comprometida agregada, 4 s CPU user-mode agregado,
2 processos ativos, deadline monotônico 15 s com polling 250 ms.
Não é cap de percentual de CPU nem RSS/GPU; CPU user-mode não inclui
kernel. Ação de término por tempo de job explícita. Inicialização
confiável -I -S espera stdin; atribuição e check antes de qualquer byte.
O bootstrap antes da atribuição não é limitado pelo job; não executa
trabalho, cria descendentes ou lê assets; EOF inválido encerra.
A execução verifica direitos/fence antes do envio, polling, após saída
e após limpeza. Término de árvore e contagem zero antes do recibo,
nega resultado se descendentes remanescentes; close mata associados
também se limpeza falha ou host encerra. Exclusividade de sessão não
é trava de todas as sessões/máquinas; nenhum controle contra host
malicioso. Não é sandbox de rede/FS/token, sem worker real ou modelos.
Communicate somente para código fixo confiável com saída curta;
não há limite geral de stdout de adapter, deadline pode atrasar por
I/O/SQL/OS bloqueante. Não registrar PID nem matar por PID.
`asset_supervisor.py` mantém método v1 sintético, compartilha checagem
de binding/fixture/rights; novo método synthetic-windows-job-v2, hash
inclui código/limites/flags/nome, sem fallback v1 em host incompatível.
Recibo hash apenas, sem payload, ciência ou mídia. Cancel/expiry/revoke
continuam fenced; sem renovação/retry/ack automático nem scheduler.
Docs API Microsoft:
https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information
https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_end_of_job_time_information

14 testes de contrato executados localmente no Linux, 14 PASS;
7 testes nativos Windows explicitamente skipped, não PASS.
3 novos testes de integração Windows com fila/cofre/rights não
executados pelo assistente. 162 focal esperados (138+21+3) no Windows,
zero skips, execução sequencial. Sem alteração de schema/DB/produção.
Supervisor precisa validação nativa; não habilitar mídia nem adapters
arbitrários. Próximo: teste nativo, backup pós-0016, full e smoke;
contratos de processor, integração sintética, isolamento e quotas
por adapter, reconciliador seguro antes de piloto autorizado.

### Operador — validação supervisor Windows e backup pós-0016
Com todos os writers parados:
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr-recovery
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q tests/test_a02_operational_upgrade.py tests/test_asset_lineage.py tests/test_asset_vault.py tests/test_asset_rights.py tests/test_asset_rights_registry.py tests/test_discovery_backup.py tests/test_a02_payloads_preflight.py tests/test_asset_windows_job.py
& $py scripts/verify_zero_spend.py
```
Após 162 PASS sem skips:
```powershell
$env:TAPI_TENANT_ID = "local-research"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$report = & $py scripts/a6_backup_restore_drill.py --output-name "a02-post0016-$stamp.sqlite3" --confirm-all-writers-stopped | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $report.status -ne "BACKUP_RESTORE_VERIFIED") { throw "Backup falhou" }
$report | ConvertTo-Json -Depth 8
```
Enviar somente resumo agregado, não DB ou credenciais. Sem migrar
novamente, não executar mídia, não criar grants, não mesclar PR.


## A02.6 — supervisor Windows validado e contrato tipado (18/11)
Operador HEAD 020b23587e99f40cdf6706dc87a97e2b36e181d9: 162/162 focal
PASS em 85,03s, zero skips/falhas; espelho 32/32 e zero-spend PASS.
Inclui 7 casos kernel nativos e 3 integrações fila/cofre/rights.
Backup pós-0016 a02-post0016-20261118-104730.sqlite3 SHA256
81163709870e1712241b99a668cfa6aa30b002f8b8eb66e2d648ab67a2692d43,
10.117.120 bytes, backup/restore 219/140ms, integridade/FK/schema e
conteúdo lógico iguais, revisão 0016. 46 tabelas de domínio + alembic; 1065 únicos/21 perfis, 0 duplicatas, 1169 snapshots,
5 documentos Studio; 7 tabelas de rights/lineage/jobs/payload vazias.
Evidência do operador, não inspeção direta do backup. Sem novo gate.

Novo asset_processor_results.py: envelope candidato estrito versionado,
binding tenant/job/object/digest/attempt/purpose/method/config/processor,
sem ciência/rubrica canônica/probabilidade calibrada. ASR/VAD intervalos
em ms com timeline PCM, ordem/duração/overlap; OCR palavras/bbox/frame
digest/time e confiança bruta opcional; temporal diferença normalizada
e transições amostradas (não cortes semânticos); VLM categorias candidatas
text_present/scene em frame, rejeita contradição e exige abstenção quando
tudo incerto. Abstenção sem campos de observação. JSON com limite 1MB,
duplicatas rejeitadas, tipos estritos, números finitos e revalidação
após model_copy/construct. Estrutura não valida verdade, não substitui
contratos canônicos de EvidenceBundle ou Rubrica. Não admite evidência.
asset_processor_fixture.py: quatro rotas por spec (ASR/VAD, OCR, temporal,
VLM), método synthetic-typed-windows-v3 e hash de configuração distinto
por processor. Somente fixture header de 12 bytes, child fixo com saída
curta explícita abstained/fixture_header_only. Não decodifica vídeo nem
invoca modelo. Host vincula envelope ao lease e ref, revalida após
cleanup do Job Object, e usa DerivedPayloadStore.finish atomicamente.
Retenção derivada deve estar autorizada; sem ela não persiste. Leitura
trusted-host continua exigir retain+process, integridade AEAD e lineage.
API opaca anterior permanece, contrato tipado obrigatório apenas na nova
rota sintética. Não cria grants reais, endpoint, modelo, EvidenceBundle
ou nova migração. Não é adapter real de ASR/OCR/VLM/FFmpeg.

23 testes de contrato em cópia isolada byte-idêntica PASS em Linux
(Pydantic 2.13.5); 7 integrações Windows adicionadas não rodadas aqui:
4 processors, retenção faltante, configuração errada, cancel tardio.
192 focais esperados (162+23+7), todos sem skip em Windows x64.
IMP-040/044/045/054/063/064/136/137; CT candidatos preservados.
Custo zero e DEC018, nenhum gate. Próximo: validação focal, full
pós-recuperação e smoke, adapters de mídia sintética válida com
proveniência/checkpoints e budgets medidos, sem promover header probe
a inferência nem habilitar caminhos de mídia externos.

### Operador — contrato tipado
Com ambiente tapi-asr-recovery e checkout limpo:
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q tests/test_a02_operational_upgrade.py tests/test_asset_lineage.py tests/test_asset_vault.py tests/test_asset_rights.py tests/test_asset_rights_registry.py tests/test_discovery_backup.py tests/test_a02_payloads_preflight.py tests/test_asset_windows_job.py tests/test_asset_processor_results.py
& $py scripts/verify_zero_spend.py
```
192 esperados sem skips. Sem nova migração ou grants; backup pós-0016
já verificado. Regressão full após PASS, com env reduzido via A00 runner,
tessdata pinado local conforme histórico; manter smoke operacional
separado. Não executar mídia externa, merge ou release.


## A00/A02 — full pós-recuperação e temporal FFmpeg (18/11)
Operador HEAD 36afc26ce5593bd8086d8bccddbd6c59459c99f5:
192/192 focal PASS em 104,23s; full a02-full-20261118-110319,
1108 coletados/1107 PASS/1 skip opt-in
tests.test_evidence_lab.test_operator_actual_triplet_when_configured,
0 falhas/erros, 357,238s. JUnit SHA256
cadb703db4a6627a097d684838a50f3416d540ec34ca103af67fd9ca13e38aba.
pytest.log SHA256
7941a63d3126581eb118082d0576220ae9104334f7c5cb040a684a6ff3e165a9.
Node (5 arquivos), Gate0, zero-spend e checkout PASS, OCR opt-in true,
108 módulos/99 testes Python/16 migrations. Baseline de engenharia
pós-recuperação; full sem skips=false. Sem banco operacional, sandbox
OS ou benchmarks standalone de modelos. Evidência reportada pelo operador.

### IMP-040/044/045/054/063/064/123/136/137 — primeiro adapter temporal real
`asset_temporal_fixture.py`: três MP4 autorais pequenos (64x64, 4 fps,
3s, MPEG4, faststart, sem áudio), bytes base64 e SHA256 pinados.
static (black/black/black), one (white/white/black), two
(black/white/black). FFmpeg real usa pipe, sem arquivos temporários,
protocolo pipe apenas, demuxer MP4 fixo, frames 64x64 gray, 12 frames,
1 thread de decoder/filtro/encoder solicitada. Não é leitura de PTS
original ou detector de cortes semânticos; reducer existente
bd-temporal-fixture.v1 sobre bytes realmente decodificados, exige
igualdade exata ao oracle de cores; diferenças de implementação
do FFmpeg falham fechadas. Temporal candidato registra 12 amostras e
transições em 0/1/2 instantes esperados, com frame hashes. Nenhum hook,
ritmo de cortes canônico ou inferência de conteúdo.
Método synthetic-temporal-ffmpeg-v4, hash de configuração inclui caso,
input, saída oracle, SHA256 do executável FFmpeg local, child, limites,
flags e versão reducer. FFmpeg resolvido do PATH do host confiável;
pin local antes/depois (não aprovação de supply chain nem hash de DLLs).
Mídia exata selecionada por hash do ref, não caminho do caller. Rights,
lease, tenant e engine rechecados; persiste envelope tipado via AEAD,
origin adapter_candidate + synthetic_fixture no recibo. Direitos
retain/process/derive específicos continuam necessários. Sem grants
reais, mídia externa, rubrica ou EvidenceBundle. O header-only anterior
permanece separado e abstém.

`asset_windows_job.py`: wrapper antigo preserva limite 64 bytes.
Primitiva privada de output exato permite até 128 KiB input/oracle
para fixtures confiáveis; stdout limitado por construção no child
FFmpeg fixo (não limite streaming genérico, não aceita decoder arbitrário).
Novo budget exclusivo do fixture: 512 MiB commit agregado, 10s CPU
user-mode agregado, 2 processos, 30s wall; parâmetros conservadores
de engenharia, não medidos para produção. Bootstrap confiável antes
de assign ainda não limitado, sem dados/descendentes. Sem sandbox
rede/FS, ACL, GPU, ou defesa contra host malicioso.

Testes locais isolados Linux: 9/9 novos (3 decodificações FFmpeg reais,
3 corrupções, caso inválido, pin config, bounds); 14/14 contratos
supervisor anteriores PASS, 7 nativos skipped. Reducer reproduzido
em cópia mínima da função fonte inspecionada, não full checkout.
6 novos casos integração Windows (3 fixtures, rejeição header,
retenção faltante, cancelamento tardio) não executados aqui.
207 focal esperados no Windows (192+9+6), zero skips. Espelho preservado.
Sem schema, migração ou operação no banco real; custo zero.
Próximo: validação focal e medição, OCR e ASR/VAD reais em fixtures
autoria local; VLM com checkpoint e budget específicos, reconciliador
e smoke antes de piloto. Nenhum gate liberado.

### Operador — temporal FFmpeg
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr-recovery
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q tests/test_a02_operational_upgrade.py tests/test_asset_lineage.py tests/test_asset_vault.py tests/test_asset_rights.py tests/test_asset_rights_registry.py tests/test_discovery_backup.py tests/test_a02_payloads_preflight.py tests/test_asset_windows_job.py tests/test_asset_processor_results.py tests/test_asset_temporal_fixture.py
& $py scripts/verify_zero_spend.py
```
207 PASS esperados, sem skip. Se falhar, preservar output redigido;
não aumentar limites ou relaxar oracle para obter PASS. Sem migração,
sem mídia real, sem merge. Full anterior pinado permanece histórico.


## A02.6 — temporal aprovado; adapter OCR real (18/11)
Operador HEAD 9483932b91377ed38c4d0e29d7fae0ec34719f8a:
207/207 focal PASS em 112,14s; zero falhas/erros/skips.
Espelho 32/32 e zero-spend PASS. 3 decodificações FFmpeg e seis
integrações Windows aprovadas. Evidência de console reportada,
não JUnit adicional. Sem nova migração ou dado operacional.

Novo asset_ocr_fixture.py: três PNG autorais grayscale 960x540,
Pillow default font, bytes e SHA256 pinados. Duas frases:
Organize suas vendas / Salve para revisar depois; controle vazio.
Tesseract real por stdin/stdout, TSV, por+eng, OEM1/PSM11, OMP_THREAD_LIMIT=1.
Diretório tessdata local explícito por trusted host, SHA256 de por/eng
e executável no pin de configuração, verifica antes/depois; não é
aprovação externa de supply chain/DLLs. Nenhum download, arquivo de
mídia temporário, texto de origem externa ou chamadas pagas.
Novo método synthetic-ocr-tesseract-v5. Validação do TSV: cabeçalho
completo, página única/dimensões, registros completos, IDs de palavras
não duplicados, parser bd-ocr-fixture.v1 (caixas/confiança finita),
oráculo palavras em ordem exata. Confiança bruta não calibrada; não
exige hash do TSV variável entre versões. Blank exige página válida
e nenhuma palavra, retorna abstenção no_observable_signal, nunca
negação de rubrica. Frame hash é hash do PNG de entrada, timeline
image t=0. Envelope adapter_candidate vincula spec/ref/lease e
persistência AEAD. Rights derive/retain/process separados, engine/tenant
e fence rechecados. Nenhuma EvidenceBundle ou rubrica admitida.

Supervisor: helper privado de resultado variável para fixtures
confiáveis, _run_bounded_fixture. Limites gerais desta rota restrita
input<=128KiB, output<=128KiB; OCR child lê no máximo 16KiB+1 do
stdout Tesseract e só encaminha se tamanho/exit code válidos.
Pai confirma limite, cleanup e árvore vazia antes da validação semântica
e recibo. Não é executor de comandos arbitrários nem cap streaming
para child hostil; pipe bloqueante é contido pelo deadline/kernel.
Wrapper exact-output anterior mantém oracle e bounds.
Budget OCR de fixture 512MiB commit, 10s CPU user-mode, 2 processos,
30s wall; decisão inicial de engenharia, não medição produtiva.
Sem sandbox rede/FS/token/GPU, sem grants reais.

Testes locais em cópia isolada Linux: 22/22 novos OCR PASS (3 chamadas
Tesseract reais, parser/negativos/binding/bounds); 14/14 portáveis do
supervisor PASS, 7 Windows nativos skipped. Funções parser/verify_tessdata
e hash reproduzidas da fonte inspecionada, não checkout integral.
Tesseract local reconheceu sete palavras em dois casos, zero no branco;
sem estimativa de precisão generalizável, sem gold independente.
6 novos testes integração Windows não executados pelo assistente:
3 casos AEAD, retain faltante, config incorreta, cancel tardio.
235 focal esperados (207+22+6) em Windows x64 com tessdata opt-in.
IMP-040/044/045/054/063/064/123/136/137; sem schema ou gate.

### Operador — validar OCR
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr-recovery
$py = Join-Path $env:CONDA_PREFIX "python.exe"
$env:TAPI_OCR_TEST_TESSDATA = "C:\Models\tapi\tessdata-fast-4.1.0"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q tests/test_a02_operational_upgrade.py tests/test_asset_lineage.py tests/test_asset_vault.py tests/test_asset_rights.py tests/test_asset_rights_registry.py tests/test_discovery_backup.py tests/test_a02_payloads_preflight.py tests/test_asset_windows_job.py tests/test_asset_processor_results.py tests/test_asset_temporal_fixture.py tests/test_asset_ocr_fixture.py
& $py scripts/verify_zero_spend.py
```
235 PASS esperados sem skips. Sem tessdata explícito, casos reais
são skipped e não aprovação. Não relaxar oracle nem substituir resultado
em falha. Full A00 com --tessdata-dir já encaminha esse opt-in.
Sem nova migração, mídia real, merge ou release. Próximo: Whisper/VAD
com fixtures PCM autorais, modelos locais e recursos medidos, depois VLM,
reconciliador e EvidenceBundle; smoke antes de piloto.
