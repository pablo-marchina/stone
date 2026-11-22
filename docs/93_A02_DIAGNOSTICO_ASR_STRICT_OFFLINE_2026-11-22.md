# A02 / IMP-063 — diagnóstico offline de WER Strict

> Complemento instrumental da Base Atemporal v6.1, sem aprovação científica, direitos externos, nova política ou liberação de G0–G6 e IMP-131.

## Motivação

O benchmark sintético ASR pode falhar o critério Strict. É necessário saber por fixture quais palavras foram **substituídas, omitidas ou inseridas**, identificar alucinações em casos sem fala e distinguir falha individual de **WER agregado acima do limite**. O diagnóstico não altera MAX_POOLED_WER = 0.30 nem MAX_CASE_WER = 0.50, e nunca seleciona modelo automaticamente.

## Contrato implementado

- Módulo: src/tapi_gate0/asr_strict_diagnostic.py.
- Aceita somente relatórios com formato do benchmark sintético run_asr_fixture_benchmark, suites baseline, challenge e guarded, candidatos small e medium, com partição e ordem exatas das fixtures congeladas, política, versão e checkpoint declarado coerentes.
- Recalcula todos os erros e WER com normalize_words, word_errors e evaluate_cases já existentes no projeto; compara os valores originais antes de explicar as diferenças.
- Faz alinhamento Levenshtein determinístico palavra a palavra; registra posições, substituições, omissões e inserções, além de hashes das strings de referência e transcrição.
- Admite relatórios que **falharam** o benchmark, mas rejeita divergência de métricas, referência, checkpoint declarado, política, flags de fontes externas ou afirmação de gold.
- Distingue motivos POOLED_WER_EXCEEDED, CASE_WER_EXCEEDED e NEGATIVE_HALLUCINATION. Falha agregada pode ocorrer sem nenhuma fixture individual exceder 50%; o diagnóstico não a mascara.
- Nunca atribui atestação independente ao modelo: independently_attested_model=false, independent_gold=false, scientific_admissions=0, production_approved=false e global_gates_released=false.

A verificação do digest declarado no relatório NÃO substitui uma verificação independente dos bytes reais do checkpoint.

## Execução offline

Script: scripts/a02_asr_strict_diagnostic.py. Exige repositório limpo no HEAD exato, fonte JSON já existente sob artifacts/private, SHA-256 dos bytes completos e novo nome de saída em artifacts/private. Não sobrescreve, não usa caminhos externos, recusa symlinks e JSON com chaves duplicadas; não faz downloads, transcrição ou operações no banco.

Comando ilustrativo no checkout completo (trocar todos os marcadores):

    python -m scripts.a02_asr_strict_diagnostic --expected-head SHA40_REAL --input-name relatorio-asr-existente.json --input-sha256 SHA256_BYTES_REAIS --output-name diagnostico-asr-novo.json

A saída detalhada fica SOMENTE no arquivo privado, com permissões locais restritas em POSIX; stdout contém exclusivamente indicadores, quantidade e hash da saída, sem transcrições ou tracebacks.

## Evidência e limitações

- **28 testes locais PASS** em ambiente isolado sobre os mesmos quatro arquivos de implementação/teste publicados, comparados por comprimento, soma de caracteres e checksum ponderado.
- Cobertura: baseline/challenge/guarded, WER por fixture, hipótese vazia e alucinação negativa, falha só por WER agregado, relatórios adulterados, checkpoint declarado, diretório privado, SHA da entrada, overwrite, paths e symlink.
- O ensaio isolado usou uma reprodução fiel das funções de normalização, WER, gate e fixtures do módulo ASR; NÃO executou faster-whisper, eSpeak NG, checkpoint real, shared-AV, A00 nem a aplicação completa.
- A11 agora espera uma nova etapa A02 de 28 casos, além de A05/A07 269 e A06/E1 29. Esses números são **contagens esperadas**, não resultados da suíte integrada.
- **Escopo explícito:** este diagnóstico aceita o benchmark ASR sintético independente. Não aceita diretamente relatórios do benchmark shared-AV de sete clipes; seu adaptador requer outro contrato. Caso as falhas históricas Strict estejam apenas no shared-AV, esta ferramenta ainda não explica esses relatórios.

## Caminho de fechamento

Executar os testes no checkout real no mesmo HEAD, produzir relatórios de benchmark genuínos no host nativo, diagnosticar falhas WER sem afrouxar os critérios, decidir perfis somente após ensaios controlados, estender análise validada ao shared-AV e executar novamente os oráculos Strict. Depois completar A02.7, System One operacional, pesquisa científica, agentes, Studio e G0–G6/IMP-131. **Sem merge, migração operacional, gasto ou deploy nesta etapa.**
