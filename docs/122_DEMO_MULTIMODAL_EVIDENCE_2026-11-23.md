# Demonstração 48h — painel de evidências multimodais (23/11/2026)

Base PR #86: 05495005db59475fe7996ec0756075fd84fa5c77. Incremento de apresentação isolada, não promoção operacional.

## Implementação
O teste integrado de nove casos existentes registra uma projeção dos resultados somente depois de todas as asserções passarem, inclusive revogação, replay e contagens do ledger. Um exportador transforma as propriedades JUnit de uma execução focal integral bem-sucedida em JSON limitado aos nove textos autorais e campos previstos. O contrato rejeita flags de inferência nativa, validação científica ou produção, e valida escopo, cardinalidades, estados, hashes, revisões e tipos. O relatório não é assinatura nem prova independente de autenticidade. O launcher opcional --av-report expõe apenas o relatório histórico local por rota autenticada e sem cache. Sem leitura operacional ou execução nativa adicional.
A interface permite explorar os nove casos, comparar baseline e guard, observar ASR/VAD, OCR, temporal e VLM, contagens de suporte/veto, motivo da decisão, fingerprint e cadeia de checkpoints. A nova navegação fixa permite saltar entre pesquisa, ranking, multimodal, agente, criativos e resultados. O download JSON preserva o relatório exibido. Não há inferência ao vivo nesse painel.

## Evidência executada
- 9 pytest PASS em 17,33 s: test_shared_av_ablation_policy_and_rights. JUnit SHA-256 786bfa3c4ddaf1c35822a5d23584822685f521733abcc91e8dafa8047566145d. 36 decisões, 13 candidatos, 23 abstenções, 3 supressões pelo guard, 35 checkpoints, 9 casos com acesso bloqueado depois da revogação. O primeiro export falhou por código alfanumérico DIRECTED_REQUEST_V2; correção do contrato e export bem-sucedido. Quatro checagens negativas adicionais do contrato passaram.
- API autenticada: 401 sem token; relatório exato e Cache-Control private/no-store com sessão.
- 52 pytest PASS em 17,21 s nas suítes demo, histórico, propostas, handoff, jornada vertical e Studio E1/E5/E6. Primeira seleção de regressão usou nome de arquivo inexistente e não executou testes; seleção corrigida. Node syntax e verify_zero_spend PASS.
- Chromium real com ponte FastAPI em processo: nove casos visíveis, supressão e abstenção explícitas, download JSON idêntico, e jornada anterior de ranking, FTS5, cinco propostas, edição, carrossel, ZIP, MP4 verificado e logout. Capturas e exports locais. Não é novo ensaio HTTP completo no host Windows.
- Sete blobs de código/teste conferidos contra os arquivos testados. Nenhum relatório operacional privado foi importado.

## Executar
Com dependências instaladas e checkout desta branch:
```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path "src"
python -m scripts.demo_stone --video --av-report "C:\caminho\stone_demo87_av.json"
```
Abra http://127.0.0.1:8765/app/demo.html, organização stone-demo, usuário demo e senha local escolhida no terminal. Acrescente --technical-report "C:\caminho\relatorio.json" somente para agregados técnicos históricos legítimos. O relatório sintético pode ser regenerado localmente (sem modelos, rede ou dados reais):
```powershell
python -m pytest -q tests/test_asset_rights_registry.py::test_shared_av_ablation_policy_and_rights --junitxml=demo-av.xml -o junit_family=legacy
python -m scripts.demo_av_report demo-av.xml demo-av.json
```
A saída JSON precisa ser um arquivo novo; não sobrescreve relatórios anteriores.

Evidência parcial A02.7/Stone-S1/DEC-008, CAP-003/005/022. Não declarar benchmark científico, inferência nativa, aquisição externa, aceite integral ou produção. G0–G6/IMP-131 bloqueados. R$0; nenhum merge/deploy.
