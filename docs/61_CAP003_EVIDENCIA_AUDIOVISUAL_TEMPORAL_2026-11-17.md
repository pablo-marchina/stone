# CAP-003 — evidência audiovisual temporal local (17/11/2026)

## Rastreabilidade
Arquitetura consolidada + v5.2, metodologia v3, DEC-016/017/018 e
Plano Único IMP-063 (processamento audiovisual) / IMP-136 (evidência temporal).
Incremento parcial de IMP-063/136, dependências IMP-064/065 e IMP-083.
Não muda os critérios, escopo de entrega, matriz de capacidades ou gates.

## Evidência operacional V10
Operador HEAD 5b5c386: 100 testes focais PASS em 1,12 s, zero spend PASS.
Contrastes tema/CTA e quatro campos executados com revalidação de snapshots:
a6-rubric-contrasts-20261117-140535.json,
a6-rubric-proof-offer-20261117-140542.json,
a6-rubric-contrasts-four-20261117-145217.json.
858 posts/21 perfis; tema 67, CTA 64, oferta 1, prova social 0 candidatos.
132/3432 células grounded, 3300 abstenções. Não é cobertura de rubrica
canônica nem de posts únicos. 439 semânticos exploratórios, 1 grounded
positivo MPE. Todos os limites de sensibilidade calculados incluem zero.
Marketing técnico +48,94 pp global e -6,47 pp intraperfil; CTA salvar
+88,89 pp global sobre 1 único candidato no top. Não promover para agente.
Nenhuma alteração de ranking, revisão humana, admissão científica ou DB.

## Incremento audiovisual
Preserva o adaptador multimodal.py existente (OpenCV/Tesseract). Adiciona
multimodal_temporal.py para medir três clipes gerados localmente com FFmpeg
e ffprobe: estático, duas transições 1s/2s com tom de 440 Hz, uma transição
2s. Gera apenas em pasta temporária e remove arquivos ao término.
Restringe entrada aos clipes gerados pelo runner, protocolos file/pipe
na decodificação, tempo/tamanho/amostras limitados, sem rede ou input de
mídia social. Amostragem uniforme 4 Hz em grayscale 64x64, hashes dos
frames dos primeiros 3s, diferença média absoluta normalizada e transições
candidatas; não são cortes semânticos nem timestamps originais PTS.
Áudio PCM mono 16 kHz, janelas de 1s dos primeiros 3s, hash e RMS, presença
de stream e duração. Tom sintético não é fala ou transcrição.
Gate de engenharia: três fixtures; 12 frames, duração 3s e transições
esperadas com tolerância 0,25s; presença de stream e PCM com RMS >0,01
nas três janelas quando há áudio. Não é validação em vídeos reais,
nem F1/MAE de rubrica ou WER. Sem inferência VLM/ASR, rótulos, banco,
release, publicação, grants ou gasto.

## Operador
```powershell
git pull --ff-only
git rev-parse --short HEAD
python -m pytest -q tests/test_multimodal_temporal.py tests/test_offline_visual.py tests/test_discovery_rubric_contrasts.py tests/test_discovery_rubric_grounded.py tests/test_discovery_rubric_benchmark.py tests/test_discovery_rubric_coverage.py tests/test_discovery_audience_benchmark.py
python scripts/verify_zero_spend.py
python scripts/a6_multimodal_readiness.py --check-ready
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_multimodal_readiness.py --synthetic-temporal --report-name "a6-multimodal-temporal-$stamp.json"
```
Em tapi-s1; não precisa GLiNER, token Meta, manifesto ou dados reais.
Readiness detecta binários e módulos, não atesta compatibilidade ou pesos.
Teste FFmpeg real pode ser pulado se executáveis ausentes; CLI exige os
dois. Smoke isolado de geração/decodificação executado pelo assistente
em Linux: fixture de duas transições, 12 frames (0/255/0), PCM 48128
amostras/3,008s, RMS ~0,088 nas três janelas. Não é suíte do repositório.
Testes completos novos ainda pendentes no ambiente operador.

## Próximas dependências
ASR local com checkpoint fixado e teste WER em material sintético/autorizado;
OCR/visão e VLM local com avaliação por campo, sem inventar temporalidade;
registro operacional de direito de processamento por ativo (grant
de metadados/legenda ou direito Studio não equivale a licença audiovisual).
Somente depois conectar mídia real legitimamente disponibilizada ao
pipeline. A política externa permanece deny-by-default. Não baixar mídia
do Instagram ou YouTube, nem marcar prova social/tom/hook/cortes como
avaliados a partir de medições brutas. Continuar CAP-001 expansão e
CAP-005/006 agente/MCP conforme dependências do Plano Único.
