# Evidência de implementação — contratos e domínio unificado

## Estado observado localmente

- **138 testes automatizados aprovados**: 102 da base Gate 0 mais 36 verificações adicionais de contratos/domínio (contagem obtida pela suíte pytest local).
- `scripts/check_gate0.py`: **11 verificações estruturais aprovadas**.
- `scripts/verify_zero_spend.py`: política local de custo **R$ 0** aprovada.
- Gerador `scripts/export_local_openapi.py`: **22 rotas OpenAPI**, incluindo as do bootstrap e as ações externas explicitamente bloqueadas; não significa 22 capacidades de produto implementadas.
- Modelos Pydantic da jornada de conteúdo e de governança; migração SQLite local `0001_unified_local_domain.sql`.
- Teste de persistência após reiniciar o processo com o mesmo banco local; rollback em caso de falha de gravação; outbox transacional.
- Ranking sintético determinístico por `(likes+comments)/followers`, recorte por idade, metadados de seguidores, tratamento de missing/zero e empate por ID.
- Testes de evidência em cada valor da rubrica, incluindo campos temporais e comprovação externa de empreendedor.
- Testes de bloqueio de coleta externa, publicação, CRM, campanha paga e tentativas de troca de tenant.

## Como reproduzir

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
PYTHONPATH=src python scripts/export_local_openapi.py
```

## O que NÃO foi validado

Nenhum dado real, processamento multimodal real, sistema de identidade de produção, integração OAuth, LangGraph, FastMCP, frontend, avaliação humana institucional, PostgreSQL, hospedagem, SLO, ISO/IEC 25010 completa ou direitos sobre mídia. Este relatório **não atesta homologação, qualidade estatística da pesquisa nem operação em produção**.

## Registro metodológico

- Artefato DSR: núcleo de domínio executável e seu contrato OpenAPI gerado.
- Baseline: ranking oficial sem predição; persistência SQLite local.
- Avaliações EDD: HTTP contract tests, validação Pydantic, regras de autorização, isolamento de tenant e operações de custo zero.
- Próximo ciclo de pesquisa: fechar decisões da rubrica e identidade de produção; comparar alternativas PostgreSQL/SQLite e operação gratuita sem comprometer privacidade; apenas iniciar coleta quando existir permissão.

A arquitetura mantém uma única entrega final; a existência deste registro não representa uma entrega separada do produto.
