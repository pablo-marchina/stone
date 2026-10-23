# DEC-010 — Benchmark de infraestrutura com custo financeiro obrigatório ZERO

**Decisão atual:** OPEN. É proibido contratar provedor pago; não foi contratado provedor nem selecionada hospedagem de produção. Baseline com desembolso de nuvem = R$ 0: desenvolvimento local com processos isolados/containers. Isso não é uma configuração de produção comprovada.

## Alternativas a comparar

| Alternativa | Ponto forte | Limitação / custo a conferir | Resultado |
|---|---|---|---|
| Local + containers + PostgreSQL local | Custo de nuvem zero; boa paridade para engenharia | Sem SLA público nem operação externa | Baseline local provisório |
| PaaS para API/worker + PostgreSQL gerenciado | Operação simplificada | Instâncias persistentes, filas, backups e rede podem ser pagos | Candidata aberta |
| VM única gerenciada pelo responsável + PostgreSQL | Custo previsível de infraestrutura, controle de workers | Maior custo operacional humano, patches e backups | Candidata aberta |
| Provedor split frontend + banco gerenciado + worker separado | Escalabilidade por componente | Complexidade de integração, egress e múltiplas contas | Candidata aberta |

## Alertas de planos gratuitos verificados

- **Render Free:** documentação declara inadequado a produção e banco gratuito expira após 30 dias. https://render.com/docs/free
- **Supabase Free:** 500 MB por banco, projetos podem pausar por inatividade, sem equiparar ao SLA de produção. https://supabase.com/pricing
- **Neon Free:** quota limitada de compute e armazenamento; verificar plano antes de operação comercial de produção. https://github.com/neondatabase/website/blob/main/content/docs/introduction/plans.md
- **Vercel Hobby:** limitado a projetos pessoais e uso não comercial — não presumir aplicável ao produto Stone. https://vercel.com/docs/plans/hobby
- **Cloudflare Workers Free:** limites reduzidos de CPU/ambiente; não equivalem a worker Python pesado de processamento audiovisual. https://developers.cloudflare.com/workers/platform/limits/

## Protocolo de comparação pré-registrável

Cargas sobre a **mesma** implementação e dados sintéticos: `100/1000/5000` posts tabulares; jobs 10/100, reinício de worker sob falha, reconnect SSE, chamadas p95 de ranking, ingestão de evento, restore PostgreSQL; teste de segregação de contas. Registrar CPU/RAM, uso de disco, custo por execução, mensal mínimo para operação persistente, egress, backup, custo operacional humano, RPO/RTO, limites de quota, licenças e disponibilidade por região. O desenho deve considerar serviço comercial, dados pessoais e regras Stone.

Critérios eliminatórios: direitos, segurança, criptografia, controle de acesso, backup restaurável, limites de gastos, recuperação e restrições comerciais. Em seguida comparar custo total estimado, manutenção, risco de lock-in, p95, sucesso de jobs e compatibilidade. Pesos definidos antes dos testes (`DEC-010`). Não escolher por marketing nem plano Free.

**Estimativas de custo não informadas** pois faltam região, volume, orçamento teto, plano, tráfego e perfis de carga. Essa ausência não pode ser preenchida com números fictícios.

## Restrição vinculante atual

O teto financeiro total é **R$ 0**, sem exceção presumida. A avaliação deve eliminar opções que exijam cartão, licença onerosa, pagamento, faturamento por excedente ou ações de mídia paga. Qualquer serviço gratuito só será candidato se houver forma de impedir cobrança; caso contrário, manter operação local. Este documento não escolhe provedor de produção.
