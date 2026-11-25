# Registro de validação da reorganização documental — 24/11/2026 BRT

Escopo exclusivo de organização, sem alteração normativa ou aceitação de software. Base #98 `4622d0171c8b1ea72f7c892c77fd7118fd12ae5e`. O ZIP v6.1 original passou no próprio validador. Manifesto original: 32 entradas coincidentes, byte a byte, com o Git; 204 IMP, 543 dependências, DAG acíclico, sink IMP-131.

## Execuções e método

- Validação do ZIP: PASS, 190 arquivos manifestados, 419 seções, 19 conflitos explícitos.
- Reconstrução documental descartável: 32 arquivos do ZIP com os hashes originais conferidos, validador existente com blob `4575aca3f4525501eb014fb436fd8c1084af4341`; manifesto de teste com os mesmos pares caminho/hash, páginas de entrada representadas por fixtures de presença. Não é checkout integral.
- `python scripts/documentation_catalog.py check`: PASS em reconstrução (625 nós, 7181 arestas com proveniência, 16 referências de candidatos de contrato sem correspondência nominal exata na lista de schemas).
- `python -m pytest -q tests/test_documentation_catalog.py`: 5 PASS em 0.72s na reconstrução. Blobs locais testados: script `4710e2f909038a3a8b9814503f5ce7acd4f2bff6`, teste `beac059ac16088bfce3654c73f99386cf02a3ed0`.
- Versão ampliada: 76 links relativos em Markdown alterado conferidos contra a árvore Git, zero destinos ausentes; os dois blobs de código/testes acima e os 32 blobs normativos conferem com os hashes remotos. Diff de 15 caminhos, nenhuma remoção.
- Não executados: suíte de produto, CI local integral, operação, verificação de links externos, auditoria semântica de todos os arquivos ou validação científica.

## Lacunas e limites

Os 16 registros de contrato sem correspondência nominal exata são uma constatação de nomenclatura nas duas tabelas, não prova de inexistência de implementação ou schema. O catálogo não gera equivalências falsas. Reconciliar pelos contratos e schemas existentes sob as IMP correspondentes, sem modificar unilateralmente a fonte normativa. Os nós DOMAIN e CONTRACT possuem chaves de projeção baseadas no grupo e na operação, não novos IDs oficiais. Arestas distinguem origem; múltiplos registros podem apoiar a mesma relação. Conflitos são nós sem ligações inferidas do texto livre. O catálogo cobre os 15 arquivos tabulares, sem afirmar que todas as informações de cada linha foram convertidas em arestas. Os registros antigos mantêm seus caminhos; classificação semântica detalhada e documentação de runtime/usuário final permanecem pendentes.

## Próxima ação

Executar validador, catálogo e testes no checkout exato do PR #99; reportar SHA e saídas. Não promover gates, DEC-008, ciência, publicação ou IMP-131. Preservar DEC-018 e custo zero.
