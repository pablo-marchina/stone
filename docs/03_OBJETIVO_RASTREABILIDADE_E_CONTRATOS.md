# Rastreabilidade e fechamento de contratos

Referência científica/engenharia: Design Science Research, Evaluation-Driven Development, ISO/IEC 25010:2023. Referência de arquitetura: v5.1. Referência de execução: Plano Único.

## Identificação

`U01–U18` = critérios; `CAP-001–CAP-022` = capacidades; `DEC-001–DEC-012` = decisões; `CT-01–CT-18` = verificações metodológicas; `F01–F12` = lacunas da auditoria v5.1. Nenhum identificador implica execução concluída.

## Contratos que ainda precisam de fechamento

Os 23 esquemas de `reference/contract_candidates.json` e a rubrica de `reference/rubric_candidate.schema.json` são **candidatos**. Um `source_use_grant` é um contrato de permissão, não um contrato completo de `/v1/collections`. Da mesma forma, o plano estatístico não substitui contrato do endpoint de ranking.

Para cada capacidade, especificar: request, response, códigos de erro, validações cruzadas, ACL/tenant, idempotência, exceções, volume, versão, telemetria, testes positivos/negativos, critérios de segurança e normas ISO relevantes. Publicar OpenAPI/Pydantic/MCP com *contract tests* e compatibilidade entre versões. A decisão formal sobre categorias ausentes no PDF deve permanecer explícita; não inventar faixas de duração.

## Gate de engenharia

Novo endpoint só é implementável com `contract_id` real, fixtures, comportamento no caso sem permissão e teste definido antes da implementação. Um endpoint só é liberável após validação completa; placeholders e endpoints vazios não contam como capacidade operacional.
