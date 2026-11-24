# Demonstração — hipóteses editoriais derivadas de agregados

Base PR #88, e68e7ccbcd64b7cec312dc96de1ffe7d54cddf9f. Incremento isolado, sem promoção operacional.

O relatório histórico validado agora produz até três hipóteses independentes: maior contraste positivo observado por formato, tema e CTA. Os cards e exportações JSON/HTML mostram contagens, denominadores, perfis no top, diferença em pontos percentuais e extremos de identificação sob atribuição arbitrária dos desconhecidos. Esses extremos não são intervalos de confiança e não ajustam confundidores. Cada hipótese propõe comparar um fator por vez; não estima efeito conjunto, não autoriza publicação e não cria peça editorial vinculada a fonte externa.

Validação: 12 testes focais PASS (1,81 s); 56 testes de regressão PASS (17,08 s), com sobreposição. Chromium com ponte FastAPI em processo PASS: novo card, download JSON idêntico, relatório HTML, demais etapas incluindo vídeo. Primeira tentativa falhou por seletor ambíguo, corrigido e reexecutado. Node syntax e zero-spend PASS. Seis blobs de código/teste conferidos. O operador confirmou anteriormente o dashboard da PR #88 em Windows com relatório histórico real; o novo painel foi ensaiado com fixture explicitamente sintética, e a função de hipóteses aplicada aos agregados anônimos enviados pelo operador. Não armazenar o relatório privado no repositório.

Executar com os mesmos argumentos --video --av-report e --technical-report da PR #88. Nenhuma nova dependência. Sem merge, deploy público, gasto externo, inferência causal ou promoção de gates.
