# A11 / CAP-005/023 — convergência rápida por duas frentes

**Escopo:** incremento de desenvolvimento empilhado sobre PR #71, sem merge na main, provedor externo, migração operacional, publicação, compra ou autorização de produção. Base v6.1 intacta. DEC-008=OPEN, G0–G6=BLOCKED, IMP-131=BLOCKED.

## Frente 1: caminho crítico verificável, não percentual inventado

scripts/a11_architecture_frontier.py lê as matrizes oficiais BACKLOG_UNICO_IMPORTAVEL.csv, DEPENDENCIAS.csv e MATRIZ_CAPACIDADES.csv, valida IDs, tipos de dependência, igualdade entre as arestas e a coluna dependencies, sink IMP-131, aciclicidade e vínculos CAP. Calcula a cadeia de maior soma de horas históricas e agrupa workstreams, com SHA-256 de entradas. Emite PLANNING_FRONTIER_ONLY: nunca alega tarefa concluída, gate, ciência ou deploy.

Verificação local com as matrizes espelhadas do ZIP v6.1: 204 IMP, 23 CAP, 543 dependências, 39 camadas, soma histórica de 1.561 horas e maior cadeia de dependências de 301 horas. Ela inclui IMP-071→073→074→075 antes do aceite IMP-131. Testes unitários do analisador: 6/6 PASS, usando fixtures locais descartáveis. Não é prova de que o checkout completo está verde.

## Frente 2: exercício vertical real das interfaces existentes

tests/test_architecture_vertical_synthetic.py utiliza app segura, sessão autenticada e SQLite descartável, sem provider. Cobre fonte e snapshot sintéticos, modo analisar e recomendar com checkpoints reais; requisição separada de brief autoral por POST /v1/agent/creative-drafts, criação transacional de DesignDocument e duas versões com If-Match, consulta e rechecagem; também exige que gerar_criativo ABSTAIN sem escrita autônoma. O texto adversarial presente na legenda não pode controlar o fluxo.

**Limite:** o grafo não gerou o brief e não autorizou o Studio; a escrita ocorre por outro endpoint autenticado e com o PEP habitual. Não existe integração A02 audiovisual real, comprovação científica ou exportação no teste. Arquivo compilado em Python; pytest integrado NÃO EXECUTADO neste ambiente sem checkout íntegro.

## Frente 3 independente: DEC-008

Resultado Windows anterior: 49/49 testes com LangGraph real em SHA 3d099e7. Os quatro testes novos de falha injetada do SqliteSaver no HEAD 75e0229 ainda precisam de execução Windows. Não inferir exactly-once, atomicidade entre bancos ou autorização externa.

## Comandos no checkout limpo da nova branch

    $env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
    python -m scripts.a11_architecture_frontier
    python -m pytest -q -rs tests/test_a11_architecture_frontier.py
    python -m pytest -q -rs tests/test_architecture_vertical_synthetic.py
    python -m pytest -q -rs tests/test_dec008_langgraph_saver_failure_actual.py
    python -m scripts.a05_python_source_preflight
    python scripts/verify_zero_spend.py
    python docs/base_atemporal/ferramentas/validar_espelho.py

Após resultados PASS, incluir a suíte vertical no A11 fixado ao HEAD, executar A11 integral e a regressão total no mesmo SHA, sem diminuir verificações. Manter R$0 e controle de rights.

**Próximas implementações funcionais:** A02→E1→A05 com prova de vinculação; modo gerar_criativo com autoridade por operação; exportação Studio com proveniência; ciência e operações G0–G6.
