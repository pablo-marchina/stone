# CAP-003 / IMP-063 — ASR comparativo, silêncio digital e diagnóstico (17/11/2026)

## Evidência operacional
Operador enviou logs do provisionamento e do benchmark, 17/11.
44 testes PASS + 1 SKIP OCR esperado no HEAD 6d5d110, zero-spend PASS.
Correção das duas flags offline no docs/62 e docs/63 em fa67d85.
Download Medium concluído, alerta prévio de 990,27 MB livres versus
1527,91 MB esperados. Espaço atual desconhecido; não inferir ENOSPC.
Peso Medium SHA256 9b45e1009dcc4ab601eff815b61d80e60ce3fd8c74c1a14f4a282258286b51ae
verificado. Auxiliares registrados, não atestados independentemente:
config 3622a2ddc41ec0e0fd4e68c13c6830f03b90c38d89aaad184de02c8c642cf807
tokenizer fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab
vocabulary 34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913.

| Candidato | Suite | WER | Erros/referência | Inserções negativos | Gate |
|---|---|---:|---:|---:|---|
| Small | v1 | 41,94% | 13/31 | 0 | FAIL |
| Small | v2 | 33,33% | 17/51 | 223 | FAIL |
| Medium | v1 | desconhecido | desconhecido | desconhecido | BLOCKED |
| Medium | v2 | 11,76% | 6/51 | 0 | PASS |

Relatórios a6-asr-small-challenge-20261117-153948.json e
a6-asr-medium-challenge-20261117-153948.json. Small silêncio 223 palavras
em 3s (baseline silêncio zero); entrega WER 112,5%. Medium challenge
estoque 3/8, custos 0/9, planejamento 0/9, atendimento 2/9,
preço 0/8, entrega 1/8, negativos zero. RTF fala 3,44–5,13.
Comparação usa parâmetros/versões declarados iguais; hashes PCM dos
relatórios completos ainda não comparados. Medium candidato prioritário,
não validado integralmente. Baseline Medium retornou TEMPORAL_LOCAL_ERROR,
causa não diagnosticada, não classificar como FAIL de qualidade.
Nenhum novo OCR resultado, Tesseract ausente no último readiness.

## Incremento
Suite guarded v3 explícita, sem alteração de baseline v1 ou challenge v2:
as seis frases challenge, sete negativos (silêncio 3 vezes, tom 2,
ruído 2), mesmos bytes em cada repetição; guard por conteúdo PCM,
não por case_id ou rótulo. Somente PCM digital exatamente zerado
retorna abstenção EXACT_DIGITAL_SILENCE, sem inferência.
PCM com qualquer amostra não zero segue caminho original. Não é VAD,
não identifica ruído, música ou fala baixa; não generalizar. Registra
inference_attempted e abstention_reason; guard não conta como sucesso
intrínseco do modelo. Mesmos critérios WER <=30% agregado, <=50% individual,
zero palavras negativas. Repetições não são observações independentes.
Não substituir resultados originais, nem promover Small pelo guard.
Diagnóstico de falha por stage/case_id/exception_type sanitizados, sem
mensagem livre, caminho ou conteúdo. Preflight checkpoint, temp, runtime,
model_load, fixture_generation, inference, scoring, checkpoint_postflight,
report_storage_preflight, report_write. 64 MiB livres mínimos em temp e
volume de relatórios (guard operacional, não recomendação de espaço).
Readiness exibe bytes livres do volume do repo, temp e checkpoint.
Sem remoção de arquivos, novos downloads, mudança de permissão, acesso
real, DB ou rubrica. Testes adicionados; não executados pelo assistente.

## Próximas verificações Windows
```powershell
git pull --ff-only
git rev-parse --short HEAD
Get-PSDrive -PSProvider FileSystem | Select-Object Name,Used,Free
Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory
python scripts/a6_multimodal_readiness.py --check-ready --model-dir "$medium" --asr-candidate medium
python -m pytest -q tests/test_multimodal_asr.py tests/test_multimodal_temporal.py tests/test_multimodal_ocr.py tests/test_offline_visual.py
python scripts/verify_zero_spend.py
```
Se espaço criticamente baixo, resolver primeiro sem apagar corpus,
modelos ou backups. Não baixar VLM agora. Se houver espaço suficiente,
reexecutar apenas Medium baseline e guarded:
```powershell
$stamp=Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/a6_multimodal_readiness.py --synthetic-asr --model-dir "$medium" --asr-candidate medium --report-name "a6-asr-medium-baseline-retry-$stamp.json"
python scripts/a6_multimodal_readiness.py --synthetic-asr --model-dir "$medium" --asr-candidate medium --asr-suite guarded --report-name "a6-asr-medium-guarded-$stamp.json"
```
Comparar PCM e versões dos challenges já persistidos, sem repetir:
```powershell
$s=Get-Content artifacts/private/a6-asr-small-challenge-20261117-153948.json -Raw | ConvertFrom-Json
$m=Get-Content artifacts/private/a6-asr-medium-challenge-20261117-153948.json -Raw | ConvertFrom-Json
$s.cases | ForEach-Object {
    $row=$_
    $other=$m.cases | Where-Object { $_.case_id -eq $row.case_id }
    [PSCustomObject]@{ Case=$row.case_id; SamePCM=($row.pcm_sha256 -eq $other.pcm_sha256) }
}
```
Nenhuma liberação real/científica. OCR conforme docs/63 somente após
verificação de disco; VLM, fusão multimodal, ablação ainda pendentes.
