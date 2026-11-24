# Demonstração 48h — storyboard e vídeo local (23/11/2026)

Base PR #85, 2fd06326d16c58fb66eabcf88476b53307c0deb6. Incremento de apresentação isolada, não liberação operacional.

## Implementação
A opção explícita --video habilita apenas no processo do launcher a execução local do renderer E6 existente. O operador autenticado admin confirma os direitos locais do carrossel textual original. O navegador rasteriza as três páginas da versão persistida, compara hashes de uploads, registra atestações por ativo com validade de uma hora, cria storyboard de três cenas, enfileira o job e solicita uma execução única do worker. O worker conserva seus gates, verificações de direitos e de integridade, limite temporal e watermark. O navegador compara o SHA-256 do MP4 com o registro SQL. A interface apresenta vídeo, passos da renderização e download, e invalida a prévia ao mudar o documento/versão. Contadores de storyboards e artefatos são consultados no banco.
O modo padrão mantém o worker de demonstração indisponível. O novo endpoint exige admin, loopback e opt-in; não inicia scheduler nem altera o banco operacional. O vídeo é um rascunho silencioso de 15 segundos, não publicação ou validação audiovisual científica.

## Evidência executada
- 52 pytest PASS em 15,70 s (demo, relatório histórico, propostas, handoff, jornada vertical, Studio E1/E5/E6); zero falhas/skips. Node syntax e verify_zero_spend PASS.
- Chromium real em ponte de teste FastAPI: ranking 20/4/2, FTS5 cinco hits, rubrica 20 campos, seis checkpoints, cinco propostas, dois rascunhos, quatro versões, dois eventos de proveniência, ZIP três páginas, storyboard e renderização FFmpeg real, MP4 baixado com SHA-256 conferido. Resumo JSON confirma um storyboard e um vídeo. Logout PASS.
- FFprobe confirmou H.264, 360x640, 8 FPS, 120 quadros, 15 s, uma faixa de vídeo sem áudio; MP4 SHA-256 067933576318d88ed579d426ca6c036599abfa59b51e29b31ebfcfea3e4eefff.
- Uvicorn em processo separado em loopback: HTTP real 200 para HTML, login e consulta autenticada do painel. Não equivale a ensaio completo da navegação HTTP no Chromium nem a homologação de Windows.
- Seis blobs alterados conferidos contra os arquivos testados. Dados fictícios, nenhum relatório privado real importado neste ciclo.

## Executar no host de apresentação
Requer Python/dependências existentes e FFmpeg no PATH. No checkout da branch:
```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path "src"
python -m scripts.demo_stone --video
```
Abra http://127.0.0.1:8765/app/demo.html, tenant stone-demo, usuário demo, senha escolhida no terminal. Para agregados técnicos históricos, acrescente --technical-report "C:\caminho\relatorio.json". Selecione "Planeje a próxima semana", edite uma página, confirme a atestação local e renderize. Não requer token externo ou banco operacional. Ctrl+C descarta o banco temporário; guarde exports previamente.

O ensaio no Windows e importação de relatório legítimo ainda são necessários. R$0, sem merge, deploy público, autorização externa ou aprovação científica. G0–G6/IMP-131 bloqueados. Evidência parcial CAP-016/023, IMP-187/188 e fluxo E6.
