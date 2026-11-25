# Consolidação da main — 24/11/2026 BRT (25/11 UTC)

O responsável autorizou explicitamente integrar a cadeia de desenvolvimento. A main anterior `ed77e4e6ff3ceb24616264d9d04b38d0fba57209` era ancestral do HEAD #99 `3c892e39aa8b655e5132eed0f41e9f5c286c0438` (1116 commits ahead, 0 behind). O [PR #99](https://github.com/pablo-marchina/stone/pull/99) foi redirecionado para main e mesclado com preservação de ancestralidade. Merge `98a6f8fb8c3b44e86e3dc960684e3b564ecdfc00`; árvore Git `5ffa5fcf7ff430a8c1f0f5efb6d50bc753e5afff` idêntica ao HEAD validado pelo operador. Nenhuma modificação de runtime ou resolução de conflito foi necessária durante o merge.

## Disposição dos PRs e branches

- 56 PRs inicialmente abertos; após a integração, zero abertos. #99 e #43 marcados merged no GitHub; outros 51 PRs ancestrais encerrados como redundantes (commits alcançáveis na main); #49, #58 e #70 encerrados por portabilidade/reconciliação no #71, não por identidade integral nem ancestralidade de seus heads.
- As 99 refs de branches foram preservadas; nenhuma branch excluída ou reescrita. [Inventário do corte](BRANCH_INTEGRATION_2026-11-24.json). PRs anteriormente mesclados podem ter heads divergentes por squash/rebase. Registro de merge anterior não constitui auditoria de equivalência semântica de cada arquivo.
- Propostas antigas encerradas #10/#22/#27–32 (exceto PRs de fato mesclados) não são reintroduzidas; DEC-018 e decisões vigentes prevalecem. Laboratórios arquivados podem conter experimentos únicos ainda não avaliados. A branch sem PR feat/a027-s1-guarded-readonly-handoff-20261123 é alternativa histórica ao handoff protegido #78: implementação e runner evoluídos e teste com outro nome; arquivo de teste antigo não está na main, sem declaração de equivalência de cada caso. A branch rebase/imp170-discovery-v2-0006-20261103 permanece preservada como variante histórica. Eventual recuperação seletiva deve ser vinculada às IMP existentes e verificada, não aplicada cegamente.
- #70: asset_fixture_batch.py e dois arquivos de teste idênticos por blob ao HEAD #99; runner e documentação reconciliados. #58: teste CLI idêntico, bridge e runner evoluídos. #49: arquivos de PEP e testes evoluídos; #71 documenta a incorporação do lock e teste negativo. Não alegar merge individual dessas três branches.
- A partir deste corte, novos trabalhos devem partir da main atual, e não de branches arquivadas. O inventário é histórico, não monitoramento vivo.

## Evidência do operador (reportada, não reexecutada nesta sessão)

No SHA `3c892e39aa8b655e5132eed0f41e9f5c286c0438`: PASS_ESPELHO_DOCUMENTAL, 32 blobs, 204 IMP, 543 dependências, DAG acíclico, sink IMP-131. PASS_DOCUMENTATION_STRUCTURE, 152 Markdown, 625 nós, 7181 arestas, 16 candidatos sem correspondência nominal. 5 testes documentais PASS em 1.96s e verify_zero_spend PASS. A árvore do merge é idêntica ao SHA testado; este registro posterior é documental, exige revalidação do HEAD final. Nenhuma regressão integral do produto foi executada nesta integração.

## Limites e continuidade

Consolidação Git de desenvolvimento, não autorização de produção nem homologação. Sem migração de banco, nova aquisição, publicação externa, serviço faturável ou promoção científica. G0–G6, DEC-008, IMP-131 e demais critérios permanecem sujeitos a suas evidências. Preservar DEC-018, controles efetivos e R$0. Reexecutar espelho, catálogo, testes documentais, preflight, focais e regressão integral no checkout limpo da main. Não transferir PASS de um SHA para outro.
