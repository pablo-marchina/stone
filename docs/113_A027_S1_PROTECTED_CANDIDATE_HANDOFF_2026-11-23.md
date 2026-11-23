# A02.7 / A06 / A11 — handoff protegido de candidatos Stone-S1 (23/11/2026)

## Objetivo e limites

Unir a saída do processamento AV protegido à superfície interna de propostas do Stone-S1 sem confundir as quatro decisões candidatas com o contrato E1 de texto, a rubrica canônica ou admissão científica. Não é integração operacional de E1/DEC-008/Creative Studio. Não há novo endpoint, migração, permissão, escrita de rubrica, consulta externa ou gasto.

## Implementação

- `asset_system_one_guarded_handoff.bridge_guarded_av_to_system_one` recebe quatro IDs distintos de artefatos, exige finalidade `research_analysis` e chama o avaliador existente de cobertura protegida. O avaliador reabre os derivados cifrados, verifica direitos/ancestralidade/escopo e reavalia revogação antes de retornar. Não aceita relatório de fusão fornecido pelo chamador como autorização.
- Projeção candidata mantém o fingerprint da evidência, o escopo do conteúdo, cobertura completa de quatro processadores, distinção entre insuficiência e ausência observada de sinal, rejeições de qualidade, estado e valor dos quatro campos, contagens de suporte/veto e hash da proveniência. Suprime valores que o guard suprimiu; não devolve texto bruto, locators ou payloads. Não reutilizar o recibo como grant.
- A02.7/A06: 22 testes unitários novos; nove casos existentes de ablação com SQLite real, grants assinados, filas e derivados cifrados foram ampliados para checar a ponte, paridade de ordem, ausência de eventos novos, seleção incompleta e revogação. Nenhum desses nove usa ASR/VLM real.
- A11: a etapa `python_a027_integrated` passa a exigir 47 casos (16 anteriores + 22 novos + 9 casos integrados selecionados). O pacote fixa os arquivos da ponte, a fonte de composição de evidências e o arquivo de testes da registry. Mantém 10 etapas, A05/A07 407 e A06 E1 35. As metas são contagens esperadas, não resultados observados.

## Evidência observada

PR #77, Windows, `a8fb601671e907689679845c4c67f172d77385fd`: 49/49 testes portáteis PASS em 7.55s.

Nesta branch, o assistente executou em Python 3.13.5 as cópias exatas dos dois arquivos abaixo, verificadas por `git hash-object`:

- `src/tapi_gate0/asset_system_one_guarded_handoff.py`: blob `cbe5b5922a112c4ad024a1fbd6d6aee1ee41e450`
- `tests/test_asset_system_one_guarded_handoff.py`: blob `9a9aaf3a35729c8660469fa1cd4ea161df5ebb9f`

Resultado isolado: **22 passed in 0.06s**, com stand-in explícito para o import do módulo de fusão e mocks dos testes originais; o stand-in não executa fusão/rights. Não significa aprovação da integração real ou do A11. Os nove casos com a registry real e o pacote A11 permanecem NOT_RUN no novo SHA. Não exigir modelos nativos para esses testes.

## Próximo passo de convergência

Consolidar validação dos testes portáteis com o checkout completo. Criar um contrato de consumo do resultado para DEC-008 com revalidação no boundary e associação ao ledger somente por digest; não transformar a projeção em grant nem executar ferramenta criativa. A escrita no Studio deve permanecer operação distinta e autorizada. Avaliar a durabilidade dos agentes, a ciência e os CTs antes de release. DEC-008 OPEN, G0–G6 e IMP-131 BLOCKED, produção não aprovada.
