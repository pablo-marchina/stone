# Política financeira — gasto financeiro total igual a ZERO

**Decisão vinculante do solicitante:** nenhum desembolso financeiro no projeto, incluindo hospedagem, modelos/API, armazenamento, CI/CD, compra de créditos, uso além de franquia gratuita e compra de mídia.

- Desenvolvimento principal: hardware já disponível, ambiente local e bibliotecas gratuitas/open-source sob licença compatível, usando datasets sintéticos ou autorizados.
- GitHub: repositório privado em GitHub Free, sem habilitar workflows automáticos, Codespaces, produtos pagos, serviços de IA faturáveis, runners maiores ou recursos com overage.
- Sem provisionamento automático de nuvem; avaliação de alternativas gratuitas deve rejeitar cobrança por excedente ou necessidade de compra de créditos.
- Se uma capacidade requer pagamento de terceiros (por exemplo, campanha paga), implementar modelo, interfaces, fluxo de aprovação e simulação **sem custo**; não afirmar que a veiculação paga foi exercitada ao vivo. Se o requisito exigir a própria compra de anúncios, registrar incompatibilidade material com gasto zero.
- Nenhuma chamada a API de IA que exija chave faturável, mesmo se tiver crédito promocional temporário. Preferir modelos locais open-source, com benchmarking de RAM, CPU, qualidade e latência reais.
- A operação em produção com SLA público poderá não ser viável sem infraestrutura já disponível; não declarar prontidão de produção antes de cumprir os gates.
- O limite é **zero de gasto financeiro**, não zero de utilização de CPU, energia, tempo humano ou hardware pré-existente. Não assumir gratuitamente que esses recursos têm custo econômico zero.

## Critérios objetivos

`budget_policy.json`: limites por operação, mês e total em `0`; serviços remunerados desabilitados; GitHub Actions automáticos ausentes do diretório `.github/workflows`; operações externas bloqueadas enquanto faltam direitos; validação com `scripts/verify_zero_spend.py`.

As políticas são controles de planejamento e testes locais; **não são** garantia de ausência de cobrança em contas externas que não controlamos. A configuração de limites de cobrança na conta GitHub ou nos provedores deve ser verificada pelo proprietário antes de utilizá-los.
