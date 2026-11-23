# A11 / A05 / A07 / DEC-008 — ampliação focal e SVG real (23/11/2026)

## Estado verificado pelo operador antes deste incremento

SHA 587f4c5cfc22205b11a58422520cc0267a9c374d, Windows/Conda, PYTHONPATH do próprio checkout. Bateria focal de nove arquivos: **72 passed in 61.08s; TEST_EXIT=0**, sem falhas/skips. Inclui testes reais LangGraph e SqliteSaver, retomada após exceção, preflight de integridade, nova jornada vertical e DAG. Resultado é log do operador, não prova assinada de CI, hard kill, exactly-once ou gates.

## Frente A — A11 obrigatória e reproduzível

Em scripts/a11_focal_evidence_packet.py, os testes portáveis abaixo passam a fazer parte do estágio Python A05/A07:

- tests/test_a11_architecture_frontier.py (6 cenários);
- tests/test_dec008_resume_preflight.py (6 cenários);
- tests/test_architecture_vertical_synthetic.py (agora 3 cenários, inclusive export SVG real).

Contagem fixada: **406 = 391 antigos + 6 + 6 + 3**. Mudança não remove testes antigos, checkpoints, gates ou requisitos: A11 continua a recusar skips/falhas, HEAD incorreto, banco não autorizado, mídia e qualquer desvio de gasto zero. A11 fixa SHA-256 do analisador, três matrizes oficiais, probe Node, novos testes e código do adaptador.

O teste tests/test_a11_focal_evidence_packet.py foi atualizado para expectativa 406 e para garantir que novos casos estão **incluídos na execução**, não apenas no inventário de arquivos.

## Frente B — API segura -> documento editado -> SVG

scripts/a11_studio_export_probe.mjs roda a implementação E4 real studio_export_e4.js sem rede ou navegador, usando VM/Canvas de teste. Recebe por stdin SOMENTE o DesignDocument fornecido pela API autenticada em testes/test_architecture_vertical_synthetic.py, já na versão 2 após edição explícita com If-Match.

O teste verifica bytes de SVG, digest SHA-256 do manifest, versão 2, título alterado, marca "RASCUNHO - NAO PUBLICAR", imutabilidade do documento e ausência de texto adversarial do caption. Imprime apenas JSON reduzido, nunca conteúdo criativo bruto. Não aprova publication/rights/corpus.

Limites claros: **não conecta o grafo autônomo à escrita no Studio**; essa transferência exige um ato distinto do operador e passagem pelo PEP. O teste não processa mídia real, não valida gold científico, não demonstra paridade de pixels do navegador, não publica e não valida G0–G6.

## Validação pendente

Novo HEAD da PR #72 deve executar:
1. python -m pytest -q -rs tests/test_architecture_vertical_synthetic.py tests/test_a11_focal_evidence_packet.py
2. python -m scripts.a11_focal_evidence_packet --expected-head SHA_EXATO --output CAMINHO_NOVO.json
3. Regressão integral somente após A11 focal PASS, no **mesmo commit**.

Meta esperada para o A11: **10/10 etapas** como antes, com estágio Python A05/A07 **406/406** em vez de 391/391. Este ainda não é resultado observado no HEAD novo.

**Todos os gates G0–G6, IMP-131 e deploy permanecem BLOCKED**. DEC-008 continua OPEN; nenhum merge, migração operacional, LLM externo ou gasto autorizado.
