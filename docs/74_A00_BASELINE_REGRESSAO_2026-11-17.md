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


## A02.6 — OCR aprovado; adapter ASR/VAD protegido (18/11)
Operador HEAD 3ad7a688d5893f0b7d895282ac9d098b5dc048da:
235/235 focal PASS em 114,41s, zero falhas/erros/skips.
Espelho 32/32 e zero-spend PASS. Evidência reportada pelo operador,
não JUnit novo. Três OCR reais e seis integrações Windows aprovadas.
Sem schema, banco operacional, grant real ou gate.

Novo asset_asr_fixture.py: synthetic-asr-vad-whisper-medium-v6.
Fixtures autorais WAV PCM s16le mono 16kHz; inventory "Confira o
estoque antes de aceitar novos pedidos." e 2s/1s de padding, silêncio
digital e tom 440Hz. TTS eSpeak NG/FFmpeg local por pipe, receita
fixa baseada no benchmark anterior (agora stdout sem arquivo);
sintetizado no host confiável antes do job, sem mídia externa,
não pin prévio cross-runtime de eSpeak. SHA256 do WAV e PCM da
execução na configuração; regeneração deve coincidir com ref/bytes.
O subprocesso TTS/FFmpeg de geração autoral ainda não usa Job Object
nem env reduzido, não recebe mídia ou texto arbitrário. Nenhum arquivo
de mídia temporário. Fixture tamanho <=480044 bytes, <=15s.
Modelo já instalado Medium CPU INT8 4 threads, weights SHA256 do
verificador anterior; demais arquivos hashados e verificados antes/depois,
Silero v6 hash 4cbf549b8326f60f80f2536d9eefeb450a9abe83365a098031c89719f1be17d2
observado anteriormente, não atestado independentemente.
Pin de config contém versões, source hashes, model files, opções,
código filho, digest e referência; não certificação supply chain.
Filho aguarda WAV exato antes de importar libs/modelo; -I -S,
sys.path local explícito, DLL paths Conda locais, HF offline,
local_files_only; sem site .pth, sem forwarding de credenciais
no subprocesso de inferência. Não sandbox rede/FS/token/GPU.
Reusa detect_regions e transcribe_regions de bd-vad-asr-fixture.v1.
Silêncio digital: zero VAD/ASR; tom: VAD real e zero ASR exigido;
fala: VAD primeiro, cache limpo antes de Whisper, uma região
esperada. Timestamps PCM sem concatenar pausas; não PTS original.
Gate individual pré-definido WER<=50%, IoU>=60%, erro fronteira
<=0,75s, nenhuma inserção nos negativos, sem ajuste retroativo.
Parser JSON estrito, hash PCM, tipos, limites, segmentos dentro
de região e ordem, arredondamento para dentro dos ms. Resultado
tipado ASR ou abstenção, nunca negativa canônica. AEAD e fence
mantidos; derive/retain/process separados.

Supervisor: ModelFixtureLimits separado (4096MiB commit agregado,
240s CPU user, 1 processo, 90s wall); cap inicial de engenharia,
não medição produtiva, lease 120s inalterado, sem renovação
automática. Child Python importa bibliotecas só após input.
Output JSON <=32KiB, medição kernel peak commit, CPU user/kernel
e wall no sucesso, sem medir GPU/RSS e sem diagnóstico de pico
em falha. Limites anteriores preservados. A coleta não prova RAM
física livre ou desempenho em produção. Não executar em paralelo.
Se limite/timeout/quality falhar, preservar evidência sem ampliar
automaticamente cap ou relaxar gate.

21/21 testes ASR locais isolados PASS (Python 3.13/Pydantic 2.13.5,
fixtures, parsing, gates, pin, limites; TTS real com eSpeak legado
1.48 exposto como espeak-ng no Linux para smoke, não a versão
Windows); 14/14 testes portáveis do supervisor PASS, sete nativos
skipped. Não há checkpoint Medium/Silero/faster-whisper no container,
nenhuma inferência VAD/ASR real realizada pelo assistente.
Seis integrações Windows com modelos locais pendentes; 262 focal
esperados (235+21+6), zero skips com ambos opt-ins.
A00 full runner ainda não encaminha opt-in ASR; testes de modelo
podem ficar explicitamente skipped nesse perfil, não contá-los
como PASS. Focal com opt-in obrigatório antes de declarar adapter.
IMP-040/044/045/054/063/064/123/136/137, DEC018 intacta.

### Operador — ASR/VAD
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr-recovery
$py = Join-Path $env:CONDA_PREFIX "python.exe"
$env:TAPI_OCR_TEST_TESSDATA = "C:\Models\tapi\tessdata-fast-4.1.0"
$env:TAPI_ASR_TEST_MODEL_DIR = "C:\Models\tapi\faster-whisper-medium"
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q --capture=tee-sys tests/test_a02_operational_upgrade.py tests/test_asset_lineage.py tests/test_asset_vault.py tests/test_asset_rights.py tests/test_asset_rights_registry.py tests/test_discovery_backup.py tests/test_a02_payloads_preflight.py tests/test_asset_windows_job.py tests/test_asset_processor_results.py tests/test_asset_temporal_fixture.py tests/test_asset_ocr_fixture.py tests/test_asset_asr_fixture.py
& $py scripts/verify_zero_spend.py
```
262 PASS esperados, sem skips. Enviar linhas ASR_FIXTURE_METRICS
e resumo. Não baixar modelos, não executar mídia externa, não
relaxar limites ou qualidade se falha. Sem migração. Próximo VLM,
reconciliação, EvidenceBundle e smoke; nenhum gate liberado.

### Endurecimento adicional antes de validar ASR
Subprocessos da síntese autoral agora também recebem ambiente reduzido
(SystemRoot/WINDIR/ESPEAK_DATA_PATH somente), binários resolvidos em
paths absolutos, shell=false/close_fds. Geração permanece fora do Job
Object, com frase fixa e timeout; não é sandbox OS. Teste negativo
adicional comprova não encaminhamento de TAPI_DATABASE_URL/HF_TOKEN.
22/22 testes ASR locais + 14 portáveis supervisor PASS; sete nativos
skipped no Linux. Corrige a limitação de env completo registrada acima.
**Contagem focal atualizada: 263**, não 262, sem skips com ambos opt-ins.
Nenhuma inferência Medium/Silero executada pelo assistente.


## A02.6 — ASR: falha no positivo e diagnóstico (18/11)
Operador HEAD 5aaaf465a7e76f07a0a94a6336179db578ee6396:
262 PASS / 1 FAIL em 124,62s, zero skips; espelho 32/32 e zero-spend
PASS. Falha test_real_asr_fixture_encrypted_result inventory:
ASR_FIXTURE_WINDOWS_PROBE_OUTPUT_INVALID, antes de result_from_output.
Sem confirmação de WER/IoU, etapa de falha, código nativo ou pico
de memória. Silêncio: zero VAD/ASR, pico commit 149749760 bytes,
CPU user/kernel 265,625/281,25ms, wall 656ms. Tom: 1 VAD/0 ASR,
pico commit 168308736 bytes, CPU user/kernel 390,625/343,75ms,
wall 688ms. Dois negativos PASS, não aprovação do adapter.
Evidência de console do operador, não inspeção de DB ou JUnit.

Causa ainda desconhecida; não alterar limites, WER, IoU, checkpoint
ou fixtures sem diagnóstico. Novo método synthetic-asr-vad-whisper-medium-v7
mantém todas as políticas, acrescenta protocolo de marcadores fixos
no stdout (bootstrap/imports/vad/model_load/transcribe/serialize),
flush a cada etapa, envelope final separado. Exceções Python geram
classe/razão allowlisted; classificação por texto local é heurística,
não diagnóstico definitivo. Nunca retornar stderr, mensagem bruta,
paths, PCM, transcript parcial ou texto arbitrário no erro.
O supervisor retém código de saída hexadecimal e pico commit quando
readback disponível mesmo em saída inválida; falha de readback não
mascara erro original. Falha nativa pode fornecer apenas último marcador,
código e pico. Timeout/cancelamento ainda têm diagnóstico próprio
sem esse relatório. Cap de 32768 bytes total preservado, reserva de
1024 bytes para framing; payload de resultado continua tipado e
validado com mesmos gates. Método/hash novo evita reaproveitar
recibo/config de v6. Nenhuma inferência adicional real aqui.
41 PASS / 7 skip Windows em cópia isolada Linux (27 ASR + 14 supervisor);
5 novos casos: falha Python memória/DLL, término abrupto simulado,
framing positivo, rejeição marcador inválido/oversize. TTS smoke
Linux via eSpeak legado, não valida runtime Windows/modelo real.
Base integral estrutural PASS; espelho 32 blobs preservado.
268 focais esperados após solucionar falha, não declarar PASS antecipado.

### Operador — diagnóstico focal imediato
Com HEAD atualizado, mesmo ambiente, model dir e tessdata:
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py -m pytest -q --capture=tee-sys --tb=short tests/test_asset_rights_registry.py -k "test_real_asr_fixture_encrypted_result"
```
Se falhar, enviar código sanitizado ASR_FIXTURE_WINDOWS_PROBE_OUTPUT_INVALID
com stage/exception/reason/exit/peak_commit_bytes, mais métricas negativas.
Não repetir automaticamente nem ampliar budget. Se 3 PASS, rodar
suite focal anterior (268 esperados) e espelho/zero-spend. Nenhuma
migração, mídia externa, grant real, merge ou gate.


## A02.6 — ASR diagnóstico de memória; orçamento revisado v8 (18/11)
Operador HEAD 51a797e7bfe7c6e9695f29e414e2d69bb76c2910:
1 FAIL / 2 PASS / 76 deselected, 33,41s. Inventory:
PROBE_OUTPUT_INVALID;stage=model_load;exception=RuntimeError;
reason=memory;exit=0x00000004;peak_commit_bytes=4303360000.
Pico 4104,004 MiB próximo/acima do limite de 4096 MiB (8,004 MiB
de diferença), forte evidência de orçamento insuficiente no load,
não prova de pico necessário no sucesso nem exclusão de pressão
global de commit. Classificação reason=memory é heurística.
Sem WER/IoU positivo. Silêncio 0 VAD/0 ASR, 149446656 bytes,
CPU user/kernel 265,625/187,5ms, wall 547ms. Tom 1 VAD/0 ASR,
168837120 bytes, CPU user/kernel 406,25/203,125ms, wall 609ms.
Negativos PASS; adapter ainda não aprovado.

Decisão de engenharia: um experimento controlado, orçamento fixo
ModelFixtureLimits 6144 MiB (6 GiB), somente Whisper Medium fixture,
mesmos 240s CPU user-mode, 90s wall, 1 processo, lease 120s,
mesmo checkpoint, parâmetros, oracle, WER/IoU e formato de saída.
Sem aumento de JobLimits de FFmpeg/OCR ou probe; sem retry/escalada
automática e sem 8GiB. Método synthetic-asr-vad-whisper-medium-v8,
hash inclui orçamento e política de admissão. Antes de spawn:
check de direitos, GlobalMemoryStatusEx (Windows x64), mínimo
4096 MiB disponíveis físicos e 7168 MiB de commit disponível
ao processo pai (cap 6144 + reserva 1024). Se insuficiente,
MODEL_HOST_HEADROOM_INSUFFICIENT com valores agregados, sem spawn.
Não representa reserva de RAM nem garantia de disponibilidade
contínua; não confundir commit com RSS ou memória física. Não
alterar pagefile, liberar apps manualmente; não executar em paralelo.
O host pode perder headroom entre consultas. Cap ainda no kernel.
Documentação Microsoft: https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/ns-sysinfoapi-memorystatusex

48 PASS / 7 skip nativos em cópia isolada Linux (34 ASR + 14 supervisor).
7 novos testes (fronteiras de admissão, bloqueio antes do spawn,
orçamento fixo e ABI); sem modelo real ou execução Windows aqui.
Teste de integração verifica teto revisado. Espelho 32/32 intacto.
275 focais esperados após aprovação, sem skips com opt-ins.
Não alterar DB/migração/grants, sem mídia externa ou gate.

### Operador — preflight memória e três casos
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr-recovery
$py = Join-Path $env:CONDA_PREFIX "python.exe"
$env:TAPI_ASR_TEST_MODEL_DIR = "C:\Models\tapi\faster-whisper-medium"
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
& $py -c "import json; from tapi_gate0.asset_windows_job import ModelFixtureLimits, require_model_headroom; print(json.dumps(require_model_headroom(ModelFixtureLimits())))"
if ($LASTEXITCODE -ne 0) { throw "Headroom insuficiente ou consulta falhou" }
& $py -m pytest -q --capture=tee-sys --tb=short tests/test_asset_rights_registry.py -k "test_real_asr_fixture_encrypted_result"
```
Se preflight falhar, não executar modelo, enviar valores agregados.
Se positivo falhar, enviar diagnóstico; sem ampliar cap de novo.
Se 3 PASS, executar focal completo (275) e espelho/zero-spend,
avaliar pico, latência e qualidade. Não habilitar mídia real.


## A02.6 — ASR/VAD focal aprovado; adapter visual protegido (18/11)
Operador HEAD 8394df96e7b5736cc33347d350265cb723edd72a:
275/275 focal PASS em 124,69s, checkout limpo, sem falhas/skips;
espelho 32/32 e zero-spend PASS. Inventory WER 0,375, IoU
0,9317703013278856, fronteira 0,1971875s, peak commit 5270040576 bytes,
CPU user/kernel 24750/6296,875ms, wall 9235ms; silêncio 0/0 chamadas,
149262336 bytes, 531ms; tom 1/0, 168456192 bytes, 641ms. Reproduz
execução anterior; WER individual ainda alto. Cap ASR 6GiB mantido,
não otimizado definitivamente. Evidência agregada do operador.

Novo asset_vlm_fixture.py: synthetic-vlm-qwen3-single-scene-v1.
3 PNGs autorais 960x540 bytes/SHA256 fixos (texto Organize suas vendas,
retângulo+triângulo, fundo uniforme). Reusa prompt/schema e guard
single-scene v2; duas chamadas Qwen3-VL-2B Q4_K_M + mmproj Q8_0,
uma guard uniforme sem modelo. Presença de texto derivada de scene,
não independente. Gate integração 3/3 cenas corretas, sem abstenções
ou erro; conflito blank não uniforme vira uncertain e bloqueia fixture.
Não substitui benchmark v2 de 26 posições nem falha em texto pequeno.
Hash do PNG na timeline image t=0, contrato candidato VLM, AEAD e
fencing/rights; sem rubrica, EvidenceBundle ou admissão científica.

Pin GGUF publicado via verify_checkpoint existente; binário b6907
SHA256 observado anteriormente obrigatório; hashes DLLs adjacentes,
sources/versions/config e rechecagem pós-execução. Não atesta supply
chain, DLLs do SO ou host malicioso. Child -I -S espera input exato
antes de imports, paths locais explícitos. llama-server nasce dentro
do Job Object (sem breakaway), CPU 4 threads/ctx2048/np1, max tokens64,
offline, loopback 127.0.0.1, chave efêmera via LLAMA_API_KEY em env
reduzido (sem arquivo/argv; acessível a processos privilegiados do
host), sem proxy ou redirects. Verifica 401 em POST inferência vazio
sem credencial e alias no endpoint models antes de enviar PNG base64.
Health/models podem ser públicos, não confiar neles como auth.
Porta efêmera selecionada antes de bind (janela de corrida), alias
e auth mitigam, não isolamento de host malicioso. HTTP resposta
limitada 100KB, JSON estrito, stdout 32KiB com framing sanitizado;
sem arquivo de mídia temporário, sem servidor persistente.
Docs runtime pinado:
https://github.com/ggml-org/llama.cpp/blob/b6907/tools/server/README.md

VlmFixtureLimits separado: 4096MiB commit, 240s CPU user agregado,
2 processos, 90s wall, lease 120s. Headroom 4GiB físico e 5GiB
commit disponível, guard antes de spawn, não reserva. Valores
iniciais de engenharia, não medidos para VLM. ASR e JobLimits
anteriores intactos. Framing VLM separado, failure callback no
supervisor, kernel metrics no sucesso e saída inválida; sem raw
stderr. Sem sandbox rede/FS/token/GPU. Não executar em paralelo.
22/22 testes VLM novos locais em cópia isolada Linux PASS, com
reprodução mínima das classes Frame/VLM e guard exact_uniform de
fonte inspecionada; testes de parser, fixtures, mock HTTP e child
stub, não inferência Qwen real. 4 novos testes supervisor e 6
integrações Windows não executados pelo assistente. 307 focal
esperados (275+22+4+6) com opt-ins ASR/OCR/VLM; sem skips.
Sem novos downloads/schema/DB/grants/mídia externa/gates/merge.

### Operador — VLM três casos antes da regressão
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr-recovery
$py = Join-Path $env:CONDA_PREFIX "python.exe"
$env:TAPI_VLM_TEST_MODEL_DIR = "C:\Models\tapi\qwen3-vl-2b-gguf"
$servers = @(Get-ChildItem "C:\Models\tapi\llama-b6907" -Recurse -File -Filter llama-server.exe)
if ($servers.Count -ne 1) { throw "Expected one llama-server.exe" }
$env:TAPI_VLM_TEST_SERVER_EXE = $servers[0].FullName
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
& $py -c "import json; from tapi_gate0.asset_windows_job import VlmFixtureLimits,require_model_headroom; print(json.dumps(require_model_headroom(VlmFixtureLimits())))"
if ($LASTEXITCODE -ne 0) { throw "Headroom insuficiente" }
& $py -m pytest -q --capture=tee-sys --tb=short tests/test_asset_rights_registry.py -k "test_real_vlm_fixture_encrypted_result"
```
3 PASS esperados, enviar VLM_FIXTURE_METRICS. Se falhar, preservar
diagnóstico, não escalar cap ou flexibilizar oracle. Depois 307
focais incluindo test_asset_vlm_fixture.py, espelho e zero-spend.
Full A00 ainda não encaminha opt-ins ASR/VLM, não contar skips.
Próximo: reconciliação, EvidenceBundle, smoke, piloto autorizado
quando rights específicos existirem. Nenhum gate liberado.


## A02.6 — regressão consolidada; reconciliação de manutenção (18/11)
Operador HEAD 43d085ba16e1e96ee5b3d1dc0e75b0a910f0ff20:
307/307 PASS em 209,46s, zero falhas/erros/skips, espelho 32/32
e zero-spend PASS. ASR inventory WER 0,375, IoU 0,9317703013278856,
fronteira 0,1971875s, peak commit 5269770240 bytes, CPU user/kernel
25953,125/6453,125ms, wall 9641ms; silêncio 0/0 calls, 149262336 bytes,
562ms; tom 1/0, 168521728 bytes, 641ms. VLM sales text_card 1 call,
2515156992 bytes, CPU user/kernel 117656,25/4218,75ms, wall 32125ms;
geometry 1 call, 2515267584 bytes, 120718,75/4171,875ms, wall 32984ms;
blank guard 0 calls, 24715264 bytes, 312ms. Evidência de console do
operador, não JUnit novo. Quatro adapters protegidos em fixtures,
não homologação científica/produtiva. WER individual ainda alto.
Caps mantidos. Base integral estrutural validada.

Novo asset_reconcile.py, asset-reconciliation.v1, duas operações
trusted-host explícitas (sem endpoint, daemon ou scheduler):
reconcile_tenant: uma transação BEGIN IMMEDIATE por tenant, até 32
escopos (TrustedAuthority, platform) provisionados independentemente,
validação exata de head, assinatura, janela e issuer/key/scope; sem
autodiscover de confiança a partir de DB. Scope duplicado ou stale
aborta tick, sem tombstones parciais. Ausência de scope não equivale
a revogação; TTL-only explícito permitido e cobertura reportada.
Invalida raízes revogadas/expiradas e descendentes, reusa _invalidate.
Cancela queued, sinaliza running, preserva histórico completed;
invalidação antes de expiração de lease impede retry de input revogado.
Reusa _expire para retry/exhaustion, não cria tentativa ou mata worker.
Sem ack automático, sem prova de worker parado. Head revogado
anteriormente commitado continua negar direitos mesmo se tick falhar.
Contagens agregadas, outbox/audit existentes, sem payload retornado.

cleanup_tenant: exige atestado explícito de TODOS workers/writers/readers
parados e vault canônico do tenant fornecido pelo host; valida binding
queue/index/vault/store e ausência de leases ativos globalmente.
Limite 1..100 por lote, primeiro derivados AEAD invalidados e depois
raízes invalidadas sem recibo de descarte v3. Reusa purge_invalidated
e discard_invalidated com verificações por item; não lê plaintext,
não usa paths do caller. Cada item commit independente; erro interrompe
lote, commits anteriores ficam duráveis, retry seleciona restantes.
Não há lock abrangendo o lote fora da atestação de parada do host,
não é prova de parada real. Recibos existentes são pulados; não
audita arquivos reaparecidos, órfãos de staging ou vault incorreto.
Não secure erase de WAL/backups/SSD nem revoga bytes já entregues.
Relatório remaining_at_snapshot não garante estado futuro. Sem chaves
novas, DB operacional ou schema. RAG/cache/exports/treino não
integrados ainda; IMP-040/045/126/137/145 parcialmente atendidos,
não fechar IMP/gates. Decisão de engenharia: manutenção explícita
em vez de agendar daemon antes do piloto.

9 novos testes integração SQLite nas fixtures de rights registry:
cascata + lote, cancel/ack, revogado expirado sem retry, lease válido
expirado com retry, TTL, falta/stale/duplicate scope, rollback, retry
após purge parcial, atestação/binding/tenant. Sintaxe Python dos dois
trechos compilada localmente; testes de integração não executados
pelo assistente (checkout completo indisponível). 316 focais esperados
(307+9); primeiro 9 isolados. Sem merge, gate, grant real ou migração.
Próximos: EvidenceBundle multimodal, fusão, full runner opt-ins e smoke.

### Operador — manutenção sintética
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr-recovery
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q --tb=short tests/test_asset_rights_registry.py -k "test_maintenance_"
& $py scripts/verify_zero_spend.py
```
9 PASS esperados sem skips; se PASS, repetir suite focal 316 com
opt-ins ASR/OCR/VLM anteriores. Não chamar manutenção no DB real.


## A02.6 — manutenção aprovada; EvidenceBundle candidato (18/11)
Operador HEAD b77e294f2bcf80c33a8763401b7aaac1cfb92f7e:
9/9 novos PASS, 85 deselected, 6,28s, espelho 32/32 e zero-spend
PASS. Evidência de console do operador, não JUnit. Reconciliador
aprovado em fixtures; 316 focal ainda não executado no mesmo SHA.

Novo asset_candidate_evidence.py: asset-candidate-evidence-bundle.v1.
Complementa, não altera, EvidenceBundle textual E1 (DEC017).
Entrada explícita tenant, object_id, purpose e 1..4 artifact_ids;
um resultado por processador, sem busca automática de latest.
Exige raiz RetainedAssetRef ativa e mesmo objeto exato (não só
content_id/digest), derivações diretas, nenhuma mistura de grants,
raízes, tenants ou finalidades. Valida seleção antes de decrypt.
Reusa leitura AEAD/fence de job completed, receipt, attempt, método,
config, hash do input, digest de payload, parent e direitos atuais.
Refatora read_for_processing em helper privado de transação (API
pública inalterada), validate_persisted_binding sem inventar lease.
Todas as leituras e revalidação final de ancestrais, TTL, direitos de
retain/derive/process e head atual em uma transação BEGIN IMMEDIATE.
Nenhuma mutação de payload/audit, model call, ingestão, publicação,
chave nova ou persistência do bundle. Contrato frozen/strict, entradas
ordenadas por processador, fingerprint SHA256 canônico determinístico,
payload JSON canônico obrigatório. Rejeita opaque bytes e typed
payload com spec divergente apesar de AEAD válido. Sem retorno
de erro Pydantic bruto do parser/contrato. Imagem exige frame t=0
timeline=image e SHA256 do PNG igual ao input; vídeo requer timeline
resampled_uniform, não prova igualdade de frames entre modalidades.
Sem concatenação textual, caption arbitrária ou inferência de ausência.
Coverage explicita observed/abstained/missing/not_applicable por
tipo de entrada, não cobertura temporal integral. Sem probability,
canonical_rubric ou scientific_evidence. Fingerprint não é grant,
assinatura de execução do modelo, nem prova de verdade. O store
continua confiando no host que finaliza payload: typed outputs
podem ser fabricados por código privilegiado. Não armazenar bundle
como autorização; reassemblar em cada boundary, revogação não
recupera bytes já retornados. Não deriva rubric_evidence nem
concede direitos adicionais; S1/fusão/uso operacional ainda pendentes.
Sem novo schema, migração, API, gate ou alteração do DB operacional.

16 casos novos no registry: 15 SQLite com payloads sintéticos
construídos pelos testes (inclui 4 abstenções header e OCR+VLM
observados na mesma imagem simulados); um nativo Windows opt-in
usa PNG blank idêntico dos adapters (OCR real + guard VLM,
sem chamada Qwen), valida co-referência real. Casos negativos
de seleção, duplicate processor, tenant/purpose, mesmo digest
em outra raiz, três bindings falsos, bytes opacos/não canônicos,
frame/hash divergente, missing process, revogação/purge, expiry
no final e ciphertext adulterado. Sintaxe dos novos módulos
e testes compilada localmente; refatoração revisada por diff,
não executei testes SQLite ou Windows no checkout integral.
332 focal esperados (307+9+16), sem skips com os três opt-ins.
IMP-054/063/064/136/137 parcial, não fechamento ou gate. Próximo:
fusão conservadora com proveniência e direitos rubric_evidence,
runner A00 com opt-ins ASR/VLM, regressão integral e smoke.

### Operador — bundle
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr-recovery
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q --tb=short tests/test_asset_rights_registry.py -k "test_candidate_bundle_ and not test_candidate_bundle_real_blank"
& $py scripts/verify_zero_spend.py
```
15 PASS esperados. Com opt-ins OCR/VLM anteriores, execute também
`pytest -q --tb=short tests/test_asset_rights_registry.py -k test_candidate_bundle_real_blank`
(1 PASS; não carrega Qwen). Depois focal completo 332 com todos os
opt-ins. Sem uso no banco real ou novos modelos.


## A02.6 — bundle aprovado; fusão candidata S1 (18/11)
Operador HEAD dd2880c5e25d2a587862e9628da022fbd92bc6fb:
15/15 SQLite PASS em 12,75s, 95 deselected; 1/1 Windows blank
OCR real + guard VLM PASS em 10,98s, 109 deselected. Espelho 32/32
e zero-spend PASS. Evidência de console, não JUnit novo.
332 focal ainda não executado no mesmo SHA.

asset_candidate_fusion.py: asset-s1-candidate-fusion.v1, rota local
determinística, não GLiNER/Qwen novo, não canonical RubricAssessment.
Reusa grounded theme e directed CTA v2, sem concatenação entre
segmentos ASR ou modalidades. OCR sem IDs de linha: só usa semântica
quando todas caixas ordenadas na mesma faixa vertical, sem overlap
horizontal ou gaps >2 alturas, texto <=10000; heurística de engenharia
não calibrada. OCR parcial ainda candidato positivo de texto na tela.
VLM isolado nunca promove texto; voto no negativo de frame idêntico
(inclui hash, timeline, t) bloqueia os 4 campos avaliados, mesmo com
ASR presente, por conservadorismo; outros frames não vetam.
Até 128 fragmentos sem truncamento, erro fechado acima do limite.
4 campos candidatos/abstenções: tema_principal, tipo_cta, tem_cta,
texto_na_tela; outros 16 not_assessed. Sem negativa inferida, score de
cortes, hook, face, claims de prova social, probabilidade, treino.
Support vincula artifact/payload hash, índice de segmento, timeline,
timestamp, frame hash, índices de palavra e digest textual quando
semântico. Sem texto bruto no relatório, não prova execução.
Fingerprint do bundle, contrato frozen/strict, 20 campos ordenados.
Derive rubric_evidence explícito antes do decrypt e depois de fusão,
revalida direitos de todos os resultados em mesma transação SQLite.
Refatora montagem em helpers privados, API anterior preservada.
Nenhuma persistência, retain/display/export grant, endpoint ou
autorização reutilizável. Não integrar ainda ao ranking/agent.
11 novos casos SQLite (positivo, conflito, 4 CTA não elegíveis,
VLM isolado, ASR/temporal, conflito entre modalidades, permissão,
expiração/revogação). Não é novo benchmark independente.
343 focal esperados (332+11) com opt-ins. Testes do novo commit
ainda não executados; validar primeiro test_candidate_fusion_,
depois regressão focal e full runner opt-ins. Sem schema/DB real,
gate ou merge. IMP-054/063/064/136/137 parcial.


## A02.6 — fusão 11/11; runner A00 multimodal (18/11)
Operador: 11 passed, 110 deselected em 17,41s no filtro
test_candidate_fusion_; reportado após instruções a9cda63, trecho
não inclui HEAD, não é confirmação independente do commit.
343 focal ainda não executado conjuntamente. PR #44.

a00-local-baseline.v2: --asr-model-dir, --vlm-model-dir,
--vlm-server-exe e --require-multimodal, além de tessdata existente.
Opt-ins explícitos, full-only; VLM exige ambos paths; caminhos locais
absolutos não redirecionados, arquivos requeridos e nome do server.
Preflight de existência, não validação de checkpoint; testes adapters
já fazem pins de conteúdo e admissão de memória. Strict exige Windows
64-bit e os quatro paths, sem download. Opt-ins apenas no pytest,
não encaminha ambient TAPI_* ou credenciais aos outros steps.
Full inclui mirror documental, Gate0, zero-spend, pytest JUnit e Node;
tee-sys preserva ASR/VLM metrics no log privado. JUnit verifica 12
grupos exigidos com mínimos fixos (kernel, supervisor, typed,
temporal decode/integração, OCR decode/integração, ASR, VLM,
bundle blank, manutenção e fusão). Cada grupo exige todos coletados
PASS, mínimo atingido, nomes únicos; contagens não são inventário
exato de nodeids, não atestam conteúdo do modelo por si. Strict falha
mesmo que pytest exit=0 quando grupo está ausente/skipped. Skip
opt-in Evidence Lab continua separado e não vira PASS; sem global
gate ou production approval. Sem benchmark standalone, DB operacional,
download ou OS sandbox. API execute preserva primeiro argumento
tessdata posicional. 13 novos casos de runner; revisão por inspeção,
execução integral pendente. Sem schema/merge.


## A00/A02.6 — regressão strict multimodal PASS (18/11/2026)

Operador reportou HEAD `298426d76db962c649afd1abbeb60452f26ee583`,
árvore `d3e45319324da70d75f2ca2a1ab2576fe5e2f304`, ambiente
tapi-asr-recovery, Python 3.11.18. PR #44 draft, base #43.
Runner isolado 21/21 PASS (1,13s), espelho 32/32 e zero-spend PASS.
Relatório privado `a02-multimodal-20261118-150119`, policy a00-local-baseline.v2,
full strict, OCR/ASR/VLM opt-ins true, checkout unchanged, checks_passed=true.
1272 coletados / 1271 PASS / 0 FAIL / 0 ERROR / 1 SKIP explícito:
tests.test_evidence_lab.test_operator_actual_triplet_when_configured.
pytest 672,588s, Node (5 arquivos), Gate0 histórico, zero-spend e espelho
exit 0. 115 módulos Python, 103 arquivos de testes Python, 16 migrações.
12/12 grupos JUnit obrigatórios (68 casos) PASS: kernel 7, supervisor 3,
typed 7, temporal decode 3/integração 6, OCR decode 3/integração 6, ASR 6,
VLM 6, bundle blank 1, manutenção 9, fusão 11. Não afirmar execução focal
separada de 343 casos; full cobre a suíte e valida grupos obrigatórios.
Hashes SHA256 reportados:
- pytest.xml 1b2c54739c9d072fc045318227a533a4d56df590257a934735f7433b93c126bf
- pytest.log 134de64983b44205b2dcf32332cea3e3b8887b60b7dff7044300e1ef008726a7
- node.log 51e855ebbfcd203b6e9bc3eaf722435db5eff335a160e4760b0c6aaa1a3e4884
- legacy_gate0.log f3115f87c8f4fa3768406a03445a0dacf21b0fe25edea391ba67c4dfcf7338e7
- zero_spend.log 742195993c63e078537534ccfb5011723ff35dc154585e798f271b2df1ad1d22
- documentary_mirror.log c1889eee083dcbe651dc1e42b4ad7b0a8c7702499c0f93805c465414d66917b1

Relato do operador, não inspeção independente dos logs/DB/modelos.
Sem benchmark standalone, DB operacional, sandbox de rede, gates
globais ou aprovação de produção. Sem nova migração ou inferência real.
Baseline strict aprovada no SHA testado; A00/A02.6 ainda aguarda opt-in
Lab e smoke browser. Não repetir full só pela contagem focal; se
necessário, auditar nodeids no JUnit original. Preserve relatório original.
Nenhuma homologação de IMP/CT inferida da contagem de testes.

### Validação final do Lab — incremento de teste, IMP-083 parcial (CAP-003/CAP-004, U06/CT-06)

Commit `eae562d94ddbb257c2fbfe62c13377a662e9d346`: amplia exclusivamente
test_operator_actual_triplet_when_configured em tests/test_evidence_lab.py.
Reutiliza os relatórios pinados do docs/73 e recomposição real;
confere 7 IDs distintos, 20 campos, 15 braços, 140 células e contagens
12/28/16/84, composição PASS e VLM FAIL preservado, sem canonical,
independent gold, player ou production. Exercita GET autenticado de
summary e todos os sete casos por TestClient, private/no-store, 401,
404, 405, logout, correspondência de hash/estado e ausência de linhas
de corpus/rubrica/eventos. DB SQLite descartável em tmp_path,
bootstrap/login/logout apenas nele. Nenhuma mudança de runtime,
schema, permissões ou comportamento do runner. O teste mantém o
skip explícito se não configurado; não expõe conteúdo dos relatórios.
Não executado pelo assistente: arquivos privados e ambiente local
indisponíveis. PASS anterior não transferido ao novo SHA.
Não implementar A02.7 até reconciliar este teste e smoke aplicável;
IMP-054/063/064/136/137 permanecem parciais.

Operador: na sessão Windows anterior, com writers/ingestão parados,
checkout limpo, reusar ambiente e tenant existentes. Pins históricos
fixos, não recalcular hashes para contornar divergência:

```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr-recovery
$py = Join-Path $env:CONDA_PREFIX "python.exe"
if ([string]::IsNullOrWhiteSpace($env:TAPI_TENANT_ID)) {
    throw "Reutilize o tenant existente (sem bootstrap operacional)"
}
$env:TAPI_EVIDENCE_LAB_TENANT=$env:TAPI_TENANT_ID
$env:TAPI_EVIDENCE_LAB_SHARED_NAME="a6-shared-multimodal-20261117-174208.json"
$env:TAPI_EVIDENCE_LAB_SHARED_SHA256="4808374885f1ae860507aa513c93830b0cd62ca8ce062160896912e8f93ea4fc"
$env:TAPI_EVIDENCE_LAB_VLM_NAME="a6-vlm-single-scene-v2-20261117-182203.json"
$env:TAPI_EVIDENCE_LAB_VLM_SHA256="9709cc2b7853829fc3056cb5a605ba77b0850ec2ebf4788c34fc8b3d5552200b"
$env:TAPI_EVIDENCE_LAB_REPORT_NAME="a6-multimodal-evidence-v2-20261117-183535.json"
$env:TAPI_EVIDENCE_LAB_REPORT_SHA256="bbb4a4d9a267ad2aeee63734d9fdb7288e99b2cb7372f48bb079f5fbc1d04c60"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q --tb=short tests/test_evidence_lab.py
node --test tests/test_evidence_lab_ui.mjs
& $py scripts/verify_zero_spend.py
```

Esperado 5/5 Lab, zero skip; não considerar expectativa resultado.
Se PASS, iniciar o servidor local usando a configuração operacional
já existente (docs/73), somente loopback. Smoke: Dashboard login,
overview/SSE e navegação; Data Explorer inventário/detalhe/rubrica e
paginação; Ranking população/contrastes/drilldown (replay opt-in já
configurado, se ausente registrar not_configured); Lab consultar os
7 casos, filtros, locadores, 15 braços, composição PASS/VLM FAIL,
logout limpa dados; Studio abrir rascunho existente, verificar editor
sem salvar, renderizar, exportar ou publicar; logout. Nenhuma escrita
de corpus/Studio, login/logout podem alterar identidade. Não iniciar
coleta ou modelo. Registrar HEAD e resultado de cada superfície,
não confundir smoke manual com E2E automatizado. Se falha, preservar
log e corrigir antes de avançar. Próximo incremento A02.7: orquestração
integrada somente em fixtures autorizadas, sem grants reais ou gate.


## A00 — Evidence Lab opt-in e smoke parcial PASS (18/11/2026)

Operador HEAD 9bd1b6a62c55cc6ffa0f38e387f6dcc5db491e78:
espelho 32/32, Lab Python 5/5 PASS sem skip em 6,22s,
um StarletteDeprecationWarning (httpx), Node Lab 7/7 PASS em
206,6648ms, zero-spend PASS. Relato de console, sem JUnit novo.
Teste opt-in confirmou os sete casos e todos os campos via API
autenticada e banco descartável. Servidor operacional loopback
iniciou; auth, overview, SSE, inventário limit=25/offset=0,
Studio biblioteca, Lab summary e caption_only HTTP 200.
Operador copiou UI com 20 campos, 12/28/16/84 total,
15 braços, composição PASS/VLM FAIL; 9/10 caption+audio+OCR
e all. Não confirmou ranking, detalhes/paginação, outros
seis casos no browser, editor ou logout manual. Node e API
automatizados não substituem browser QA. Não alegar DB sem
mutações de identidade ou nova admissão. A00 strict permanece
PASS apenas no SHA 298426d (1271/1272, skip Lab); opt-in
aprovado separadamente no 9bd1b6a. Não somar contagens de suítes.

Decisão operacional: avançar A02.7 isolado em fixtures porque
smoke inicial e teste opt-in passaram; manter itens browser
pendentes, sem reclassificar gates. Não é dispensa de CT/aceite.

## A02.7 — orquestração fixture-only, primeiro incremento (18/11)

Base documental integral validada localmente (PASS estrutural,
204 IMP, 543 arestas, 23 CAP, 18 DEC, 28 CT, 7 gates), espelho
reportado pelo operador. IMP-054/063/064/136/137/145/178 parciais;
CAP-003/009/016/022/023; DEC-017/018; CT-04/09/11/18 e CT-STUDIO-07
relacionados, não cumpridos. Não altera DAG/matrizes.

Commits de código:
- f1bc9e9: asset_fixture_pipeline.py, claim opcional por job_id
  exato, testes de retomada, isolamento, falha e permissão.
- bebc69d: casos nativos individuais FFmpeg, ASR/VAD, OCR e VLM;
  runner strict inclui grupo fixture_pipeline.
- 9c19604: lease expirado não prova saída física do worker;
  bloquear retry sem reconciliação e retry_stopped=True explícito
  do host confiável, testes de expiração e revogação assinada.

FixturePlan frozen com fingerprint dos JobSpec determinísticos
e modo/caso. Host preserva fingerprint fora do DB e informa
expected_plan ao retomar após restart; sem índice persistente
de plano, não garante retomada se host omitir pin. Seis modos
fixos (header, temporal, asr, ocr, vlm, image_pair blank).
Não aceita callback de modelo, mídia arbitrária, upload ou
scheduler. Entradas exatas por SHA256, tamanho, MIME, método
e configuração. Preflight direitos de retain/process/derive
e retain/process de cada output, derive rubric_evidence;
rechecagem a cada step, adaptadores e fusão. Um job por tick,
completos reutilizados apenas com recibo encrypted_payload;
fusão reautentica todos os artefatos ao final, sem parcial,
rubrica canônica, admissão, nova persistência ou saída pública.
A fila preserva orçamento, exclusão lógica global e manutenção
existentes, inclusive expiração de leases; não é sandbox nem
garantia de isolamento físico. Host deve garantir worker parado
antes de manutenção/retry. Sem fallback automático; falha do
adapter propaga e não libera lease por conta própria. Sem
chaves/grants reais ou novas aprovações institucionais.
O header de MP4 não é vídeo decodificável: quatro abstenções.
Par nativo somente PNG blank idêntico de OCR/VLM, sem chamada
Qwen no guard. Cada adapter real pode rodar separadamente em
fixture nativa; não há ainda vídeo comum com áudio/frames
processado nas quatro modalidades. Próximo incremento após
testes: fixture audiovisual compartilhada, timeline/frames
co-referenciados e derivação protegida, sem ampliar direitos.
Nenhuma migração, operação Meta, gasto ou acesso a DB real.

12 novos testes (6 nativos Windows, 6 SQLite sem dependência
de modelo): retomada/dedup, claim alvo, falha/cancelamento,
invalidação, escopo, quatro headers, par blank, quatro adapters
nativos individuais, recuperação de lease expirado e recibo
opaco/revogação assinada. Contagem é expectativa. Não executados
pelo assistente; revisão de código/diff, não checkout integral.
Strict exige 13 grupos e 80 casos mínimos (68+12). Não afirmar
benchmark ou full PASS no novo HEAD até execução.

### Operador — validação incremental
Parar servidor local Ctrl+C e writers. Reutilizar os opt-ins
locais anteriores, nenhum download ou benchmark standalone.
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr-recovery
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q --tb=short tests/test_asset_rights_registry.py -k test_fixture_pipeline_
& $py -m pytest -q --tb=short tests/test_a00_baseline.py
& $py scripts/verify_zero_spend.py
```
Esperados 12 PASS sem skip do pipeline, 21 runner PASS,
espelho e zero-spend PASS; não são resultados realizados.
Se PASS, executar full strict no HEAD limpo, mesmos quatro
paths explícitos de tessdata/ASR/VLM/server, report name novo.
Esperar 13 grupos, fixture_pipeline 12/12, zero falhas/erros,
Lab opt-in continua skip no runner isolado; executar Lab
separadamente caso necessário, sem herdar DB operacional.
Não operar o pipeline diretamente sobre corpus real.


## A02.7 — regressão do orquestrador PASS (18/11/2026)

Operador HEAD 5f00e611799aa7f897a83cf729e58e4d701caa29,
árvore 259bfd971be716fe8ce0641ad8c789e2a1bcf956.
12/12 focal em 117,28s (121 deselected), runner 21/21 em 1,02s,
zero-spend PASS. Full strict a02-pipeline-20261118-153112,
Python 3.11.18, tapi-asr-recovery, OCR/ASR/VLM opt-ins true,
1284 coletados / 1283 PASS / 0 FAIL / 0 ERROR / 1 SKIP Lab opt-in,
pytest 711,588s, Node/espelho/Gate0 estrutural/zero-spend exit 0,
checkout inalterado. 13/13 grupos e 80 casos obrigatórios, incluindo
fixture_pipeline 12/12. 116 módulos Python, 103 arquivos de testes,
16 migrações. SHA256 do JUnit:
1a805f02221d6723c2b9400f519cfee3e74f1aa960a42fba1465b1ca857aaac1.
pytest.log 6644ec6f7eb8de2579aa105231ac36bba96173634a524edea34205115760809b.
node.log 9b979e77497c15174c79450e7adc899b81fcf2092b7e8ab637ab78cd06078167.
Demais logs iguais aos reportados no full 298426d.
Relato de operador, não inspeção direta do JUnit/DB. Não benchmark
standalone, sandbox de rede, mídia real, aprovação produção ou gates.
Lab opt-in PASS separado no SHA 9bd1b6a; não somar contagens.

## A02.7.2 — fixture audiovisual compartilhada, incremento de engenharia

Base atemporal integral validada pelo assistente no pacote local
(PASS_INTEGRIDADE_E_RASTREABILIDADE; 204 IMP, 543 arestas, 23 CAP,
18 DEC, 28 CT, 7 gates). Espelho PASS reportado no full acima.
IMP-054/063/064/136/137/145/178 parciais, CAP-003/009/016/022/023,
DEC-017/018, G0/G1/G3/G4 relevantes. Sem alteração de DAG, matrizes,
contrato público rubric.v1, status de IMP, autorização ou aceite.

Commits:
- 11c1ebe: SharedAVSource, SharedAVBinding e método distinto
  synthetic-shared-av-v1; revalidação de escopos process audio/image
  no _check_rights, bundle exige fonte idêntica; VLM refatorado em
  helpers privados de imagem sem alterar wrapper original.
- efc4f59: asset_shared_av_fixture.py e modo shared_av do
  FixturePipeline, quatro jobs sobre a mesma raiz retida.
- 51a4061: rejeição de recipe/decoder adulterado, testes nativos,
  revogação pós-decode, testes do contrato e serialização legada.
- 790e408: métricas nativas do decoder, ASR e VLM e qualidade ASR
  devolvidas no step; não persistidas nem estimativa econômica.
- 6a03a3b: direitos individuais ausentes e assertions/prints métricos,
  strict inclui shared_av_contract (4), shared_av (7).

Dois casos fixos: inventory, reutiliza fala e WAV autorais do ASR
inventory, PNG sales do OCR, primeira imagem uniforme oposta e
transição em 1000ms; silence, WAV silencioso e PNG blank. Mux local
H.264 RGB lossless (libx264rgb qp0) + ALAC, MP4 faststart, 4fps,
960x540 RGB grayscale, mono 16kHz, ceil de amostras/4000, até
60 frames e 4MB contêiner. Requer os codecs locais; sem download.
A geração e regeneração exclusivamente autorais usam TemporaryDirectory,
sem entradas arbitrárias ou mídia de terceiros; limpeza normal não é
prova de secure erase. Mesmo runtime deve reproduzir bytes exatos;
mudança de binário/codec/TTS pode exigir nova fixture e novo pin, não
substituição silenciosa do plano. Host conserva fingerprint.

Cada job reconstitui a receita fixa, compara estrutura integral,
revalida job e vault. Decoder FFmpeg recebe somente bytes exatos
do vault via pipe; verifica contêiner, stream RGB inteiro, PCM,
frame gray selecionado (índice 4, 1000ms) e hashes das amostras
temporais. Saída esperada byte a byte, até ~1,13MB; Job Object
512MiB/10s CPU/30s wall/2 processos; sem alterar limites genéricos.
Amostras gray64 por point sampling, primeiros 8s no máximo, 4fps,
não PTS originais nem mesmo hash do frame 960x540. Frame selecionado
igual aos pixels do PNG pinado; adaptadores recebem o PNG canônico
verificado ou WAV remontado do PCM decodificado. ASR mantém WER<=0,5,
IoU>=0,60 e erro fronteira<=0,75s; OCR mantém palavras exatas;
VLM deve classificar o PNG sales (não idêntico ao antigo VLM sales)
como text_card, blank usa guard sem inferência. Não flexibilizar
se falhar. VLM benchmark anterior FAIL continua. Lease renovado
uma vez após decode, sem aumentar deadline da tentativa.

SharedAVSource contém hashes do contêiner, decoder, RGB, PCM,
frame/pixels, PNG, amostras 64x64, dimensões e tempo; SharedAVBinding
vincula configuração do decoder/adaptador e orçamento ao JobSpec.
Resultado tipado inclui binding somente nesse método, serializer
omite campo ausente para preservar bytes/hash e fingerprint legado.
Fusão não aceita misturar shared/legado ou manifestos divergentes;
revalida direitos e todos os resultados persistidos. Proveniência
prova correspondência estrutural e integridade no host confiável,
não execução independente, verdade semântica, PTS real ou gold.
Process video, process audio e process image exigidos na mesma raiz
durante todos os checks do método, também retain/process de derivados
e derive rubric_evidence. Sem direitos de export/display/publicação,
media_enabled=false, sem mídia externa, acesso Meta, schema DB,
migração, treinamento, CAP/gate novo ou rubrica canônica.

Métricas do decoder e jobs ASR/VLM (peak commit, CPU user/kernel,
wall), chamadas e qualidade ASR são devolvidas em memória e impressas
pelos testes. Não há métricas de OCR separado nem custo total de
geração/planejamento/hash ou benchmark comparativo; medir depois.
Decodificação repete por job para provar a mesma origem; não há cache
durável de pixels/PCM, nenhum derivado audiovisual claro persistido.
Não medir latência total apenas pelos tempos de subprocessos.

Assistente: experimento independente Linux com FFmpeg local
(libx264rgb + ALAC), frames RGB gerados e PCM sintético, dois muxes
idênticos e decode exato: 132796 bytes, 27 frames, 106001 samples,
SHA256 49aadb13a2970020fd8370298417563eb3b182d1ff10771015ca5ca4244c1d3e.
Outro teste local 3s/12 frames também lossless. Não é execução da
fixture do repositório, ambiente Windows, Tesseract, Whisper ou Qwen.
Smoke independente Pydantic 2.13.5 de serializer nested passou,
não teste do contrato integral. Sem execução pytest pelo assistente.

11 testes novos esperados: 4 contrato (bytes legados, binding,
amostras, fontes misturadas); 7 registry (nenhum/um escopo ausente,
2 pipelines nativos, recipe adulterado, revogação depois do decode).
Strict passa de 13/80 para 15 grupos/91 casos mínimos. Expectativa
de 1295 coletados no full, não resultado. Sem novo skip permitido
nos grupos. Lab continua opt-in separado.

### Operador — A02.7.2
Parar servidor/writers; reusar os quatro paths explícitos anteriores,
FFmpeg/espeak local, sem baixar modelos nem repetir benchmarks.
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
conda activate tapi-asr-recovery
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q --tb=short tests/test_asset_processor_results.py
& $py -m pytest -q --capture=tee-sys --tb=short tests/test_asset_rights_registry.py -k test_shared_av_
& $py -m pytest -q --tb=short tests/test_a00_baseline.py
& $py scripts/verify_zero_spend.py
```
Esperado: 4 novos contratos no arquivo de resultados; 7/7 shared
registry sem skips; 21 runner PASS. Registrar SHARED_AV_METRICS e
SHARED_AV_SOURCE (somente hashes/contagens). Se falhar, não trocar
codec, abaixar critério ou promover silenciosamente; preservar logs
e diagnosticar. Se PASS, full strict no HEAD limpo, mesmos paths
e report-name novo, grupos shared_av_contract 4/4 e shared_av 7/7.
Próximo incremento: reconciliar execução, robustez/ablação
compartilhada, orçamento e preflight de direitos operacionais.


## A02.7.2 — shared AV native PASS (18/11/2026)

Operador HEAD 20aea114c2cbe90422762e2ae6287ad8aa863d39,
árvore e7e8576b625f422c9a5ffbb6bae80f2121bebf7e.
Contratos 27/27 em 2s, shared AV 7/7 em 143,94s,
runner 21/21 em 1,20s, zero-spend PASS. Full strict
a02-shared-av-20261118-164816: 1295 coletados / 1294 PASS /
0 FAIL / 0 ERROR / 1 SKIP Lab opt-in; 15/15 grupos, 91 casos
obrigatórios; pytest 1016,429s, Node 7,913s, checkout inalterado.
Gate0 histórico, espelho, zero-spend e Node exit 0.
JUnit SHA256 96e3fe89784aea6f7a0a94f5707e1f9e1886ca240b8e7055431a9a2d6a116f89.
pytest.log 21f82485387349090725bdf3a4026cbe87c9c61bf9db593b89e4cc59c5e0bb01.
node.log d2aabaef884b33d387b0f7041cc185919b76a9bc766fb3f9f866b3f658137479.
117 módulos, 103 arquivos Python de testes, 5 Node, 16 migrações.
Relato de operador, não inspeção independente dos artefatos locais.
Lab opt-in PASS separado no SHA 9bd1b6a; não somar contagens.

Manifestos reportados (SHA256):
- inventory contêiner ec135d29470134176b8ee24349939dc60eb3865d54e82693fa3beb4ef81239c8,
  RGB 9e4cc10037a0793d8fc9e680c3c9768c5ea4ec84c0ce184208d2fa72ba01272e,
  PCM a466b1a2a12073c94175aa7202fc55d874b614a4b72ae03612323fd6c79f9a9b,
  frame a2089e243374b41af7e91847a031e6d80942bc4ba74707b57756231a6ba86641,
  27 frames / 106381 amostras PCM.
- silence contêiner 57e11385ecc617926a0e60fad7ec5564025c08a8f51fe5e57827fdbdbcd891d6,
  RGB d7856ae58457f17c637a57e807c4b05965fb92127809b9eaef9d1cc25ff12ad2,
  PCM 55873fecc61a79e87ca550c7072e38ccdd7ecb600ace286fe4717952a97c42b0,
  frame d64bb75f9897d781a54a1e4c4e9571a17a7c447d21a4d40cc16d603951997f87,
  12 frames / 48000 amostras PCM.
- FFmpeg comum 1a65d5b0b10d8d9a81d2824a3538046a40ed3607c906b335a166add87613f705.
Frames 960x540, 1000ms, 4fps, gray64 primeiros 8s, autorais.

Métricas (temporal, OCR, ASR, VLM, nessa ordem):
inventory decode wall 766/688/687/703ms (2844ms total);
peak commit 116662272/119091200/118943744/118579200 bytes.
ASR 21172ms, 5270159360 bytes, user/kernel 47093,75/13609,375ms,
WER 0,375, IoU 0,9317703013278856, fronteira 0,1971875s.
VLM 46953ms, 2515099648 bytes, user/kernel 164671,875/7875ms.
Chamadas 0/1/2/1 (ASR agrega VAD+Whisper).
silence decode wall 531/500/484/438ms; peak commit
69730304/70164480/66756608/69586944 bytes.
ASR guard 1156ms, 150601728 bytes; VLM guard 703ms, 24686592 bytes;
zero chamadas VAD, Whisper e Qwen. OCR executa uma chamada.
Não somar picos de jobs sequenciais como pico do host.
VLM maior componente de wall medido no positivo; não medir throughput
total com tempos parciais. OCR, geração, hashing, planejamento,
DB/fusão não medidos separadamente nesse relatório.
VLM quality benchmark anterior FAIL permanece, sem mídia real,
admissão, validação independente, gate global ou aprovação produção.

## A02.7.3 — expansão de casos e replay de ablação protegido

Commits:
- 094debe: seis receitas adicionais fixas, TTS restrito a frases
  autorais allowlisted, replay de 15 subconjuntos não vazios em
  evaluate_shared_av_ablation, dentro da mesma transação de direitos.
- 0139708: oito pipelines nativos e seis testes de política sobre
  observações surrogates persistidas; preserva chamada legada do ASR
  inventory. Grupo strict shared_av passa de 7 para 19.
- 2a45658: métricas OCR nativas e wall do step (inclui preflight,
  jobs, regeneração, hashes e processamento, não inclui __init__,
  geração inicial, última fusão ou avaliação de ablação).

Receitas novas: agreement (fala vendas + tela vendas), conflict
(custos fixos + tela vendas), complementary (CTA salvar + tela
vendas), audio_only (mesmo CTA + blank), screen_only (silêncio +
tela vendas), tone_negative (440 Hz + blank). Mantém inventory
e silence sem intenção de alterar bytes/IDs/configuração anteriores.
Usa mesmas imagens autorais e parâmetros/limites de ASR/OCR/VLM.
Não expõe texto TTS arbitrário, não baixa modelos, não cria
escopo externo. TTS local pode não reproduzir a semântica esperada,
WER/VAD ou VLM podem falhar; não alterar limiares para obter PASS.

Ablation: exige quatro resultados shared autenticados da mesma
raiz, mesma fonte e propósito; deriva rubric_evidence antes e
depois da avaliação, direitos atuais de todos os artefatos,
ordenação determinística; não usa resultados de outro ativo,
nem executa inferência adicional ou grava decisões. 15 arms de
ASR/VAD, OCR, temporal e VLM, sem caption (distinto dos 15 arms
do Lab anterior). Cada decisão mantém fingerprint da seleção,
suportes e vetos exclusivamente das modalidades selecionadas.
A política atual não usa temporal para semântica; teste verifica
equivalência semântica de arms com/sem temporal, sem desqualificar
medições temporais. Excluir VLM pode perder veto de conflito visual,
não confundir ablação retrospectiva com autorização, política
de roteamento, economia realizada ou segurança de omissão.

Oráculo autoral fixo dos quatro campos (tema, tipo_cta, tem_cta,
texto_na_tela): inventory (null,null,null,true), silence
(null,null,null,null), agreement (vendas,null,null,true),
conflict (null,null,null,true), complementary
(vendas,salvar,true,true), audio_only (null,salvar,true,null),
screen_only (vendas,null,null,true), tone_negative
(null,null,null,null). null = abstenção esperada, não ausência real.
Cada caso imprime SHARED_AV_ABLATION com 15 arms e contagens full
wrong_nonabstained/missed_candidates/exact_match. PASS dos testes
nativos exige integridade, qualidade individual existente e
invariantes de política/abstenção negativa; não implica
full_exact_match de cada caso. Erro semântico reportado não é
silenciosamente convertido em evidência de qualidade.
Sem gate semântico novo, sem seleção automática de melhor arm.

Seis desafios de política usam resultados tipados artificiais
persistidos em DB de teste, não mídia decodificada: concordância,
tema conflitante, complementaridade, CTA conflitante, negação,
pedido dividido entre modalidades. Testam decisões/vetos,
partição completa, rejeição de subset na entrada da ablação,
revogação assinada e ausência de novos eventos/tentativas.
Não são gold independente nem benchmark de ASR/OCR/VLM.
Nenhuma alteração de contrato público, migração, matrizes,
gates ou grants reais; IMP-054/063/064/136/137/145/178 parciais,
DEC-017/018 vigentes. R$0.

12 casos novos esperados (6 nativos + 6 surrogates).
Full esperado 1307 coletados, 15 grupos / 103 casos mínimos.
Não executados pelo assistente: inspeção de diff no GitHub,
ambiente Windows e modelos locais indisponíveis. PASS pinado
somente no 20aea11. Smoke restante das interfaces permanece
pendente e fora das mudanças deste incremento.

### Operador — validação A02.7.3
Parar writers/servidor. Reusar paths locais e modelos existentes.
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q --tb=short tests/test_asset_asr_fixture.py tests/test_asset_processor_results.py tests/test_a00_baseline.py
& $py -m pytest -q --tb=short tests/test_asset_rights_registry.py -k test_shared_av_ablation_policy_and_rights
& $py -m pytest -q --capture=tee-sys --tb=short tests/test_asset_rights_registry.py -k "test_shared_av_ and not test_shared_av_ablation_policy_and_rights"
& $py scripts/verify_zero_spend.py
```
Esperados 6/6 policy, 13/13 restantes shared sem skip; enviar
SHARED_AV_ABLATION e SHARED_AV_METRICS dos oito casos. Se PASS,
full strict mesmos quatro paths explícitos e report-name novo.
Analisar erros/misses mesmo se pytest PASS, comparar arms e
custos por caso antes de decidir roteamento/cache. A02.7.4:
reconciliar qualidade e custo, then benchmark de estratégia
seletiva e preflight operacional; não liberar mídia externa.


## A02.7.3 — execução focal parcial FAIL e recuperação ASR (18/11/2026)

Operador reportou comandos do incremento 9647102 (sem novo HEAD
impresso no trecho): ASR/contratos/runner 82/82 PASS em 3,99s,
policy surrogates 6/6 PASS em 10,36s, native/shared restante
11 PASS / 2 FAIL em 686,40s, 139 deselected, zero-spend PASS.
Sem full strict novo. Não inferir SHA testado do log sem confirmação.
Último full strict PASS continua 20aea11, 1294/1295 e 15/15 grupos.
SHA256 do arquivo de console recebido
5b9a998a39e4cb805bc0cef8917ae5084b3f3c68a0c75248e124c603d44eab33.
Não é JUnit nem relatório de execução independente.

Falhas complementary e audio_only: ASR_FIXTURE_WER_GATE, mesma
frase CTA autoral; VAD/decoder/OCR precedentes executados, não
completou ASR persistido, VLM ou ablation nesses dois casos.
WER exato e hipótese não presentes no console. Não tratar
como sucesso, não baixar threshold 0,50, nem trocar receita.
Seis de oito clipes completos, cinco full_exact_match, um
erro de tema (inventory, venda em vez de abstention).
Ablation parcial 90 arms, 360 células, não 480 completas.
Sobre 24 células full (6 candidatos esperados):
ASR sozinho 1 correto/1 errado/5 missed/18 exatas;
OCR 6 corretos/2 errados/0 missed/22 exatas;
ASR+OCR e full 6 corretos/1 errado/0 missed/23 exatas.
Sem ganho semântico do VLM/temporal nesses seis clipes, não
justifica retirada: VLM pode vetar conflito visual, temporal
tem medições; missingness dos dois CTA impede comparação final.
Inventory ASR WER .375 e sem âncora gestão; OCR vendas promove
tema. Agreement WER 0 e vendas em ambas; conflict WER .222222
e finanças vs vendas, abstention correta. Não alterar fusão
com regra específica do oráculo, nem assumir falta de conflito
quando a modalidade não recupera âncoras. A transcrição real
de inventory/CTA não foi fornecida, causa acústica/decodificação/
TTS ainda hipótese.

Commits de recuperação:
- 5350fd7: perfil ASR context_500ms, diagnóstico WER, módulo
  asset_asr_recovery.py e CLI scripts/a02_asr_recovery.py.
- aac8667: controle separado de transporte UTF-8 stdin para
  CTA, métricas, testes.
- c2da6a6: rejeições temporais diagnósticas distintas de falhas
  nativas; abortar em falha de kernel/cleanup, não continuar
  automaticamente, teste de não promoção.

Experimento separado de áudio autoral, sem DB/vault, sem inputs
de terceiros, sem download. Seis casos originais (inventory,
agreement, conflict, cta, silence, tone) em dois perfis, mais
CTA utf8_stdin em ambos (14 avaliações). Perfis comparados
somente no mesmo PCM argv original. Transportes têm hashes
separados e não contam como recuperação do input anterior.
UTF-8 é hipótese de codificação argv Windows, não causa provada.
Mantém a receita original por default, nenhuma troca de texto,
referência ou gate. Código pinado por configuração; novos
hashes de fonte/configuração são esperados e não reusam recibos
do commit anterior. VAD permanece OPTIONS original; candidato
decodifica até 500ms extra dos dois lados da região sem passar
região vizinha/limites PCM. Rejeitar timestamps fora de VAD
por mais de 250ms ou sem overlap; clip apenas a interseção.
Não usa referência ou prompt para inferência, mesma configuração
Whisper Medium CPU int8 e supervisor 6144MiB/240s CPU/90s wall.
Guarda silêncio e tom preservada. WER acima de 0,50 continua
lançando ASRFixtureQualityError (subclasse ValueError, código
inalterado); diagnóstico numérico e hash, não payload aprovado.
Rejeições de contexto retornam envelope experimental que não
passa result_from_output. Falha nativa/estrutural aborta a CLI.
Os resultados rejeitados não viram observação persistida.
A CLI imprime apenas métricas/hashes/âncoras permitidas e
presença das palavras autorais esperadas, não transcript bruto.
Cada perfil só passa gate experimental se todos os seis casos
originais satisfizerem qualidade e âncoras esperadas (inventory
gestão; agreement vendas; conflict finanças; cta salvar;
negativos sem candidatos). Sem seleção automática, sem
alteração do perfil baseline no pipeline, sem novo gate global.
Seis testes unitários novos esperados, não executados pelo
assistente. Novo código é candidato, não correção comprovada
das falhas de integração. A02.7.4 seletivo suspenso até
reconciliar qualidade; não repetir full antes da correção.
Sem alteração de schema DB, matrizes, gates, grants, mídia
externa, merge ou gasto; IMP-063/064/136/137 parciais.

### Operador — recuperação focal
Parar writers/servidor; usar o ambiente e modelo local anteriores.
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q --tb=short tests/test_asset_asr_fixture.py tests/test_asset_processor_results.py tests/test_a00_baseline.py
& $py scripts/verify_zero_spend.py
```
Esperado 88/88 (82+6), não resultado. Se PASS, executar somente
o experimento focal, sem novos modelos:
```powershell
if ([string]::IsNullOrWhiteSpace($env:TAPI_ASR_TEST_MODEL_DIR)) {
    throw "Reutilize o caminho local do Whisper Medium já pinado"
}
& $py scripts/a02_asr_recovery.py --model-dir "$env:TAPI_ASR_TEST_MODEL_DIR"
```
Enviar JSON integral (profiles/rows, hashes, métricas) e HEAD.
Se falha nativa/estrutural, preservar erro e parar; não liberar
lease ou baixar modelos. Se perfil candidato passa, revisar
resultados e comparar PCM antes de qualquer promoção; se
nenhum passa, investigar outro candidato sem reduzir critérios.
Depois de correção comprovada, repetir testes shared nativos,
ablação e full strict. Não executar full neste passo.


## A02.7.3 — recuperação ASR v1 FAIL, segunda rodada (18/11/2026)

Operador reportou 88/88 PASS em 4,56s, zero-spend PASS e
14 avaliações completas authored-asr-recovery.v1. Trecho não
imprime HEAD, portanto não inferir SHA local confirmado;
HEAD remoto na reconciliação 9412cd4. Console recebido SHA256
2d27e8fe31b9dab697cc482f1c6adaadbaa4086bd1c4bac1dc01943fc73259b7.
Sem full strict novo, último aprovado 20aea11.

Baseline argv: qualidade 5/6, semântica 4/6, gate FAIL.
Inventory WER .375, estoque ausente, IoU .9317703, fronteira
.1971875s, 20719ms; agreement WER 0, vendas presente,
24875ms; conflict WER .222222, custos/fixos presentes, 16671ms;
CTA WER 4/7=.5714286, hipótese 8 palavras, salve/conteúdo ausentes,
este presente, IoU .9312810, 16843ms. Negativos PASS sem ASR.
Context_500ms: qualidade/semântica 2/6, gate FAIL; todos os
cinco inputs com fala (incluindo UTF8) rejeitados por
ASR_RECOVERY_CONTEXT_TIMESTAMP. Não chegaram a WER, não
inferir efeito acústico negativo a partir da rejeição de alinhamento.
CTA utf8_stdin: WER 2/7=.2857143, hipótese 7 palavras, conteúdo
e este presentes, salve ausente, sem CTA, 15969ms. Novo PCM
7ea19e0442aeb03a7a5020a0a79f8e9fde097fce9c63c94717c9af3fbb0793cf
vs argv aba15de4d51a3c6f699b31be456dea7caab466369bbc89fbe8cd1ee4535b08b6.
Confirma efeito do transporte sobre áudio/resultado nesse host,
não prova causa única de codificação; controle não substitui input.
Nenhum perfil promovido, sem correção comprovada.

Commits v2:
- 820919d: dois perfis experimentais, beam10 (região VAD
  original e beam 10), word_context_500ms (beam 5, mesmo
  contexto de 500ms, alinhamento de palavras). Mantém v1
  acessível via --round v1; v2 default. Baseline original
  continua default da execução operacional/fixtures.
- daf82d3: fixa os sete hashes PCM reportados na v1; v2
  aborta se regeneração divergir. Sumário somente dos perfis
  executados, exige seis IDs distintos e pins correspondentes,
  não permite PASS vazio. Seis novos casos unitários.
O código novo ainda não foi executado pelo assistente; inspeção
de diff e logs, não benchmark local. 14 avaliações esperadas.
Beam10 mantém VAD, modelo, temperatura zero, sem prompt
ou hotwords; limites de supervisor preservados. Pode piorar
latência/memória ou qualidade; não aumentar limites para PASS.
Word-context usa timestamps estimados por palavra para avaliar
a mesma região VAD. Exige correspondência normalizada entre
todas as palavras e texto do segmento, nenhuma palavra lexical
sem overlap ou além da tolerância existente 250ms. Não descarta
palavras, não alarga VAD, não usa referência; reconstitui apenas
span do segmento pelos limites de palavras alinhadas, preserva
texto original. Rejeição experimental é distinta de observação
válida; falhas nativas/estruturais abortam. Não trata timestamps
do modelo como gold independente. Avaliação de contexto por
palavra é hipótese, não validação concluída.

R2 compara seis casos argv e CTA utf8 de controle, dois perfis
(14 avaliações). Os pins v1 são explícitos em asset_asr_recovery.py.
Mudança de código altera configuração/source hashes, não áudio
esperado. UTF8 mantém hash distinto. Qualidade WER<=.50, VAD
IoU>=.60 e fronteira<=.75s, negativos sem hallucination e
semântica exata dos seis casos argv permanecem. Não escolher
automaticamente perfil, não ajustar por caso/oráculo. Se ambos
falharem, manter falha e investigar candidatos locais adicionais
ou abstenção de tema quando áudio não tem evidência suficiente
como política experimental separada, sem mascarar WER.
Nenhum novo gate global, media real, grants, migração, DB,
merge, gastos ou alteração de matrizes. IMP-063/064/136/137
parciais. A02.7.4 seletivo ainda não elegível.

### Operador — rodada v2 focal
Parar writers/servidor, reusar modelos locais anteriores.
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q --tb=short tests/test_asset_asr_fixture.py tests/test_asset_processor_results.py tests/test_a00_baseline.py tests/test_multimodal_asr.py tests/test_multimodal_vad_asr.py
& $py scripts/verify_zero_spend.py
```
Se focal PASS sem novos skips, rodar exclusivamente:
```powershell
& $py scripts/a02_asr_recovery.py --model-dir "$env:TAPI_ASR_TEST_MODEL_DIR" --round v2
```
Enviar HEAD e JSON. Não repetir v1 nem full strict nesse passo.
Se falha de PCM, não atualizar pins automaticamente; investigar
ambiente. Se falha native/cleanup parar e preservar log.


## A02.7.3 — recuperação v2 interrompida, correção supervisor Windows (18/11/2026)

Operador: focal ASR/contratos/runner/ASR+VAD 123/123 PASS
em 9,71s, zero-spend PASS. CLI --round v2 interrompida em
asset_windows_job._run_fixture_output por DESCENDANTS_REMAIN
(após communicate e validação de saída). Sem JSON de rodada,
sem caso/perfil identificado, sem HEAD local impresso no
trecho. HEAD remoto na reconciliação d321680. Não inferir
resultado de WER ou semântica da v2, nem afirmar ausência
de processos remanescentes a partir do traceback. Última
regressão integral aprovada permanece 20aea11.

Diagnóstico de código: o supervisor consultava ActiveProcesses
enquanto mantinha o handle de Popen do root já encerrado.
A documentação Win32 de JOBOBJECT_BASIC_ACCOUNTING_INFORMATION
explica que o contador pode decrementar somente após a liberação
das referências ao processo encerrado. CPython Windows Popen
mantém _handle e o libera na finalização do objeto (Handle.Close).
Fontes públicas:
- https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information
- https://github.com/python/cpython/blob/main/Lib/subprocess.py
Hipótese consistente com o erro, não causa comprovada no host.
Não remover verificação nem presumir que era apenas race.

Commits:
- 42a1794: release explícito do handle do root encerrado antes
  de interpretar contabilidade; grace de até 1s somente com
  TotalProcesses==ActiveProcesses==1, dentro do deadline original,
  check de direitos/lease a cada polling. Nenhum PASS enquanto
  ActiveProcesses != 0. Histórico com mais de um processo e
  contagem ativa não zero continua rejeitado imediatamente.
  Cleanup mantém o Job Object aberto, termina árvore em falha,
  espera root e libera handle mesmo no caminho de erro, verifica
  árvore vazia, fecha job e revalida antes de devolver resultado.
  Não reabre PID, não altera flags, limites, orçamento ou
  tolerância ASR. Usa API privada CPython Handle.Close já no
  contexto de dependência Windows Popen._handle. Sem suporte
  garantido a outros runtimes. 4 novos testes: handle antes
  de accounting, grace/timeout/rights, rejeição de root sem
  exit comprovado, 24 probes nativos sequenciais root-only.
  Regressão strict kernel mínimo 8 (era 7). Testes antigos
  de descendente real, timeout, memória, CPU, host crash e
  exclusividade preservados.
- f47a390: hash de asset_windows_job.py passa a compor runtime
  ASR, evitando equivalência silenciosa de configuração após
  mudança de supervisor. Progresso sanitizado por caso/perfil/
  transporte/pin PCM e contador (stderr, stdout permanece JSON
  final), um novo teste de abortar sem iniciar o próximo arm
  se native/cleanup falhar. Não salvar resultados parciais
  como aprovação, não auto-retry, não alterar os sete pins PCM.

5 testes novos esperados (4 portáveis, 1 nativo). Não executados
pelo assistente; inspeção de diff e fonte pública, sem Windows
ou modelos disponíveis. Não repetir full até resolver recuperação.
Métricas de subprocesso anteriores não incluem a espera de
contabilidade pós-exit. Nenhuma alteração de schema, grants,
modelo, TTS, critérios WER/VAD, DAG, gates, mídia real ou merge.
IMP-063/064/136/137 parciais. R$0, DEC-018 preservada.

### Operador — validação antes de repetir v2
Parar servidor/writers e não executar outros probes em paralelo.
Não matar processos por nome/PID; se SESSION_JOB_BUSY ou erro
de cleanup persistir, preservar logs e investigar antes de retry.

```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q --tb=short tests/test_asset_windows_job.py
& $py -m pytest -q --tb=short tests/test_asset_asr_fixture.py tests/test_asset_processor_results.py tests/test_a00_baseline.py tests/test_multimodal_asr.py tests/test_multimodal_vad_asr.py
& $py scripts/verify_zero_spend.py
```
Esperar kernel 8/8 nativos, arquivo Windows sem skip, focal
ASR 124/124 e zero-spend/espelho PASS. Contagens são expectativas.
Se tudo PASS, repetir v2 com mesmos modelos e PCM:
```powershell
& $py scripts/a02_asr_recovery.py --model-dir "$env:TAPI_ASR_TEST_MODEL_DIR" --round v2
```
Enviar HEAD, JSON final e se falhar a última linha
ASR_RECOVERY_PROGRESS + traceback. Nenhum perfil selecionado
até reconciliar evidência. Não repetir v1 nem full neste passo.


## A02.7.3 — supervisor validado, encerramento de tuning Medium e cobertura (18/11/2026)

Operador reportou 29/29 supervisor PASS em 6,85s, 124/124
focal ASR em 5,31s, zero-spend PASS, 14/14 avaliações v2
completas sem falha nativa. Sete pins PCM iguais aos v1.
Console recebido SHA256
fd32a3ded2bda68a7b1a5cb13ea786ea178b1ddbb3ab73833f96c70dc13b1fd9.
Sem HEAD local impresso; HEAD remoto na reconciliação
169706a. Full strict ainda não repetido; último 20aea11.
Não extrapolar uma rodada concluída como garantia de
ausência futura de falhas de encerramento.

Beam10: quality 5/6, semântica 4/6, gate FAIL. Hashes
das hipóteses coincidem com v1 baseline nos sete inputs,
inclusive silêncio, tom e CTA UTF8. Inventory WER .375,
estoque ausente, 17063ms. Agreement WER 0, 17328ms.
Conflict .222222, 17516ms. CTA argv .5714286, salve e
conteúdo ausentes, 17625ms. UTF8 .2857143, conteúdo
presente, salve ausente, 16468ms. Nenhum ganho semântico.
Word_context_500ms: quality 3/6, semântica 3/6, gate
FAIL. Inventory, agreement, CTA argv e UTF8 rejeitados
por ASR_RECOVERY_WORD_TIMESTAMP; conflict passa .222222,
hash de hipótese diferente, semântica igual ao baseline,
17782ms. Negativos ambos passam sem ASR. Não inferir
WER dos rejeitados por timestamp.

Decisão IMP-129: encerrar exploração beam/contexto
no Medium nestes fixtures; baixo ganho marginal. Não
aumentar tolerância, trocar frases, corrigir transcript
por oracle ou baixar WER. Manter baseline atual.
Comparar Small já pinado se disponível localmente;
não baixar automaticamente. Priorizar também cobertura
e abstenção explícita, separadamente da recuperação.
Sem nova aprovação, release, gates ou operações externas.

Commits:
- c60f6cd: round v3 small_baseline, 7 avaliações, mesmos
  pins PCM v1, mesmo VAD, beam5, CPU int8, 4 threads e
  orçamento supervisor existente. Usa verify_checkpoint
  small existente (Systran/faster-whisper-small, revisão
  536b0662742c02347bc0e980a01041f333bce120, peso SHA256
  3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671).
  Somente diretório local explícito --small-model-dir; sem
  download, fallback ou promoção. Não reduzir orçamento
  declarado com base no tamanho de checkpoint. Medium
  permanece default do adaptador, v1/v2 preservados.
- cd28b6e: evaluate_shared_av_coverage_guard em transação
  de direitos existente, somente shared AV autenticado,
  sem nova inferência/persistência. Compara baseline e
  versão guardada, sem promoção. Evidência ausente ou
  abstenção insuficiente em ASR/OCR/VLM suprime candidatos
  de tema/CTA; OCR/VLM ausente/insuficiente suprime texto.
  Se ASR e OCR observados, tema exige suporte de ambos.
  Controle no_observable_signal é distinto de insuficiente,
  utilizável somente nesta política sintética, não prova de
  ausência em todo vídeo real. CTA complementar preservado
  quando modalidades utilizáveis; não garante ausência
  de conflito não reconhecido. Abstenção conserva suportes
  e vetos, sem inventar valor. Revalida direitos/lineage.
  3 casos surrogates adicionais, 9 policy no total, e
  2 testes ASR de seleção/pin explícitos. Strict shared_av
  mínimo 22 (era 19), kernel 8 preservado. Nenhuma mudança
  na fusão default, schema DB ou contrato público.
- bb9a91c: coverage_details com estado/razão, comparação
  SHARED_AV_COVERAGE_GUARD nos clipes completos, mede
  wrong_nonabstained, missed_candidates, exact_match e
  suppressed_fields contra oracle autoral já congelado.
  Não executa novos modelos, não muda critérios dos testes
  nativos nem transforma falha ASR em candidato.
- f83c38b: report v3 inclui identidade/hashes do checkpoint.

Tradeoff esperado (ainda não medido na versão nova):
suprimir venda em inventory com áudio observado mas
sem tema reconhecido, porém também suprimir tema vendas
em complementary (OCR vendas + fala CTA). Não selecionar
guard automaticamente; precisa comparação risco-cobertura.
Partial replay não libera mídia nem faz continuar um lease
falho. Direitos atuais ainda necessários para todos os
artefatos selecionados e derive rubric_evidence. Sem gold
independente, sem rubrica canônica. A02.7.3 quality ainda
FAIL, A02.7.4 roteamento não aprovado. VLM quality FAIL
preservado. IMP-063/064/136/137/129 incrementais, sem
alteração de matrizes (Base v6.1), schema, grants ou merge.

5 testes novos esperados neste incremento; não executados
pelo assistente (inspeção de diff, sem checkout Windows).
Small local disponível não confirmado. Se indisponível,
registrar not_available e continuar avaliação determinística
da cobertura; não inventar resultado nem bloquear indefinidamente
o desenvolvimento de infraestrutura independente do ASR.
Não repetir full antes de reconciliar os casos nativos.

### Operador — validação focal e comparação Small
Parar writers/servidor, reutilizar ambiente anterior.
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q --tb=short tests/test_asset_asr_fixture.py tests/test_asset_processor_results.py tests/test_a00_baseline.py tests/test_multimodal_asr.py tests/test_multimodal_vad_asr.py
& $py -m pytest -q --tb=short tests/test_asset_rights_registry.py -k test_shared_av_ablation_policy_and_rights
& $py scripts/verify_zero_spend.py
```
Esperados 126 focal e 9 policy, sem skip. Se PASS, verificar
diretório Small já existente (ajustar se salvo em outro path):
```powershell
$small = "C:\Models\tapi\faster-whisper-small"
if (Test-Path -LiteralPath $small -PathType Container) {
    & $py scripts/a02_asr_recovery.py --model-dir "$env:TAPI_ASR_TEST_MODEL_DIR" --small-model-dir "$small" --round v3
} else {
    Write-Output "ASR_SMALL_NOT_AVAILABLE"
}
```
Enviar HEAD, focal/policy e JSON (ou indisponibilidade).
O hash do peso é validado antes da inferência; erro de
pin não é motivo para atualizar hash ou baixar modelo
automaticamente. Se Small também falhar, encerrar esta
comparação local e desenvolver percurso protegido de
evidência parcial/abstenção com qualidade explicitamente
reprovada, preservando o benchmark original e o strict.
Não repetir v1/v2 ou full neste passo.


## A02.7.3 — Small FAIL e percurso experimental de evidência parcial (18/11/2026)

Operador: focal 126/126 em 10,38s, policy 9/9 em 21,90s,
zero-spend PASS, v3 7/7 avaliações concluídas, todos PCM iguais
à v1. Small weights SHA256 3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671,
revisão 536b0662742c02347bc0e980a01041f333bce120. Supporting files
hash local, não verificados independentemente. Quality 4/6,
semantic 3/6, gate FAIL. WER inventory .375 (estoque ausente),
agreement 0, conflict .555556, CTA argv .571429, UTF8 1.142857
(salve presente mas qualidade rejeitada). Negativos sem ASR.
Wall quatro speech argv 6906/6531/6812/6469ms; peak commit
~2,55 GiB. Comparação descritiva com beam10 Medium ~17,38s vs
Small ~6,68s de média, não efeito isolado de tamanho de modelo.
HEAD local não impresso. Último full strict aprovado 20aea11.
35 avaliações de recuperação em 3 rodadas; nenhum perfil aprovado.
Encerrar tuning desses checkpoints nessas frases. Medium baseline
mantido, sem promoção. A02.7.3 quality FAIL e VLM quality FAIL.

Conector GitHub restabelecido após timeout; HEAD remoto confirmado
7a6a02c. Implementação revisada diretamente sobre arquivos remotos,
não exige que operador aplique patch offline. Commit c0592a2:
modo shared_av_partial explícito no FixturePipeline. Configuração
parcial distinta em todos jobs; strict omite campo novo para
preservar serialização/fingerprint antigos. Bundle rejeita mistura
de políticas. Apenas ASRFixtureQualityError com WER > .50 e
validações estruturais/VAD anteriores pode gerar abstenção
fixture_quality_rejected com métricas numéricas tipadas, sem
transcrição, palavras ou hash da hipótese. WER consistente com
contagens de palavras e distância inteira de edição. Native,
cleanup, VAD, negative insertion, rights, estrutura e binding
continuam falhas. Não usar saída parcial em evaluate_candidate_bundle
ou evaluate_shared_av_ablation; somente coverage guard protegido.
O guard mantém diagnóstico baseline para comparação, sem promoção.
OCR/VLM podem sustentar texto observado quando autorizados.
Final parcial declara asr_fixture_quality_gate_passed=false,
semantic_quality_validated=false. Sem schema DB, matrizes,
mídia real, gasto ou merge. Não alterar critérios strict.

5 testes novos: 2 ASR unitários, 1 contrato, 2 nativos; grupos
strict adicionados (não retirados os dois casos WER reprovados).
Novo código revisado no GitHub, não executado pelo assistente
no Windows. Não executar full para alegar PASS parcial.

### Operador — validar incremento publicado
Parar writers/servidor; não aplicar patch local.
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q --tb=short tests/test_asset_asr_fixture.py tests/test_asset_processor_results.py tests/test_a00_baseline.py tests/test_multimodal_asr.py tests/test_multimodal_vad_asr.py
& $py -m pytest -q --tb=short tests/test_asset_rights_registry.py -k test_shared_av_ablation_policy_and_rights
& $py scripts/verify_zero_spend.py
```
Esperados 129 focal, 9 policy; se PASS:
```powershell
& $py -m pytest -q --capture=tee-sys --tb=short tests/test_asset_rights_registry.py -k test_partial_shared_av_native_pipeline
```
Esperados dois nativos sem skip, enviar HEAD e SHARED_AV_PARTIAL.
Nenhum PASS integral ou semântico pressuposto.


## A02.7.3 — validação focal PASS; nativos parciais bloqueados por capacidade (18/11/2026)

Operador: 129/129 focal PASS em 6,97s, 9/9 policy PASS
em 21,41s (148 deselected), zero-spend PASS.
Dois testes parciais nativos FAIL em 70,16s (155 deselected),
ambos SHARED_AV_WINDOWS_MODEL_HOST_HEADROOM_INSUFFICIENT,
em _run_model_fixture -> require_model_headroom, antes de
spawn ASR. Complementary: physical 2508 MiB, commit 8223 MiB.
Audio_only: physical 2696 MiB, commit 8378 MiB.
Exigidos 4096 MiB physical e 7168 MiB commit (6144 + 1024).
Commit disponível atende, physical não. Não há saída ASR
nem SHARED_AV_PARTIAL nesta execução; não inferir que modo
parcial falhou semanticamente ou que WER foi reproduzido.
Jobs temporais/OCR precedem o bloqueio; não inferir recibos
finais completos. Falha ambiental fail-closed correta.
HEAD local não impresso; remoto confirmado b85e105.
Último full strict aprovado 20aea11, qualidade ASR ainda FAIL.

Decisão: nenhuma alteração de código, orçamento, VAD, modelo,
WER, tolerância ou proteção de headroom. Sem conversão de
insuficiência de recursos em quality rejection. Não repetir
focal já aprovado após mudança apenas documental. Fechar
aplicações não necessárias, salvar trabalho, parar servidores/
writers do projeto de forma normal; se necessário reiniciar
Windows, reativar ambiente e restaurar opt-ins locais anteriores.
Não matar processos por PID/nome, não limpar banco/vault,
não aumentar pagefile para contornar physical. Preflight
usa a mesma função do supervisor, snapshot sem reserva.
Só repetir nativos após PASS; se bloqueio voltar, registrar
valores e parar. Fixtures pytest usam armazenamento temporário;
não reconciliar leases do banco operacional por este log.

```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py -c "from tapi_gate0.asset_windows_job import require_model_headroom, ModelFixtureLimits; print(require_model_headroom(ModelFixtureLimits()))"
if ($LASTEXITCODE -ne 0) { throw "Headroom ASR insuficiente; nao iniciar testes nativos" }
& $py -m pytest -q --capture=tee-sys --tb=short tests/test_asset_rights_registry.py -k test_partial_shared_av_native_pipeline
```

Enviar HEAD, preflight e SHARED_AV_PARTIAL/traceback.
Nenhum PASS nativo novo, perfil promovido, migração, gasto,
merge, operação externa ou liberação de gate.


## A02.7.4 — evidência parcial nativa PASS; replay de roteamento (18/11/2026)

Operador HEAD 556cd1c5b34560c179e3d28d51bbc5dcb5a960ec
igual remoto, diff desde b85e105 apenas docs/74. Espelho PASS
32 blobs, 13 matrizes, 204 IMP, 543 dependências, DAG acíclico
sink IMP-131. Focal 129/129 PASS 3,11s; policy 9/9 PASS
12,16s; zero-spend PASS. Nativos parciais 2/2 PASS 111,10s,
155 deselected. Ambos candidate_partial, WER 4/7=.571429,
8 hyp/7 ref, IoU .9312810088202866, boundary .1793125s,
VAD/ASR 1/1. Complementary OCR observado, texto_na_tela
true, 3 semânticos abstidos. Audio_only OCR no_observable_signal,
4 abstidos. Temporal e VLM observados nos dois. Sem promoção
semântica, sem recuperar CTA, sem mudar gate de WER.
Preflight headroom não impresso, porém execução nativa completa.
Último full strict válido 20aea11, dois casos strict WER FAIL
permanecem. A02.7.3 infraestrutura parcial PASS, qualidade FAIL.

Incremento IMP-063/064/129:
- 342a7b3: evaluate_shared_av_routing_replay, 15 subconjuntos
  guardados do mesmo bundle completo autenticado, strict ou
  parcial, mesma transação de direitos pré/pós, sem inferência
  nova. Preserva reprovações do conjunto completo e distingue
  ausência de modalidade em cada braço. Seleção shadow fixa:
  só propor omitir VLM se ASR e OCR ambos no_observable_signal,
  nunca se ASR quality rejected/insuficiente. Não usar VLM
  para decidir se VLM seria chamado. Não executar roteamento.
- 8a874d6: coorte 8 clipes pelo mesmo modo parcial, 32
  células semânticas e 16 outros campos não avaliados por
  clipe. Dois casos WER rejeitados preservados; outros seis
  devem completar sem rejeição. Todos 4 processadores de
  todos os clipes realmente executados uma vez por caso;
  15 braços reaproveitam resultados. Inclui baseline
  diagnóstico (não permitido como decisão parcial) e guard
  completo. Testa igualdade do braço completo ao resultado
  pipeline, ordem invariável, seleção incompleta negada,
  suportes confinados, revogação e idempotência. Sem mudar
  testes strict originais. Strict grupo partial native 2->8,
  novo grupo summary 4. Total 10 casos adicionais.
- Relatório SHARED_AV_ROUTING por caso, agregado offline
  scripts/a02_shared_av_routing.py. Oracle autoral fixo
  igual anterior, exige oito casos únicos e 15 braços.
  Conta correct/wrong_nonabstained, missed_candidates,
  exact_cases, coverage, selective_error_rate (null se
  zero candidatos), custos (soma step wall observado,
  chamadas, max pico commit Job). Custos contrafactuais
  não medidos; não são economia realizada, nem custo
  total de host ou percentil. Exclui replay final. Não
  otimizar por acerto de abstenções apenas. Sem escolha
  automática. CLI aceita log UTF8/UTF16 BOM de PowerShell;
  entrada diagnóstica local, não autorização autenticada.

Testes novos não executados pelo assistente em Windows.
Sem downloads, alterações de gates/matrizes, schema DB,
grants, mídia real, gasto, merge ou release.
Próximo: comparar risco-cobertura-custo após 8/8; se shadow
sem perdas nesta coorte, ainda não aprovar omissão real sem
validação de controles difíceis independentes de seleção.
Não inferir qualidade VLM aprovada.

### Operador — avaliação de roteamento shadow

```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q --tb=short tests/test_asset_shared_av_routing.py tests/test_a00_baseline.py
& $py -m pytest -q --tb=short tests/test_asset_rights_registry.py -k test_shared_av_ablation_policy_and_rights
& $py scripts/verify_zero_spend.py
```
Esperados summary 4/4 e policy 9/9; demais runner sem
falha. Se PASS, preflight e execução serial (sem outros
workers, parar writers/servidores normalmente):

```powershell
& $py -c "from tapi_gate0.asset_windows_job import require_model_headroom, ModelFixtureLimits; print(require_model_headroom(ModelFixtureLimits()))"
if ($LASTEXITCODE -ne 0) { throw "Headroom ASR insuficiente" }
$log = Join-Path $env:TEMP ("stone-routing-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt")
& $py -m pytest -q --capture=tee-sys --tb=short tests/test_asset_rights_registry.py -k test_partial_shared_av_native_pipeline | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) { throw "Coorte incompleta; nao agregar" }
& $py scripts/a02_shared_av_routing.py --log "$log"
```
Esperados 8/8 sem skip, 8 linhas SHARED_AV_ROUTING,
JSON agregado 15 braços; enviar HEAD, resultado testes
e resumo. Sem full neste passo.


## A02.7.4 — coorte shadow PASS e decisão de não promover (18/11/2026)

Operador: 25/25 focal (0,91s), 9/9 policy (14,97s),
zero-spend PASS; preflight physical 5379497984 bytes,
commit 11493392384 bytes, total physical 16597598208.
8/8 nativos PASS (399,44s), 155 deselected, 8 linhas
SHARED_AV_ROUTING, agregado 15 braços, 120 replays.
Console 33406 bytes SHA256
03c2417cc6271d039c5d17e93c652a121cf31ebf98bdb9ef3da5c4a99d6da41f.
HEAD local não impresso neste log; remoto confirmado 45decc3.
Sem nova validação documental neste console. WER rejected
complementary/audio_only 4/7, IoU .931281, boundary .1793125,
sem transcrição admitida. 6 outros complete_guarded.
32 células, 12 positivos esperados. Baseline diagnóstico:
8 corretos, 1 errado (inventory), 4 perdidos, cobertura
9/32, selective error 1/9, exatos 5/8. Guard completo:
7 corretos, 0 errados, 5 perdidos, cobertura 7/32,
selective error 0/7, exatos 6/8. Suprime erro inventory
mas também tema correto complementary. Não generalizar
zero erro ou promover policy com esta amostra autoral.

Custo soma de passos: 352937.913 ms; VLM 238289.086,
ASR/VAD 91131.026, OCR 13032.681, temporal 10485.120.
24 chamadas (11 ASR/VAD, 8 OCR, 5 VLM; métricas do
adaptador, não somente chamadas ao Whisper). Peak Job
5270228992 bytes. Guard OCR+VLM: 5 corretos, 7 perdidos,
251321.767ms, 13 chamadas. ASR+OCR+VLM: 7 corretos,
5 perdidos, 342452.793ms, 24 chamadas. Temporal não
acrescenta aos 4 campos semânticos, mas suas medições
permanecem necessárias ao escopo IMP-136 e rubrica.
Zero cobertura em vários braços é consequência do
guard, não prova de incapacidade do modelo isolado.

Shadow mantém valores completos nos oito casos:
omite apenas VLM em silence/tone_negative, 343734.238ms,
estimativa 9203.675ms (2,61%), zero chamadas economizadas
porque guard de imagem vazia já evitou inferência.
Decisão IMP-129: não promover roteador/guard a default
nem executar omissão; ganho contrafactual pequeno,
sem controles visuais difíceis e gold independente.
A02.7.4 experimento concluído, roteamento operacional
não aprovado. A02.7.3 qualidade ASR FAIL e VLM quality FAIL
preservados. Último full strict aprovado 20aea11.
Não gastar outra rodada nas mesmas fixtures agora.

## A02.8/9 — diagnóstico de prontidão operacional somente leitura

7fb0dc3: asset_operational_readiness.inspect e CLI
scripts/a02_operational_readiness.py. Usa SQLite existente,
mode=ro + query_only, transação de leitura única, revisão
0016 obrigatória, tenant existente, integrity/foreign keys.
Não abre vault, descriptografa payloads, lê chaves, fornece
trust anchor, concede grants, chama modelo, rede, claim,
reconcilia lease ou altera banco. Contagens agregadas
por tenant: 7 tabelas A02, linhagem por estado, jobs por
estado, lease expirado, pendência, histórico, tentativas
por dia UTC e bytes de envelope; globais apenas limites
de segurança/contagens agregadas. Não expõe IDs, conteúdo,
credenciais ou paths. Snapshot pode ficar obsoleto, não
constitui lock nem atestado de autorização; SQLite pode
usar infraestrutura de leitura WAL/SHM. Bloqueadores
explícitos mesmo se grants existirem: trust independente,
permissão exata por ativo, chaves e adaptador de mídia
real não avaliados/ativados. Não é PEP. A02.8 real
continua condicionado às credenciais/licenças/grants
legítimos e execução autorizada, não repetir DEC-018.
Cinco testes em DB descartável (sem execução pelo
assistente): revisão/tenant, ausência de arquivo, URL
remota, isolamento tenant, integridade do arquivo,
agregação de lease expirado sem reconciliação, CLI HEAD.
Não alterar schema, matrizes, grants ou gates.
Não é necessário rerodar coorte 8 nem full para este
diagnóstico; preservar última evidência full.

### Operador — prontidão local
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q --tb=short tests/test_asset_operational_readiness.py
& $py scripts/verify_zero_spend.py
```
Se PASS, parar writers normalmente para snapshot de
manutenção (não é necessário backup novo, migração ou
restauração). Reutilizar TAPI_DATABASE_URL e TAPI_TENANT_ID
configurados para banco local 0016, nunca imprimir valores:
```powershell
$head = git rev-parse HEAD
& $py scripts/a02_operational_readiness.py --expected-head "$head"
```
Enviar JSON agregado; status esperado A02_READINESS_INSPECTED_MEDIA_BLOCKED,
não PASS de autorização. Ausência de grants não é falha
da infraestrutura nem pedido de nova aprovação; não
fabricar chaves/autoridades nem executar mídia real.


### A02.8 — correção de inicialização do CLI

Operador: 5/5 readiness PASS (3,59s), zero-spend PASS.
Execução direta do CLI falhou no import scripts.a00_baseline
(ModuleNotFoundError: scripts), antes da inspeção do banco.
HEAD local obtido em variável mas não impresso; remoto
confirmado d563a36. Nenhum diagnóstico operacional emitido.
Causa: execução por caminho inclui scripts/ e não
necessariamente a raiz; pytest importa pela raiz.
Corrigido import condicional por contexto __package__,
sem modificar sys.path, controles de checkout/DB intactos.
Dois testes de subprocesso real (direto fora da raiz,
módulo na raiz), sem PYTHONPATH/PYTHONHOME ou TAPI_*,
HEAD inválido deve chegar ao guard antes de acesso DB.
Esperados 7/7 readiness; testes novos ainda não executados
pelo assistente. Usar preferencialmente:
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py -m pytest -q --tb=short tests/test_asset_operational_readiness.py
& $py scripts/verify_zero_spend.py
$head = git rev-parse HEAD
& $py -m scripts.a02_operational_readiness --expected-head "$head"
```
Sem migração, mídia, grants, alteração de gates ou merge.


## A02.8/9 — diagnóstico operacional concluído; A03 em andamento

Operador: JSON A02_READINESS_INSPECTED_MEDIA_BLOCKED,
2026-11-19T02:39:45.551590+00:00, HEAD local
d563a36c90bc4e2cd6b872d59d038b7d72379d9e, anterior ao fix
6c8288b (modo módulo funcionou). 5/5 readiness anteriores
PASS, dois testes CLI novos ainda não reportados. Banco
operacional local-research, revisão 0016, integrity/FK ok,
sete tabelas A02 vazias, zero leases/jobs/tentativas/bytes,
ingestão inativa. Nenhum grant por ativo, nenhuma autoridade
ou referência retida. Trust independente/permissões exatas,
chaves e adapter real não avaliados/habilitados. Sem mutação,
chaves carregadas, chamadas externas ou liberação de gates.
Ausência de autorização operacional não é nova exigência
institucional. A02 infraestrutura/diagnóstico concluídos
na extensão demonstrada; execução de mídia real continua
bloqueada. Qualidade ASR/VLM FAIL, full strict anterior
20aea11, sem promoção de política.

A03: seguir Plano Único IMP-048/049/050/051/052/164-170,
sem abrir backlog paralelo. A aquisição oficial metadata-only
já tem caminhos supervisionados (identidade, reconciliação,
grants técnicos, histórico e scheduler). Não confundir
ingestion_source_grants com asset_rights_grants. Última
evidência 17/11: 1065 únicos/21 perfis, 859 primários,
858 legendas, zero admissão científica. Referência bruta
mínima 2000/30: gap histórico 935/9, não gap científico.
A aquisição pode avançar sem mídia se guardas e credenciais
existentes permitirem. Não executar rede automaticamente.

096b59c: snapshot A03 read-only mode=ro/query_only, revisão
0016, integrity/FK, uma transação, contagens metadata_only
Instagram distintas por item/perfil, registro de perfis,
grants técnicos ativos e estados de frontier apenas
agregados. Limite conservador igual ao planner existente:
4 unidades por run + identity reservations no dia UTC,
80/dia, 10 identidades/dia; não quota Meta. Estimativa
otimista de runs max(ceil(gap bruto/40), gap perfis),
exclui identidades, perdas, formatos, idade, validade
e audiência. Não promessa de atingir a meta. Nenhum
ID/cursor/credencial exposto, sem validar manifesto/viewer/
cursor ou autorização, sem inferência/admissão. 3 novos
testes em DB descartável, não executados pelo assistente.

### Operador — primeiro diagnóstico A03
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py -m pytest -q --tb=short tests/test_asset_operational_readiness.py tests/test_discovery_expansion_capacity.py
& $py scripts/verify_zero_spend.py
$env:TAPI_TENANT_ID = "local-research"
if ([string]::IsNullOrWhiteSpace($env:TAPI_DATABASE_URL)) { throw "Restaurar URL operacional existente" }
$head = (git rev-parse HEAD).Trim()
& $py -m scripts.a03_expansion_capacity --expected-head "$head"
```
Esperados 10/10 tests e A03_CAPACITY_INSPECTED_PLAN_ONLY.
Não executar novo bootstrap, migration, restore ou mídia.
Enviar JSON agregado. Depois usar manifesto privado V10
existente (fingerprint faae42aa652a5b4b49c025d7522ac2e2f029c09bdc1434923c11df9d0ebdb1bb)
e viewer IG existente, sem divulgar ID/token, para planner
de identidade e histórico já implementados. Não usar
78/80 histórico como saldo de hoje, não executar coleta
sem preflight atual. Sem merge, alteração de matrizes,
novo grant, gasto ou autorização.


### A02.8/9 — confirmação final do CLI direto e snapshot operacional

Operador HEAD bdc20452728572f808beb9f27319cc7d955392f8,
igual ao remoto confirmado. Diff desde d563a36: três
commits, fix CLI, diagnóstico A03 e documentação.
Readiness 7/7 PASS em 4,68s, zero-spend PASS. CLI direto
scripts/a02_operational_readiness.py executado com
--expected-head, JSON A02_READINESS_INSPECTED_MEDIA_BLOCKED
em 2026-11-19T02:43:50.437192+00:00.
Revisão 0016, integrity/foreign_key ok; todas sete tabelas
A02 do tenant vazias. Zero jobs (todos estados), leases
ativos globais/expirados tenant, pendência, histórico,
tentativas UTC e bytes criptografados globais/tenant.
Ingestão inativa. Limites: concorrência global 1,
pendência tenant 100, histórico tenant/global 20000/50000,
tentativas dia UTC tenant/global 50/100, envelope tenant/
global 100000000/500000000 bytes. Nenhuma autoridade,
grant por ativo ou referência retida ativa. Bloqueadores
de trust independente/permissão exata, chaves e adapter
real preservados. authorization_evaluated=false,
keys_loaded=false, media_enabled=false, database_mutated=false,
grants_created=0, jobs_claimed=0, external_calls=0,
global_gates_released=false. Não confundir as sete tabelas
A02 vazias com corpus/ingestion_source_grants vazios.
Nenhuma migração ou provisionamento necessário neste
passo. A02.8/9 diagnóstico local confirmado, execução
operacional real ainda bloqueada; ASR/VLM qualidade FAIL,
último full strict aprovado 20aea11, não declarar gate PASS.
Espelho não reapresentado neste console.

### A03 — próximo passo efetivo

O incremento 096b59c já contém snapshot read-only de
capacidade, não criar planejador paralelo. Os três testes
A03 e execução contra banco operacional ainda não foram
reportados. Primeiro executar somente o teste novo e o
CLI, com tenant/URL existentes, sem token/rede:
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q --tb=short tests/test_discovery_expansion_capacity.py
if ($LASTEXITCODE -ne 0) { throw "Capacidade A03 nao validada" }
& $py scripts/verify_zero_spend.py
if ($LASTEXITCODE -ne 0) { throw "Zero spend nao validado" }
$head = (git rev-parse HEAD).Trim()
& $py -m scripts.a03_expansion_capacity --expected-head "$head"
```
Esperados 3/3 e A03_CAPACITY_INSPECTED_PLAN_ONLY. Enviar
JSON agregado. Não repetir readiness já aprovado em
código idêntico. Não assumir inventário ou quota atual
a partir do histórico 1065/21 ou 78/80. A seguir, se
capacidade permitir, usar o manifesto V10 existente e
hash canônico faae42aa652a5b4b49c025d7522ac2e2f029c09bdc1434923c11df9d0ebdb1bb,
viewer existente e planners identity/history já
implementados, inicialmente em modo plano, não execute.
Sem merge, mídia, novos grants, nova aprovação DEC-018,
gasto ou execução externa por este incremento.


## A03.1 — capacidade operacional confirmada e seleção da próxima onda

Operador: A03_CAPACITY_INSPECTED_PLAN_ONLY, HEAD
a33ce31cf03261923691518ebee073eb271adb8d igual remoto,
captured_at_utc 2026-11-19T02:46:16.382415+00:00.
1065 registros metadata_only/1065 IDs únicos/21 perfis
observados/21 perfis registrados/0 duplicatas entre fontes.
22 grants técnicos ativos/verificados, 21 com registros,
21 continuation_recorded, 1 no_checkpoint, zero scope_mismatch,
frontier_unconfirmed e unknown_state. O grant adicional
sem registros não é automaticamente elegível: conferir
correspondência ao manifesto, viewer, grant, prazo e
frontier pelo planner existente. Não criar novo grant
nem modificar manifesto a partir da contagem agregada.
Ingestão inativa, 0 reservas identity/metadata, saldo
local conservador 80/80, 10 slots identity e até 20 runs
sem identity. Não é quota Meta, manifesto/viewer/cursor
não verificados pelo snapshot. Zero chamadas, mutação,
credenciais carregadas, admissões, mídia, autorização.
Testes A03 3/3 e espelho não reapresentados neste log;
não afirmar PASS não reportado. Zero-spend anterior PASS
em bdc2045; readiness 7/7. Qualidade/gates inalterados.

Referência bruta: 935 posts e 9 perfis faltantes.
Limite otimista 24 runs/96 unidades de história antes
de identidade, exclusões, repetições e validade. Proposta
para 19/11 UTC (não autorização): até 10 identidades em
dois lotes de até 5; até 17 runs história (68 unidades)
em lotes de até 5 fontes; total 78/80, margem 2. Se
menos candidatos elegíveis, recalcular saldo; não repetir
falhas/ignorar guardas para preencher orçamento. Máximo
teórico 680 observações de história, não 680 novos posts;
gap bruto mínimo ainda 255 mesmo no caso otimista.
Diversidade de estratos e fontes antes de concentrar
volume; usar política coverage já existente. Replanejar
depois de cada lote e confirmar dia UTC; nenhum cron
ou loop automático. Priorizar identidade para ampliar
frame, reconciliar somente sucessos exatos, provisionar
grant técnico sob DEC-018 existente, depois históricos
de fontes novas e elegíveis. Não reusar artefatos
grounded/ranking antigos como se refletissem corpus novo.
Sem ajuste de matrizes ou promoção de qualidade.

### Operador — prévias offline da próxima onda (sem execute)

Usar ambiente e DB existentes, parar ingestão/writers
normalmente; não imprimir credenciais ou ID do viewer.
Não baixar modelos, não criar backup/restore/migration
para mera prévia. Verificar manifesto canônico V10
antes de passar aos planners existentes:

```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py -m pytest -q --tb=short tests/test_discovery_expansion_capacity.py
if ($LASTEXITCODE -ne 0) { throw "Teste A03 falhou" }
& $py scripts/verify_zero_spend.py
if ($LASTEXITCODE -ne 0) { throw "Zero spend falhou" }
$manifest = "artifacts/private/bd_manifest_a6_v10.json"
if (!(Test-Path -LiteralPath $manifest -PathType Leaf)) { throw "Manifesto V10 ausente" }
if ([string]::IsNullOrWhiteSpace($env:TAPI_META_IG_ID)) { throw "Restaurar viewer existente sem imprimir ID" }
& $py -c "from pathlib import Path; from tapi_gate0.discovery_batch import BatchManifest; m=BatchManifest.model_validate_json(Path(r'artifacts/private/bd_manifest_a6_v10.json').read_text(encoding='utf-8')); print(m.fingerprint()); assert m.fingerprint()=='faae42aa652a5b4b49c025d7522ac2e2f029c09bdc1434923c11df9d0ebdb1bb', 'Manifesto V10 divergente'"
if ($LASTEXITCODE -ne 0) { throw "Manifesto nao corresponde ao pin V10" }
& $py -m scripts.a6_identify_sources --manifest "$manifest" --plan-expansion --max-sources 5 --daily-request-budget 80
& $py -m scripts.a5_business_discovery_cycle --manifest "$manifest" --mode history --max-sources 5 --page-limit 10 --max-pages 4 --daily-request-budget 80 --priority-policy coverage
```

Enviar status, seleção e motivos de deferimento das
prévias (nomes públicos já selecionados pelo manifesto,
sem IDs, token, credenciais, cursors ou payloads privados).
Esperados EXPANSION_PLAN_READY ou EXPANSION_NO_NEW_CANDIDATES
e PLAN_ONLY_NO_EXTERNAL_READ, não assumir sucesso.
Guardas auth/recovery/expiração/escopo têm precedência;
se bloqueio, registrar código e parar. Nenhuma execução
oficial até confirmar prévias, token real vigente,
gasto zero e condições existentes. Sem nova aprovação
institucional. Este commit apenas documental, não
introduz planner redundante nem modifica código testado.


### A03.2 — prévias bloqueadas por ambiente incompleto

Operador: fingerprint V10 faae42aa652a5b4b49c025d7522ac2e2f029c09bdc1434923c11df9d0ebdb1bb confirmado.
Identidade retornou BD_IDENTITY_INVALID_INPUT_OR_DATABASE;
history A5_PREREQUISITES_MISSING, missing_environment_names
[TAPI_META_IG_ID], external_data_accessed=false. O CLI
identity acessava os.environ antes de abrir DB e capturava
KeyError genericamente; ausência do viewer explica ambos.
HEAD local não impresso; remoto anterior 16ffd69.
Nenhuma seleção, reserva ou rede realizada. Não inferir
falha de banco/manifesto, quota, token ou autorização.
Corrigido CLI identity para prévia/execute detectar nomes
ausentes/vazios antes de abrir manifesto, DB ou relatório.
Novo teste de CLI (ausente e whitespace) não executado
pelo assistente. Sem mudança de guardas, grants ou flags.

Restaurar somente o viewer já registrado no doc/57,
sem exibir seu valor nem consultar a Meta. Extrair a
atribuição documentada localmente; exigir exatamente um
ID distinto compatível com o formato esperado. Não
selecionar ID de fonte do manifesto como viewer.
Executar prévias offline novamente:
```powershell
git pull --ff-only
git status --short
git rev-parse HEAD
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py -m pytest -q --tb=short tests/test_discovery_identity_expansion.py tests/test_discovery_expansion_capacity.py
if ($LASTEXITCODE -ne 0) { throw "Testes A03 falharam" }
& $py scripts/verify_zero_spend.py
if ($LASTEXITCODE -ne 0) { throw "Zero spend falhou" }
$viewerIds = @(Select-String -LiteralPath "docs/57_CAP001_A6_EXPANSAO_IDENTIFICACAO_2026-11-12.md" -Pattern '^\s*\$env:TAPI_META_IG_ID\s*=\s*"([0-9]{5,32})"\s*$' | ForEach-Object { $_.Matches[0].Groups[1].Value } | Sort-Object -Unique)
if ($viewerIds.Count -ne 1) { throw "Viewer documentado ambiguo ou ausente" }
$env:TAPI_META_IG_ID = $viewerIds[0]
Remove-Variable viewerIds
$manifest = "artifacts/private/bd_manifest_a6_v10.json"
& $py -m scripts.a6_identify_sources --manifest "$manifest" --plan-expansion --max-sources 5 --daily-request-budget 80
& $py -m scripts.a5_business_discovery_cycle --manifest "$manifest" --mode history --max-sources 5 --page-limit 10 --max-pages 4 --daily-request-budget 80 --priority-policy coverage
```
Não habilitar flags externas, não executar chamadas,
não alterar token ou expiração. Enviar seleção/motivos
ou novo código de bloqueio, sem IDs ou credenciais.


### A03.2 — prévias V10 concluídas, credencial ainda não verificada

Operador log 13305 bytes SHA256 5ee0379011564ebd1f29dbbb8c4a49e68975b2c709ad6b7b495bb17deda025e7.
EXPANSION_PLAN_READY, PLAN_ONLY_NO_EXTERNAL_READ, UTC
19/11, manifesto V10 pin confirmado. HEAD local/testes
não impressos neste log; remoto 2f7b383 confirmado.
Identidade: abavnacional, abfoficial, agisaalimentos,
amarefashiongo, andraeltec. Cinco estratos distintos,
todos 0 aprovados/observados/posts, audience uncertain.
16 outros não tentados; 6 missing rationale/viewer e 2
prior attempt review (nuvemshop, aanadesales). Não repetir
deferidos. Nenhuma pending_identity_action. História:
seliganoton (105, fairness), menteempreendedora (3),
contaazul (20), ifoodparaparceiros (26),
empreendedorasdabelezagb (29); 183 posts vs 367 recency,
5 estratos em ambos, predicted_yield=null. 50 fontes,
21 aprovadas, 29 não aprovadas, 16 aprovadas deferidas
por limite. Grant extra fora das 21 aprovadas não usar.
Saldo 80/80 local, 5 identidades/20 páginas máximas
nas prévias. 1065/21, zero duplicatas/admissões/mutação.
Auth NOT_CHECKED, expiry UNKNOWN, provider_verified=false.
Não confundir prévia pronta com autenticação confirmada.

Próximo: executar somente primeiro lote de 5 identidades
após operador confirmar validade real do token existente
com ferramenta oficial da Meta e R$0, datas reais ISO
8601 com fuso (data de acesso somente se informada),
TAPI_META_REQUIRE_TOKEN_EXPIRY=1; não inventar prazo,
não usar expiração de grant. Manter secret local, nunca
colar token ou IDs em chat. Reexecutar plan-expansion
e confirmar mesmo dia UTC, mesmo manifesto pin, seleção,
saldo >=5, sem bloqueio. Validar teste focal A03 e zero
spend antes; writers/ingestão parados. Se token ausente
restaurar por input seguro local, não imprimir. Identidade
execute exige admin existente e flags específicas;
ativar só identidade/metadata/zero-billing temporariamente,
restaurar flags a 0 em finally. Relatório exclusivo privado
a6-identity-v11-<stamp>.json, stdout não compartilhar IDs.
Enviar apenas status/cycle_key/username/status/code e
contagem reserved_requests. Primeiro erro interrompe;
reservas do lote não reembolsadas, não repetir automaticamente.
Depois reconciliar apenas sucessos do ciclo exato, planejar
grant técnico existente DEC-018; não executar history
usando manifesto desatualizado. Nenhuma execução externa
pelo assistente, nenhuma autorização adicional, mídia,
merge ou gate liberado. Commit documental.


### A03.2 — ajuste do protocolo de credenciais por solicitação do operador

Decisão: retirar a consulta manual obrigatória ao Access
Token Debugger e o preenchimento obrigatório de datas de
expiração como pré-condição dos lotes A03. Substitui a
instrução operacional imediatamente anterior; preserva
o registro histórico de auth NOT_CHECKED e expiry UNKNOWN.
Usar configuração existente do monitor (REQUIRE_EXPIRY=0).
Não modificar guardas nem apagar datas de expiração
conhecidas, não aceitar credencial ausente ou auth
bloqueada, não ignorar expiração já declarada ou inválida.
Erro de autenticação retornado pela Meta continua
interrompendo o lote e acionando o bloqueio persistente.
Nenhum bypass, retry automático ou alteração de quotas.
Não requer nova aprovação institucional.

Operador: com DB/tenant/viewer/manifesto V10 existentes,
token local configurado, escritores parados e flags
externas desligadas, validar testes e zero spend, repetir
a prévia offline e confirmar os mesmos cinco nomes e
saldo >=5. Se seleção mudou, parar e replanejar.
```powershell
git pull --ff-only
$py = Join-Path $env:CONDA_PREFIX "python.exe"
$manifest = "artifacts/private/bd_manifest_a6_v10.json"
$env:TAPI_META_REQUIRE_TOKEN_EXPIRY = "0"
& $py -m pytest -q --tb=short tests/test_discovery_identity_expansion.py tests/test_discovery_expansion_capacity.py
if ($LASTEXITCODE -ne 0) { throw "Testes A03 falharam" }
& $py scripts/verify_zero_spend.py
if ($LASTEXITCODE -ne 0) { throw "Zero spend falhou" }
& $py -m scripts.a6_identify_sources --manifest "$manifest" --plan-expansion --max-sources 5 --daily-request-budget 80
```
Após prévia compatível, token local presente e confirmação
da operação oficial sem cobrança, executar o lote explícito:
```powershell
if ([string]::IsNullOrWhiteSpace($env:TAPI_INSTAGRAM_ACCESS_TOKEN)) { throw "Restaurar credencial existente localmente" }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$env:TAPI_BD_IDENTITY_ENABLED = "1"
$env:TAPI_OFFICIAL_METADATA_READS = "1"
$env:TAPI_ZERO_BILLING_CONFIRMED = "1"
try {
    & $py -m scripts.a6_identify_sources --manifest "$manifest" --source abavnacional --source abfoficial --source agisaalimentos --source amarefashiongo --source andraeltec --daily-request-budget 80 --execute --report "artifacts/private/a6-identity-v11-$stamp.json"
}
finally {
    $env:TAPI_BD_IDENTITY_ENABLED = "0"
    $env:TAPI_OFFICIAL_METADATA_READS = "0"
    $env:TAPI_ZERO_BILLING_CONFIRMED = "0"
}
```
Enviar status/cycle_key/username/status/code e reservas,
sem token/IDs. Não executar se guardas atuais bloquearem.
Ajuste exclusivamente documental e de configuração local
prevista, sem alteração de código, teste, schema, matriz,
grants, mídia, merge, gasto ou execução externa.


### A03.3 — primeira identidade real V11 concluída (19/11/2026 UTC)

Operador: IDENTITY_BATCH_COMPLETED, ciclo
a6identity-20261119030035-8762664b, manifesto de entrada
V10 faae42aa652a5b4b49c025d7522ac2e2f029c09bdc1434923c11df9d0ebdb1bb,
DEC-018. 5/5 IDENTIFIED: abavnacional, abfoficial,
agisaalimentos, amarefashiongo, andraeltec. 5 reservas
identity; saldo esperado 75/80 conservador no mesmo dia
se não houve outras operações. Expiry UNKNOWN não
bloqueante (declaração opcional conforme operador);
plan interno external_data_accessed=false é prévia, não
nega as cinco consultas efetivamente realizadas.
Zero grants, posts e admissões; production_approved=false.
Não registrar IDs privados neste documento.
HEAD local/testes/zero-spend não reapresentados; remoto
af3b33a confirmado. Não declarar nova regressão PASS.

Próximo: reconciliar somente ciclo exato contra V10,
gerar intermediário privado exclusivo com IDs, sem
DB write/rede; verificar 5 identidades, 5 IDs adicionados,
21 approved, 50 fontes, 0 skipped. Planejar cinco grants
técnicos (não asset rights) usando manifesto reconciliado,
verificar 5 grants_to_create e nenhum conflito. Backup
offline verificado com todos escritores parados antes
da escrita administrativa; usar CLI existente sob DEC-018,
não solicitar aprovação institucional. Saída exclusiva
bd_manifest_a6_v11.json, esperado 26 approved, 5 criados,
technical_verified=false até primeira coleta oficial.
Não marcar as novas fontes cientificamente elegíveis,
não contar grant como perfil observado. Nenhum grant
provisionado pelo assistente. Não reexecutar identidade.
Em caso de falha pós-commit, preservar arquivo/recibo,
reconciliar estado antes de tentar novo nome; não
sobrescrever manifesto nem recriar grants. Após sucesso,
prévia history coverage em V11, preflight capacity
atualizado; não usar V10 para coleta. Testes focais
A03 ainda sem log. Sem merge, mídia, pagamento ou gates.

```powershell
git pull --ff-only
$py = Join-Path $env:CONDA_PREFIX "python.exe"
$env:TAPI_META_REQUIRE_TOKEN_EXPIRY = "0"
$v10 = "artifacts/private/bd_manifest_a6_v10.json"
$reconciled = "artifacts/private/bd_manifest_a6_v11_identified.json"
$v11 = "artifacts/private/bd_manifest_a6_v11.json"
$cycle = "a6identity-20261119030035-8762664b"
$sources = @("--source","abavnacional","--source","abfoficial","--source","agisaalimentos","--source","amarefashiongo","--source","andraeltec")
& $py -m scripts.a6_reconcile_identities --manifest "$v10" --cycle "$cycle" --output "$reconciled"
if ($LASTEXITCODE -ne 0) { throw "Reconciliacao bloqueada" }
& $py -m scripts.a6_provision_grants --manifest "$reconciled" @sources
if ($LASTEXITCODE -ne 0) { throw "Plano de grants bloqueado" }
```
Após conferir resultados esperados e parar todos writers:
```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
& $py -m scripts.a6_backup_restore_drill --output-name "a03-pre-v11-$stamp.sqlite3" --confirm-all-writers-stopped
if ($LASTEXITCODE -ne 0) { throw "Backup bloqueado" }
& $py -m scripts.a6_provision_grants --manifest "$reconciled" @sources --execute --output "$v11"
if ($LASTEXITCODE -ne 0) { throw "Provisionamento bloqueado; inspecionar estado" }
& $py -m scripts.a5_business_discovery_cycle --manifest "$v11" --mode history --max-sources 5 --page-limit 10 --max-pages 4 --daily-request-budget 80 --priority-policy coverage
```
Enviar somente status, contagens, fingerprint V11,
seleção history e bloqueadores, sem IDs/credenciais.


### A03.3 — reconciliação V11 concluída

Operador: IDENTITIES_RECONCILED, ciclo
a6identity-20261119030035-8762664b, V10 pin confirmado,
intermediário bd_manifest_a6_v11_identified.json fingerprint
662300b06739d886a613c6682993638c86cc383edc0a26bc4792c56e461c3623.
5 identidades verificadas, 5 IDs adicionados, 0 skipped,
50 fontes, 21 approved; novas cinco ainda candidate.
Zero grants, database_written=false, external_data_accessed=false,
scientific_admissions=0. Não repetir reconciliação/identidade
ou sobrescrever intermediário. HEAD local não impresso;
remoto anterior 8e81036 confirmado. Próximo: plano de
grants das cinco fontes, verificar grants_to_create=5,
backup com escritores parados e provisionamento conforme
comandos anteriores. Após gerar V11, prévia history e
snapshot de capacidade. Nenhuma nova aprovação ou
declaração manual de validade de token. Saldo 75/80
era estimativa pós-lote no mesmo dia, conferir snapshot
antes de coletar. Commit documental, sem alteração
de código, grants, banco, mídia, gates ou merge.


### A03.3 — V11 provisionado e primeiro histórico planejado

Console operador 23953 bytes SHA256
55c76415f145a847aa07b4dfe94c9643e5f9d6fe8b6bd493febbcd6de72027bd.
Reconciliacao 5/5 confirmada novamente no console;
TECHNICAL_GRANTS_PLANNED 5 novos, 0 existentes,
DEC-018, lease técnico 30 dias, sem rede.
BACKUP_RESTORE_VERIFIED 2026-11-19T11:12:01.002827+00:00,
a03-pre-v11-20261119-081159.sqlite3, SHA256
f586e7f3ed2d49b12c9ea1c08b5014aebc19d2e2a2ffcd434228b76f567ade20,
10121216 bytes, backup 1172ms/drill 406ms.
Integridade/FK OK, schema 02f66a45b4e198183176faaafea2ee7262dfd91f63042d3d6d83a50ca4133c6f,
0016, inventário e conteúdo lógico iguais, restore
descartável, writers parados atestados, sem restore live.
Pré-provisionamento 1065 posts/21 perfis/1169 snapshots,
53 runs/21 checkpoints/22 grants técnicos no banco,
2465 eventos/outbox; sete tabelas A02 vazias,
0 revisões científicas. Não confundir tabela de contextos
vazia com eventos de contexto documental.

TECHNICAL_GRANTS_PROVISIONED 5 criados, 26 approved,
50 fontes, fingerprint V11
19c38ca968585a7e056402dd2f5f743df232f778c161b762e9c764d713e71840,
arquivo privado bd_manifest_a6_v11.json. Sem rede,
technical_verified=false, 0 admissões. Contagem de
grants no DB pós-escrita não reaferida; não confundir
26 manifesto com 27 linhas esperadas no DB.
PLAN_ONLY_NO_EXTERNAL_READ history coverage: cinco
novos perfis abavnacional, abfoficial, agisaalimentos,
amarefashiongo, andraeltec, 0 posts/5 estratos vazios,
20 páginas/200 observações máximas, 5/80 reservas
usadas, saldo 75 no momento da prévia. 24 fontes não
aprovadas e 21 aprovadas deferidas por limite. Sem
previsão de yield, auth NOT_CHECKED, expiry UNKNOWN
não bloqueante (opção do operador), sem rede nessa
prévia. HEAD local/testes não impressos; remoto ba0aa75.
Não repetir grant/backup pré-V11 já verificados.

Próximo: executar exatamente um histórico V11 com
planner coverage (replaneja sob lease), mesmas fontes
se estado inalterado. Flags específicas temporárias,
token existente, R$0, sem exigência manual de expiração.
Parar writers, verificar prévia atual, fingerprint V11,
quota/dia e condições de coleta metadata-only. Guardas
prevalecem; parar se seleção mudou, erro ou bloqueio.
Relatório privado exclusivo; reauditar somente se
BATCH_COMPLETED ou BATCH_NO_ELIGIBLE_OBSERVATIONS.
Não repetir falhas automaticamente. Depois planejar
segundo lote identity em V11 (até 5 slots restantes);
se coleta usar todas 20 reservas, saldo 55, após mais
5 identidades saldo 50, até 12 runs adicionais de
história com 2 unidades de margem, no mesmo dia e
sem outras operações. Não fixar yield nem forçar quota.
Sem mídia, cobrança, nova aprovação, produção ou merge.

```powershell
git pull --ff-only
$py = Join-Path $env:CONDA_PREFIX "python.exe"
$manifest = "artifacts/private/bd_manifest_a6_v11.json"
$env:TAPI_META_REQUIRE_TOKEN_EXPIRY = "0"
& $py scripts/verify_zero_spend.py
if ($LASTEXITCODE -ne 0) { throw "Zero spend falhou" }
& $py -m scripts.a5_business_discovery_cycle --manifest "$manifest" --mode history --max-sources 5 --page-limit 10 --max-pages 4 --daily-request-budget 80 --priority-policy coverage
```
Se prévia compatível e operação oficial sem cobrança:
```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$historyReport = "artifacts/private/a03-history-v11-$stamp.json"
$env:TAPI_BD_CONTINUOUS_ENABLED = "1"
$env:TAPI_BD_TECHNICAL_INGEST = "1"
$env:TAPI_OFFICIAL_METADATA_READS = "1"
$env:TAPI_ZERO_BILLING_CONFIRMED = "1"
try {
    & $py -m scripts.a5_business_discovery_cycle --manifest "$manifest" --mode history --max-sources 5 --page-limit 10 --max-pages 4 --daily-request-budget 80 --priority-policy coverage --execute --report "$historyReport"
    $historyExit = $LASTEXITCODE
}
finally {
    $env:TAPI_BD_CONTINUOUS_ENABLED = "0"
    $env:TAPI_BD_TECHNICAL_INGEST = "0"
    $env:TAPI_OFFICIAL_METADATA_READS = "0"
    $env:TAPI_ZERO_BILLING_CONFIRMED = "0"
}
if ($historyExit -ne 0) { throw "Historico bloqueado; nao repetir" }
```
Somente se batch completo (inclusive sem observações):
```powershell
& $py -m scripts.a6_audit_history_reports --report "$historyReport"
if ($LASTEXITCODE -ne 0) { throw "Reauditoria falhou" }
& $py -m scripts.a6_identify_sources --manifest "$manifest" --plan-expansion --max-sources 5 --daily-request-budget 80
```
Enviar resumo de ciclo, auditoria e nova seleção; não
compartilhar relatório privado, IDs, cursor ou token.
Commit exclusivamente documental, não executado pelo
assistente no banco operacional.


### A03.3 — primeiro histórico V11 interrompido, diagnóstico pendente

Console operador 14585 bytes SHA256
03a6848c3dc6679a090c0f19e8712d678a19f06bfe89360692df60aba3692055.
Ciclo a5history-20261119112216-5adfc90b, manifesto V11
pin 19c38ca968585a7e056402dd2f5f743df232f778c161b762e9c764d713e71840,
BATCH_STOPPED_ON_SOURCE_FAILURE. Seleção 5 novas fontes,
zero registros novos/refresh/duplicatas/returned/accepted/
pages_examined no agregado; inventário antes/depois
1065/21, 0 admissões, sem produção. A primeira fonte
é abavnacional, nenhuma conclusão no batch; código exato
não presente no console. O agregado zero não demonstra
zero chamadas: a reserva pode ter sido registrada e o
provider pode ter sido chamado antes da falha. Não assumir
saldo 55 ou 71 até inspeção. Flags externas restauradas
a 0 via finally. Relatório privado
a03-history-v11-20261119-082214.json. HEAD local/testes
não impressos; remoto e2946db confirmado.

Defeito de observabilidade: CLI omitia failed_run_key,
failure_code e diagnóstico numérico do batch. Adicionada
função cycle_console_summary com projeção dos dois
campos e allowlist numérica http_status/code/error_subcode;
não expõe batch/evidence, mensagens ou payloads. Um
teste focal de projeção ainda não executado pelo
assistente. Não muda aquisição, recuperação, quotas,
grants, schema, política ou autorização.

Diagnosticar relatório existente sem nova chamada:
```powershell
git pull --ff-only
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py -m pytest -q --tb=short tests/test_discovery_history_a5.py -k cycle_console_failure_summary
$report = Get-Content -Raw -LiteralPath "artifacts/private/a03-history-v11-20261119-082214.json" | ConvertFrom-Json
[pscustomobject]@{
    status = $report.status
    cycle_key = $report.cycle_key
    failed_run_key = $report.batch.failed_run_key
    failure_code = $report.batch.failure_code
    provider_http_status = $report.batch.provider_diagnostic.http_status
    provider_code = $report.batch.provider_diagnostic.code
    provider_error_subcode = $report.batch.provider_diagnostic.error_subcode
    attempted = $report.batch.selection.attempted
} | ConvertTo-Json
& $py -m scripts.a5_recover_business_discovery
$head = (git rev-parse HEAD).Trim()
& $py -m scripts.a03_expansion_capacity --expected-head "$head"
```
Da inspeção recovery enviar somente estado de lease
(presente/ausente), reserved_runs, run_key, status,
reason_code, observations_recorded, reviewed,
recovery_action, meta_auth.status/blocked, e contagem
de órfãos/quarentena; não enviar IDs. Sem review-failure,
restart, reset auth, novo lote identity ou history até
classificar erro. A política de recuperação só admite
retry de falhas conhecidas sem observações, ou restart
com checkpoint seguro em erros específicos de paginação;
não promover erro desconhecido. Planner identity bloqueia
quando há última falha A5 não revisada. Não usar relatório
de sucesso para reauditar lote interrompido. Não repetir
token debugger manual nem apagar expiração conhecida.
Sem merge, novas permissões, chamadas externas ou gasto
pelo assistente.


### A03.3 — causa confirmada: credencial Meta rejeitada, recuperação técnica

Operador HEAD 32e81210dcfe6238438528f445375dc8e48e19b0
igual ao remoto; teste cycle_console_failure_summary
1 PASS, 19 deselected, 2,65s. Relatório existente
a03-history-v11-20261119-082214.json: attempted=1,
failed_run_key a5history-20261119112216-5adfc90b-01,
PROVIDER_PERMISSION_DENIED HTTP401, Graph code190
sub463 (token/sessão expirado ou inválido segundo
https://developers.facebook.com/docs/graph-api/guides/error-handling).
Não é evidência de falha específica da ABAV ou grant.
Recuperação: último run failed, reviewed=false,
BD_META_AUTH_INVALID, 0 observações; recovery_action
blocked_unclassified_or_integrity (não review-failure
genérico). Circuit breaker global BLOCKED desde
2026-11-19T11:22:17.481917+00:00. Lease null, 0 reserved,
0 órfãos e 0 quarentena. Sem mutação na inspeção.
Capacity 2026-11-19T11:50:12.657579+00:00: 1065/21,
22 grants ativos tecnicamente verificados (21 com
registros), 21 continuation, 1 no_checkpoint.
Cinco grants recém-provisionados V11 não entram na
contagem de verificados até sucesso técnico; não
reprovisionar nem inferir desaparecimento dos grants.
9/80 reservas UTC (5 identidade + 4 por um run),
saldo 71, 5 slots identity, até 17 history sem
identity. Sem quota provider verificada; saldo datado.

Recuperar usando fluxo existente: substituir credencial
realmente rejeitada pelo mesmo app/conta e escopos
autorizados, sem exigir debugger/datas de expiração.
Input local seguro, não imprimir token. Com todos
processos de ingestão parados, CLI
--reset-meta-auth-after-rotation autenticado, somente
após substituição. META_AUTH_RESET_UNVERIFIED é reset
local, não validação. Não apagar evento, alterar quota,
review-failure genérico, restart-history, revogar grant
ou contornar auth. Planner history permite último
AUTH_INVALID sem registros após reset; planner identity
expansion ainda bloqueia falha não revisada, então
primeiro executar history de uma fonte (ABAV) para
confirmar funcionamento no fluxo real, não chamada
extra de diagnóstico. Planejar com max-sources=1,
page-limit=10/max-pages=4, coverage, conferir seleção
ABAV, pin V11, auth RESET_UNVERIFIED não bloqueado e
saldo >=4; se incompatível parar. Sob R$0 confirmado,
flags metadata temporárias e relatório privado novo,
executar exatamente um run; reauditar sucesso antes
de planejar restantes. Se 190 novamente, breaker
bloqueia; não repetir automaticamente. Preservar
reserva anterior. Não exigir validação manual da
expiração; datas conhecidas válidas continuam guardadas,
não apagar para contornar. Sem nova aprovação DEC-018.

```powershell
git pull --ff-only
$py = Join-Path $env:CONDA_PREFIX "python.exe"
$manifest = "artifacts/private/bd_manifest_a6_v11.json"
$env:TAPI_META_REQUIRE_TOKEN_EXPIRY = "0"
# Somente apos gerar novo token pelo fluxo oficial do mesmo app/conta.
$secret = Read-Host "Novo token Meta" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $env:TAPI_INSTAGRAM_ACCESS_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    $secret.Dispose()
    Remove-Variable secret,bstr
}
& $py -m scripts.a5_recover_business_discovery --reset-meta-auth-after-rotation --confirm-all-ingestion-stopped
if ($LASTEXITCODE -ne 0) { throw "Reset bloqueado" }
& $py -m scripts.a5_business_discovery_cycle --manifest "$manifest" --mode history --max-sources 1 --page-limit 10 --max-pages 4 --daily-request-budget 80 --priority-policy coverage
```
Apos prévia compatível e operação oficial sem cobrança:
```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$historyReport = "artifacts/private/a03-history-v11-recovery-$stamp.json"
$env:TAPI_BD_CONTINUOUS_ENABLED = "1"
$env:TAPI_BD_TECHNICAL_INGEST = "1"
$env:TAPI_OFFICIAL_METADATA_READS = "1"
$env:TAPI_ZERO_BILLING_CONFIRMED = "1"
try {
    & $py -m scripts.a5_business_discovery_cycle --manifest "$manifest" --mode history --max-sources 1 --page-limit 10 --max-pages 4 --daily-request-budget 80 --priority-policy coverage --execute --report "$historyReport"
    $historyExit = $LASTEXITCODE
}
finally {
    $env:TAPI_BD_CONTINUOUS_ENABLED = "0"
    $env:TAPI_BD_TECHNICAL_INGEST = "0"
    $env:TAPI_OFFICIAL_METADATA_READS = "0"
    $env:TAPI_ZERO_BILLING_CONFIRMED = "0"
}
if ($historyExit -ne 0) { throw "Historico bloqueado; nao repetir" }
& $py -m scripts.a6_audit_history_reports --report "$historyReport"
```
Reauditar somente batch completo (inclusive vazio);
se nenhum devido, parar sem reauditoria de sucesso.
Enviar reset, prévia, resumo de ciclo e auditoria sem
IDs/credenciais. Se sucesso, recalcular reservas,
planejar 4 restantes e segundo lote identidade após
recuperação. Não declarar token validado permanentemente
nem exigir data manual. Commit exclusivamente documental,
sem alteração de código, DB, rede, gates ou merge pelo
assistente.


### A03.3 — reset confirmado; execução de recuperação ainda pendente

Console operador 13105 bytes SHA256
058a735685395871cedc2d49cb80afd3eb51abcced45ab62cb2b09de2b300cf8.
META_AUTH_RESET_UNVERIFIED, quota_reservation_preserved=true,
external_data_accessed=false. Prévia V11 pin
19c38ca968585a7e056402dd2f5f743df232f778c161b762e9c764d713e71840,
RESET_UNVERIFIED desde 2026-11-19T11:53:40.321688+00:00,
blocked=false, selected_sources=[abavnacional], 9/80
reservas, 4 páginas/40 observações máximas, 1065/21.
Não consta execução --execute após reset; chamada direta
ao auditor com $historyReport retornou BD_REPORT_AUDIT_MISMATCH.
Provável referência ao relatório interrompido anterior;
arquivo efetivamente auditado não impresso, não afirmar
identidade exata do arquivo. Auditor exige batch completo.
Não é nova falha de OAuth nem evidência de defeito do
auditor; nenhuma nova coleta demonstrada. HEAD local
não impresso; remoto 2e63494 confirmado.

Próximo: não repetir reset nem a rotação, nem consultar
validade manual. Confirmar prévia atual com seleção ABAV
e saldo >=4, sem bloqueio, flags externas desligadas.
Com escritores parados, R$0 e mesma credencial local,
usar novo nome exclusivo e executar exatamente uma coleta.
Somente auditar o relatório recém-gerado se execução
exit=0, status BATCH_COMPLETED/BATCH_NO_ELIGIBLE_OBSERVATIONS,
manifesto V11 e seleção ABAV confirmados; não auditar
NO_DUE_AUTHORIZED_SOURCES. Se erro, parar e preservar
relatório e reservas. Usar comandos da seção anterior,
com checagem explícita do status do arquivo novo antes
da reauditoria. Após sucesso, planejar quatro fontes
restantes e segundo lote identity. Nenhuma mudança de
código, dados operacionais, gates, merge ou rede pelo
assistente. Saldo 71 apenas na prévia observada.


### A03.3 — recuperação oficial ABAV concluída e reauditoria aprovada

Console operador 16210 bytes SHA256
1d9bfc1d09342dce10c851d788c16c5174d6a0b3bf397ab8707fe56f2407f568.
BATCH_COMPLETED a5history-20261119115859-a83ea47a,
V11 pin 19c38ca968585a7e056402dd2f5f743df232f778c161b762e9c764d713e71840,
abavnacional, report privado
a03-history-v11-recovery-20261119-085857.json.
40 retornados, 38 aceitos/novos, 2 too_recent,
0 refresh/duplicates, 4 páginas. Reauditoria
HISTORY_REPORTS_REAUDITED 1 report/1 run, 38/38
observações válidas, 0 missing_metrics/invalid_metadata/
unsupported_format/duplicate_in_page. Checkpoint
continuation_available. Corpus 1065→1103 únicos,
21→22 perfis observados, zero cross-source duplicates.
26 fontes aprovadas no manifesto, zero admissões,
sem validação científica ou produção. Credencial
substituída funcionou nesta coleta, não afirmar
validade futura; RESET_UNVERIFIED no plano é estado
anterior ao run, não resultado OAuth negativo.
A falha anterior e reserva de 4 unidades preservadas.
Estimativa pós-run 13/80 (5 identity + 2 runs x4),
saldo 67, 5 slots identity, confirmar snapshot atual.
HEAD local/testes não impressos; remoto 9be6556.

Próximo: continuar V11 com max-sources=4, coverage,
esperadas abfoficial/agisaalimentos/amarefashiongo/
andraeltec (sem registros), confirmar prévia atual;
16 unidades/160 observações máximas, não previsão.
Se seleção divergente, parar e replanejar. Após
conclusão, reauditar conjuntamente recuperação ABAV
e novo relatório completo (não incluir batch falho).
Depois planejar segundo lote identity com V11,
até 5 candidatos inéditos. Se 4 runs e 5 identities,
saldo estimado 46/80; até 11 runs adicionais (44
unidades, margem 2), sujeito a quotas/dia/guardas.
Não alterar token ou repetir reset sem nova falha.
Usar flags temporárias existentes, R$0, writers
parados, relatório exclusivo. Sem mídia, gasto,
nova aprovação institucional ou merge.

```powershell
git pull --ff-only
$py = Join-Path $env:CONDA_PREFIX "python.exe"
$manifest = "artifacts/private/bd_manifest_a6_v11.json"
$head = (git rev-parse HEAD).Trim()
& $py -m scripts.a03_expansion_capacity --expected-head "$head"
& $py -m scripts.a5_business_discovery_cycle --manifest "$manifest" --mode history --max-sources 4 --page-limit 10 --max-pages 4 --daily-request-budget 80 --priority-policy coverage
```
Após prévia compatível, saldo >=16, e condições
de aquisição oficial sem cobrança:
```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$historyReport = "artifacts/private/a03-history-v11-remaining-$stamp.json"
$env:TAPI_BD_CONTINUOUS_ENABLED = "1"
$env:TAPI_BD_TECHNICAL_INGEST = "1"
$env:TAPI_OFFICIAL_METADATA_READS = "1"
$env:TAPI_ZERO_BILLING_CONFIRMED = "1"
try {
    & $py -m scripts.a5_business_discovery_cycle --manifest "$manifest" --mode history --max-sources 4 --page-limit 10 --max-pages 4 --daily-request-budget 80 --priority-policy coverage --execute --report "$historyReport"
    $historyExit = $LASTEXITCODE
}
finally {
    $env:TAPI_BD_CONTINUOUS_ENABLED = "0"
    $env:TAPI_BD_TECHNICAL_INGEST = "0"
    $env:TAPI_OFFICIAL_METADATA_READS = "0"
    $env:TAPI_ZERO_BILLING_CONFIRMED = "0"
}
if ($historyExit -ne 0) { throw "Historico bloqueado; nao repetir" }
$result = Get-Content -Raw -LiteralPath $historyReport | ConvertFrom-Json
if ($result.status -notin @("BATCH_COMPLETED","BATCH_NO_ELIGIBLE_OBSERVATIONS")) { throw "Coleta nao concluida" }
& $py -m scripts.a6_audit_history_reports --report "artifacts/private/a03-history-v11-recovery-20261119-085857.json" --report "$historyReport"
if ($LASTEXITCODE -ne 0) { throw "Reauditoria falhou" }
& $py -m scripts.a6_identify_sources --manifest "$manifest" --plan-expansion --max-sources 5 --daily-request-budget 80
```
Enviar resumo/auditoria/seleção, sem relatório bruto,
IDs privados, cursors ou segredos. Documentação apenas;
nenhuma execução externa ou mutação DB pelo assistente.


### A03.3 — V11 completo e segundo lote identity V12 selecionado

Console operador 33999 bytes SHA256
5dfc611627bd0e3b59a65e5a73f6bbf5a07ec09d2eecbd167200fbaa319c4b62.
Capacity 2026-11-19T12:01:39.775522+00:00, HEAD local
060e3d2735d80f54e2ab0aa1bab2f744b750bf90 igual remoto.
Antes do lote restante: 1103 únicos/22 observados,
23 grants ativos tecnicamente verificados (22 com
registros), 22 continuation/1 no_checkpoint, 21
registered_profiles. A diferença registered_profiles
vs perfis com registros deve ser inspecionada na
consolidação documental A03.4; não pressupor que
registro/contexto de pesquisa foi criado pela coleta.
13/80 unidades (5 identity + 2 runs), saldo 67, ingestão
inativa, zero mutação/rede/admissões/gates no snapshot.

BATCH_COMPLETED a5history-20261119120146-fd412051,
relatório privado a03-history-v11-remaining-20261119-090144.json,
V11 pin 19c38ca968585a7e056402dd2f5f743df232f778c161b762e9c764d713e71840.
Quatro fontes esperadas, 160 retornados, 139 novos,
21 too_recent, 16 páginas, zero refresh/duplicatas.
Corpus 1103→1242 IDs únicos, 22→26 perfis observados.
Reauditoria conjunta HISTORY_REPORTS_REAUDITED: 2
reports/5 runs, 200 retornados/177 novos e aceitos,
23 too_recent, 20 páginas, zero missing_metrics,
unsupported_format, invalid_metadata, duplicate_in_page,
refresh/unchanged_duplicates. ABAV 38, ABF 31,
Agisa 37, Amare 35, Andraeltec 36; todas 40 retornados
e continuation_available, audit_valid=true. 88,5% de
aproveitamento técnico; nenhuma admissão científica,
produção ou cobertura exaustiva. Não repetir V11 inicial.
Gap bruto agora 758 posts e 4 perfis; mínimo otimista
19 runs/76 unidades antes de custos de identidade.

EXPANSION_PLAN_READY V11, mesmo dia UTC 19/11,
5/10 identity e 29/80 unidades usadas, saldo 51.
Selecionados casa.artemisia.escola, endeavorbrasil,
institutolojasrenner, wabizapp, abraseloestepotiguar.
Quatro estratos ainda vazios, último foodservice_association_regional
já 1 fonte/45 posts, declared_audience=mpe_targeted;
quatro demais uncertain. 11 outros candidatos inéditos,
8 deferidos (6 rationale/viewer, 2 prior attempt),
pending_identity_actions vazio. Não inferir elegibilidade
científica a partir de intent ou estrato. Não repetir
identidade de fontes já tentadas.

Próximo: executar somente segundo lote explícito de 5
identidades sob DEC-018, mesma credencial, sem
declaração manual de expiração. Confirmar prévia atual
V11 e dia UTC, condições R$0, writers parados e
credencial configurada; não alterar viewer/manifesto.
Se falha, parar e preservar reservas; reconciliar apenas
sucessos exatos. Se 5 sucessos, provisionar em V12
(31 approved potenciais), depois history de cinco
novas fontes e mais seis runs se orçamento permitir:
34/80 após identity, 54/80 após cinco histories,
78/80 após seis histories, margem 2. 440 observações
máximas adicionais (11 runs), não previsão de yield.
Não prometer atingir 2000 hoje. Após aquisição e
auditoria: backup, registrar perfis/contextos
documentais faltantes pelo fluxo existente e recalcular
elegibilidade/caption/ranking com corpus atual; não
reusar métricas grounded V10. Sem mídia, cobrança,
merge ou gates. Atualização apenas documental.

```powershell
git pull --ff-only
$py = Join-Path $env:CONDA_PREFIX "python.exe"
$manifest = "artifacts/private/bd_manifest_a6_v11.json"
$env:TAPI_META_REQUIRE_TOKEN_EXPIRY = "0"
& $py -m scripts.a6_identify_sources --manifest "$manifest" --plan-expansion --max-sources 5 --daily-request-budget 80
```
Se seleção e saldo compatíveis, token presente e
operação oficial sem cobrança:
```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$identityReport = "artifacts/private/a03-identity-v12-$stamp.json"
$env:TAPI_BD_IDENTITY_ENABLED = "1"
$env:TAPI_OFFICIAL_METADATA_READS = "1"
$env:TAPI_ZERO_BILLING_CONFIRMED = "1"
try {
    & $py -m scripts.a6_identify_sources --manifest "$manifest" --source casa.artemisia.escola --source endeavorbrasil --source institutolojasrenner --source wabizapp --source abraseloestepotiguar --daily-request-budget 80 --execute --report "$identityReport"
    $identityExit = $LASTEXITCODE
}
finally {
    $env:TAPI_BD_IDENTITY_ENABLED = "0"
    $env:TAPI_OFFICIAL_METADATA_READS = "0"
    $env:TAPI_ZERO_BILLING_CONFIRMED = "0"
}
if ($identityExit -ne 0) { throw "Identidade interrompida; preservar relatorio, nao repetir" }
```
Enviar status/cycle_key/reservas e username/status/code,
sem IDs privados ou segredos. Não provisionar ou
coletar V12 antes de reconciliar resultados efetivos.


### A03.4 — segundo lote identity parcial, V12 com três sucessos

Operador: IDENTITY_BATCH_STOPPED, ciclo
a6identity-20261119120439-0e4f8f74, manifesto V11
19c38ca968585a7e056402dd2f5f743df232f778c161b762e9c764d713e71840,
DEC-018, UTC 19/11. 3 IDENTIFIED: casa.artemisia.escola,
endeavorbrasil, institutolojasrenner. wabizapp BLOCKED
PROVIDER_REQUEST_FAILED, HTTP400 code110 sub2207013
(mesmo diagnóstico numérico de aanadesales, causa não
demonstrada; não é regra de bloqueio global 190).
abraseloestepotiguar reservada sem resultado, não
consultada. 5 reservas integralmente mantidas, 10/10
identity hoje; 34/80 compartilhadas (estimativa a
confirmar), saldo 46, até 11 runs history, margem 2.
4 resultados, zero grants/posts/admissões, sem
produção. HEAD local não impresso, remoto 5544088.
Não atribuir falha a expiração ou remover grant;
não resetar auth sem bloqueio 190. Não repetir wabizapp
ou abraseloestepotiguar automaticamente, inclusive
próximo dia: planner considera ambos prior attempt
review. Fonte reservada sem resultado não é falha
de provider e requer tratamento distinto na revisão
posterior; não devolver quota ou apagar eventos.

Reconciliar ciclo exato sobre V11, 3 IDs adicionados,
2 skipped (PROVIDER_REQUEST_FAILED e NO_RESULT_RESERVED),
50 fontes, 26 aprovadas. Provisionar apenas três
sucessos via fluxo DEC-018, 29 approved esperados.
Backup local antes da escrita, todos writers parados.
Não criar grant para as duas deferidas. Após V12,
prévia history 3 novas fontes (12 unidades, 120
observações máximas); se sucesso e saldo confirmado,
reauditar e planejar outros 8 runs (32 unidades)
em lotes de até 5. Total máximo 440 observações
adicionais hoje, não promessa de rendimento. Mesmo
com 3 novos perfis observados, 29/30; identificação
adicional somente novo dia UTC, com seleção inédita
do planner. 758 posts gap atual, mínimo 19 runs
otimistas, impossível completar 2000 neste dia
com saldo atual. Não inferir admissões científicas.
Prioridade de cobertura preservada. Sem mídia, gasto,
merge ou liberação de gates. Atualização documental.

```powershell
git pull --ff-only
$py = Join-Path $env:CONDA_PREFIX "python.exe"
$v11 = "artifacts/private/bd_manifest_a6_v11.json"
$reconciled = "artifacts/private/bd_manifest_a6_v12_identified.json"
$v12 = "artifacts/private/bd_manifest_a6_v12.json"
$cycle = "a6identity-20261119120439-0e4f8f74"
$sources = @("--source","casa.artemisia.escola","--source","endeavorbrasil","--source","institutolojasrenner")
& $py -m scripts.a6_reconcile_identities --manifest "$v11" --cycle "$cycle" --output "$reconciled"
if ($LASTEXITCODE -ne 0) { throw "Reconciliacao bloqueada" }
& $py -m scripts.a6_provision_grants --manifest "$reconciled" @sources
if ($LASTEXITCODE -ne 0) { throw "Plano de grants bloqueado" }
```
Após conferir 3 sucessos/2 skips e plano de 3 grants:
```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
& $py -m scripts.a6_backup_restore_drill --output-name "a03-pre-v12-$stamp.sqlite3" --confirm-all-writers-stopped
if ($LASTEXITCODE -ne 0) { throw "Backup bloqueado" }
& $py -m scripts.a6_provision_grants --manifest "$reconciled" @sources --execute --output "$v12"
if ($LASTEXITCODE -ne 0) { throw "Provisionamento bloqueado" }
$manifest = $v12
& $py -m scripts.a5_business_discovery_cycle --manifest "$manifest" --mode history --max-sources 3 --page-limit 10 --max-pages 4 --daily-request-budget 80 --priority-policy coverage
$head = (git rev-parse HEAD).Trim()
& $py -m scripts.a03_expansion_capacity --expected-head "$head"
```
Enviar resumos/contagens/fingerprint/seleção, sem IDs
privados, credenciais ou relatório bruto. Não executar
histórico antes de confirmar prévia V12.


### A03.4 — V12 provisionado e backup pré-escrita verificado

Console operador 11904 bytes SHA256
31e10e28e6d7ea34ffdad86ddcb54c382edfa6358012757a81741b453872936f.
IDENTITIES_RECONCILED: ciclo a6identity-20261119120439-0e4f8f74,
V11 pin confirmado, 3 verificadas/3 IDs adicionados,
2 skipped: abraseloestepotiguar NO_RESULT_RESERVED,
wabizapp PROVIDER_REQUEST_FAILED. 50 fontes, 26 approved,
0 grants, database_written=false, external_data_accessed=false.
Intermediário privado V12 fingerprint
d4a2ddb5f7df5289bd7d32d1cb8215ceb43feeb32fd1cb42c79c5e48a7ab79e2.
TECHNICAL_GRANTS_PLANNED 3 novos/0 existentes, DEC-018,
lease técnico 30 dias, sem rede/admissões.

BACKUP_RESTORE_VERIFIED 2026-11-19T12:07:02.701881+00:00,
a03-pre-v12-20261119-090701.sqlite3, SHA256
651cd8cd94f626954817f96f779dd6a6b816cc58284b6cc31a78ed5135337cc6,
11624448 bytes, backup 672ms/drill 391ms. Integrity/FK
ok, inventory/logical contents match, schema 0016,
writers parados atestados, restore descartável, não live.
Pré-provisionamento 1242 únicos/26 perfis, 1346 snapshots,
26 creators/checkpoints, 59 ingestion_runs, 27 grants
no DB, 2835 events/outbox, 21 corpus_profiles, 0
corpus_source_research_contexts e scientific_reviews,
sete tabelas A02 vazias. Diferença de 5 perfis observados
vs registrados confirmada; tratar na consolidação
documental sem inferir elegibilidade.

TECHNICAL_GRANTS_PROVISIONED: 3 criados, 29 approved,
50 fontes, V12 privado bd_manifest_a6_v12.json pin
43372c6fe04ae12e5735e7b932d98a53a114ee0f5eb44d06fa5bea86a465b081.
Sem rede, technical_verified=false, 0 admissões.
Não repetir reconciliação/provisionamento/backup
pré-V12. HEAD local/testes não impressos, remoto
0a44ace confirmado. Prévia history V12 e capacity
ainda não reportadas. Saldo estimado 46 (34/80),
10/10 identity no dia UTC, confirmar snapshot.

Próximo: prévia history 3 fontes e capacity, verificar
pin V12, seleção exata casa.artemisia.escola,
endeavorbrasil, institutolojasrenner, saldo >=12,
ingestão inativa, sem bloqueios. Sob condições R$0
e writers parados, flags temporárias e relatório
exclusivo, executar max-sources 3, page-limit10,
max-pages4, coverage, orçamento80. Reauditar apenas
novo batch completo junto aos dois relatórios V11.
Se falha, parar; não tentar outras fontes para contornar.
Após sucesso, snapshot e prévia próximo lote <=5,
saldo estimado 34 (8 runs de história, margem2).
Sem novas identidades hoje, sem nova autorização
institucional ou declaração manual de validade de
token. Não prometer rendimento. Sem mídia, gasto,
merge ou gates. Atualização exclusivamente documental.


### A03.4 — V12 coletado, 29 perfis observados, 34 unidades restantes

Console operador 48392 bytes SHA256
bb81d0ad8f72f89a13f216854f9d7c50896ed5a69c882566a5ce0d3cf386a6de.
HEAD local eaf3472b007f27184eedefddff8e5bf5affd2c01 igual remoto.
V12 pin 43372c6fe04ae12e5735e7b932d98a53a114ee0f5eb44d06fa5bea86a465b081.
Snapshot antes 2026-11-19T12:09:10.556689+00:00: 34/80,
46 restantes, 1242 únicos/26 perfis, 27 grants verificados.
BATCH_COMPLETED a5history-20261119120923-47012abc,
a03-history-v12-20261119-090921.json. 101 retornados,
79 novos, 21 too_recent, 1 missing_metrics, 11 páginas.
Casa Artemisia 17/21 (3 páginas, frontier_unconfirmed),
Endeavor 33/40, Renner 29/40 (ambos 4 páginas,
continuation_available). Não presumir fim de histórico
nem reiniciar Casa Artemisia; planner exclui com
BD_HISTORY_FRONTIER_UNCONFIRMED. Sem refresh/duplicatas.
Reauditoria 3 reports/8 runs, 301 retornados/256 novos
e aceitos, 44 too_recent, 1 missing_metrics, 31 páginas,
8/8 audit_valid, 0 invalid_metadata/unsupported_format/
duplicates. 85,05% aproveitamento técnico. Sem
admissões, produção ou cobertura exaustiva.

Snapshot depois 2026-11-19T12:09:41.777427+00:00:
1321 registros/IDs únicos, 29 observados, 21 registrados
(gap documental 8), 30 grants ativos tecnicamente
verificados, 29 com registros. 28 continuation,
1 frontier_unconfirmed, 1 no_checkpoint (grant extra
fora do manifesto não usar). 0 scope_mismatch/unknown.
46/80 unidades reservadas (10 identity + 9 runs x4,
inclui run falho OAuth anterior), saldo 34, 8 runs
history possíveis, identity slots 0. Ingestão inativa;
snapshot sem mutação/rede/gates. Gap bruto 679 posts/
1 perfil, 17 runs/68 unidades otimistas. Meta técnica
não atingível hoje, teto adicional 320 observações
(não previsão de novos). Nenhuma declaração manual
de expiração; credencial funcionou nestes runs.

Prévia V12 confirmada para cinco fontes já observadas:
seliganoton (105, fairness), menteempreendedora (3),
contaazul (20), ifoodparaparceiros (26),
empreendedorasdabelezagb (29); soma 183 posts existentes
vs recency 367, cinco estratos distintos em ambas,
predicted_yield=null. 20 unidades/200 observações
máximas. Depois reauditar quatro relatórios completos,
recalcular capacidade e planejar até 3 runs finais
(12 unidades; saldo esperado 2). Não fixar seleção
do último lote antecipadamente. Não repetir falhas,
não usar grant extra, não alterar limites ou resetar
quota. Dia UTC 19/11, sem novas identidades até novo dia.
Após conclusão do dia, backup verificado e consolidação
documental dos oito novos perfis; reavaliar corpus
e rankings atuais, sem inferência científica automática.

Próximo: manter condições R$0, escritores parados,
mesmo manifesto/viewer/tenant/credencial, confirmar
prévia atual e saldo >=20. Usar CLI existente com
--mode history --max-sources 5 --page-limit 10
--max-pages 4 --daily-request-budget 80
--priority-policy coverage --execute, relatório privado
exclusivo a03-history-v12-expansion-<stamp>.json;
flags CONTINUOUS/TECHNICAL_INGEST/OFFICIAL_METADATA_READS/
ZERO_BILLING_CONFIRMED temporárias e restauradas
a 0 em finally. Reauditar apenas novo batch completo
junto com a03-history-v11-recovery-20261119-085857.json,
a03-history-v11-remaining-20261119-090144.json e
a03-history-v12-20261119-090921.json. Parar se falha.
Depois capacity e prévia max-sources3. Nenhuma execução
externa, alteração de código ou banco pelo assistente;
commit exclusivamente documental. Sem merge ou gates.


### A03.4 — expansão histórica V12: 1513 únicos, último lote planejado

Console operador 36176 bytes SHA256
5475ec0e7ae8e585425a6a52805bcf2d4f13cb3bd77d7a23cbf98bae01c5308c.
HEAD local 0250df8bbb166baa1b9fb51baaae8b416767bfd7 igual remoto.
BATCH_COMPLETED a5history-20261119121236-ec966c97,
a03-history-v12-expansion-20261119-091234.json,
V12 pin 43372c6fe04ae12e5735e7b932d98a53a114ee0f5eb44d06fa5bea86a465b081.
200 retornados, 192 aceitos/novos, 8 missing_metrics,
0 too_recent/unsupported/invalid/duplicates/refresh,
20 páginas. seliganoton +38 (143), menteempreendedora
+40 (43), contaazul +34 (54), ifoodparaparceiros +40
(66), empreendedorasdabelezagb +40 (69); todas
continuation_available. Rendimento técnico 96%.
HISTORY_REPORTS_REAUDITED 4 relatórios/13 runs,
501 retornados, 448 aceitos/novos, 44 too_recent,
9 missing_metrics, 51 páginas, 13/13 audit_valid,
zero duplicatas/refresh/invalid/unsupported.
Aproveitamento acumulado 448/501 (89,42%).
Sem admissões científicas, cobertura exaustiva ou
produção. Corpus 1513 únicos/29 observados/21 registrados.
Snapshot 2026-11-19T12:13:26.217929+00:00: 66/80
reservas (10 identity + 14 runs x4, inclui falha OAuth),
14 restantes, 3 slots history, 0 identity slots.
30 grants tecnicamente verificados, 29 com registros,
28 continuation, 1 frontier_unconfirmed, 1 no_checkpoint,
zero scope_mismatch/unknown. Ingestão inativa.
Gap 487 posts/1 perfil; mínimo otimista 13 runs/52
unidades antes de identidade. Snapshot sem rede/mutação.

Prévia final: stone (106, fairness), institutolojasrenner
(29), abfoficial (31). Soma 166 vs baseline recency
218, 3 estratos em ambas, predicted_yield=null.
12 unidades/120 observações máximas; se 3 runs,
78/80 e margem 2. Não usar margem para novas
identidades (10/10) ou reduzir orçamento por run.
Manter Casa Artemisia bloqueada para history,
não usar grant extra. Dia UTC 19/11. Executar
somente se prévia atual ainda compatível, mesmo
manifesto/viewer/tenant, saldo >=12, R$0, escritores
parados. Flags temporárias como nos lotes anteriores,
relatório privado exclusivo a03-history-v12-final-<stamp>.json.
Após batch completo, reauditar os 5 relatórios do dia
(incluir a03-history-v12-expansion-20261119-091234.json
e os três anteriores, nunca relatório falho OAuth).
Recalcular capacity, confirmar estado de recuperação,
backup final com escritores parados e verify_zero_spend.
Se sucesso, avançar consolidação documental dos 8 perfis
e análise atual; próxima expansão de identidade só
em novo dia UTC com prévia inédita. Não declarar
2k/30 atingido, nem cobertura científica. Commit
exclusivamente documental, sem rede Meta, mutação
operacional, mídia, merge ou liberação de gates.


### A03.5 — fechamento de aquisição UTC 19/11 e preparação documental

Console operador 33382 bytes SHA256
942ed48952c08d7241cb7c08e5ee6d64a5622d3986e7d1945905b9c5956b3686.
HEAD local 83cd76a7d0815488c91b9722c719b4d09e778c09 igual remoto.
BATCH_COMPLETED a5history-20261119121535-76c2eeb6,
a03-history-v12-final-20261119-091533.json, V12 pin
43372c6fe04ae12e5735e7b932d98a53a114ee0f5eb44d06fa5bea86a465b081.
120 retornados/117 aceitos e novos, 3 missing_metrics,
12 páginas; stone +38 (144), institutolojasrenner
+39 (68), abfoficial +40 (71); todos continuation_available.
Reauditoria 5 relatórios/16 runs, 621 retornados,
565 aceitos/novos, 44 too_recent, 12 missing_metrics,
63 páginas, 16/16 audit_valid, zero duplicatas,
refresh, unsupported_format ou invalid_metadata.
Corpus 1065→1630 únicos (+53,05%), 21→29 observados,
90,98% aproveitamento de aquisição, 0 admissões.
Snapshot 2026-11-19T12:16:01.660261+00:00:
78/80 reservas, 10 identity + 17 runs x4 (1 falho
OAuth), saldo 2, zero slots history/identity. 30
grants ativos verificados, 29 com registros,
28 continuation, 1 frontier_unconfirmed, 1 no_checkpoint,
21 perfis formalmente registrados; gap documental 8.
Gap bruto 370 posts e 1 perfil, mínimo otimista 10
runs/40 unidades antes de identidade. Ingestão inativa,
sem execução autorizada pelo snapshot.
RECOVERY_INSPECTION: lease null, 0 falhas A5 pendentes,
órfãos/reservas/quarentena, auth RESET_UNVERIFIED
não bloqueado, expiry UNKNOWN não bloqueante.
verify_zero_spend PASS invariantes locais (não auditoria
de fatura). BACKUP_RESTORE_VERIFIED
2026-11-19T12:16:05.501470+00:00, backup
a03-daily-final-20261119-091604.sqlite3, SHA256
cc7f5399c368a59c9ad3435f43e32f6e2280226240d1af647c61de2808adf5a5,
14991360 bytes, backup 641ms/drill 390ms.
Integrity/FK ok, inventário/conteúdo lógico iguais,
0016, writers parados atestados, restore descartável.
1630 content_items/ingestion_records/rubric_assessments,
1734 snapshots, 29 creators/checkpoints, 21 corpus_profiles,
70 runs, 30 grants, 3614 events/outbox, 0 scientific_reviews
e source_research_contexts (contextos DEC-018 por eventos
são separados), sete tabelas A02 vazias. Sem restore live.

A03.5 offline: antes de registrar os oito perfis V11/V12,
estender mapas documentais SECTORS/TYPES com os oito
estratos observados. Decisão de implementação: setor
amplo a partir do rótulo amostral (travel/ERP services,
food safety food, fashion/circular fashion commerce,
cosmetics beauty, franchise/growth cross_sector no
contexto e other na análise); creator_type_candidate
other para todos, business_size unknown, nenhum rótulo
por post. Nenhuma alteração dos 21 mapeamentos anteriores,
nenhum aumento de escopo, gates ou inferência legal.
Oito casos adicionados à parametrização existente
test_expanded_sampling_context, ainda não executados
pelo assistente. Não registrar antes da aprovação focal.

Próximo: nenhum novo acesso Meta neste dia UTC.
Com backup pré-escrita já verificado, escritores parados,
mesmo tenant/viewer e V12, executar testes focais,
preview lexical/registration_plan e readiness.
Esperado 8 REGISTER e 21 ALREADY_REGISTERED, sem
conflitos; conferir antes da mutação. Registrar
sampling_profiles por admin autenticado via bridge,
sem contexto ou admissão automática. Depois plan-contexts
esperado 8 PROVISION e 21 ALREADY_PROVISIONED se eventos
anteriores ativos; não pressupor contagem, verificar.
Só provisionar contextos se todos actions permitidos.
Contextos são eventos DEC-018 de escopo offline, não
human reviews nem autorização mídia. Atualizar readiness,
pilotos e ranking com pin V12 e partição atual; relatórios
V10 antigos não reutilizáveis como evidência de V12.
Sem nova aprovação institucional, token debugger,
mídia, gastos, merge ou liberação de gates.

```powershell
git pull --ff-only
$py = Join-Path $env:CONDA_PREFIX "python.exe"
$manifest = "artifacts/private/bd_manifest_a6_v12.json"
& $py -m pytest -q --tb=short tests/test_discovery_audience_signals.py tests/test_discovery_corpus_readiness.py tests/test_discovery_contextual_integration.py
if ($LASTEXITCODE -ne 0) { throw "Regressao documental bloqueada" }
& $py scripts/verify_zero_spend.py
if ($LASTEXITCODE -ne 0) { throw "Zero spend falhou" }
& $py -m scripts.a6_corpus_bridge --manifest "$manifest"
if ($LASTEXITCODE -ne 0) { throw "Previa bloqueada" }
& $py -m scripts.a6_corpus_readiness --manifest "$manifest"
```
Conferir registration_plan e readiness antes de
registrar; enviar agregados, não IDs/credenciais.


### A03.5 — regressão documental aprovada, registro e escopo local planejados

Console operador 47589 bytes SHA256
e37c18a18aab0eeac55e792cfae0b6c0f617754fd445fd4e4d1cb2d823265255.
51 PASS em 2,98s (audience_signals, corpus_readiness,
contextual_integration), verify_zero_spend PASS.
HEAD local não impresso; remoto 41d14f5 confirmado.
AUDIENCE_SIGNALS_PLANNED 2026-11-19T12:23:34.870032+00:00,
CORPUS_READINESS_PLANNED 2026-11-19T12:23:39.790502+00:00,
pin V12 43372c6fe04ae12e5735e7b932d98a53a114ee0f5eb44d06fa5bea86a465b081.
1630 registros/IDs únicos, 29 perfis observados, 0 fora
do manifesto, 29 TECHNICAL_SCOPE_MATCHED, 63 runs
completos não vazios auditados, 0 completed runs sem
trace válido. Partição readiness: 281 NONPRIMARY_FORMAT,
1 CAPTION_UNAVAILABLE, 1348 CAPTION_AVAILABLE_FOR_ASSESSMENT,
zero demais bloqueios. Não confundir 1349 primários
no readiness com 1063 tecnicamente elegíveis no card
canônico pré-registro; este exclui 335 posts dos oito
perfis não registrados antes de excluir 232 formatos.
21 perfis registrados, 21 contextos documentais ativos
por eventos, 1063 posts técnicos com contexto, 0
contextos revisados/decisões científicas. 9 sinais
lexicais explícitos (Sebrae 7, Aliança 1, CDL-BH 1),
63 mention_only, 1276 abstain, total 1348; não inferir
negativos, precisão ou targeting confirmado.
Registro planejado 8 REGISTER, 21 ALREADY_REGISTERED,
zero conflitos: abavnacional, abfoficial, agisaalimentos,
amarefashiongo, andraeltec, casa.artemisia.escola,
endeavorbrasil, institutolojasrenner. Mapeamentos
V11/V12 confirmados. Nenhuma mutação ou rede nos previews.

Próximo: com todos writers parados e backup diário
já verificado (se houve outra mutação relevante após
backup, renovar backup), mesmo tenant/viewer/V12,
registro autenticado local via --register-profiles.
Esperado SAMPLING_PROFILES_REGISTERED 8 novos/21
existentes, 0 contextos e admissões; se divergência,
parar e inspecionar. Depois --plan-contexts, projetar
somente username/action e contagens (context bruto
contém IDs, não compartilhar). Esperado 8 PROVISION,
21 ALREADY_PROVISIONED, confirmar sem conflito;
somente então --register-contexts. Escopos locais
DEC-018 por eventos auditados, não tabelas de revisão,
não nova aprovação institucional. Reavaliar readiness:
29 registros, 0 excluded_unregistered, 1349 posts
tecnicamente elegíveis se estado inalterado, 1348
legendas, 29 contextos ativos após provisionamento.
Não afirmar números antes da saída. Backup pós-registro
e contexto. Nenhuma consulta Meta, sem mídia, sem
mudança de credencial/expiry/gates. Ainda 78/80 reservas
e 0 slots no dia 19/11. Atualização documental apenas.

```powershell
git pull --ff-only
$py = Join-Path $env:CONDA_PREFIX "python.exe"
$manifest = "artifacts/private/bd_manifest_a6_v12.json"
& $py -m scripts.a6_corpus_bridge --manifest "$manifest" --register-profiles --confirm-all-ingestion-stopped
if ($LASTEXITCODE -ne 0) { throw "Registro bloqueado" }
$planJson = & $py -m scripts.a6_corpus_bridge --manifest "$manifest" --plan-contexts
if ($LASTEXITCODE -ne 0) { throw "Plano de contextos bloqueado" }
$contextPlan = $planJson | ConvertFrom-Json
$contextPlan.sources | Select-Object username,action | Format-Table
$contextPlan | Select-Object status,scoped_sources,sources_to_provision,scientific_admissions | ConvertTo-Json
```
Se registro e plano confirmados e todos actions
PROVISION/ALREADY_PROVISIONED:
```powershell
& $py -m scripts.a6_corpus_bridge --manifest "$manifest" --register-contexts --confirm-all-ingestion-stopped
if ($LASTEXITCODE -ne 0) { throw "Contextos bloqueados" }
& $py -m scripts.a6_corpus_readiness --manifest "$manifest"
if ($LASTEXITCODE -ne 0) { throw "Readiness bloqueado" }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
& $py -m scripts.a6_backup_restore_drill --output-name "a03-post-context-v12-$stamp.sqlite3" --confirm-all-writers-stopped
if ($LASTEXITCODE -ne 0) { throw "Backup bloqueado" }
```
Enviar resumos sem IDs/segredos. Depois piloto contextual
e grounded rubric atuais, revisão de ranking e A04.


### A03.5 — oito perfis registrados; escopos locais prontos para provisionamento

Operador confirmou SAMPLING_PROFILES_REGISTERED:
8 novos, 21 já registrados, plano exatamente os oito
V11/V12, sem conflito; 0 source_contexts_created,
0 scientific_admissions, external_data_accessed=false,
database_mutated/operation_mutated/sampling_registry_mutated/
identity_session_written=true. Total 29 perfis formalmente
registrados (a confirmar no novo data card). Não repetir
registro. CAPTION_RESEARCH_PLANNED: 29 linhas, 21
ALREADY_PROVISIONED e 8 PROVISION, zero outras ações,
0 admissões. Escopos anteriores preservados. HEAD local
não impresso; remoto cceb91f confirmado. Não afirmar
provisionamento concluído antes da execução.

Próximo: mesmo V12/tenant/viewer, escritores parados,
backup diário anterior preservado; executar registro de
contextos via admin autenticado, esperado 8 novos/21
existentes. Reavaliar readiness (esperado 29 registrados,
29 contextos documentais ativos, 1349 técnicos primários,
1348 legendas, 0 excluded_unregistered, 0 científico),
confirmar escopo local com a6_audience_contextual sem modo
execute, global classify deny preservado. Backup pós
contextos, verify_zero_spend. Se qualquer divergência,
parar e inspecionar sem repetir writes. Nenhum uso Meta,
mídia, nova aprovação DEC-018 ou exigência de data token.
Contextos documentais não são revisão humana.

Depois, com backup e preflight aprovados, executar
grounded audience V12 em tapi-s1 diretamente ativado,
checkpoint local previamente fixado
C:\Models\tapi\gliner25-multi-decide, sem download,
flags HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE/HF_DATASETS_OFFLINE=1,
TAPI_SYSTEM_ONE_ENABLED=1 temporária (restaurar a 0).
Usar --execute --grounded --manifest V12
--confirm-all-ingestion-stopped --report-name
a03-grounded-v12-<stamp>.json. Gate sintético repetido
no fluxo; não forçar se GROUNDED_BENCHMARK_NOT_PASSED.
Esperar 1348 candidatos se partição inalterada, não
inferir performance científica ou novos labels. Guardar
relatório privado, modelo/hash/manifesto/partição.
Depois avaliar rubrica em dois pares disjuntos (tema/CTA,
prova/oferta), mesmo checkpoint e partição, antes de
ranking exploratório V12. Não reutilizar resultados V10
nem persistir novos drafts sem suporte. Commit somente
documental; nenhuma execução local/DB/Meta/modelo pelo
assistente. Sem merge/gates.


### A03.5 — consolidação V12 confirmada; runtime semântico ausente

Console operador 45272 bytes SHA256
4a21e160af74bf4c6cbcea500b79c181ca16337b2369f3029b7d17962f636d0f.
CAPTION_RESEARCH_PROVISIONED 8 novos/21 existentes,
offline_bd_caption_candidate_classification, 0 humanos/
admissões, sem rede; DB/operation/identity session escritos.
CORPUS_READINESS_PLANNED 2026-11-19T12:29:17.091662+00:00,
V12 pin 43372c6fe04ae12e5735e7b932d98a53a114ee0f5eb44d06fa5bea86a465b081:
1630 únicos, 29 perfis observados e registrados,
29 grants/technical verification, 29 contextos
documentais ativos por eventos, 1349 posts técnicos
primários com contexto, 1348 legendas disponíveis,
1 indisponível, 281 não primários, 0 fora manifesto/
unregistered/trace missing/invalid metrics/other blockers,
63 runs não vazios auditados, 0 sem trace válido.
Setores técnicos commerce291 food133 services470
beauty85 other370. 0 elegíveis científicos, 0 reviews
e contextos humanos; déficit científico 2000/30.
Gap técnico primário 651 posts/1 perfil; gap bruto
370/1 não equivale a elegibilidade primária. Não
alterar critérios para atingir contagem. Preflight
CONTEXTUAL_READINESS local_caption_scope_allowed=true
29 fontes; classification_scope_allowed=false,
EXTERNAL_DENIED_PENDING_VERIFIED_GRANT preservado.
verify_zero_spend PASS invariantes locais.

BACKUP_RESTORE_VERIFIED 2026-11-19T12:29:25.397606+00:00,
a03-post-context-v12-20261119-092924.sqlite3,
SHA256 211000248f0913a0f24a0b0a4a67c6c7b5d272999898c20a1a38bdaace380b8d,
15020032 bytes, backup734ms/drill406ms, integrity/FK
ok, inventário e conteúdo lógico equivalentes, 0016,
restore descartável, escritores parados atestados.
1630 content/ingestion/rubric, 1734 snapshots,
29 creators/corpus_profiles/checkpoints, 30 grants,
70 runs, 3630 events/outbox (+16), 41 identity sessions,
75 audit; 0 scientific_reviews/source_research_contexts
(tabelas humanas), sete tabelas A02 vazias. Não repetir
registro/contextos/backup sem alteração relevante.

Inferência: conda activate tapi-s1 retornou
EnvironmentNameNotFound; PowerShell permaneceu em
tapi-asr-recovery. Execução --execute --grounded
V12 retornou BLOCKED BD_CONTEXTUAL_LOCAL_ERROR,
stage checkpoint_validation, RuntimeError,
SAFETENSORS_REQUIRED_FOR_CHECKPOINT_VALIDATION,
0 candidates, sem mutação/rede. Escopo local 29
true. Causa imediata import safetensors indisponível
no interpretador usado; não prova pesos inválidos.
HEAD local não impresso, remoto 718b832 confirmado.
Flag S1 restaurada a 0. Nenhum resultado de inferência.

Recuperar runtime isolado, não instalar GLiNER no
tapi-asr-recovery que passou regressão audiovisual.
Inspecionar conda info --envs e espaço em disco,
reaproveitar ambiente semântico compatível se houver;
caso ausente, criar tapi-s1-recovery com Python 3.11.18
e pip, instalar extra existente .[system_one_local]
e versões previamente reportadas torch 2.15.0,
gliner2 2.1.0, transformers 5.22.1, safetensors 0.8.0.
Verificar disponibilidade de pacotes antes de trocar
versões; não prometer reprodução integral sem lock
transitivo. Preferir cache/artefatos locais quando
disponíveis; downloads públicos de dependências só
se necessários e sem cobrança, nunca baixar pesos
novamente nem usar prepare checkpoint downloader.
Não remover ambientes, alterar banco, secrets ou
política. Validar pip check/imports/versões, validar
checkpoint existente por validate_local_checkpoint
com hash publicado e revisão e173bca1f0c4217d7a55b3b0c705d5ece8a0218d;
não contornar verificação. Usar caminho absoluto do
python do ambiente confirmado; não continuar após
falha de ativação. Regressão focal semantic e smoke/
gate grounded antes de processar legendas reais.
Flags HF offline e S1 temporária, novo relatório
privado exclusivo. Se falha, parar e enviar código
agregado; nenhum novo acesso Meta ou registro.
Commit exclusivamente documental; nenhum pacote
instalado ou inferência executada pelo assistente.


### A03.5 — smoke semântico recuperado; regressão e gates pendentes

Operador reportou CONTEXTUAL_SYNTHETIC_SMOKE, relatório privado
a03-s1-recovery-smoke-20261119-094220.json, 6 legendas sintéticas,
model_load_ms=33114.425, torch 2.15.0, gliner2 2.1.0,
transformers 5.22.1, safetensors 0.8.0. Revisão
e173bca1f0c4217d7a55b3b0c705d5ece8a0218d, pesos SHA256
9efe0f88c99f2aa794452e9559dc60e98d60d9fa2bf1b60cf2710411b6da5b4e.
HEAD local, nome do ambiente e pip check não impressos; remoto
ecd49bc confirmado. Carregamento e execução sintética demonstrados;
não afirmar recuperação integral/reprodutibilidade ou qualidade.
V1: 2 sinais explícitos negativos, 1 menção incerta positiva,
3 sem sinal (2 positivos/1 negativo), zero abstenções. Não promover V1.
Zero targeting, revisão humana, admissão, acesso externo ou mutação;
global classification deny preservado. Não repetir smoke se mesmo
runtime/checkpoint confirmados.

Próximo: confirmar interpretador semântico isolado e checkout limpo,
pip check, A00 --profile semantic, benchmarks --audience-benchmark
--grounded e --rubric-grounded-benchmark com modelo existente,
flags HF offline e S1 temporária. Os benchmarks standalone podem
retornar exit 0 com gate falso: inspecionar engineering_gate_passed
e field_engineering_gate dos quatro campos (tema/CTA/prova/oferta).
Não inferir aprovação de tom. Se audience PASS, executar V12 apenas
com readiness/escopo/ingestão parada confirmados e pin V12 inalterado;
pilotos somente para pares com gates aprovados, cada fluxo repete seu
benchmark. Se falha, preservar relatórios e diagnosticar sem
flexibilizar critérios. Zero rede Meta, mídia, gasto ou nova admissão.
Último full strict permanece 20aea11. Atualização exclusivamente
documental; sem merge ou gates globais.


### A03.5 — ambiente semântico confirmado; runner sem pytest

Operador 40df63a0a1abadb5ba48fd272fe00f29cefd28b3,
tree 219804006132d98acb28d809e14b81b751e29119,
tapi-s1-recovery/Python 3.11.18, pip check sem conflitos,
imports torch/gliner2/transformers/safetensors OK.
A00 semantic a03-semantic-recovery-20261119-101836-904:
legacy_gate0 e zero_spend exit 0, checkout unchanged,
matrizes 204 IMP/543 edges/23 CAP/18 DEC/7 gates,
121 módulos, 106 testes Python, 5 Node, 16 migrações.
pytest package=null, subprocess exit 1 em 0.078s,
pytest=null (sem JUnit), checks_passed=false. Log SHA256
242ac110f36b4074a2aeb8c20866d894f2cbf7e2cc5bf0743a6553ee5c112765.
Causa provável ausência do pytest; confirmar log original
antes de instalar. Não interpretar como falhas de casos.
pyproject dev exige pytest>=8,<10; nove arquivos do perfil
importam pytest. Instalar apenas essa dependência no
tapi-s1-recovery, sem upgrade de modelos/runtime ou extra
audiovisual. pip check e versões novamente, runner semantic
no novo HEAD limpo com nome exclusivo; verificar zero
falhas/erros/skips antes de benchmarks. Se outra falha,
diagnosticar log sem repetir smoke ou alterar critérios.
Preservar relatório anterior. Nenhum benchmark, corpus,
DB, rede Meta, mídia, merge ou gate global. Atualização
exclusivamente documental; último full strict 20aea11.


### A03.5 — regressão semântica recuperada e aprovada

Operador HEAD 1ca426a24bc4200728835f24f8907c645cbc0e4f,
tree d9604097489502f6c58639850a3408dfeae2ff0f,
checkout limpo e inalterado, tapi-s1-recovery/Python 3.11.18.
pytest 9.2.0 instalado, torch 2.15.0/gliner2 2.1.0/
transformers 5.22.1/safetensors 0.8.0 preservados.
A00 semantic a03-semantic-recovery-20261119-102108-214:
189/189 PASS, 0 FAIL/ERROR/SKIP, pytest 12.181s,
checks_passed=true, legacy_gate0 e zero_spend exit 0.
JUnit SHA256 3a4fbbc1e72dc90eb952827745dc012f857c106d73bb10efcc61727a88921a97,
pytest.log SHA256 6c52c9398d578a21b6fa8c72d3489c0eed2de393907e628fabd6e6f636cc809e.
121 módulos Python, 106 arquivos teste Python, 5 Node, 16 migrações.
204 IMP/543 edges/23 CAP/18 DEC/7 gates preservados.
Sem forwarding do banco operacional ou credenciais.
Correção do ambiente demonstrada; não é full regression,
não é benchmark de modelo, não é avaliação científica.
Último full strict aprovado continua 20aea11.

Próximo: sem repetir smoke/regressão de código idêntico,
executar benchmarks standalone sintéticos de audiência grounded
e rubrica grounded com checkpoint/revisão/hash existentes,
mesmo ambiente isolado, flags offline, relatório privado
exclusivo por benchmark. Inspecionar gates explícitos,
não apenas exit code (standalone pode retornar 0 com gate false).
Audiência exige zero positivos indevidos por split e
>=5/10 development, >=3/6 additional; rubrica por campo
e split exige >=2 candidatos esperados, zero incorretos,
>=50% corretos. Prosseguir V12 apenas nos fluxos aprovados,
com escopo local, manifesto pinado e ingestão parada.
Nenhuma alteração de código, banco, direitos ou gates;
sem mídia, Meta, gasto ou merge. Atualização documental.


### A03.5 — gates grounded reproduzidos; piloto V12 autorizado pelo escopo existente

Operador HEAD 13da7186711be9bd88235ce0cb4647262b678500,
checkout limpo, tapi-s1-recovery, versões e checkpoint preservados.
Console 107343 bytes SHA256
fb15be01ac9d470ae93eefdc93a082db731f76562939e0d522a5396b33fffcc0.
Relatórios privados a03-s1-audience-benchmark-20261119-102853-624.json
e a03-s1-rubric-benchmark-20261119-102853-624.json.
Revisão e173bca1f0c4217d7a55b3b0c705d5ece8a0218d,
pesos 9efe0f88c99f2aa794452e9559dc60e98d60d9fa2bf1b60cf2710411b6da5b4e.
Warnings de tipo de modelo Transformers e depreciação torch.jit.script,
sem falha de carregamento; não suprimir nem alterar stack neste passo.
Audiência bd-audience-grounded.v1: 48 casos, híbrido 8/10 e 4/6
positivos corretos, zero positivos indevidos nos dois splits, 35/48
exatos, 31 abstenções, engineering_gate_passed=true. Regra isolada
16/16 positivos, 45/48 exatos, zero positivos indevidos; hipótese
IMP-129 para avaliação adicional, não promoção automática.
Rubrica bd-caption-rubric-grounded.v1: 62 casos, híbrido nos quatro
campos aprovados 52/52 exatos (inclui abstenções), tema 8/8+3/3,
CTA 5/5+3/3, prova 2/2+2/2, oferta 3/3+2/2 candidatos corretos;
zero candidatos errados. Tom FAIL, 0/4+0/2 corretos e 10/10
abstenções; não incluir nos pilotos. 5/5 gates necessários PASS,
não gold independente, não validação científica. Ambos synthetic_only,
database_mutated=false, external_data_accessed=false, zero admissões,
classificação externa global deny preservada. Último full strict 20aea11.

Próximo: mesmo V12, tenant/viewer, backup pós-contextos preservado,
todos escritores/ingestão parados; confirmar readiness 1630/29,
1348 legendas, pin 43372c6fe04ae12e5735e7b932d98a53a114ee0f5eb44d06fa5bea86a465b081,
local_caption_scope_allowed=true/29 e global deny. Não trocar banco
ou manifesto, não solicitar nova aprovação institucional.
Executar --execute --grounded e dois --rubric-grounded-pilot
pares disjuntos tema/CTA e prova/oferta, serialmente, com flags
HF offline e S1 temporária; cada comando repete seu gate.
Relatórios privados exclusivos; validar status, pin, revisão/hash,
1348 assessed_captions em cada e zero mutação/admissão. Parar em
falha ou divergência. Não enviar private_evidence ou conteúdo bruto.
Reconciliar partições e snapshots via ranking/contraste existente
antes de atualizar replay/UI; nenhuma reutilização de V10.
Sem nova coleta no orçamento UTC esgotado, mídia, cobrança,
alteração de política, merge ou gate global. Commit documental.
