# DEC-017 E1.3 — Diagnóstico de CTA e observabilidade em português

**Estado:** experimento de diagnóstico **somente com dados sintéticos**. Não autoriza inferência em posts reais, coleta externa, homologação científica ou alteração do baseline de produção. O E1.2 anterior passou com 291 testes; a comparação de 14 exemplos artificiais mostrou F1=0 e cobertura=0 do GLiNER nos dois campos de CTA, apesar de resultados exploratórios maiores para tema e tom.

## Hipótese verificável

A função atual `LocalGLiNERDecider.evaluate` faz uma classificação multi-head com `tem_cta` e `tipo_cta`, além de outros campos. O adaptador só publica `tipo_cta` quando a **resposta bruta** de `tem_cta` é `sim`. Se a saída conjunta trouxer `tem_cta=nao` e `tipo_cta=comentar`, a tipagem fica abstida por dependência do adaptador. Isso é uma **hipótese de causa**, não prova de que o checkpoint falhou.

O E1.3 registra e confronta, para cada exemplo sintético:

1. Classificação multi-head original, preservando a política do E1 sem modificá-la.
2. Classificação isolada de `tem_cta` usando o mesmo checkpoint.
3. Classificação isolada de `tipo_cta` usando o mesmo checkpoint.
4. Decisões finais e motivos de abstenção do adaptador; alerta limitado de imperativos diretamente negados no baseline.
5. Matriz de confusão sobre referências sintéticas **observáveis**, separado das reivindicações em campos não observáveis.

O relatório inclui contagens de divergência, supressões de CTA por dependência, respostas e motivos permitidos, métricas E1.2 pareadas e identificação somente **ordinal** dos exemplos sintéticos. **Não inclui legendas, IDs originais, URLs, textos brutos ou valores desconhecidos retornados pelo modelo**. Valores fora do esquema são agrupados em `out_of_schema`. Esses dados são diagnóstico de engenharia, não gold humano.

## Garantias

- **Sem alteração do adaptador de produção.** Nenhum resultado isolado é promovido automaticamente a `tem_cta=True` ou `tipo_cta`. Uma discordância pode decorrer de formulações, dados ou especificidade do modelo; primeiro observamos.
- `tipo_hook` permanece não observável sem prova dos primeiros 3 segundos de vídeo; ausência de CTA na legenda **nunca** vira CTA ausente no vídeo.
- O baseline `DeterministicTextDecider` permanece inalterado; a detecção de "não siga", "nunca comente" é **apenas um sinal de auditoria**. Exemplos como "não deixe de seguir" não são interpretados como negados; o detector é deliberadamente simples.
- O programa exige `source_kind=synthetic`, `gold_kind=synthetic_fixture`, `split=smoke`, no máximo 200 casos, `TAPI_SYSTEM_ONE_ENABLED=1` explícito, checkpoint real **SHA-pinned** íntegro, execução Hugging Face offline e liberação do caminho fora do Git.
- `scientifically_validated=false` sempre. Nenhuma modificação em rubrica oficial, Gate 0B, banco, gastos, direitos ou corpus científico.

## Ambiente Windows / Miniforge

O experimento usa os mesmos pesos validados no E1.1. Não baixar novamente o checkpoint.

```powershell
git fetch origin
git switch --track origin/feat/dec017-e13-cta-diagnostic-ptbr-20261104
python -m pytest -q tests/test_system_one_e13.py
python scripts/build_e13_ptbr_cta_smoke.py --output dec017_e13_ptbr_synthetic.jsonl

$env:TAPI_SYSTEM_ONE_ENABLED = "1"
try {
    python scripts/diagnose_system_one_e13.py `
        --input dec017_e13_ptbr_synthetic.jsonl `
        --output dec017_e13_cta_diagnostic_report.json `
        --model-dir "C:\Models\tapi\gliner25-multi-decide"
}
finally {
    $env:TAPI_SYSTEM_ONE_ENABLED = "0"
}

python -m pytest -q
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
```

O arquivo sintético inclui **28 casos fictícios**: os 14 do E1.2, mais 14 focados em CTAs afirmativos, imperativos negados, instruções mistas, homônimos, "não deixe de seguir", CTA múltiplo e contexto de segurança. As referências artificiais são didáticas e de observabilidade limitada.

## Interpretação de resultados

Se `suppressed_by_presence_dependency` for positivo, há **saídas válidas de tipo** retidas pela política de corroborar presença. Comparar as histogramas `multi_presence` e `single_presence` indica se o problema pode estar no esquema multi-head. Isso **não autoriza remover o gate**: precisamos validar consistência, erros e risco de atribuir um tipo de CTA onde a legenda não contém chamada explícita.

Se o baseline acionar imperativos explicitamente negados, investigamos um possível falso positivo da regex atual. Não modificaremos a regex principal com base em exemplos artificiais; qualquer ajuste deve ser proposto num PR separado, comparado em dev/test e revisado por humanos.

A matriz de confusão separa `ABSTAIN` das classes. F1 calculado sobre poucas referências tem variância alta; a auditoria mede apenas a instrumentação e gera hipóteses para o próximo experimento.

**Critério de saída E1.3:** o relatório revelar qual etapa gera abstenção ou conflito nos CTAs sem quebrar contratos, testes, Gate 0 e custo zero. **Critério não atendido apenas com E1.3:** selecionar o melhor classificador para produção ou aumentar automaticamente elegibilidade MPE.
