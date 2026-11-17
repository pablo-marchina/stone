# CAP-003 — Rubrica grounded após V10 (17/11/2026)

## Vínculo arquitetural
Arquitetura consolidada + v5.2, revisão metodológica v3, DEC-016/017/018,
CAP-003 IMP-064/065; dependências de CAP-002/005/007/023. Sem novo plano,
mudança de autorização, admissão científica, mutação de banco ou merge.

## Evidência operacional reportada
V10: 858 legendas, 21 perfis; 1 candidato grounded positivo e 857 abstenções.
Ranking técnico 858/top86; semântico exploratório 439/top44.
Preview: collect_more_evidence, zero hipóteses/referências/criativos.
Rubrica: 858 metadata, 636 candidatos lexicais, 858 medidas, 14808 não
avaliados de 17160 células. Benchmark anterior (36 fixtures): consenso
9/10 tema, 7/9 CTA, 3/5 prova, 5/6 oferta, 3/6 tom; 10 testes focais PASS
reportados. Não é validação científica. Não reduzir thresholds do agente.

## Incremento
discovery_rubric_grounded.py compara PT/EN/consenso, regra e híbrido em
36 casos anteriores e 26 novos exemplos autorais. Evidência por offsets
Unicode e SHA-256, abstenção em ambiguidade e guardas conservadores.
Prova social é alegação textual, não verificação factual. Tom dominante
permanece deliberadamente sem regra lexical. Gate experimental por campo:
em cada divisão >=2 casos esperados não abstidos, zero candidatos errados
e >=50% de acertos dentre os candidatos esperados. Este critério de
engenharia não altera o aceite institucional nem habilita inferência real.
Testes unitários e CLI simulada publicados; execução ainda pendente.

## Operador (tapi-s1)
```powershell
git pull --ff-only
python -m pytest -q tests/test_discovery_rubric_grounded.py tests/test_discovery_rubric_benchmark.py tests/test_discovery_rubric_coverage.py tests/test_discovery_audience_benchmark.py
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_audience_contextual.py --rubric-grounded-benchmark --model-dir "C:\Models\tapi\gliner25-multi-decide" --report-name "a6-rubric-grounded-$stamp.json"
```

Sem manifesto, chamadas Meta, atualização de pesos ou gravação de rótulos.
Próximo: piloto real escopado com proveniência por campo após avaliação;
melhorar cobertura de audiência em experimento separado; adicionar mídia
autorizada conforme arquitetura; integrar ao ranking/agente somente com
evidência suficiente. Não tratar as fixtures como gold independente.


## Piloto real condicionado, implementado no mesmo incremento
`--rubric-grounded-pilot` exige manifesto, campos explicitamente
selecionados (sem repetição), confirmação de ingestão parada e escopo
local de pesquisa vigente. Repete o benchmark no mesmo carregamento e
não processa legendas se algum campo solicitado falhar. Revalida escopo
antes, durante e depois; usa record observer reauditorado e guarda
content_id, snapshot_id, hash e offsets em relatório privado. Stdout
agregado. Nenhuma gravação de rótulo ou mudança no ranking/agent/Studio.
Tests com transporte simulado publicados, ainda não executados.

Executar primeiro o benchmark sintético acima. Escolher explicitamente
somente campos true de field_engineering_gate; se nenhum passar, não
executar o piloto. Exemplo condicional para tema e CTA, somente se ambos
passarem:

```powershell
$manifest = "artifacts/private/bd_manifest_a6_v10.json"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_audience_contextual.py --rubric-grounded-pilot --rubric-field tema_principal --rubric-field tipo_cta --manifest $manifest --model-dir "C:\Models\tapi\gliner25-multi-decide" --confirm-all-ingestion-stopped --report-name "a6-rubric-pilot-$stamp.json"
```

Se um campo falhar, nenhuma inferência real é realizada nessa execução;
o relatório privado registra o motivo e a evidência do benchmark. O
escopo global externo continua deny-by-default. O resultado não é
RubricAssessment validado e não implica aceite de G3.
