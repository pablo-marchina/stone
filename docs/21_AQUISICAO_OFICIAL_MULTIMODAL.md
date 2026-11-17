# Pipeline de aquisição oficial, normalização e classificação baseada em evidências

**Escopo implementado:** ingestão **limitada de metadados** por conectores oficiais do Instagram profissional e YouTube Data API, normalização para domínio unificado, persistência transacional e classificação parcial da rubrica. **Não significa que uma conexão real já foi autenticada ou que o objetivo de 2.000–5.000 posts foi alcançado.** Nenhuma coleta real foi executada nesta implantação.

## Limites, conformidade e autorizações

- O solicitante declarou a aprovação geral para fontes e operações, mas o uso de cada **conta e finalidade** é registrado por um administrador em `ingestion_source_grants` com referência à aprovação e validade. O registro é uma **atestação administrativa auditável, não uma assinatura ou prova legal automática**.
- `TAPI_OFFICIAL_METADATA_READS` tem valor **desativado por padrão**. Sem `TAPI_OFFICIAL_METADATA_READS=1`, `TAPI_ZERO_BILLING_CONFIRMED=1` (após verificação independente de ausência de cobrança no console do provedor), grant persistido, sessão com permissão e token correspondente em variáveis de ambiente, a leitura oficial falha antes de gerar tráfego.
- A autorização de leitura de conta é checada em cada execução por uma requisição oficial. **Para YouTube, essa consulta confirma que o canal retornado corresponde ao ID solicitado, mas não comprova que o usuário OAuth é proprietário desse canal**; a legitimidade da coleta de terceiros deve continuar amparada por sua autorização registrada. No Instagram, a conta precisa ser profissional e acessível ao token conforme a API oficial.
- **Instagram:** apenas `/{account-id}` e `/{account-id}/media` do Graph API; vídeos sem indicação `media_product_type=REELS` não são classificados automaticamente como Reels; imagens e carrosséis são tratados conforme mídia. Não há scraping, Business Discovery irrestrito ou coleta de contas pessoais.
- **YouTube:** apenas `channels.list` e `videos.list` por IDs explicitamente autorizados; exige referência do operador identificando os vídeos como Shorts. A classificação de Shorts **não é provada somente pelo endpoint de metadados**, portanto precisa de verificação humana independente. Não há `search.list`, downloads ou captions de terceiros.
- Sem mídia, vídeo ou transcrição, os campos de hook, rosto, cortes e texto visual permanecem **não observáveis**. Conteúdo caption-only permite apenas classificações determinísticas conservadoras com evidência de URL. Cada campo da rubrica carrega proveniência e as ausências não viram zeros falsos.
- Os denominadores Instagram correspondem à contagem **atual** do perfil, não necessariamente ao instante de publicação. Os inscritos do YouTube são **arredondados** pela plataforma; nenhuma precisão histórica é inventada. O ranking oficial demanda avaliação da comparabilidade temporal antes de inferências estatísticas.
- O conjunto inicialmente coletável por APIs oficiais pode ser insuficiente para 30 criadores e 2.000–5.000 posts, e isso não autoriza meios alternativos contrários às regras.
- **Sem garantia financeira de plataforma por mera franquia:** para manter R$ 0, criar projeto/API apenas onde o provedor permitir configuração sem cobrança e sem overage; não ativar faturamento nem execução de campanha paga. Nenhuma requisição foi enviada à API oficial nesta etapa. Limite local: 5 execuções/conta/dia UTC, até 10 posts e no máximo duas chamadas oficiais/execução.

## Contratos executáveis (FastAPI seguro)

- `POST /v1/ingestion/grants`: somente `admin`, cadastra plataforma, ID de conta, referência documental e expiração. Nunca recebe token no body.
- `POST /v1/ingestion/runs`: `admin`, `researcher` ou `service`, checa flag/credencial/grant, reserva cota de segurança, valida conta remota, busca lote limitado, normaliza, persiste e emite eventos. `run_key` é único por tenant; reutilização falha em vez de repetir a coleta.
- `GET /v1/ingestion/connections/{platform}/{account_id}`: apresenta estado operacional da autorização e presença de credenciais sem expor segredos.
- `GET /v1/ingestion/runs`: lista execuções do tenant sem credenciais e sem conteúdo sensível.
- Tabelas versionadas por `0002_official_ingestion`: `ingestion_source_grants`, `ingestion_runs`, `ingestion_records`, com referências por tenant. Eventos `ingestion.content_processed` são gravados com outbox **na mesma transação** do criador/post/métricas/rubrica. Retries do mesmo item não duplicam o registro ou evento, mas a versão atual ainda **não atualiza métricas de um post existente**; isso precisa de contrato de refresh posterior.
- OpenAPI gerado da instância segura reflete os novos endpoints. `POST /v1/collections` legado permanece bloqueado até migração contratual explícita para não abrir o endpoint antigo involuntariamente.

## Instruções de execução (sem credenciais no Git)

```bash
python -m pip install -e '.[dev]'
export TAPI_DATABASE_URL="sqlite:////CAMINHO/secure.sqlite3"
python -m alembic upgrade head
python -m tapi_gate0.ops bootstrap-admin --tenant local-research --username admin
export TAPI_ALLOW_HTTP_LOOPBACK=1
uvicorn tapi_gate0.secure_api:from_environment --factory --host 127.0.0.1 --port 8000
```

Antes de habilitar qualquer acesso real: operador confirma direito de uso para **aquela conta e finalidade**, autenticação OAuth Meta/Google em sua própria conta, escopos concedidos e ausência de faturamento. Guarde o token num local seguro fora do repositório e configure `TAPI_INSTAGRAM_ACCESS_TOKEN` ou `TAPI_YOUTUBE_ACCESS_TOKEN` **apenas no ambiente protegido da execução**, assim como `TAPI_OFFICIAL_METADATA_READS=1` e `TAPI_ZERO_BILLING_CONFIRMED=1` **somente depois de verificar no console do provedor que cobrança e overage estão impossibilitados**. A flag não fornece proteção técnica contra faturamento configurado na conta do provedor. Os testes nunca usam rede real: `httpx.MockTransport`.

## Adaptador visual offline opcional

Atualização de segurança (17/11/2026): `inspect_approved_local_media(path, expected_sha256)` falha fechada com MEDIA_VERIFIED_ASSET_GRANT_REQUIRED antes de abrir arquivos de terceiros. TAPI_APPROVED_MEDIA_ROOT e SHA-256 são atestação local de integridade/confinamento, não uma autorização verificável por ativo. Não há serviço de grants de mídia ligado à entrada legada. O helper privado de atestação conserva seus testes de confinamento; não é fronteira de autorização. `inspect_generated_visual_fixture()` aceita zero inputs e gera uma imagem preta localmente para testar o baseline OpenCV/Tesseract, conforme política synthetic_local. Nenhum resultado é gold ou classificação canônica. A classificação legada que recebe VisualObservation continua provisória; sua integração com autorização/proveniência verificada permanece pendente. Não abrir mídia externa até implementação de grants específicos. Ver docs/72 para a composição de evidência sintética multimodal.

## Próximas verificações

- Contas e tokens reais, escopos Meta/Google, disponibilidade de quotas sem faturamento e evidência de consentimento/licença por criador.
- Testes de integração com dados reais de contas autorizadas, sem expor credenciais nos logs; política de retenção/apagamento.
- Benchmark de qualidade multilabel em amostra humana (mínimo 50), concordância e calibração; validação da análise de vídeos e áudios em infraestrutura própria.
- Refresh idempotente de métricas, política de retenção específica por fonte, PostgreSQL/RLS/backup e concorrência do worker, e tratamento de erros em lote.

Referências oficiais consultadas: [Instagram API (Meta)](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api), [YouTube vídeos](https://developers.google.com/youtube/v3/docs/videos/list), [YouTube canais](https://developers.google.com/youtube/v3/docs/channels), [YouTube quota](https://developers.google.com/youtube/data/getting-started).
