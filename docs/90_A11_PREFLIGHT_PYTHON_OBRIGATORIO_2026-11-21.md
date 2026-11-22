# A11 — preflight Python 3.11 obrigatório no recibo focal

> Base Atemporal v6.1. Incremento fail-closed de validação local, **sem autorização** de produção, merges, rights, serviços externos, gastos ou liberação de G0–G6/IMP-131.

## Defeito evitado

O módulo A05 PEP tinha uma assinatura inválida que impedia importações (`*` duplicado). A PR anterior acrescentou `scripts/a05_python_source_preflight.py` para detectar sintaxe inválida **offline**, mas a execução não era obrigatória no pacote focal A11. Portanto, um operador poderia tentar registrar os resultados focais sem ter rodado a varredura de sintaxe.

## Alteração no runner A11

A ordem obrigatória após validar HEAD do Git e SHA-256 de fontes:
1. `scripts/verify_zero_spend.py` — cheque de custo zero; se falha, não executa nada mais.
2. `python -m scripts.a05_python_source_preflight` — parse Python 3.11 de fontes, scripts, migrations e testes, sem imports ou side effects.
3. pytest do grupo A05/A07, pytest A07 CDP, Node TAP e Chrome parity — somente após os dois preflights bem-sucedidos.

O runner A11 só aceita como pré-requisito sintático uma **única saída JSON parseável** com `schema_version=stone-python-source-preflight.v1`, `status=PASS`, `python_grammar=3.11`, pelo menos **300 arquivos** inspecionados, `errors=[]`, `deployment_authorized=false` e código de saída zero. Um fragmento de texto `PASS`, JSON incompleto, escopo reduzido, erro oculto, saída não zero ou campo indicando deploy gera `BLOCKED_PYTHON_SYNTAX_PREFLIGHT` e interrompe antes do pytest. O runner não grava logs brutos nem qualquer permissão operacional.

Os 300 arquivos são um **mínimo de sanidade da descoberta** (a árvore desta PR já contém mais de 300 fontes Python); não substituem o escopo de diretórios obrigatório do preflight, nem a confirmação integral de files/SHAs pelo checkout. Mudar o limite ou interpretar parsing bem-sucedido como aprovação é proibido.

## Testes adicionados

- Um caso que verifica interrupção depois dos dois preflights e antes de qualquer pytest, Node ou Chrome quando há sintaxe inválida.
- Cinco entradas maliciosas ou incompletas para o parser de recibo: texto PASS sem JSON, JSON incompleto, contagem insuficiente, `deployment_authorized=true`, processo com saída não zero.
- Ajuste do mock de execução normal para simular a nova verificação e exigir a sequência de seis etapas.
- A expectativa do pytest focal A05/A07 **permanece 265 casos**, pois os testes novos pertencem à suíte do próprio runner A11, não ao grupo de testes focais.

**Estado de prova:** alterações escritas e revisadas no GitHub; a regressão A11 no HEAD desta PR não foi executada no checkout completo. Nenhum PASS de testes históricos foi atribuído ao HEAD atual. O preflight isolado havia passado 4 testes de componente no incremento anterior, mas isso não equivale a aprovação integrada.

## Validação obrigatória antes da integração

```powershell
git rev-parse HEAD
python -m scripts.a05_python_source_preflight
python -m pytest -q -rs tests/test_a05_python_source_preflight.py tests/test_a05_import_compilation_gate.py tests/test_a11_focal_evidence_packet.py
python scripts/verify_zero_spend.py
python docs/base_atemporal/ferramentas/validar_espelho.py
```

Executar então o runner focal completo com `--expected-head` exato, um arquivo novo de recibo, e todos os testes A00/CT/sci/ASR nativos que compõem os gates. Mesmo com todos os diagnósticos focais passando, o retorno será `FOCAL_DIAGNOSTICS_VERIFIED_NO_GATE_RELEASE`: **G0–G6 e IMP-131 continuam bloqueados**. Sem deploy até arquitetura integral e homologação independente. Teto R$0 e DEC-018 mantidos.
