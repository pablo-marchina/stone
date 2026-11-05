# Trilha C — CreativeSpec → DesignDocument editável (incremento C1)

**Estado:** editor de **documentos de texto estático** como contrato/persistência de draft. Não existe ainda canvas gráfico, asset autorizado, geração LLM, export PNG/JPEG/SVG, vídeo ou publicação.

## Implementado

- `src/tapi_gate0/studio_e1.py`: `CreativeSpec`, `Canvas`, `TextLayer`, `DesignPage`, `DesignDocument` e patch explícito de texto/posição/tamanho. Valida geometria, IDs únicos, limites e números inteiros.
- `draft_from_spec`: documento editável de três camadas (título, corpo e CTA) sem inventar referências e sem afirmar que houve inferência IA. Os IDs de conteúdo continuam `reference_status=unverified` até serem verificados contra o repositório de evidências.
- `StudioStore`: head + histórico imutável de versões, isolamento por tenant, escrita transacional e lock otimista por `expected_version`.
- `migrations/versions/0007_studio_e1.py`: tabelas de documentos e versões com FK; requer Alembic 0006 já integrado.
- `src/tapi_gate0/studio_api.py`: autenticação em `/v1/studio/documents`, GET do head e de versões e POST de patch; somente admin/editor podem escrever, demais papéis autenticados podem visualizar no tenant.
- Toda versão é `approval_status=draft`, `rights_status=pending_review`, `render_status=not_implemented`: sem publicação ou render implícito.

## Verificar (Windows/Miniforge)

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_studio_e1.py
python -m pytest -q
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
git rev-parse HEAD
```

Para um banco persistente que já esteja na migração 0006, executar `python -m alembic upgrade head` **somente em ambiente de desenvolvimento**, com `TAPI_DATABASE_URL` seguro; revisar backup e rollback antes de produção.

## Próxima implementação de C2

Comparar Fabric/Konva (DEC-013), implementar canvas visual e serializador seguro, salvar camadas de imagem vetorizadas/ativos licenciados, carregar versões/undo/redo, exportação reproduzível; depois carrossel e timeline/FFmpeg (DEC-014). Vincular CreativeSpec aos IDs de recomendações B sem confiar em IDs fornecidos por cliente. Integrar RBAC e migrações de forma compatível com as demais branches.

**Atenção à integração:** as trilhas B e C tocam `secure_api.py`. Ao juntá-las, preservar ambos os roteadores. Não atribuir a C1 uma capacidade de edição visual que ainda não foi implementada.



## Incremento C2 — canvas visual, PNG e edição persistida

- A tela **`/app/studio.html`** possui login seguro, criação/abertura de rascunho, seleção e arraste de camadas, edição de textos, upload de imagem e exportação PNG pelo navegador. Usa canvas nativo JS; DEC-013 (Fabric/Konva) ainda será comparada antes de escolher um motor de edição avançado.
- `studio_canvas_c2.py` guarda arquivos PNG no banco por tenant, com SHA-256, tamanho máximo de **512 KiB**, dimensões máximas 2048×2048, cabeçalhos/CRC/pixels verificados e atestação de direito do ativo. Nunca requisita ativos externos nem aceita SVG executável.
- `ImageLayer` foi incorporada ao `DesignDocument`. Operações de inserir imagem e mover/redimensionar geometria são transacionais, com versão esperada e histórico append-only.
- A migration Alembic **0007** agora cria `studio_assets` além de `studio_documents` e `studio_document_versions`.
- API: `POST /v1/studio/assets/png`, `GET /v1/studio/assets/{id}/binary`, `POST /v1/studio/documents/{id}/image-layers`, `POST /v1/studio/documents/{id}/geometry`. Todos autenticados, mutações só para admin/editor.
- O PNG exportado é um artefato **raster derivado no navegador**; não altera `DesignDocument`. Render de servidor, ZIP de carrossel, fontes externas, undo/redo avançado, timeline/vídeo e revisão por IA permanecem pendentes.

### Testes

```powershell
python -m pytest -q tests/test_studio_e1.py tests/test_studio_c2.py
python -m pytest -q
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
node --check src/tapi_gate0/web/studio.mjs
git rev-parse HEAD
```

A migration 0007 deve ser aplicada com `python -m alembic upgrade head` **somente em banco de desenvolvimento revisado**. O armazenamento é limitado por arquivo (512 KiB); quotas agregadas, antivírus e backup/restore ainda precisam ser projetados para operação prolongada.
