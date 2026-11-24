# Demonstração 48h — busca FTS5, carrossel e resultados da sessão

Base: PR #84, d938952c64b5aadbc263545ef372cc6ee774877f. Continuação da demonstração isolada, sem alterar os critérios do Plano Único ou promover gates.

## Entregas
- Busca lexical FTS5 no recorte sintético elegível, com identificação de snapshot, ER, legenda fictícia e seleção de referências do top 10%. Reutiliza IMP-071, ranking SQL e EvidenceRetriever. Índice efêmero, consulta limitada, sem alegação de relevância científica.
- Proposta de planejamento em três páginas editáveis, com prévia vinculada ao digest da proposta. Seleção, persistência, edição de uma página sem alterar as demais, versão imutável e exportação ZIP de PNGs com manifesto e hash por página. Quatro demais propostas continuam em formato feed.
- Painel e download JSON dos contadores consultados no banco da sessão: corpus, perfis, top, execuções, checkpoints, rascunhos, versões e proveniência. Relatório histórico opcional separado, sem combinar dados sintéticos e reais.
- Rotas adicionais limitadas ao launcher autenticado local. Não é homologação científica, deploy público ou produção operacional.

## Validação observada
46 pytest PASS em 14,02 s na regressão combinada (demo, propostas, Studio, trace/draft, histórico e jornada vertical); node --check e verify_zero_spend.py PASS. Chromium real com FastAPI em processo: 20 posts/4 perfis/2 top; cinco hits de estoque, 20 campos da rubrica, 6 checkpoints, 5 propostas, dois documentos e quatro versões, dois eventos de proveniência. Exportação SVG/PNG e ZIP de três PNGs validada por SHA-256, resumo JSON baixado, logout. A primeira tentativa do ensaio falhou por seletor ambíguo de captura; seletor corrigido e jornada completa PASS. Sete blobs de código e teste correspondem aos arquivos testados. Nenhuma validação de navegação HTTP real no Windows ou carga operacional foi realizada.

## Executar
Com dependências já instaladas e checkout da branch:
```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path "src"
python -m scripts.demo_stone
```
Abra http://127.0.0.1:8765/app/demo.html, tenant stone-demo, usuário demo, senha local escolhida. Opcional: --technical-report "C:\caminho\relatorio.json" para importar agregados históricos legítimos. Nenhum banco operacional ou credencial externa utilizado. A proposta Planeje a próxima semana tem três páginas e botão Exportar carrossel ZIP. O painel de resultados permite baixar JSON.
A execução real com relatório do operador, teste do launcher no ambiente de apresentação e produção pública permanecem pendentes. R$0, G0–G6 e IMP-131 bloqueados. Sem merge ou deploy.
