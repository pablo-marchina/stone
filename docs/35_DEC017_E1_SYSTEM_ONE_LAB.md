# DEC-017 E1 — Laboratório System One tipado e offline

**Estado:** EXPERIMENTAL, não homologado, desligado por padrão. **Data de referência:** 03/11/2026.

**Vínculos:** IMP-062–065, IMP-069, DEC-016, Metodologia Científica v2 (§2 H1/H5, §3 EDD) e estudo `TAPI_Stone_Estudo_Viabilidade_System_One_Jev_SubQ_VideoJev_2026-11-03.md` (documento fornecido fora do repo).

## Questão de pesquisa e limites

Investigar se um classificador de decisões tipadas (System One) melhora a classificação de **texto observado e autorizado em português brasileiro**, sem mudar a rubrica institucional de 20 campos. O E1 é **uma peça de classificação**, não um agente com ferramentas. Não obtém mídia, não faz scraping, não chama APIs pagas, não cria grants, não altera persistência/ranking/data card e não treina modelos.

A classificação experimental `mpe_targeted` é uma hipótese por **post**, independente de quem o publicou. Ela **não** integra os 20 campos oficiais nem altera `scientifically_eligible_instagram_posts` sem revisão humana posterior.

## Arquivos e contratos

| Arquivo | Responsabilidade |
|---|---|
| `src/tapi_gate0/system_one_e1.py` | `ObservedText`, `EvidenceBundle`, `Decision`, `DecisionBundle`, `DecisionModel`, baseline, adaptador GLiNER local e conversão segura para `RubricAssessmentCreate` |
| `src/tapi_gate0/system_one_benchmark.py` | `BenchmarkCase` e avaliação pareada com cobertura, macro-F1, acurácia e latência |
| `scripts/benchmark_system_one_e1.py` | CLI JSONL somente local; escreve relatório agregado, sem ecoar texto |
| `evidence/experiments/dec017_e1_synthetic_smoke.jsonl` | Quatro exemplos fictícios para validar execução e fórmulas, não um gold set científico |
| `tests/test_system_one_e1.py` | Testes de segurança, integridade, abstenção, whitelist de categorias, comparabilidade e não promoção científica |

`ObservedText` guarda modalidade `caption` ou `transcript`, bytes textuais, localizador e SHA-256 validado. `EvidenceBundle` guarda tenant/post/criador e origem. `source_kind=approved_local` exige `rights_reference` e escopo explícito `offline_classification`; ambos são **declarações do operador**, não prova jurídica independente.

`DecisionBundle` só inclui decisões com valores previstos no contrato, evidência rastreada, modelo/versão e abstenção. Nenhuma probabilidade é inventada: `confidence=null` até existir saída probabilística/calibração real. A conversão só aceita fingerprint e localizador que correspondam ao `EvidenceBundle`, retorna uma **avaliação candidata** do modelo e marca os campos não observáveis como `None`/`not_observable`; não chama `record_scientific_post_review`.

## Sete perguntas tipadas em E1

| Campo | Estratégia de texto | Condição |
|---|---|---|
| `tema_principal` | Choice das oito categorias oficiais | Abster em dúvida/ambiguidade |
| `tom` | Choice das quatro categorias oficiais | Tom textual, não audiovisual |
| `tipo_hook` | **Abster sempre no E1** | Gancho inicial exige observar os primeiros 3 segundos |
| `tem_cta` | Noul textual | Afirmar apenas presença; não inferir ausência no vídeo |
| `tipo_cta` | Choice das cinco categorias oficiais | Exigir `tem_cta=sim` concomitante |
| `oferta_ou_beneficio_explicito` | Noul textual | Se não estiver explícito, abster; não assumir `false` |
| `mpe_targeted` | Noul exploratório | Não promove posts ao corpus sem revisão humana |

O baseline usa apenas as expressões determinísticas **já existentes** em `classification.py`, preservando o comportamento padrão de ingestão. O `LocalGLiNERDecider` usa `gliner2.AutoExtractor` + `classify_text`, com labels controlados por schema; exige diretório de pesos existente e `TAPI_SYSTEM_ONE_ENABLED=1`.

## Segurança e execução offline

- `TAPI_SYSTEM_ONE_ENABLED=0` em `.env.example`. O baseline executa sem flag. O modelo local não pode carregar quando OFF, inclusive nos testes com injeção de classe falsa.
- O carregador **não aceita um ID remoto** como caminho e define `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `HF_DATASETS_OFFLINE=1` antes de importar a biblioteca. Pesos devem existir previamente em diretório local e sua licença ser revisada. O PR **não baixa modelos nem altera dependências padrão**.
- O extra opcional `[system_one_local]` inclui `gliner2[local]>=2.1,<3` e não faz parte do ambiente `[dev]`. Instalação opcional pode envolver download de pacotes, exigindo aprovação separada.
- Não há análise de frames, áudio, vídeo completo, inferência causal nem prova de empreendimento real; os atributos temporais/visuais continuam `not_observable`.
- Dados e rótulos reais requerem direitos por operação, revisão institucional e acesso autorizado; o gate de custo externo R$0 e Gate 0B permanecem inalterados.

## Passos reproduzíveis

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_system_one_e1.py
python scripts/benchmark_system_one_e1.py --input evidence/experiments/dec017_e1_synthetic_smoke.jsonl --output dec017_e1_smoke_report.json --model baseline
python -m pytest -q
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
```

O relatório do exemplo tem obrigatoriamente `scientifically_validated=false`; F1 e acurácia sobre quatro textos artificiais servem apenas para testar cálculo. **Não versionar relatórios com conteúdos ou identificadores privados**.

### Uso local GLiNER, opcional, não executado pelo PR

```powershell
# Somente após aprovar licença/dependências e colocar pesos autorizados no disco:
python -m pip install -e ".[system_one_local]"
$env:TAPI_SYSTEM_ONE_ENABLED="1"
python scripts/benchmark_system_one_e1.py --input evidence/experiments/dec017_e1_synthetic_smoke.jsonl --output dec017_e1_local_report.json --model both --model-dir "C:\models\GLiNER2.5-multi-Decide"
```

**Referência de interface:** https://huggingface.co/fastino/GLiNER2.5-multi-Decide ; https://pypi.org/project/gliner2/ . O modelo usa texto e classifica rótulos, não garante compreensão temporal nem resultado comprovado para a Stone. Custos de GPU/CPU/RAM devem ser medidos; não há benchmark do checkpoint real neste PR.

## Próxima avaliação científica (fora do E1)

Após obter legendas/transcrições/frames com direitos, construir gold set de revisão humana (requisito institucional ≥50 revisões), separar por criador, definir rótulos/âncoras e comparar qualidade por campo com baselines sob a mesma evidência. Medir macro-F1, precisão/recall de `mpe_targeted`, taxas de abstenção e erro sem evidência, latência p50/p95, energia, memória e custo por post. Pontuações 0–10, E2 multimodal e E3 fine-tuning ficam fora do E1.

**Gate de aceite E1:** contratos testados e benchmark sintético executável, nenhuma coleta externa, nenhuma mudança no domínio, na persistência científica ou nas métricas de ranking. O classificador real local permanece *opt-in*. Nenhum modelo vencedor será declarado sem gold independente.
