# Demonstração 48h — contraste editorial e relatório executivo (23/11/2026)

Base PR #87: e8293fbed7b579583ef8c71baa5bb3ffe9bc6fba. Incremento de demonstração isolada, sem promoção operacional.

## Implementação
- Projeção anônima de quatro dimensões editoriais do relatório histórico A6 (formato, tema, CTA, idade), reutilizando ER exato, critério top 10% e distribuição descritiva existentes. Campos não reconhecidos são desconhecidos; denominadores observados e ausência de comparabilidade explícitos. Nenhum identificador, handle ou texto livre exposto.
- Painel comparativo interativo, diferenças em pontos percentuais, cobertura por grupo e barras. Não infere causalidade, eficácia ou relevância científica.
- Download de relatório executivo HTML independente, sem scripts ou recursos externos: contadores SQL da sessão sintética, agregados históricos quando importados, cobertura e contrastes. Conteúdo inserido via textContent. A fixture de QA é explicitamente rotulada no painel e no relatório.
- Kit offline de contingência fornecido ao responsável, com capturas da jornada efetivamente executada, imagem, carrossel, vídeo, relatórios e hashes. Não é aplicação interativa nem implantação pública.

## Evidência executada
- 10 pytest focais PASS em 1,88 s (contraste, projeção histórica, demo).
- 54 pytest PASS em 16,52 s (contraste, histórico, demo, propostas, handoff, jornada vertical e Studio E1/E5/E6). As contagens se sobrepõem.
- Chromium real com ponte FastAPI em processo PASS: ranking, contraste com fixture marcada (formato 100 p.p.; tema sem denominador comparável; CTA sem observações), busca, rubrica, nove casos multimodais, seis checkpoints, cinco propostas, dois documentos/quatro versões, três páginas em ZIP e MP4. Export HTML verificado sem scripts e identificadores privados. Node syntax e zero-spend PASS.
- Kit offline: 22 entradas ZIP, CRC e hashes dos arquivos previstos no manifesto conferidos.
- Sete blobs alterados conferidos contra arquivos testados. Não foi importado relatório real do operador; os números da fixture não constituem resultado da pesquisa.

## Executar
No checkout desta branch, dependências existentes:
```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path "src"
python -m scripts.demo_stone --video --av-report "C:\caminho\stone_demo87_av.json" --technical-report "C:\caminho\relatorio-a6.json"
```
A opção --technical-report é facultativa e deve receber apenas relatório histórico legítimo no ambiente autorizado. Sem ela, os dados reais não são simulados. Abra http://127.0.0.1:8765/app/demo.html, tenant stone-demo, usuário demo, senha local criada no terminal. No painel Resultados, baixe relatório executivo HTML.

QA com fixture explicitamente sintética:
```powershell
python -m scripts.demo_stone_browser_qa --video --av-report "C:\caminho\stone_demo87_av.json" --contrast-fixture --output demo-evidence
```

G0–G6/IMP-131 bloqueados, R$0, nenhum merge ou deploy público. O teste HTTP no host de apresentação, relatório operacional real e autorização efetiva de implantação ainda não foram comprovados nesta rodada.
