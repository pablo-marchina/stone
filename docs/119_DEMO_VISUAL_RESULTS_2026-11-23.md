# Demonstração de 48h — resultados visuais e rubrica (23/11/2026)

Base PR #83 c017e56a91dcec65a1b40fcffdaad4e903962842. Incremento de demonstração local, sem promoção de gates, alteração normativa ou publicação.

## Entregas
- Cinco layouts editoriais determinísticos (paleta, hierarquia e cinco camadas editáveis). A prévia usa o gerador do documento persistido; o digest de seleção inclui o layout e a prévia. Todos os documentos continuam marcados como rascunho, sem direitos aprovados.
- Rubrica visual de 20 atributos na jornada sintética: metadado observado, medição de caracteres, candidatos lexicais da legenda e não avaliados. Não afirmar presença/ausência audiovisual nem semântica validada. Rotas de leitura adicionais somente no launcher local autenticado.
- Painel opcional do relatório histórico A6, com recálculo de agregados e conferência de consistência interna. Mostra contagens, medianas ER, estratos e cobertura da rubrica quando disponível; não expõe IDs, handles, legendas ou registros individuais. Hash do arquivo de entrada, data e ausência de validação científica/direitos atuais explícitos. Não constitui nova coleta, verificação de autenticidade externa ou ranking ao vivo.

## Executar
No checkout da branch, dependências Python previamente instaladas:
```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path "src"
python -m scripts.demo_stone
```
Abra http://127.0.0.1:8765/app/demo.html, organização stone-demo, usuário demo e senha local escolhida no terminal. Se houver relatório salvo pelo a6_exploratory_ranking.py com private_rows, use `python -m scripts.demo_stone --technical-report "C:\caminho\relatorio.json"`. Não enviar relatório privado ao GitHub. O launcher não usa o banco operacional e só escuta loopback.

## Evidências
46 pytest PASS em 14,47 s (suítes demo, projeção histórica, propostas, trace/draft, integração vertical e studio_e1). Chromium real com FastAPI em processo: ranking 20/4/2, 20 campos, seis checkpoints, cinco prévias, duas versões, PNG/SVG com hashes, logout PASS. A seleção mantém a prévia exata salvo ID definitivo; cinco paletas distintas testadas. Projeção de relatório com fixture, rejeitando resumo, cobertura, flags, duplicatas e estrato inconsistente. Não houve leitura de relatório real do operador nesta rodada. Node syntax e zero-spend PASS; 11 blobs publicados correspondem aos arquivos locais testados. Capturas reais e exportações locais produzidas; não incluir dados privados no repositório.

IMP-055/057/074/075/078/174/175/184 e CAP-002/003/005/007/023 recebem evidência parcial. Não é homologação integral A11 nem deployment público. Próximo foco: carregar relatório técnico histórico legítimo no ambiente de apresentação, ensaiar navegador/servidor local, demonstrar busca e exportações adicionais. G0–G6/IMP-131 continuam BLOCKED; R$0.
