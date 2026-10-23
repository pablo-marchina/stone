# Experimentos técnicos de readiness (pré-registro candidato)

| Experimento | Hipótese verificável | Dados/benchmark | Oráculo | Limite atual |
|---|---|---|---|---|
| EXP-G0-POLICY | Nenhuma fonte externa pode executar operações no bootstrap | Matriz completa de oito fontes × operações | `permitted=false` em todos os casos externos | Validável localmente |
| EXP-G0-SCHEMA | Contratos de referência são sintaticamente válidos, mas não homologados | 23 schemas + rubrica de 20 campos | JSON Schema Draft 2020-12 | Não mede semântica |
| EXP-G0-RANK | Métrica oficial e casos de borda retornam cálculo esperado | Fixtures sintéticas sem posts reais | Decimal aritmético + erro para divisor zero | Desempate/ceil a homologar |
| EXP-G0-API | Bootstrap informa corretamente readiness e não expõe endpoints de integração | TestClient | health + status + rotas exatas | Apenas app local |
| EXP-G0-INFRA | Infra selecionada reduz TCO sem regredir confiabilidade | Cargas 100/1000/5000 e falhas induzidas | custos/latência/restore aferidos | Pendente benchmark |
| EXP-G0-EVAL | Separação por criador e teste final selado não permite vazamentos | Corpus autorizado e gold | Auditoria de grupos/duplicatas | Pendente fonte |

Artefatos de evidência de cada execução: versão do código, hardware, versão dos dados, seeds e parâmetros, métricas, falhas e decisão. **Nenhuma medição sintética deve ser apresentada como acurácia real de VLM.**
