# Sincronização das matrizes do Plano Único v5.2 — 05/11/2026

**Fonte obrigatória:** `TAPI_Stone_Plano_Unico_Implementacao_v5_2_2026-10-30.zip`, SHA-256 `0dbb51bf18a75734fcb2121373590bfc1ba3ae5cd729aff9a4dcb537491aa04d`.  
**Commit auditado:** `main@79bb0173c90cbc993481bf1e959154adf796a5de`.  
**DEC-018:** [registro formal da decisão do responsável](53_DEC018_CONFIRMACAO_ALCANCE_E_CRITERIO_REVISAO_2026-11-05.md).

## Arquivos e estados

| Matriz original | Linhas antes | Linhas depois | Tratamento |
|---|---:|---:|---|
| `MATRIZ_CAPACIDADES.csv` | 23 | 23 | Atualização de estado com PR e ressalva |
| `BACKLOG_UNICO_IMPORTAVEL.csv` | 204 | 204 | 67 tarefas com evidência incremental; nenhuma conclusão total inferida |
| `MATRIZ_DECISOES.csv` | 15 | **18** | Preserva DEC-001–015; acrescenta DEC-016/017/018 |
| `MATRIZ_GATE_GLOBAL.csv` | 7 | 7 | Status auditado; **nenhum gate liberado automaticamente** |

**Invariantes:** 204 IDs e ordem de tarefas preservados, **543/543 dependências idênticas**, grafo acíclico, 23 CAP, 7 gates, 207 relações ISO e 414 relações critério-capacidade preservadas. Os outros nove CSVs do ZIP permanecem byte a byte inalterados no pacote completo entregue nesta conversa.

## Estado no Git

Versionamos as evidências incrementais na pasta `planning/v5_2/audit_2026-11-05/`:

- `MATRIZ_CAPACIDADES_EVIDENCIAS.csv` — 23 linhas;
- `BACKLOG_EVIDENCIAS_INCREMENTAIS.csv` — 67 linhas, incluindo IMP-062;
- `MATRIZ_DECISOES_EVIDENCIAS.csv` — decisões com evidência nova;
- `MATRIZ_GATES_EVIDENCIAS.csv` — 7 linhas.

O gerador `scripts/sync_plano_v52_audit.py` aplica esses overlays ao **ZIP original exato**, valida contagens, IDs, dependências e ciclos, e reconstrói os CSVs completos com um manifesto. O ZIP completo atualizado também foi disponibilizado como artefato na conversa, **não como blob no GitHub**. Isto mantém rastreabilidade entre baseline externo e deltas em Git.

### Reproduzir localmente

```powershell
python scripts/sync_plano_v52_audit.py "C:\\TAPI-Private\\TAPI_Stone_Plano_Unico_Implementacao_v5_2_2026-10-30.zip" --out-dir "C:\\TAPI-Private\\matrizes-sincronizadas"
```

Não precisa de rede ou credenciais. O script recusa a versão incorreta do ZIP e não altera banco, grants ou código do produto. A saída deve ser conferida no checkout do PR usando o ZIP original com o SHA informado.

## Aplicação de DEC-018

O responsável comunicou **aprovação institucional formal abrangente** em 04/11 e estabeleceu **ausência de revisores humanos e de validação científica independente**. O documento institucional externo não foi anexado para auditoria independente. A exigência original de **≥50 revisões humanas** permanece registrada historicamente; sua dispensa é **mudança declarada de critério**, nunca requisito cumprido.

Assim, CAP-004 e IMP-062 apresentam a dispensa DEC-018 de forma visível, com `G3-EVAL` **não liberado** enquanto outros testes aplicáveis permanecerem incompletos. O sistema não deve fabricar revisores ou apresentar F1 de textos artificiais como acurácia científica.

## Evidências e limitações

- PR #36: 3 posts técnicos Meta reais persistidos e snapshots; **nenhum post cientificamente admitido comprovado**.
- PR #40: 358 testes Python/7 Node reportados na árvore publicada; **sem CI remoto**, quatro testes Python E8 auxiliares ausentes.
- Escolhas de Canvas/FFmpeg são baselines incrementais; não encerram automaticamente benchmarks DEC-013 e DEC-014.
- Custo financeiro R$0, direitos por operação, limites técnicos e efeitos externos bloqueados permanecem vigentes.
- Este trabalho **não constitui homologação de produção**, certificação ISO nem cumprimento do escopo institucional integral.

## Checklist

- [x] Decisões DEC-016 a DEC-018 incorporadas sem renumerar IDs.
- [x] Status de CAP, IMP, DEC e gates relacionados a PRs e evidências.
- [x] Dependências e matrizes de referência preservadas e verificadas no pacote local.
- [x] Código gerador e deltas de evidência versionados no Git.
- [ ] Rodar a reconstrução no checkout do PR usando o ZIP original.
- [ ] Aceite da entrega única permanece condicionado aos gates restantes.
