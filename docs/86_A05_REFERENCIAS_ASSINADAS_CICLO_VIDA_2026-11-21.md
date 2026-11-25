# A05 / CAP-023 — vinculação durável e rechecagem de referências criativas

> Complemento operacional do Plano Único / Base Atemporal v6.1; não substitui IMP-174/175/177/180/182/192/199, CT-STUDIO, DEC-018 ou G0–G6/IMP-131. Nenhuma licença externa ou aprovação editorial é inferida.

## Lacuna fechada neste incremento

O PEP de referência criativa existente na PR #48 verificava grants e revogações no instante da criação de um rascunho, mas o documento não preservava em tabela própria **quais grants específicos** haviam sido usados. O novo contrato armazena uma ligação imutável de cada `tenant_id + document_id + content_id` ao `grant_id` e ao digest SHA-256 da lista ordenada de referências da primeira versão.

A criação de cada registro ocorre **na mesma transação** do `POST /v1/agent/creative-drafts`, após a checagem assinada e a criação da primeira versão. Qualquer falha de insert/constraint desfaz documento, versão, auditoria e vinculações; não se usa gravação assíncrona, fila, acesso a provedores ou mídia.

A migração `0018_studio_reference_bindings` é inicialmente vazia, com chaves de tenant e documento/conteúdo e política de downgrade que **rejeita** excluir histórico não vazio. Não há backfill que atribua direitos a documentos históricos ou manualmente criados; eles ficam **sem grants vinculados** e não podem passar por uma verificação assinada positiva por inferência.

## Rechecagem

A nova operação autenticada é:

```text
POST /v1/agent/creative-drafts/{document_id}/reference-recheck
```

- Exige sessão válida e papel `admin` ou `editor`; o tenant/ator nunca são lidos do JSON.
- Lê **a versão atual** do documento no mesmo contexto de transação, valida bindings contra o digest das referências e revalida cada referência não vinculada como sintética local legítima.
- Se houver referências externas vinculadas, exige o PEP efetivamente instalado no servidor, grants assinados para **ambas** as operações, revogação e fonte atuais; audita a rechecagem bem-sucedida via event/outbox na mesma transação.
- Grants ausentes, alterados, de outro tenant, expirados ou revogados, diferenças de payload/source e documentos externos sem vinculação levam a recusa. Não se retornam tokens, conteúdos originais ou IDs internos do grant.
- Resultado positivo informa apenas `SIGNED_REFERENCES_CURRENT_FOR_DRAFT_REVIEW_ONLY`, contagem de referências verificadas e os valores imutáveis `rights_status=pending_review`, `approval_status=draft`, `publication_allowed=false`, `production_approved=false`.
- Referências estritamente sintéticas podem retornar `LOCAL_SYNTHETIC_REFERENCES_ONLY`, **sem** aprovar publicação.

**Importante:** a rechecagem é um ponto de inspeção do ciclo de vida, **não** um controle transacional já ligado a todas as APIs de edição/render/export. Antes de produção, essas operações devem exigir uma avaliação PEP no próprio limite de uso, durante a transação que altera o artefato; um resultado de rechecagem anterior não é certificado para ações futuras. Também faltam PostgreSQL locking/concorrência e teste de recuperação/backup da migração.

## Prova e estado

- Arquivos: `studio_reference_bindings_a05.py`, `studio_reference_lifecycle_a05.py`, migração 0018, endpoint em `agent_api_e1.py`, persistência em `agent_draft_a05.py`, auditoria diferenciada no PEP, testes de associação/revocação/tenant/tamper e documentação.
- Ensaiado com Alembic `Operations` e SQLite descartável com o **mesmo texto e checksums** da migração 0018 publicada: criação vazia, rollback vazio, rejeição de rollback populado e preservação do registro, **PASS**. Não é a cadeia completa de migração.
- Os casos integrais adicionados são **15** (5 PEP E2E, 1 sintético, 7 na persistência incluindo parametrização e 2 no ensaio Alembic). Foram **escritos, NOT_RUN** no checkout completo.
- Pacote A11 Python A05/A07 agora espera **240 casos**, não 240 PASS. Nenhum dos gates G0–G6 foi liberado nem IMP-131 aceito. Não há deploy, merge ou operação de provedor.

## Verificação exigida no SHA da PR

```powershell
git rev-parse HEAD
python -m pytest -q -rs tests/test_studio_reference_bindings_a05.py tests/test_studio_reference_bindings_migration_a05.py tests/test_creative_reference_pep_a05.py tests/test_agent_atomic_draft_a05.py tests/test_a11_focal_evidence_packet.py
python scripts/verify_zero_spend.py
python docs/base_atemporal/ferramentas/validar_espelho.py
```

Depois da regressão focal, executar A11 completa e A00 full no **mesmo HEAD**, ensaio real de migração 0017→0018 com backup/restore em banco descartável e concorrência sob PostgreSQL. Manter R$0. DEC-018 permanece válida; não solicitamos aprovação institucional genérica novamente, mas direitos efetivos de fonte/provedor continuam requisito de operação.
