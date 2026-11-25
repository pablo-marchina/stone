# Padrão documental unificado — v1

Escopo: organização, manutenção e apresentação. Não altera requisitos, arquitetura pretendida, decisão tecnológica, oráculos, autorização, gates ou orçamento da Base Atemporal v6.1. A precedência normativa existente em [00_Indice_e_Protocolo](../base_atemporal/00_Indice_e_Protocolo.md) permanece. Este padrão adapta Diátaxis, arc42, ADR, docs-as-code e rastreabilidade bidirecional ao Stone; não declara conformidade ISO.

## 1. Fontes únicas e autoridade

| Entidade | Fonte canônica | Visões derivadas |
|---|---|---|
| Escopo, objetivos, método, arquitetura alvo | Núcleo v6.1 + proposta/fontes integrais incorporadas + DEC vigente | Portal, mapas, explicações |
| U/CAP/IMP/DEC/CT/gates/contratos | planning/base_atemporal (matrizes) e fontes integrais correspondentes | Grafo, índice, fichas |
| Contrato implementado | schema/código executável, versão e teste | referência gerada; não substitui contrato alvo |
| Implementação presente | checkout Git com SHA | inventário e diff |
| Evidência de execução | recibo/log autorizado, SHA, ambiente, comando e resultado | snapshot, relatório |
| Estado operacional | observação autorizada e datada, não estimativa de README | snapshot e PR |
| Autorização | DEC-018 e controles efetivos aplicáveis | resumo; nunca amplia direitos |

Não duplicar backlog, status ou tabela normativa manualmente. Alterações de requisito ou método seguem DEC e revisão explícita de matriz/manifesto. Quando o código diverge da especificação, registrar lacuna; não reescrever o requisito para adequá-lo ao código. Não publicar originais privados, credenciais, grants, dados ou mídia restrita.

## 2. Classes documentais independentes

- Normativa/atemporal: o que deve ser; mudança por governança.
- Viva: guias, contratos implementados e navegação; conferir no checkout.
- Histórica: estado observado ou reportado em um corte, identificado por SHA e data; imutável por padrão, correção por adendo.
- Gerada: visão calculada de fonte(s) identificadas; não editar à mão.

A classe temporal não determina autoridade. Diátaxis (tutorial, guia prático, referência, explicação) é outro eixo. Um documento histórico pode conter referência, explicação e instruções datadas. Não promover por nome de arquivo. Os registros numerados legados conservam seus caminhos e conteúdo; seu catálogo automático oferece uma classificação inicial, não auditoria semântica.

## 3. Convenções de escrita

Português brasileiro como idioma narrativo padrão; preservar identificadores, contratos, comandos e citações originais. UTF-8, Markdown, título H1, subtítulos sem saltos desnecessários, links relativos verificáveis no contexto correto. Datas ISO 8601, hora com fuso quando conhecida, SHA completo para prova, unidades explícitas. Manter nomes dos arquivos legados. Novos incrementos em docs/records/YYYY-MM-DD/<slug>.md, novos guias em docs/guides/, novos mapas em docs/architecture/; sem renumerar IDs. Usar links para fontes canônicas, não colar seus dados. Preencher [templates](TEMPLATES.md), marcar desconhecido como NAO_AVALIADO e distinguir fixture, execução reportada e observada.

## 4. Estados e evidência

Registrar separadamente: estado documental, estado de implementação, tipo de evidência, verificação, validação científica, autorização e operação. PASS tem escopo (comando/fixture/ambiente/SHA); SKIP e FAIL são explícitos. Não somar lotes sobrepostos nem transportar PASS a outro SHA. Estado Git merged não prova aceite. Quando SHA da execução for diferente do SHA documentado, registrar ambos. Não alegar ciência por proxy, concordância de modelos ou testes técnicos. IMP-062 dispensado por DEC-018, não cumprido; scientifically_validated=false na ausência de evidência legítima. Gates somente conforme oráculos vigentes. A decisão institucional comunicada é suficiente para governança dentro do escopo, sem inventar instrumento externo ou validade; direitos técnicos, revogação, tenant, quotas e segurança continuam obrigatórios.

## 5. Fluxo docs-as-code local

Antes: consultar HEAD/PR, índice, fonte integral, IDs e dependências; executar validador do espelho. Durante: atualizar somente a fonte responsável, registrar links IMP/CAP/U/DEC/CT, incluir resultado e limites no registro datado. Depois: rodar `python scripts/documentation_catalog.py check`, testes documentais e zero-spend; revisar diff, preservar escopo, anexar evidências privadas por identificador autorizado. PRs de documentação separados quando possível; sem rebase destrutivo, automerge, CI pago ou liberação de produção. Mudança normativa exige aprovação aplicável e atualização consciente de hashes, nunca regenerá-los para esconder drift.

## 6. Critérios de qualidade e limites

IDs de nós únicos; vínculos explícitos com endpoints existentes; DAG acíclico e sink IMP-131; hashes espelhados exatos; índice da branch regenerável; fonte/escopo e limitações claros. O grafo usa os 15 arquivos tabulares e registra a origem de cada aresta; chaves de projeção para domínio e operação não são IDs normativos novos. Não inferir ligações do texto livre nem equivalências entre contratos e schemas. O catálogo valida estrutura, não correção semântica de todos os textos ou validade de URLs externas. Referências históricas privadas e links do espelho são resolvidos pelo pacote integral; não reescrever links automaticamente. Auditoria de qualidade textual, tutoriais finais, revisão de contratos runtime e evidência independente continuam distintas.

## Referências metodológicas

[Diátaxis](https://diataxis.fr/), [arc42](https://arc42.org/overview/), [C4](https://c4model.com/), [ADR](https://adr.github.io/), [Docs as Code](https://www.writethedocs.org/guide/docs-as-code/), [NASA SWE Handbook](https://swehb.nasa.gov/). As práticas foram adaptadas, não impostas como novas condições de aceite institucional.
