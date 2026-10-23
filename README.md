# TAPI Stone — Gate 0 / Engineering Readiness

**Status:** bootstrap técnico com contratos operacionais do primeiro fluxo sintético local; ainda não é a plataforma TAPI completa. **NÃO APROVADO para produção nem coleta/publicação externa.**

Este pacote materializa as decisões do responsável pelo projeto: **repositório privado** `pablo-marchina/stone` (existente e acessível), **comparar infraestrutura** (decisão aberta), **custo financeiro total R$ 0 (bloqueio obrigatório)**, **permissões pendentes**, **escopo ampliado aprovado pelo solicitante; autoridade institucional não comprovada**. Segue a Arquitetura Unificada v5.1 e o Plano Único, sem alterar o objetivo de **uma entrega final consolidada**.

## O que funciona agora

- API de bootstrap com health check e status de readiness, sem conectores a redes sociais.
- Política **deny-by-default** avaliada localmente: todas as fontes/operações externas são negadas, inclusive publicação, CRM e anúncios; fixtures sintéticas internas permitidas somente para verificação.
- Schemas candidatos da rubrica e contratos herdados sem declará-los homologados.
- Testes automáticos de autorização, invariantes e integração leve do bootstrap; CI reproduzível.
- Matrizes de autorização, decisões abertas, protocolo de experimentos de infraestrutura, restrições de gasto, governança de avaliações e registro de pendências.

## Execução local

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
uvicorn tapi_gate0.api:app --host 127.0.0.1 --port 8000
# outra janela: curl http://127.0.0.1:8000/healthz
# curl http://127.0.0.1:8000/v1/gate0/status
```

Não é necessário criar conta na nuvem ou possuir chaves para rodar. `docker compose up --build` inicia apenas a API local; o banco de teste é opt-in com `docker compose -f compose.yaml -f compose.local-db.yaml up --build` e exige `TAPI_DB_PASSWORD` configurado fora do repositório. O endpoint público não deve ser exposto à internet; ele não substitui autenticação/autorização da aplicação final.

## Fluxo seguro de implementação

`Contratos/gold/identidade → pipeline sintético interno → aquisição apenas após autorização → classificação/avaliações → experiência única → homologação operacional`. São **passos internos**, não entregas distintas.

## Situação de aprovação

- **Gate 0A:** *PARCIAL — bootstrap técnico local pronto; definição de identidade de produção, permissões, contratos restantes e decisões tecnológicas pendentes.* Pode iniciar engenharia local limitada.
- **Gate 0B:** *BLOQUEADO — não existem autorizações comprovadas de fonte/operação nem autoridade de aprovação confirmada.*
- **Aceite global da arquitetura:** *NÃO INICIADO*; aprovação de Gate 0 não representa aceite da plataforma.

Comece em `docs/00_MAPA_E_STATUS.md`, depois `docs/01_ACOES_DO_RESPONSAVEL_E_STONE.md`. Os documentos `docs/` não contêm prazos nem divisão de entregas.

## Decisões adicionais do solicitante

- **Custo financeiro máximo: R$ 0**, em todo o produto. Não habilitar integração com serviços que possam gerar faturamento.
- **Escopo ampliado aprovado pelo solicitante**, sem presumir aval institucional nem direitos sobre conteúdo externo.
- **GitHub privado em uso**: `pablo-marchina/stone`; ver `docs/15_REPOSITORIO_GITHUB.md`.
- Os testes automatizados são executados **localmente** com `bash scripts/ci_local.sh`; o workflow GitHub Actions foi movido para exemplo desativado para reduzir risco de custos.
- Ver `docs/14_POLITICA_CUSTO_ZERO.md`, `docs/16_ESCOPO_APROVADO_E_AUTORIZACOES.md` e `docs/17_STATUS_GATE0_ATUALIZADO.md`.

## Domínio e contratos executáveis (synthetic-only)

O pacote possui agora modelos Pydantic da jornada única, persistência SQLite transacional local, autorização por chave de desenvolvimento e endpoints reais do primeiro fluxo, com OpenAPI gerado do código, ranking oficial e linagem até o criativo. **Somente dados `synthetic_local` são aceitos e todas as operações externas continuam bloqueadas.** Consulte [especificação técnica do domínio](docs/18_DOMINIO_E_CONTRATOS_EXECUTAVEIS.md).

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
PYTHONPATH=src python scripts/export_local_openapi.py
```
