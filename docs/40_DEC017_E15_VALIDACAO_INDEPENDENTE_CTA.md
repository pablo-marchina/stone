# DEC-017 E1.5 — Protocolo de validação independente de CTA

**Estado:** contratos de pesquisa e ensaio com dados integralmente fictícios. Nenhuma publicação de terceiros foi coletada, importada, classificada ou revisada. O Gate 0B continua bloqueado e nenhuma autorização real foi apresentada ou inferida. A avaliação científica externa não está executada.

Dependências: DEC-016; DEC-017 E1.2 (dupla revisão e observabilidade), E1.3 (negações) e E1.4 (sete políticas). Este marco é empilhado sobre o PR #30, dependente do PR #29. Nenhuma rubrica institucional, classificador de produção, fonte externa ou grant foi alterado.

## 1. Questões e unidade de análise

A pergunta central é se políticas conservadoras de CTA melhoram o reconhecimento de instruções **afirmativas na legenda/transcrição observada**, sem transformar ausência de prova no texto em uma alegação de ausência de CTA no vídeo completo.

Hipóteses pré-registráveis:

- H1: regra sensível à negação reduz alegações positivas sobre textos sem instrução afirmativa contra baseline E1.
- H2: concordância entre tipo textual e GLiNER pode melhorar o trade-off de cobertura, abstenção e alegações indevidas.
- H3: o modelo só agrega valor se superar a regra em dados externos autorizados, com incerteza e custo computacional controlados.

Unidade observacional: fragmento de legenda/transcrição autorizado, com locator e SHA-256. Unidade independente para divisão dev/test e inferência: grupo canônico de criador, incluindo campanhas associadas. O público-alvo são MPEs; o criador da publicação não precisa ser uma empresa MPE. Separar fontes C1 externas, C2 Stone orgânico, C3 Stone Ads e C4 contexto de marca.

## 2. Gates legais e autorizações — obrigatórios antes de dados reais

1. Responsáveis institucionais confirmam direito documental por fonte e operação: leitura/cópia do texto, anotação humana, classificação offline, avaliação agregada, retenção e descarte. Metadados Business Discovery não conferem licença automática sobre mídia/transcrição de terceiros.
2. Evidência externa verificável inclui quem autoriza, fonte/itens abrangidos, escopos, datas, SHA-256 do documento e referência de aprovação do Gate 0B. O tipo approved_local e campos preenchidos em JSON **não provam juridicamente tais direitos**.
3. Validação das identidades dos revisores, regras de conflito de interesse, cegamento efetivo às saídas dos modelos, direitos de acesso e revogação são processos humanos externos.
4. Preservar segmentação e elegibilidade científica por publicação segundo DEC-016. Nunca converter contexto da conta em prova de que o conteúdo visa MPEs, nem confundir orgânico com anúncios.
5. Enquanto Gate 0B estiver bloqueado, o E1.5 não possui runner de conteúdo real; qualquer entrada approved_local é recusada no executor experimental. Nenhuma flag concede direitos ou desbloqueia inferência.

## 3. Quadro amostral e congelamento

Definir antes de ver os resultados: plataformas, período, critérios de inclusão/exclusão, modalidade observável, setores, coortes, duplicatas, recusas, estratégia de seleção, quotas, perdas por autorização e controle de viés. Registrar decisões antes de explorar o conjunto de teste.

Separar dev/test por grupo canônico de criador e campanha. Rejeitar texto exatamente duplicado em splits diferentes, mas também auditar manualmente paráfrases, repostagens, séries e aliases. Antes das revisões cegas congelar um manifesto ordenado de fingerprints de evidência, split, grupo canônico de criador e campanha, com SHA-256 em FrozenStudyProtocol. Qualquer alteração quebra o checksum e invalida a avaliação.

Como piso de triagem, o contrato define 50 casos totais, 20 positivos únicos e 20 negativos textuais no teste, com 20 grupos de criadores independentes no teste. **São mínimos administrativos de protocolo, não um cálculo de poder estatístico ou garantia de validade científica.** O plano definitivo exige análise de amostragem e viabilidade aprovada antes de acessar dados.

Congelar versões das sete políticas, checkpoint SHA-pinned, pré-processamento, limiares, métricas e critério de decisão. Ajustar apenas dev. Abrir o teste uma vez, com autorização auditada e relatório assinado; nunca reotimizar com resultados do test.

## 4. Anotação humana e observabilidade

Dois revisores reais distintos, credenciados pela instituição, treinados no protocolo, cegos às predições e entre si. Cada revisão identifica o mesmo evidence fingerprint, locator/hash, instante com fuso, justificativa e tipo de ação textual. Em caso de desacordo em estado ou tipo, exigir terceiro revisor diferente dos dois originais, posteriormente. Não arbitrar quando não existe desacordo.

Vocabulário do CTAHumanFinding:

| Estado | Leitura permitida somente do fragmento observado | Tipo |
|---|---|---|
| affirmative_single | Um CTA afirmativo de tipo único aparece no texto | Obrigatório, entre os cinco tipos da rubrica |
| affirmative_multiple | Há múltiplas instruções afirmativas; tipo único insuficiente | Nulo |
| no_affirmative_in_observed_text | Não se identifica instrução afirmativa **no texto examinado** | Nulo; **não é tem_cta=False no vídeo** |
| indeterminate | Informação insuficiente, ambiguidade ou discordância sem conclusão | Nulo |

Esse contrato é complementar ao E1.2 de sete campos; não substituir seu gold nem traduzir ausência textual em ausência de CTA global. IDs distintos, timestamps e um campo que declara cegamento não comprovam pessoas reais ou independência — o controle humano institucional permanece obrigatório.

Reportar concordância bruta, kappa nominal de Cohen para as duas revisões primárias, adjudicações e denominadores. Kappa nulo em caso degenerado é null, não 100%. Qualquer limiar de confiabilidade deverá ser predefinido e justificado com amostra suficiente.

## 5. Avaliação e incerteza

Cada política deve produzir decisões sobre os mesmos registros, sem reexecutar uma cabeça de modelo para cada braço, evitando viés de reamostragem. Registrar em cada split, por política e coorte:

- Cobertura e abstenção de presença/tipo = afirmações / todos os itens e complemento.
- Recall textual em positivos únicos = tipo corretamente afirmado / itens anotados affirmative_single, contando também erro de tipo e abstenção.
- Taxa de alegação textual indevida = afirmações positivas / itens no_affirmative_in_observed_text. Isto **não é FPR de ausência de CTA em vídeo**.
- Precisão seletiva em casos decidíveis = tipos únicos corretos / todas as afirmações de tipo em positivos únicos e negativos textuais; se nenhuma, null.
- Contagens de tipos afirmados em multiação/indeterminado, sem inventar rótulos binários.
- Concordância, adjudicações, amostra total, número de criadores independentes, distribuição por estrato e razões de exclusão.

Comparar políticas em pares no mesmo teste. **Ainda será necessário implementar antes do estudo real:** intervalos de proporções, reamostragem por grupo de criador para diferenças entre políticas, quantificação da potência/precisão prevista, análise de classes raras e eventuais ajustes por múltiplas comparações. Os números de uma simulação não permitem estimar FPR populacional.

## 6. Entrega implementada agora

| Artefato | Função |
|---|---|
| src/tapi_gate0/system_one_e15.py | Contratos de autorização declarada, duas revisões cegas, arbitragem, congelamento, prevenção de leakage e métricas em memória |
| scripts/rehearse_dec017_e15.py | Seis exemplos sintéticos e revisores simulados; baseline E1 versus regra E1.3; sem opção de importar dados |
| tests/test_system_one_e15.py | Regressões de autorização, independência, locator, pré-registro, dev/test por criador, campanha e texto |
| docs/40_DEC017_E15_VALIDACAO_INDEPENDENTE_CTA.md | Protocolo, tarefas pendentes, limites e operação |

Todos os arquivos de prova reais deverão permanecer fora do checkout e sob acesso institucional restrito. O único runner atual gera métricas agregadas de textos fictícios sem legendas, perfis, revisores ou URLs no relatório. Seu resultado declara permanentemente modo SYNTHETIC_REHEARSAL_ONLY, scientifically_validated=false, production_enabled=false e holdout_claim_allowed=false.

### Testes de engenharia no Windows / Miniforge

~~~powershell
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_system_one_e15.py
python scripts/rehearse_dec017_e15.py --output "$env:USERPROFILE\tapi-e15-rehearsal.json"
python -m pytest -q
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
git rev-parse HEAD
~~~

Não usar posts reais nem nomes de revisores reais nos testes. O executor se recusa a sobrescrever relatório congelado ou gravar dentro do repositório.

## 7. Pendências e aceite

| Gate | Estado |
|---|---|
| Contrato CTA de revisão independente | Implementado; testes locais do operador pendentes |
| Autorizações documentais, Gate 0B e direito de acesso ao conteúdo | **BLOQUEADO / NÃO COMPROVADO** |
| Amostragem, quadro científico e split real congelado | NÃO INICIADO |
| Dois revisores reais, IDs auditados e arbitragem | NÃO INICIADO |
| Gold humano autorizado validado, holdout externo | NÃO INICIADO |
| ICs, análise de poder e métricas de desempenho externo | NÃO INICIADO |
| Seleção de política de produção | PROIBIDA até todos os gates |

A homologação de engenharia deste PR não pode ser interpretada como validação científica, conformidade certificada ou permissão para ingerir dados externos.

Referências metodológicas: Protocolo Científico TAPI v2 (anexo do projeto); DEC-017 E1.2; [mlr3: grouped resampling](https://mlr3book.mlr-org.com/chapters/chapter3/evaluation_and_benchmarking.html); [CASRAI: agreement and Krippendorff alpha](https://casrai.org/guides/krippendorffs-alpha).


## 8. Verificação única integrada, sem dados reais

O validador de engenharia executa pytest focado, ensaio sintético com seis
exemplos, pytest completo, Gate 0 e zero-spend, na mesma revisão do repositório.
O relatório summary.json é agregado e registra o SHA de checkout quando o
executável Git está disponível. Nunca importa posts externos nem carrega
checkpoint; as duas avaliações humanas do ensaio são ficcionais.

~~~powershell
python scripts/validate_dec017_e15_integrated.py --output-dir "$env:USERPROFILE\tapi-e15-validation"
git rev-parse HEAD
Get-Content "$env:USERPROFILE\tapi-e15-validation\summary.json" -Raw
~~~

Mesmo se all_checks_pass=true, a única conclusão é que os contratos e os
controles do ensaio sintético passaram. O runner informa explicitamente
real_human_review_conducted=false e gate0b_authorized_by_this_runner=false.
