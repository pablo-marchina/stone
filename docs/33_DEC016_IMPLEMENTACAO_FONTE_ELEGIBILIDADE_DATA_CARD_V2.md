# DEC-016 — Implementação da seleção e elegibilidade científica

**Proposta em revisão.** O TAPI pesquisa publicações **direcionadas a MPEs**, independentemente do porte da instituição ou do profissional que as publica. O cadastro de fontes não comprova a audiência de publicações individuais.

## Fonte v2

`tapi-source-frame.v2` diferencia `creator_type` (negócio, criador, educador, instituição, fintech, marca e outros), `business_size_class`, `sector_context`, `sampling_stratum` e `audience_intent`. A intenção de audiência é hipótese de curadoria, não rótulo automático dos posts. Comprovação de porte micro ou pequeno aplica-se apenas à fonte classificada como `mpe_business`.

O manifesto `evidence/acquisition/research_source_candidates_v2_20261103.json` contém os cinco perfis históricos como candidatos ainda não verificados. O manifesto v1 foi preservado para rastreabilidade.

## Filtro por publicação

- **Elegibilidade técnica:** Reel/carrossel real, registrado sob perfil e grant válidos, com idade mínima de 14 dias e métricas disponíveis, incluindo denominador positivo.
- **Elegibilidade científica:** condição técnica mais contexto documentado e revisão humana da publicação, com evidência de conteúdo observado apontando para `mpe_targeted`, referência rastreável e hash SHA-256 do material efetivamente observado.
- **Observabilidade da rubrica:** modalidades de conteúdo efetivamente acessadas, com revisão própria. Sem legenda, imagem ou vídeo observáveis, não se atribuem notas audiovisuais.

A leitura Business Discovery atual não observa legenda, imagens ou vídeo. Seu resultado indica apenas elegibilidade técnica, não relevância do público-alvo.

## Persistência auditável e data card

A migração `0005_scientific_corpus` adiciona `corpus_source_research_contexts` e `corpus_post_scientific_reviews`. São registros de contexto do produtor e revisões por item com referência, hash da evidência para decisões positivas, responsável, instante, tipo de evidência e status, respectivamente. O hash detecta alterações mas não autoriza uso nem comprova a origem por si só.

Endpoints seguros adicionais: `POST /v1/corpus/source-contexts` (admin) e `POST /v1/corpus/content-reviews` (admin/pesquisador). A revisão não coleta dados externos.

O data card `tapi-corpus-data-card.v2` distingue posts tecnicamente elegíveis e cientificamente elegíveis. Somente os cientificamente elegíveis entram em `target_reached` e `deficit`. As contagens antigas `eligible_instagram_posts` e `eligible_instagram_profiles` passam a ser aliases das contagens científicas, não métricas brutas.

O novo data card exige migração aplicada. O PR #20 (Business Discovery para persistência) está separado e apresenta outra migração identificada como 0005: precisará ser rebaseado, renumerado e revisado antes de integração.

## Verificação sem rede

```powershell
python scripts/mpe_corpus_pilot.py --frame evidence/acquisition/research_source_candidates_v2_20261103.json
python -m pytest -q tests/test_dec016_scientific_eligibility.py tests/test_corpus_audit_v52.py tests/test_mpe_corpus_pilot.py
python -m pytest -q
```

Os comandos locais não autorizam leitura de terceiros. Até que haja fontes aprovadas, conteúdos observáveis, autorização pertinente e a revisão científica, o corpus real permanece com zero registros elegíveis.
