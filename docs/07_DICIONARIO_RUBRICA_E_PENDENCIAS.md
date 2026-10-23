# Rubrica de 20 campos — contrato candidato e decisões em aberto

`reference/rubric_candidate.schema.json` preserva exatamente os 20 nomes da rubrica. Sua semântica requer homologação.

- `duracao_faixa`: bins não fixados formalmente; **não impor** faixas inventadas.
- `legenda_tamanho`: limites para `curta/média/longa` não fixados; registrar decisão de operacionalização.
- `criador_e_empreendedor_real`: não pode ser inferido somente a partir de uma legenda ou visual; exigir evidência externa ou `null`.
- `hook_primeiros_3s`, `ritmo_cortes_0a10`: dependem de observação temporal da mídia, não apenas thumbnail.
- `forca_hook_0a10` e `clareza_mensagem_0a10`: requerem manual humano, âncoras comportamentais e medida de concordância.
- `elementos_top5`: até cinco, jamais preencher automaticamente com cinco quando evidência insuficiente.
- `tipo_post`: formatos comparáveis devem ser tratados por fonte e plataforma; ranking cross-platform condicionado à política.
- `unknown` distinto de `not_applicable`; valores ausentes não equivalem a zero ou falso.

**Bloqueio**: antes de aplicar classificação real, definir envelope `field_evidence` para cada atributo: origem, modalidade, evidência, timestamp (se aplicável), nível de observabilidade, revisor, modelo/prompt/versão e por que não observado. Este documento **não** homologa os enums candidatos da v5.
