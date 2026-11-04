# DEC-017 E1.4 — Políticas conservadoras de CTA e abstenção

**Estado:** laboratório offline experimental, PR dependente do E1.3 (#29). Não homologado, sem acesso externo, sem mudança de classificador institucional, sem selecionar política para produção. Gate 0B continua bloqueado.

## Justificativa

O E1.3 validado pelo operador no commit e044666a223fe3ba52a6f520ea2c0b0182a2f0a3 reportou 30/34 tipos de CTA suprimidos pela dependência de presença, com 4/34 mudanças do cabeçalho de presença e 1/34 do de tipo na ablação. Isso não comprova que os 30 tipos rejeitados estivessem corretos.

O E1.4 compara aceitação de CTA na **legenda observável**, não ausência de CTA no vídeo. Toda previsão negativa de presença no vídeo permanece proibida. Os rótulos autorais são sintéticos, não constituem gold independente.

## Dataset e procedência

São exatamente 34 exemplos artificiais pré-existentes (14 E1.2 e 20 E1.3), sem argumento para importar JSONL arbitrário. Os 34 rótulos autorais de ação afirmativa na legenda são fixos e separados do detector de regex. Seus grupos são:

| Subconjunto sintético | Casos | Interpretação |
|---|---:|---|
| Ação positiva única explícita | 14 | Uma ação afirmativa tipável no texto |
| Ação positiva misturada com proibição diferente | 3 | Uma ação afirmativa tipável, outra negada |
| Duas ações positivas | 1 | Presença textual, tipo único ambíguo |
| Apenas proibição | 5 | Não é instrução afirmativa de CTA na legenda |
| Apenas menção/uso metalinguístico | 4 | Não é instrução afirmativa de CTA na legenda |
| Indeterminado | 7 | Ausência de evidência conclusiva no texto |

Amostra pequena, sem revisão cega, sem representatividade e sem estimativa científica de FPR/recall.

## Braços pareados

| Nome no JSON | Interpretação |
|---|---|
| baseline_e1_original | Regras determinísticas originais, controle não modificado |
| rule_negation_e13 | Variante experimental com negação e metalinguagem |
| gliner_e1_original | Modelo GLiNER e gate de presença originais |
| gliner_e13_rule_assisted | Variante E1.3 de fallback por regra |
| e14_gliner_original_text_guard | Exige tipo positivo do adaptador e igual ao único CTA textual |
| e14_raw_type_text_agreement | Aceita tipo bruto apenas se igual ao único CTA textual não negado; presença textual positiva deve ser explícita, mesmo que o cabeçalho de presença do modelo não confirme |
| e14_raw_type_text_and_presence_agreement | A mesma concordância mais exigência de cabeçalho de presença positivo |

Os primeiros dois braços executam sem pesos; os demais requerem o checkpoint GLiNER2.5 local, SHA-pinned e opt-in. Os cinco braços usam **a mesma inferência real por caso** para assegurar comparabilidade, sem renomear fallback como acurácia pura do modelo.

## Métricas, denominações e limitações

1. Cobertura de presença/tipo: positivos aceitos / 34; abstenção = 34 - aceitos, apresentada separadamente.
2. Ações de tipo único: 17 referências textuais (14 puras + 3 mistas). Reportar acertos, erros, abstidos e recall **textual sintético**. Não inferir CTA no vídeo inteiro.
3. Nove negativos textuais: 5 proibições + 4 menções. Alegações positivas sobre esses casos são contadas como potenciais falsos positivos **na tarefa de legenda artificial**, não falsos positivos de vídeo ou de anúncios reais.
4. Precisão seletiva textual decidível: acertos de tipo nos 17 positivos únicos divididos por tipos aceitos nesses 17 mais os 9 negativos. Se nenhum tipo aceito, retornar null, não 100%.
5. Contar separadamente alegações de tipo nos 1 multiação e nos 7 indeterminados, sem rotulá-las como erro de vídeo.
6. Deltas de alegações em negativos, acertos positivos e abstenções ante controle E1. São comparações descritivas em dados sintéticos.

O JSON de resultado contém somente contagens, taxas, subtotais, digest do corpus sintético e metadados do checkpoint; nenhuma legenda, criador, URL privada ou credencial. Os marcadores de validação científica e produção são sempre false e a decisão é NO_PRODUCTION_POLICY_SELECTED.

## Execução local Windows / Miniforge

Preparar o checkout no HEAD do PR empilhado E1.4 e o ambiente com dependências existentes:

- python -m pip install -e ".[dev,system_one_local]"
- python -m pytest -q tests/test_system_one_e14.py
- python scripts/benchmark_system_one_e14.py --model baseline --output "$env:USERPROFILE\tapi-e14-baseline.json"
- $env:TAPI_SYSTEM_ONE_ENABLED = "1"
- python scripts/benchmark_system_one_e14.py --model both --model-dir "C:\Models\tapi\gliner25-multi-decide" --output "$env:USERPROFILE\tapi-e14-gliner.json"
- $env:TAPI_SYSTEM_ONE_ENABLED = "0"
- python -m pytest -q
- python scripts/check_gate0.py
- python scripts/verify_zero_spend.py

O modo GLiNER requer manifesto do checkpoint validado na E1.1. O runner fixa modo offline antes de carregar pesos e recusa salvar o relatório dentro do checkout.

## Critérios de aceite

- [ ] Tabela de 34 referências coerente, inalteradas as decisões E1 e E1.3.
- [ ] Testes E1.4 e comparação baseline aprovados no mesmo SHA.
- [ ] Comparação com checkpoint real aprovado e relatório inspecionado.
- [ ] Suíte completa, check_gate0.py e verify_zero_spend.py aprovados.
- [ ] Relatórios sem dados reais e resultados sem promoção científica.
- [ ] PR E1.3 integrado ou PR E1.4 retargetado após o merge; revisão de diff isolado.

**Proibido concluir superioridade científica ou produção a partir destas fixtures.** Um passo posterior, com corpus externo formalmente autorizado, escopo de mídia observável e duas revisões humanas independentes, poderá comparar política com validação adequada por criador. Até lá, rubrica, grants e Gate 0B continuam sem mudança.


## Validação integrada em comando único

O script `scripts/validate_dec017_e14_integrated.py` reutiliza o executor local
seguro da E1.3 e registra: pytest focado, comparação baseline, comparação
GLiNER real, pytest completo, Gate 0 e zero-spend. Salva logs privados e
`summary.json` com somente métricas agregadas permitidas; elimina arquivos
de comparação de execução anterior antes de iniciar, evitando resultados
obsoletos. O `summary.json` inclui o SHA local do checkout quando Git existe.

No PowerShell (com a branch E1.4 no HEAD), executar:

```powershell
python scripts/validate_dec017_e14_integrated.py `
  --model-dir "C:\Models\tapi\gliner25-multi-decide" `
  --output-dir "$env:USERPROFILE\tapi-e14-validation"

git rev-parse HEAD
Get-Content "$env:USERPROFILE\tapi-e14-validation\summary.json" -Raw
```

`all_checks_pass=true` exige todas as seis etapas PASS; sem checkpoint
real o comparativo GLiNER é BLOCKED, nunca marcado como aprovado. A execução
não cria autorização para dados externos nem muda qualquer classificador
institucional. A revisão deve comparar métricas e sua procedência antes do merge.
