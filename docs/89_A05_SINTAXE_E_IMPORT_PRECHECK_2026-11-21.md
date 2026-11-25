# A05 — bloqueio de importação e preflight Python 3.11

> Incremento corretivo na pilha de PRs da Base Atemporal v6.1. Não modifica o Plano Único, DEC-018, 23 CAP, 204 IMP, 543 dependências ou critérios G0–G6 / IMP-131. Sem autorização de produção.

## Falha encontrada no código atual

O método `CreativeReferencePEP.require_for_atomic_draft` em `src/tapi_gate0/creative_reference_pep_a05.py` continha **duas ocorrências de `*` como delimitador de argumentos somente-nomeados** na mesma assinatura. O Python emite `SyntaxError: * argument may appear only once`, impedindo a importação do módulo e a composição da aplicação que depende dele. Isso invalida qualquer alegação de que o caminho integrado do PEP/Studio desse commit pré-correção estava funcionando ou homologado.

A correção elimina o segundo marcador, preserva a interface de keyword-only para `token`, `tenant`, `actor`, `document_id`, `grant_ids` e `audit_event_type`, sem alterar a assinatura dos contratos de direitos. Também foi incluída verificação de **transação SQL ativa** antes do processamento de grants assinados e um teste negativo para chamadas sem transação.

## Preflight independente

`scripts/a05_python_source_preflight.py` usa apenas biblioteca-padrão, sem carregar classes do Stone. Faz `ast.parse(..., feature_version=(3,11))` em arquivos `.py` nas árvores `src/tapi_gate0/`, `scripts/`, `migrations/versions/` e `tests/`, cobrindo erros de sintaxe de Python 3.11 mesmo quando o operador estiver usando um interpretador mais recente.

- Negar se faltar alguma árvore ou fonte crítica, em vez de tratar diretórios incompletos como PASS.
- Não executa imports, banco, providers, mídia, workflows pagos, Git, concessão de chaves ou migrações.
- Emite JSON com schema `stone-python-source-preflight.v1`, arquivos inspecionados e códigos de erro; saída 0 somente para sintaxe e estrutura verificadas; saída 2 quando bloqueado.
- Campo `deployment_authorized` é **sempre false**. Um PASS não prova importações dinâmicas, comportamento de autorização, testes de API, integração com PostgreSQL, permissões reais ou os gates.

Executar em checkout completo **no SHA desta PR**, antes da suíte:

```powershell
python -m scripts.a05_python_source_preflight
python -m pytest -q -rs tests/test_a05_python_source_preflight.py tests/test_a05_import_compilation_gate.py tests/test_creative_reference_pep_a05.py tests/test_creative_reference_registry_a05.py tests/test_agent_atomic_draft_a05.py tests/test_a11_focal_evidence_packet.py
python scripts/verify_zero_spend.py
```

## Evidência nesta execução

1. Reproduzido localmente o `SyntaxError` com assinatura equivalente à versão anterior e demonstrado que a assinatura corrigida é válida com `ast.parse`. Não é prova da importação real de todos os módulos.
2. **4 PASS** nos testes locais isolados de `tests/test_a05_python_source_preflight.py` com arquivos descartáveis: fonte válida sem executar código, dois marcadores `*`, fonte crítica faltante e sintaxe Python 3.12 sob gramática 3.11.
3. Os **dois arquivos do preflight publicados no GitHub** foram verificados por comprimento, soma de codepoints e checksum ponderado, exatamente equivalentes aos testados localmente.
4. Execução do preflight contra diretório parcial de desenvolvimento devolveu `BLOCKED`, como previsto. **Não é falha do repositório completo**, que não estava montado no ambiente local.
5. **Suíte integrada A05/A11/A00 no novo HEAD NOT_RUN**. A11 Python A05/A07 espera **265 casos**, sem atribuir 265 PASS. Nenhum gate é liberado nem produção autorizada.

## Próximo gargalo

A importação do PEP deixa de ser bloqueada por esta sintaxe, mas ainda é necessário executar o teste de importação real `test_a05_import_compilation_gate.py`, os E2E com grants de fixture e a regressão integral de todas as PRs empilhadas. Em seguida, corrigir quaisquer falhas concretas de autorização/Studio e prosseguir A02 Strict, corpus/ciência, agentes 3 modos, Studio final, recuperação/observabilidade e 7 gates G0–G6/IMP-131. Não reutilizar PASS históricos de outro SHA; R$0 e nenhuma migração/deploy até homologação.
