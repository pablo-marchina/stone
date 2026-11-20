# A04 · IMP-060 / CT-04 — Gold Registry v1 (infraestrutura sintética)

**Data:** 2026-11-20. **Escopo:** IMP-060 / CAP-004 / U04 / CT-04; dependências originais IMP-011 e IMP-038; relação com IMP-071, IMP-069, DEC-017 e DEC-018.

**Status:** código e fixtures implementados no PR #44 (draft), **ainda não executados/validados localmente pelo operador**. Os resultados A00 1218 PASS/202 SKIP do HEAD `725f34c...` são anteriores a este incremento. É proibido promover esta infraestrutura a dataset gold real, validação científica, aprovação de gate ou fim do IMP-060 sem provas adicionais.

## Autoridade e interpretação de DEC-018

A Base Atemporal v6.1 preserva o oráculo original: IMP-060 exige `gold_manifest`, separação train/dev/sealed-test por criador e testes de leakage; CT-04 exige não construir prompts com sealed test e comparar baseline/candidata no mesmo sealed test.

Entretanto, DEC-018 vigente **dispensa a avaliação humana independente no plano interno**; não autoriza apresentar julgamento sintético como referência humana nem completar a exigência histórica de >=50 revisões. A implementação **não solicita nova autorização institucional** e **não aceita dados de provedores**. Não há gold verdadeiro disponível: `gold_relevance_judgments_available=false` e `scientifically_validated=false` são fixos para qualquer fixture v1.

## Contrato mínimo implementado

- `src/tapi_gate0/discovery_gold_registry.py`: registry imutável e restrito a `synthetic_fixture`, `synthetic_local`, `synthetic_oracle`. Valida conjunto exato de campos, identificadores, hashes, unicidade de conteúdos, fingerprints, queries e julgamentos, integridade referencial e completude declarada. **Não lê bancos, redes ou arquivos.**
- `load_synthetic_registry_bytes(..., expected_sha256)`: checa SHA256 dos bytes **antes** de interpretar JSON, tamanho máximo 2 MB, rejeita chaves duplicadas, constantes não JSON e falhas de schema. SHA256 assegura integridade em relação ao pin informado, não constitui assinatura de autoria ou permissão.
- Splits obrigatórios: `development`, `validation`, `sealed_test`; nenhum criador ou conteúdo pode cruzar splits, conteúdo idêntico por hash também não pode duplicar. Atesta **duplicidade exata** por digest, não detecta todos os quase-clones/semântica ou campanhas derivadas; isso permanece lacuna.
- `prompt_references()`: somente development/validation e somente referências sintéticas, nunca rótulos ou conteúdo raw. `assert_prompt_isolation()` rejeita referências explícitas (IDs/hashes de sealed test) em payload serializável; não pode detectar paráfrases ou vazamentos externos e não foi conectado automaticamente a agentes.
- `evaluate_synthetic_query()`: só calcula Recall@k/nDCG@k de fixture completa e com ranking do mesmo split; **não produz métricas gold de domínio**.
- `compare_synthetic_sealed()`: comparação agregada baseline/candidata na fixture selada exige intenção explícita, queries de teste completas e exclui referências individuais do resultado; **não equivale a teste selado institucional**, não libera gate e não garante uso único entre processos.
- `scripts/a4_gold_registry_check.py`: CLI apenas para `tests/fixtures/CT-04_*.json` pinados, sem persistência/DB; imprime contagens e status, sem referência privada. `CT-04_positive.json` usa apenas textos sintéticos conhecidos (somente hashes no arquivo), `CT-04_negative.json` contém mutações negativas.
- Testes: `tests/test_discovery_gold_registry.py` (12), `tests/test_discovery_gold_registry_cli.py` (2), `tests/contracts/test_ct_04.py` (4). **18 novos testes esperados, ainda não executados**. Não registrar como PASS antes do log do operador.

## Exercício local e critério de evidência

Em ambiente `tapi-s1-recovery` e checkout limpo no HEAD de código/documentação:

```powershell
$py = Join-Path $env:CONDA_PREFIX "python.exe"
& $py docs/base_atemporal/ferramentas/validar_espelho.py
& $py -m pytest -q tests/test_discovery_gold_registry.py tests/test_discovery_gold_registry_cli.py tests/contracts/test_ct_04.py
& $py scripts/verify_zero_spend.py
$fixture = "tests/fixtures/CT-04_positive.json"
$pin = (Get-FileHash $fixture -Algorithm SHA256).Hash.ToLowerInvariant()
& $py -m scripts.a4_gold_registry_check --fixture "$fixture" --expected-sha256 "$pin"
```

O operador deve conferir **cada código de saída**; a lista acima é referência, não pipeline de aceite automático. Em seguida, executar A00 `--profile full` no mesmo SHA, report privado com nome exclusivo e `checks_passed=true`, registrar falhas e skips. O arquivo `CT-04_negative.json` deve **reprovar** por mutações no teste, não ser tratado como manifest positivo. As referências `tests/fixtures/` são sintéticas e podem entrar no repositório; dados reais e registros privados nunca.

## Bloqueios remanescentes e próximos passos

**IMP-060 não homologado**: não há gold humano ou avaliação independente sob DEC-018, não há registry de conteúdo externo autorizado, sealed test persistente com governança de acesso por ciclo, verificação de quase-duplicatas semânticas, isolamento temporal, integração automática com agente/benchmark, nem validação de critérios formais por responsável. **CT-04 não aceito** pelo simples PASS de fixtures. A próxima implementação deve integrar avaliação sintética ao runner de baseline sem permitir `scientifically_validated=true` e desenhar protocolo de evidência de engenharia sob DEC-018. IMP-071 continua sem Recall/nDCG de relevância real.

**Restrições:** R$0; não usar Meta/API ou mídia externa, nem publicar, treinar ou permitir inferência em direitos não comprovados; PR #44 draft, sem merge, ativação externa ou mudança no auditor padrão; G0–G6 e IMP-131 não liberados. O plano mantém o DAG dos 204 IMP; este documento não altera matrices normativas.
