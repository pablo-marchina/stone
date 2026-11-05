# CAP-023 — incremento E3: IMP-182/183 (histórico e carrosséis)

**Referência vinculante:** Arquitetura Consolidada v5.1 + atualização v5.2 e Plano Único v5.2. Este incremento desenvolve o **mesmo** Creative Studio editável de C2, preservando contratos `CreativeSpec.v1` e `DesignDocument.v1`, sem criar outro produto nem alterar o plano.

## Entregas implementadas

- **IMP-182 (parcial):** rota `POST /v1/studio/documents/{document_id}/versions/restore`, recebe `expected_version` e `restore_version`. A restauração consulta uma versão histórica **do mesmo documento/tenant**, cria uma **nova versão**, preserva todas as versões anteriores e mantém estados de aprovação em `draft`, `pending_review`, `unverified`. A UI oferece Desfazer/Refazer com pilhas locais; o armazenamento remoto preserva o histórico. Texto modificado é salvo por ação explícita ou ao sair do campo (não é autosave temporizado robusto). O lock otimista de `current_version` rejeita alterações obsoletas.
- **IMP-183 (incremento de carrossel):** rotas para **duplicar/excluir/reordenar** páginas de documentos `instagram_carousel`, com limite de 10 páginas, ao menos uma página, IDs únicos, cópia independente da estrutura e preservação dos assets vinculados. A UI seleciona a página atual, edita suas camadas, duplica/exclui, move por botões ou arrasta abas. Feed continua com exatamente uma página.
- Sem novas migrações: a tabela existente `studio_document_versions` guarda snapshots imutáveis, com `edited_by` e `created_at`.
- Toda alteração exige sessão `admin/editor`, `tenant_id` obtido de autenticação e `expected_version`. `viewer` só lê. Não há efeito financeiro, publicação, download externo, autorização implícita de direitos ou admissão científica.

## Testes e evidências

- Testes de duplicar/reordenar/excluir; snapshot antigo intacto; restauração versionada; proibição de última página; feed sem carrossel; limite de dez; falha atômica; concorrência obsoleta; isolamento por tenant; autenticação e role.
- No checkout local de implementação com base B2+C2 disponível: `321/321` testes Python, `3/3` Node, `node --check`, `scripts/check_gate0.py` e `scripts/verify_zero_spend.py` passaram.
- A suíte local **não** reproduz exatamente a `main` remota A2+A3+B2+C2; o PR precisa de CI/regressão no seu HEAD antes do merge. Não afirmar homologação integral da CAP-023.

## Pendências de continuação do mesmo plano

- **IMP-182:** diff amigável entre versões, autosave persistente com recuperação após falha, ETag HTTP/If-Match explícito e UX de histórico entre sessões.
- **IMP-183:** ensaio de arrastar/reordenar em navegador real, acessibilidade e tratamento de erros em fluxos grandes.
- **IMP-184 (dependente):** renderização/exportação PNG/JPEG/SVG e **ZIP de carrossel** com verificação de paridade. O botão atual exporta **somente a página selecionada** em PNG, e não pode ser descrito como exportação integral.
- Depois, seguir as tarefas posteriores do Plano Único sem reduzir o escopo arquitetural.

## Validação local sugerida

```powershell
python -m pytest -q tests/test_studio_e1.py tests/test_studio_c2.py tests/test_studio_pages_e3.py
python -m pytest -q
node --check src/tapi_gate0/web/studio.mjs
node --test tests/frontend/test_events.mjs
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
```

Testar também o fluxo na página `/app/studio.html` em banco local ou cópia do banco, **sem substituir dados reais sem backup**.
