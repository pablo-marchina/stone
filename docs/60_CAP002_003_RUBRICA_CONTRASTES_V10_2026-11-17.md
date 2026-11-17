# CAP-002/003/008 — contrastes de candidatos grounded (17/11/2026)

## Referência e estado
Arquitetura final consolidada + v5.2, revisão metodológica v3, DEC-016/017/018,
Plano Único IMP-057/059/064/065/170. Não altera o escopo ou os gates globais.
Operador executou HEAD 8954666: 84 testes focais PASS, zero spend PASS.
Benchmark 62 fixtures autorais: quatro campos passaram, tom falhou; híbrido
56/62 vs consenso 44/62, zero candidatos incorretos nos quatro campos.
Não é gold independente. Piloto V10 858 legendas/21 fontes, tema 67 e CTA 64
candidatos, 791/794 abstenções. Prova social e oferta passaram no sintético,
não executadas em dados reais. Sem admissões, rótulos ou mutação de DB.
Relatórios privados a6-rubric-grounded-20261117-121124.json e
a6-rubric-pilot-20261117-121219.json.

## Implementação
Ranking exploratório aceita --rubric-input-name repetível (até 4 relatórios,
campos disjuntos). Reusa a política de escopo local e o inventário reauditorado.
Verifica manifesto, revisão/peso do checkpoint iguais ao relatório de audiência,
partições e totais por campo/fonte, todos os 62 casos do benchmark, gates
recalculados, snapshot exato, hash de legenda, spans e consenso rederivado
de PT/EN salvos. Predições não são assinadas ou reexecutadas; não são prova
independente. Mudança de inventário/snapshot exige nova execução do piloto.
Resultados separados em rubric_candidate_contrasts: técnico/semântico,
global/intraperfil, contagens observadas e desconhecidas, concordância com
baseline e limites de sensibilidade de cobertura. Limites são condicionais
aos candidatos observados, não IC nem limites científicos de prevalência.
Prova social/oferta são alegações textuais; ausência de candidato não é negativo.
Não modifica ranking ER, labels canônicos, agente atual ou Studio; proíbe
persistência Studio quando informado relatório grounded. Sem nova migração,
gasto, acesso externo, release, merge ou autorização.

## Operador
```powershell
git pull --ff-only
python -m pytest -q tests/test_discovery_rubric_contrasts.py tests/test_discovery_rubric_grounded.py tests/test_discovery_rubric_benchmark.py tests/test_discovery_rubric_coverage.py tests/test_discovery_audience_benchmark.py
python scripts/verify_zero_spend.py
$manifest = "artifacts/private/bd_manifest_a6_v10.json"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_exploratory_ranking.py --editorial --manifest $manifest --input-name "a6-grounded-v10-20261117-112228.json" --rubric-input-name "a6-rubric-pilot-20261117-121219.json" --report-name "a6-rubric-contrasts-$stamp.json" --confirm-all-ingestion-stopped
```
Após contraste inicial, executar prova/benefício sem repetir tema/CTA:
```powershell
$env:TAPI_SYSTEM_ONE_ENABLED = "1"
$model = "C:\Models\tapi\gliner25-multi-decide"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$proof = "a6-rubric-proof-offer-$stamp.json"
python scripts/a6_audience_contextual.py --rubric-grounded-pilot --rubric-field prova_social --rubric-field oferta_ou_beneficio_explicito --manifest $manifest --model-dir "$model" --confirm-all-ingestion-stopped --report-name $proof
if ($LASTEXITCODE -eq 0) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    python scripts/a6_exploratory_ranking.py --editorial --manifest $manifest --input-name "a6-grounded-v10-20261117-112228.json" --rubric-input-name "a6-rubric-pilot-20261117-121219.json" --rubric-input-name $proof --report-name "a6-rubric-contrasts-four-$stamp.json" --confirm-all-ingestion-stopped
}
```
Não executar ingestão concorrente. Se snapshot mudar, não ignorar guard:
reexecutar relatórios sobre inventário consistente. Não repetir chamadas Meta.
Testes novos ainda não executados pelo assistente. Próximo: análise de
cobertura, novo método de audiência com avaliação separada, mídia autorizada,
integração ao agente definitivo e expansão CAP-001. Sem homologação.
