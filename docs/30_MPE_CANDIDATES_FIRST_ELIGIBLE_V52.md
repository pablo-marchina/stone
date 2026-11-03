# IMP-167 → IMP-170 — Seleção de fontes MPE e primeiras evidências elegíveis

**Data:** 03/11/2026. **Prioridade:** P0 do Plano Único v5.2, base documentada.

## O que foi provado

O perfil de diagnóstico `@instagram` foi consultado com sucesso e a API retornou seis mídias em duas páginas; cinco eram recentes demais e **zero** cumpriram o critério de ≥14 dias. O endpoint Business Discovery e a paginação aninhada funcionam com dados reais. A conta `@academy_fellow_stone` é o sujeito autenticado, não uma fonte elegível automática. Não confundir `@instagram` com uma MPE, nem incluir os seus posts no corpus.

## Fontes candidatas: pesquisa documental ≠ autorização

O arquivo `evidence/acquisition/mpe_candidate_frame_20261103.json` registra cinco perfis nomeados em fontes públicas documentais. São **apenas candidatos**, com `status=candidate` e `size_band=unverified`; a atualidade do handle, o status Business/Creator, o porte MPE, os direitos e a disponibilidade de mídias **não foram comprovados**. Referências da primeira identificação:

- `@vaicomeroquee` — culinária/buffet, reportagem do Sebrae Bahia (2026).
- `@solmaior_supermercado` — comércio/supermercado, reportagem sobre empreendedorismo (2023).
- `@usecairos` — varejo de moda, estudo acadêmico de 2024.
- `@comuniquedigital_` — serviços de conteúdo, publicação do Sebrae com captura histórica.
- `@volkstore` — varejo de moda, reportagem de 2016; atenção especial a identidade e atualidade.

**Limitação amostral:** a shortlist preliminar é concentrada em comércio e não contém estratos aprovados de beleza; buscar diversidade em próximas fontes. Nenhuma destas contas foi consultada pelo novo piloto, autorizada ou inserida no banco.

## Processo operacional

1. **Curadoria offline:** auditar o arquivo de candidatos, sem acesso à Meta:

   ```powershell
   python scripts/mpe_corpus_pilot.py --frame evidence/acquisition/mpe_candidate_frame_20261103.json
   ```

2. **Revisão humana de fonte:** confirmar o handle ativo e tipo de conta profissional; comprovar natureza de MPE por fonte apropriada (não inferir porte por número de seguidores); confirmar setor, estrato e referência documental.
3. **Aprovação específica por finalidade/operação:** confirmar condições da API, direitos e política de retenção aplicáveis; registrar documento local privado de autorização/justificativa, titular, instante e expiração. O arquivo de pesquisa não cria autorização por si. Nunca colocar documentos pessoais ou credenciais no Git.
4. **Manifesto privado aprovado:** criar cópia em `artifacts/private/` com `status=approved`, `size_band=micro|small`, `size_evidence_reference`, `approval_reference`, `approved_by`, `approved_at`, `expires_at`, `allowed_operations=[business_discovery_metadata_read,local_research_metadata_export]`, `approval_proof_file` e `approval_proof_sha256` (SHA-256 do documento local). A prova local é controle de integridade, **não** homologação jurídica independente.
5. **Primeira coleta selecionada e limitada**, só se o projeto estiver permitido sob R$0:

   ```powershell
   python scripts/mpe_corpus_pilot.py --frame artifacts/private/mpe_approved_sources.json --execute --source PERFIL_APROVADO --evidence-dir artifacts/private/mpe_approvals --limit 5 --max-pages 2 --output-name mpe-primeira-coleta-20261103.json
   ```

6. **Revisar o pacote:** `artifacts/private/mpe_corpus/mpe-primeira-coleta-20261103.json`. Cada item elegível contém ID do perfil e da mídia, link oficial, formato Reel/carrossel, data UTC da publicação, métricas observadas, momento da observação, qualidade do denominador e hash de integridade. Digest do JSON e páginas do resultado, sem token. A saída indica `corpus_posts_persisted=0`: este é um pacote de **evidência preliminar**, não importação automática no corpus.
7. **Aprovar persistência:** somente após revisar proveniência e direitos, usar o registro de grant administrativo `POST /v1/ingestion/grants` e o registro do perfil `POST /v1/corpus/profiles` com ID do Instagram verificado. O fluxo atual `/v1/ingestion/runs` lê `/IG_ID/media` da **própria** conta autorizada; não o apontar para o ID do terceiro. Integrar adaptador Business Discovery a esse pipeline requer uma etapa específica de código, com idempotência e snapshots preservados. **Nunca** criar conteúdo como sintético e apresentar como real.

## Critérios de aceite e bloqueios

| IMP | Evidência obtida / faltante |
|---|---|
| 164/165 | OAuth e cursor Business Discovery testados na Meta, conforme PRs #15–17 |
| 166 | Filtro UTC ≥14 dias com ausência de métricas/denominador tratados por abstenção; testes offline |
| 167 | Shortlist documentada de cinco candidatos ainda não aprovados; amostra estratificada de 30 perfis ainda pendente |
| 168 | Snapshot histórico no pipeline existente; importação de Business Discovery não feita |
| 170 | Contagem elegível real persistida **zero** até o momento; déficit institucional ainda 30 perfis e 2.000 posts |

Custo financeiro faturável deve permanecer R$0; sem scraping, download de vídeo ou coleta automática de contas não aprovadas. Variáveis de ambiente `TAPI_OFFICIAL_METADATA_READS=1`, `TAPI_ZERO_BILLING_CONFIRMED=1` e `TAPI_INSTAGRAM_ACCESS_TOKEN` são exigidas apenas na execução explícita com rede. Nenhuma inferência causal ou ranking definitivo deve ser feita a partir do piloto.
