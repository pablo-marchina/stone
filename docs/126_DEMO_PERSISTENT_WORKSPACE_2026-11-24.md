# Demonstração — workspace persistente e biblioteca recuperável

Base PR #90 aaa1fa229d12e9ce8c54680f620abd780de429a9. Incremento local de apresentação, não promoção operacional.

## Implementação
- --workspace recebe uma pasta exclusiva que ainda não existe ou um workspace previamente criado pelo launcher. O banco fica em demo.sqlite. O modo padrão continua temporário.
- A pasta recebe lock de sistema operacional (flock em Unix, msvcrt em Windows) mantido durante toda a sessão. A abertura concorrente é recusada. O banco recebe marcador SQL próprio com versão e SHA-256 dos dois relatórios projetados após inicialização bem-sucedida. Reabertura exige os mesmos relatórios e marcador; não adota um banco existente sem marcador. A verificação usa SQLite somente leitura antes de chamar o factory. Não é proteção contra adulteração deliberada por administrador local.
- Na retomada, a identidade e o corpus não são recriados. A senha original continua valendo. O banco, versões, eventos e artefatos armazenados permanecem na pasta. Não há importação automática de sessões temporárias anteriores.
- A biblioteca autenticada lista até 100 rascunhos textuais compatíveis com o editor simplificado e até 50 comprovantes de pares do relatório correspondente, quando ambos os documentos estão na lista. Abre a versão atual e permite baixar a proveniência original. O painel indica se o workspace é persistente ou temporário. Nenhuma aprovação de publicação.
- O projeto não deve usar pasta operacional, banco compartilhado ou serviço público. A pasta pode conter rascunhos e dados de identidade; não enviar ao GitHub. Para backup, parar servidor e copiar pasta inteira e relatórios em ambiente autorizado.

## Validação efetivamente executada nesta rodada
10 pytest PASS (3,37 s) em test_demo_workspace.py e test_studio_e1.py sobre o núcleo local recuperado do arquivo-fonte PR #79. Houve uma primeira falha de fixture por objective curto, corrigida e reexecutada. Verificadas persistência de identidade, login após nova inicialização do factory, versão 1 e versão 2 intactas, biblioteca com versão atual e isolamento de tenant, lock concorrente, rejeição de relatório diferente, banco sem marcador intacto e workspace incompleto recusado. Os três blobs novos testados foram conferidos. Não foi executada a regressão integral da PR #90/91 neste ambiente; o arquivo-fonte mais recente não está disponível localmente. O launcher e a UI modificados foram construídos sobre os arquivos exatos da PR #90 via GitHub. Adicionado test_persistent_launcher_recovers_pair_and_revision para ensaio integrado, ainda não executado. Windows/mvcrt, navegação e recuperação dos pares no browser ainda requerem ensaio.

## Executar no host
Antes de encerrar uma sessão temporária em andamento, exportar PNGs, relatórios e comprovantes. Usar a pasta nova exclusiva:
```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path "src"
$root = "C:\Users\Inteli\Documents\Projetos\stone\artifacts\private"
$workspace = Join-Path $env:USERPROFILE "Documents\Stone-Apresentacao"
python -m pytest -q tests/test_demo_workspace.py tests/test_demo_experiment_pairs.py
python -m scripts.demo_stone --video --av-report "$env:USERPROFILE\Downloads\stone_demo87_av.json" --technical-report "$root\a04-scope27-ranking-20261119-105137-669.json" --workspace "$workspace"
```
Abra http://127.0.0.1:8765/app/demo.html. Crie a senha na primeira execução e preserve-a. Crie os pares, edite, feche e reexecute o mesmo comando. A biblioteca deve recuperar os documentos sem rebootstrap. Se a pasta preexistir sem workspace, escolha outro nome; não apague nem reconfigure banco operacional. Use exatamente os mesmos relatórios ao reabrir.

R$0 de chamadas externas, sem deploy, merge, coleta ou liberação de gates. PR #90 do operador confirmou persistência de par histórico em sessão temporária no Windows; não é evidência de retomada da nova PR.
