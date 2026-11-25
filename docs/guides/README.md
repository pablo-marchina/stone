# Guia de trabalho documental local

Pré-requisito: checkout íntegro da branch autorizada, Python do projeto e acesso à Base Atemporal privada. Não instalar serviços, modelos ou dependências para a verificação documental.

1. Confirme `git status --short`, `git rev-parse HEAD` e a base do PR. Consulte [portal](../README.md), [fluxo](../REPOSITORY_WORKFLOW.md) e fonte integral.
2. Execute `python docs/base_atemporal/ferramentas/validar_espelho.py`.
3. Execute `python scripts/documentation_catalog.py check` e `python scripts/documentation_catalog.py index`. O índice é baseado no checkout local e não deve ser tomado como inventário de outras branches.
4. Consulte `python scripts/documentation_catalog.py graph` para localizar vínculos explícitos do Plano Único. Para um arquivo local privado, redirecione a saída para um caminho fora do repositório. A ferramenta não grava por conta própria.
5. Registre o trabalho com os [templates](../governance/TEMPLATES.md), rode os testes focais e `python scripts/verify_zero_spend.py`; preserve FAIL/SKIP, SHA e limites.
6. Revise o diff e PR sem publicar fontes privadas nem modificar gate. Se houver drift, não atualizar hashes para mascarar falha; reconciliar a alteração com a autoridade da base.

## Operação do produto

A [documentação anterior pinada](https://github.com/pablo-marchina/stone/blob/4622d0171c8b1ea72f7c892c77fd7118fd12ae5e/README.md) conserva procedimentos de instalação e incrementos. Para trabalho de vídeo no corte de 24/11, consultar [Kinetic v4](../133_DEMO_SOCIAL_KINETIC_2026-11-24.md). Para ambiente nativo, seguir preflight e comandos do registro pertinente ao SHA. Esses procedimentos históricos não garantem que dependências, banco e permissões atuais estejam disponíveis. O manual de operação de produção ainda depende de homologação.
