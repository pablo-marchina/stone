# DEC-017 E1.3 — Diagnóstico do CTA: modelo vs. adaptador vs. rubrica

**Situação:** laboratório de diagnóstico sobre dados **100% artificiais em português brasileiro**, sem intervenção na produção. Base E1.2: 14 exemplos, 291 testes PASS, GLiNER2.5 checkpoint íntegro e Gate 0B bloqueado. Os números E1.2 apresentados pelo operador mostram F1 de tema 0,833 do GLiNER e F1 de CTA zero, embora o baseline tivesse F1 de CTA 1,0 sobre poucos positivos. Há também extrapolações em campos com gold `not_observable`. **Não são resultados científicos.**

## Pergunta técnica

Por que o GLiNER2.5 não respondeu positivamente a campos CTA em E1.2? Três causas distintas são plausíveis:

1. O modelo retorna "nao" ou "indefinido" para a pergunta conjunta `tem_cta` e até pode identificar `tipo_cta`. O adaptador E1 **bloqueia** `tipo_cta` quando a presença bruta não é exatamente `sim`. Isso é uma decisão conservadora de evidência, não necessariamente falta de capacidade semântica.
2. O modelo pode ter dificuldade na formulação das categorias ou na operação conjunta de vários cabeçalhos. A ablação `--ablate-cta-heads` compara **respostas brutas para os dois campos simultâneos e para cada campo isolado**.
3. O baseline busca regex de CTA e **confunde imperativos negados com comandos positivos**. Ex.: "NÃO siga este perfil". Há também usos citados/condicionais fora da intenção de CTA que uma regra de três tokens não resolve. Tratar como contraprova do baseline, não como certeza de ausência de CTA em todo o vídeo.

## Implementação e controles

O **E1 original permanece inalterado** (métodos e versões), permitindo comparação com a série histórica. A E1.3 adiciona somente variantes experimentais:

| Braço | Comportamento |
|---|---|
| baseline_original | Regex E1 atual; referência histórica sem mudanças |
| baseline_negation_aware | Rejeita CTA positivo quando negações simples precedem a expressão na mesma oração |
| gliner | Saída E1 atual, conservadora, sem regras adicionais |
| gliner_rule_assisted_experimental | Preserva respostas GLiNER válidas e acrescenta CTA quando regex conservadora encontra comando positivo no texto efetivamente observado |

**ATENÇÃO:** o híbrido não mede a acurácia do GLiNER isolado. Quando ele melhora, pode apenas reproduzir heurísticas do baseline. "Não deixe de seguir" (negação de uma negação), imperativos em citação, retórica, ironia e instruções condicionais ainda podem ser classificados incorretamente. São exemplos artificiais usados para localizar erros, não para implementar um parser semântico generalista.

Relatório sem mídia real, review ID nem URL:
- macro-F1, precisão, recall, cobertura, extrapolações e latência do benchmark E1.2 para cada braço, **em referência sintética**;
- matriz de confusão por campo, inclusive abstenção, somente onde há gold de valor observável;
- contagem de predições por campo quando a referência sintética é `not_observable`;
- motivos de abstenção/decisão, agregados por campo;
- para casos **sintéticos apenas**, ID fictício, classificações brutas sanitizadas `tem_cta` e `tipo_cta`, motivo pós-adaptador, indicador de bloqueio em cascata e rótulos encontrados pela regra;
- quando solicitado, resultado de **cabeçalhos isolados** e diferenças em relação ao cabeçalho conjunto.

As saídas de modelos externos são restringidas aos rótulos previstos pelo schema; conteúdo bruto que saia da lista vira `__out_of_schema__`. O relatório não inclui a entrada textual. Como IDs de casos são artificiais, a investigação por exemplo não expõe dados de terceiros.

## Passo 1 — baseline, sem baixar pesos nem usar rede

~~~powershell
git fetch origin
git switch --track origin/feat/dec017-e13-cta-diagnostics-ptbr-20261104
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_system_one_e13.py

python scripts/build_e13_cta_challenges.py --output dec017_e13_synthetic.jsonl

python scripts/diagnose_e13_cta.py --input dec017_e13_synthetic.jsonl --output dec017_e13_baseline_report.json --model baseline
~~~

O gerador inclui os 14 casos E1.2 mais 14 desafios novos: comandos afirmativos, negação explícita, negação dupla, negação seguida de outro CTA, comandos múltiplos, menção de imperativo sem intenção de comando e DM/link na bio. O gold não afirma ausência de CTA em vídeo nem inventa observação dos primeiros três segundos.

## Passo 2 — modelo real já instalado, apenas offline e com opt-in

~~~powershell
$env:TAPI_SYSTEM_ONE_ENABLED = "1"
try {
    python scripts/diagnose_e13_cta.py --input dec017_e13_synthetic.jsonl --output dec017_e13_both_report.json --model both --model-dir "C:\Models\tapi\gliner25-multi-decide" --ablate-cta-heads
}
finally {
    $env:TAPI_SYSTEM_ONE_ENABLED = "0"
}
~~~

O script verifica `config.json`, pesos Safetensors e SHA-256 publicado, manifesto e revisão SHA imutável **antes de carregar**, com `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE` e `HF_DATASETS_OFFLINE` ativos. Nenhum download ocorre nesse passo. A ablação faz chamadas extras locais e mede uma hipótese distinta de desempenho por modelo; não usar as latências do híbrido para comparar economia de hardware sem controle adicional.

O arquivo `dec017_e13_both_report.json` guarda os campos `diagnostics`, `synthetic_cta_trace`, `n_cta_cascade_blocked` e `cta_head_isolation`, além das métricas E1.2 e procedência do checkpoint.

Consultar sem exportar legendas:

~~~powershell
$r = Get-Content dec017_e13_both_report.json -Raw | ConvertFrom-Json
$r.n_cta_cascade_blocked
$r.cta_head_isolation.joint_vs_solo_changed
$r.synthetic_cta_trace | Format-Table -AutoSize

$resultados = foreach ($campo in $r.models.baseline_original.fields.PSObject.Properties.Name) {
    $b = $r.models.baseline_original.fields.$campo
    $g = $r.models.gliner.fields.$campo
    $h = $r.models.gliner_rule_assisted_experimental.fields.$campo
    [PSCustomObject]@{
        Campo = $campo
        F1_Original = $b.macro_f1_penalizing_abstention
        F1_GLiNER = $g.macro_f1_penalizing_abstention
        F1_Hibrido_Experimental = $h.macro_f1_penalizing_abstention
        Cobertura_GLiNER = $g.coverage_observable
        Extrapolacoes_GLiNER = $g.claims_when_gold_unobservable
    }
}
$resultados | Format-Table -AutoSize
~~~

### Hipóteses e interpretação dos diagnósticos

- `n_cta_cascade_blocked > 0`: há pelo menos um caso em que `tipo_cta` teve rótulo bruto válido, mas o adaptador o rejeitou por ausência de confirmação de `tem_cta`. Não se deve simplesmente remover a checagem, pois ela previne afirmações incompatíveis.
- `joint_vs_solo_changed > 0`: há evidência de interferência do esquema/cabeçalhos, motivando avaliação de perguntas isoladas e desenho de schema em conjunto humano separado.
- F1 positivo do híbrido com baseline estável: pode ser **efeito do fallback regex**, não melhoria do GLiNER.
- Uma classificação em campo `not_observable` é contada separadamente como extrapolação **relativa ao gold sintético**, mas não estabelece que o modelo alucinou; a referência também pode ser incompleta ou ambígua.
- Sem referência observável, o relatório deixa F1 como `null`; zero não significa capacidade zero em produção.

## Passo 3 — regressão e limites científicos

~~~powershell
python -m pytest -q
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
~~~

**Aceite experimental:** testes novos e gerais aprovados; script executa sobre exemplos artificiais, falha fechado com flag OFF, não publica texto/IDs reais, demonstra separação entre modelo, policy gate e referência; Gate 0B bloqueado e zero custos externos.

**Não é aceite científico:** um vencedor por F1 em exemplos artificiais, precisão na população brasileira, acesso a publicações reais, fine-tuning, produção ou mudança da rubrica. O E1.2 segue como base do futuro gold humano independente com direitos comprovados e splits por criador.

A decisão sobre mudar o adaptador E1 requer primeiro analisar as respostas brutas **dos pesos reais**, executar ablação e manter uma bateria de negativos para não trocar falsas abstenções por falsos positivos.


## Consolidação dos PRs #27 e #28 (04/11/2026)

**Branch canônica de consolidação:** `feat/dec017-e13-unified-cta-pr27-pr28-20261104`, derivada do PR #28.
Os PRs #27 e #28 eram variantes concorrentes com os mesmos caminhos
`src/tapi_gate0/system_one_e13.py` e `tests/test_system_one_e13.py`.
Não fazer merge direto dos dois sem resolver essa sobreposição.

| Capacidade | Origem | Resolução |
|---|---|---|
| Comparador baseline/GLiNER e ablação heads isolados | #27 e #28 | Mantido o runner único do #28 com histograma joint/solo |
| Cascata `tem_cta → tipo_cta`, saída crua sanitizada | Ambos | Preservado o adaptador E1 intacto e gerado resumo de conflitos |
| Negação explícita de imperativos, contexto misto | #27 e #28 | Função diagnóstica incorporada; correção de dupla negação `não deixe de` |
| Variantes experimentais por regra e fallback | #28 | Mantidas isoladas da classificação de produção |
| Casos PT-BR de dupla negação, uso metalinguístico e aviso de segurança | #27 | Incorporados seis novos casos sem criar rótulos falsos de CTA ausente |
| Métricas, abstenção e matriz de confusão | Ambos | Saída E1.2 e matrizes do #28; histograma e conflitos adicionados |

O dataset artificial consolidado tem **34 casos**: 14 da E1.2, 14 do #28 e seis situações distintas do #27. Todos permanecem sintéticos, sem gold humano e sem validade científica. A normalização temporal e multimodal permanece proibida quando não há evidência observável. As variantes experimentais não alteram `DeterministicTextDecider`, `LocalGLiNERDecider` ou `classification.py`.

**Validação ainda necessária no Windows/Miniforge, antes do merge:** instalar dependências existentes, executar `pytest -q tests/test_system_one_e13.py`, gerar fixtures com `build_e13_cta_challenges.py`, executar `diagnose_e13_cta.py` em modo baseline e depois `both --ablate-cta-heads` com o checkpoint SHA-pinned da E1.1. Reexecutar suíte completa, `scripts/check_gate0.py` e `scripts/verify_zero_spend.py`. **Nenhum desses resultados é presumido como PASS nesta consolidação; G0B e o uso real seguem bloqueados.**

**Interpretação do relatório:** comparar `cta_head_isolation`, `n_cta_cascade_blocked`, `cta_evidence_crosscheck.cta_conflicts` e `head_value_histograms` antes de eleger ajuste de classificador. `baseline_negation_aware` e `gliner_rule_assisted_experimental` não são o baseline institucional nem evidência de superioridade generalizável.


### Proteção de origem sintética do runner consolidado

O runner `diagnose_e13_cta.py` compara o JSONL de entrada com o conjunto canônico
produzido pelo gerador versionado. `source_kind="synthetic"` **não** basta:
um arquivo com texto real rotulado artificialmente é recusado antes do
carregamento dos pesos. O laboratório E1.3 não aceita corpus real; novos
cenários artificiais exigem alteração auditável no gerador e nos testes.
