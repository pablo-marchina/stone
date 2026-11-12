# CAP-001 A6 — expansão sistemática e identificação de fontes (incremento inicial)

Data: 12/11/2026. Base empilhada: PR #43, commit `0aa7d86e6d14531d394c6df06ed2174879b7e373`. A5 ainda aguarda confirmação do backup e autorização de merge. A6 não autoriza integração antecipada de A5, produção, admissões científicas ou agendamento.

## 1. Resultado documental A6.1 (parcial)

O arquivo `evidence/acquisition/bd_a6_candidate_expansion_20261112.json` contém 18 novos candidatos em nove estratos documentais, com URLs de evidência e finalidade. Todos estão em `candidate`, sem IDs Meta ou grants inventados. Somados aos 15 registros do manifesto privado A5 reportado (3 aprovados, 12 candidatos), espera-se 33 registros (3 aprovados, 30 candidatos); a contagem final será determinada pelo merge offline. O limite do schema permanece 100 fontes. Meta de 50 candidatos não atingida neste incremento.

- Dez Salas do Empreendedor: Água Boa, Torres, Espírito Santo/RN, São Lourenço do Sul, Santa Maria, Belo Jardim, Maceió, Cristalina, São Luís e Ângulo, com evidência institucional municipal/estadual. Não presumir volume, atividade, identidade Meta atual ou independência amostral.
- Loja Integrada e Contabilizei: canais divulgados pela própria organização e finalidade de pequenos negócios.
- Omie: publicação da organização no LinkedIn indica `omie.oficial`; materiais anteriores citam `omieoficial`, portanto identidade permanece incerta e não deve ser resolvida por suposição.
- Andrael: diretório de parceiros Bling, consultoria ERP, finalidade MPE incerta.
- Rede Mulher Empreendedora, Mente Empreendedora, Feira Preta e Endeavor: referência editorial Santander de perfis de empreendedorismo; não é prova de identidade oficial atual ou audiência exclusivamente MPE.

Os dez perfis municipais representam 10/18 da nova tranche. Evitar superrepresentação regional/institucional e grupos relacionados. A próxima tranche deverá priorizar segmentos ainda pouco representados (varejo, beleza, serviços, logística, associações independentes, empreendedorismo e comércio digital), sem inserir handles sem evidência. Nenhum perfil recebe autorização de coleta só porque foi localizado. A6.1 é uma expansão documental de conveniência e não constitui amostra probabilística.

## 2. Identificação oficial A6.2 (implementação inicial)

`scripts/a6_identify_sources.py` e `src/tapi_gate0/discovery_identity_a6.py` oferecem plano offline e execução opt-in. Até cinco handles explícitos por lote, uma requisição por handle por dia, máximo dez reservas de identidade por dia UTC; reservas contam no orçamento compartilhado de 80 unidades conservadoras (quatro por run de ingestão Instagram, uma por identidade). Não é uma medição da quota ou cobrança efetiva da Meta.

Executar somente com administrador autenticado, flags `TAPI_BD_IDENTITY_ENABLED=1`, `TAPI_OFFICIAL_METADATA_READS=1`, `TAPI_ZERO_BILLING_CONFIRMED=1`, token válido no ambiente e escopo privado específico. O escopo `IdentityScope` requer tenant, viewer, hash do manifesto, lista exata de handles, referência de autorização real, expiração timezone-aware futura e operação `business_discovery_identity_read`. Não confundir autorização de identificação com grant de leitura de mídia. Não fabricar referência ou prazo.

A única consulta é `business_discovery.username(handle){id,username}` no transporte fixo Meta Graph v26.0. Valida viewer, handle, formato de ID, ID esperado se existir e conflitos com IDs conhecidos no manifesto e lote atual. Identificações de lotes separados deverão ser reconciliadas antes de atualizar o manifesto ou criar grants. Para no primeiro erro, não repete automaticamente e não devolve reservas mesmo se não utilizadas.

Cada reserva e resultado vira evento de domínio e outbox; referência privada é armazenada somente como hash, nunca token ou conteúdo de mídia. Reserva de todo lote antes da primeira chamada. Compartilha lease A5/A6, reconhecido pelo recovery já existente; em recuperação de lease órfão não há devolução de reservas. Outros entrypoints A3/A4 não compartilham a lease e não podem operar em paralelo no mesmo tenant. Não exige migração adicional (reusa tabelas 0012, domain_events e event_outbox). Não cria grants, não altera o manifesto, não lê posts e não admite corpus.

## 3. Prévia operacional (sem rede)

Após preservar alterações locais e confirmar checkout A6, com todos os processos de ingestão desligados:

```powershell
git fetch origin
git switch feat/cap001-a6-source-expansion-20261112
git pull --ff-only
$env:PYTHONPATH = "src"
$env:TAPI_DATABASE_URL = "sqlite:///C:/stone-data/tapi.sqlite3"
$env:TAPI_TENANT_ID = "local-research"
$env:TAPI_META_IG_ID = "17841459971757521"
$env:TAPI_BD_IDENTITY_ENABLED = "0"
$env:TAPI_OFFICIAL_METADATA_READS = "0"
$env:TAPI_BD_TECHNICAL_INGEST = "0"
$env:TAPI_BD_CONTINUOUS_ENABLED = "0"
$env:TAPI_ZERO_BILLING_CONFIRMED = "0"
python scripts/a5_expand_source_frame.py `
  --base artifacts/private/bd_manifest_a5_v1.json `
  --candidates evidence/acquisition/bd_a6_candidate_expansion_20261112.json `
  --output artifacts/private/bd_manifest_a6_v1.json

python scripts/a6_identify_sources.py `
  --manifest artifacts/private/bd_manifest_a6_v1.json `
  --source nuvemshop --source contabilizei --source lojaintegrada `
  --source redemulherempreendedora --source saladoempreendedor.saoluis
```

Se o manifesto de saída já existir, não sobrescrever. O plano deve retornar PLAN_ONLY_NO_EXTERNAL_READ, cinco fontes e zero grants; caso contrário, avaliar o bloqueio. A prévia não exige token. Não executar `--execute` até confirmar backup, regressão Windows e escopo real do lote. A6 ainda não foi executada no banco do operador.

## 4. Validação e próximos incrementos

Sete testes A6: expansão sem aprovar, prévia sem escrita, identidade oficial simulada e orçamento compartilhado, expiração/identidade divergente, rate limit e reserva preservada, autorização administrativa e flags, CLI sem credenciais. Regressão focada A4/A5/A6/preflight: 46 PASS; verify_zero_spend PASS. Banco temporário SQLite e transporte simulado, sem operação Meta real.

A6.1 continuará até pelo menos 50 candidatos documentais; A6.2 requer revisão do fluxo de autorização e teste real de identidade antes da incorporação segura dos IDs. A6.3: reconciliação de resultados, curadoria e registro de grants administrativos específicos, sem promover candidatos automaticamente. A6.4: diversidade de fontes autorizadas, A6.5: expansão histórica, A6.6: agendamento local supervisionado com limites e recuperação, A6.7: cobertura e falhas, A6.8: elegibilidade científica separada. 197 posts únicos e três fontes são a última evidência A5 reportada; não avançaram nesta entrega. Sem gasto contratado.

Regressão completa local Linux: **393 PASS**, 40,20 s, exit code 0, sem credencial Meta e com flags externas desligadas no ambiente do processo. Seis blobs de implementação, teste e manifesto conferidos com a cópia testada; configuração `.env.example` revisada separadamente. Cópia local reconstruída, não CI remoto nem regressão Windows A6.
