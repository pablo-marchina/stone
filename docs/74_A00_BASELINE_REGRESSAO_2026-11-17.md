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
