# TAPI Stone — inteligência e operação de conteúdo

Plataforma unificada de pesquisa observacional, inteligência de conteúdo e criação editável para Stone/MPEs. A entrega é única (IMP-131), subordinada aos critérios da Base Atemporal e aos gates globais. Desenvolvimento incremental não equivale a homologação.

## Comece aqui

- [Portal de documentação](docs/README.md): escolha sua trilha de leitura.
- [Base Atemporal v6.1](docs/base_atemporal/INTEGRACAO.md): escopo, fontes integrais, autoridade e limites.
- [Plano Único](planning/base_atemporal/): requisitos U, CAP, IMP, DEC, CT, contratos e gates.
- [Estado observado em 24/11/2026](docs/governance/STATE_2026-11-24.md): referências pinadas, diferenças main/desenvolvimento e limites. Não é estado vivo.
- [Fluxo GitHub](docs/REPOSITORY_WORKFLOW.md) e [orientações para agentes](AGENTS.md).

## Invariantes

R$ 0; não habilitar cobrança, coleta ou publicação externa por alteração documental. DEC-018 registra a aprovação institucional comunicada; não repetir pedido genérico e não confundir aprovação com direitos efetivos, grants, credenciais, tenant, quotas ou ciência. IMP-062 dispensado, não cumprido. Não há comprovação de homologação integral neste corte.

## Desenvolvimento local

Consulte a documentação de implantação da branch e o ambiente existente antes de executar. Em checkout íntegro:

```bash
python docs/base_atemporal/ferramentas/validar_espelho.py
python scripts/documentation_catalog.py check
python scripts/documentation_catalog.py index
python scripts/documentation_catalog.py graph
python scripts/verify_zero_spend.py
```

Os três comandos documentais não usam rede, DB, modelos ou credenciais. O grafo é uma projeção das matrizes, não um plano alternativo. Para a aplicação, use o procedimento local e testes pertinentes na branch; não execute instruções históricas sem checar seu contexto.

## Histórico

O [README anterior, preservado no SHA de origem](https://github.com/pablo-marchina/stone/blob/4622d0171c8b1ea72f7c892c77fd7118fd12ae5e/README.md), contém o histórico detalhado, exemplos de instalação e incrementos anteriores. Os documentos originais e seus caminhos permanecem intactos.
