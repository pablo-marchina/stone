# A11 — Diagnóstico multitrilhas de ambiente nativo (23/11/2026)

## Contexto: referência preservada

PR #72, SHA `c2815cd3f44379095b78e068306b3d3b84f63c4e`: A11 focal **10/10 PASS**, incluindo 406/406 A05/A07, 35/35 A06, 19/19 Node e 7/7 Chrome. A regressão integral Windows no **mesmo SHA** resultou em **2107 PASS, 31 FAIL, 2 SKIP em 1288,41s** (exit 1), log SHA256 `D7ADD97D0F685A9F6581EE14564A1CDFFAF96E9FDDBA398AE40E37DA303337E5`. Custo zero e espelho documental PASS. A11 focal não libera G0-G6/IMP-131.

## Raízes observadas no trace real

1. **ASR:** `importlib.metadata.PackageNotFoundError: faster-whisper` no ambiente Windows `tapi-dec008-586aabf6`. O adaptador `asset_asr_fixture.py` fixa `faster-whisper==1.2.1` e também extrai metadados de `ctranslate2`, `onnxruntime`, `numpy`, `tokenizers`, `huggingface-hub`, `av`. Um Python que execute DEC-008/LangGraph não é automaticamente o ambiente de ASR.
2. **VLM:** o guard real `require_model_headroom` bloqueou com `MODEL_HOST_HEADROOM_INSUFFICIENT`. Disponibilidade observada ~1525–1898 MiB físicos; exige **pelo menos 4096 MiB físicos livres**, e commit disponível de **pelo menos 5120 MiB no VLM ou 7168 MiB no ASR Medium** (reserva de 1024 MiB). No log, commit ~5502–5942 MiB. Não reduzir exigências nem habilitar bypass.
3. **2 skips:** criação de symlink exige privilégios em Windows, tripleta de relatórios do Evidence Lab não configurada. Não tratar skips como teste executado.

Diversos testes de retenção, cancelamento, evidence bundle e fusão falharam **antes de exercer suas assertions**, porque o ASR não conseguiu planejar a execução ou o VLM não obteve admissão de memória. Não presumir que os cenários profundos passaram.

## Implementação incremental nesta PR (nova frente separada)

- `scripts/a11_native_host_preflight.py`: preflight offline, sem modelo, sem banco, sem rede, sem modificação, com atestado de HEAD limpo. Emite JSON redigido de distribuições ausentes, versão exata do faster-whisper, presença booleana dos caminhos configurados, capacidade física/commit e bloqueios. Reusa apenas `model_host_capacity` do runtime — **não** altera `require_model_headroom`.
- `tests/test_a11_native_host_preflight.py`: cenários sintéticos de dependência ausente, versão errada, insuficiência física, orçamento de commit por adaptador, modelos não configurados, Windows ausente, falha de consulta e JSON sem vazamento.
- O status verde `PREREQUISITES_OBSERVED_NOT_AUTHORIZATION` significa SOMENTE que os pré-requisitos quantitativos foram observados. Não valida pesos, hashes, licença, autorização, modelos, saída nem gates; o adaptador revalida tudo em execução.

**A PR #72 mantém o SHA focal intocado.** Esta PR de preflight deve ser testada e revisada independentemente antes de qualquer incorporação.

## Ações do operador

Executar o preflight sem segredos em PowerShell, após `git fetch` e checkout limpo desta nova branch, via:
```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path "src"
python -m pytest -q -rs tests/test_a11_native_host_preflight.py
if ($LASTEXITCODE -ne 0) { throw "A11_NATIVE_PREFLIGHT_TEST_FAILED" }
python -m scripts.a11_native_host_preflight --expected-head (git rev-parse HEAD)
Write-Host "NATIVE_PREFLIGHT_EXIT=$LASTEXITCODE"
```

Não iniciar todos os 31 testes nativos com memória menor que o mínimo. Se o ASR está disponível em outro ambiente, escolher conscientemente um ambiente com as dependências DEC-008 e ASR juntas; não misturar fontes/editable installs, não copiar artefatos de modelos sem verificar manifest/pins.

## Frente de arquitetura após recuperação

Continuar fechamento A02.7 ambiente nativo e lineage; A06 → E1 e integração com agentes apenas para evidências autorizadas; produção só após critérios de 23 CAP, aceites da matriz 204 IMP/543 deps, direitos e homologação independente, DEC-008 e G0-G6/IMP-131.
