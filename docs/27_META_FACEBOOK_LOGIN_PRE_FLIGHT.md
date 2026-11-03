# Meta Facebook Login — pré-verificação de leitura autorizada (v5.2)

**Situação em 03/11/2026:** o responsável reportou uma consulta bem-sucedida no Graph API Explorer. A resposta real do aplicativo e o ID IG profissional ainda precisam ser confirmados em execução do TAPI.

A fonte declarada é `@academy_fellow_stone`, vinculada à Página Facebook `61595867706725`. O ID do aplicativo Meta (`1763543721612277`) não substitui o ID da conta Instagram. O fluxo adotado é **Instagram API with Facebook Login**, em `graph.facebook.com`, consistente com a [coleção oficial Meta no Postman](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api).

## O que o script verifica

`scripts/meta_preflight.py` tem execução explicitamente opt-in e realiza apenas leituras:
1. `GET /me/accounts?fields=id,name,instagram_business_account`, limitado a 3 páginas de 50 itens, sem seguir links de paginação da resposta;
2. Confirma a Página esperada e o `instagram_business_account.id`;
3. Consulta o próprio ID IG em `GET /{ig_user_id}?fields=id,username,followers_count` e confere o username;
4. Consulta somente uma página de mídia (`limit=3` por padrão), conta Reels/carrosséis e elegíveis com 14+ dias, sem reproduzir captions nem conteúdo individual;
5. Retorna status, IDs, handle e contagens agregadas. Não grava credenciais, mídia, posts, grants ou estado de verificação.

## Execução no PowerShell (máquina com acesso à Meta)

```powershell
python -m pip install -e ".[dev]"
# Configure a variável TAPI_INSTAGRAM_ACCESS_TOKEN no ambiente local.
# Ative as guardas somente após verificar o limite de custo R$0 na Meta.
$env:TAPI_OFFICIAL_METADATA_READS = "1"
$env:TAPI_ZERO_BILLING_CONFIRMED = "1"
python scripts/meta_preflight.py --execute --limit 3
```

Sem `--execute`, nenhuma conexão externa ocorre. O token é obtido exclusivamente de `TAPI_INSTAGRAM_ACCESS_TOKEN` e não aparece em argumentos ou no JSON retornado. O relatório pode ser utilizado para obter o `instagram_user_id` sem enviar o token ao repositório.

## Próximo passo após `OFFICIAL_READ_CONFIRMED`

Em banco local com migrações `0001` a `0004` aplicadas, realizar explicitamente via API autenticada:
1. `POST /v1/ingestion/grants` com a conta verificada e a referência válida de autorização;
2. `POST /v1/corpus/profiles` com setor, estrato e referência de evidência;
3. `POST /v1/ingestion/runs` com `platform=instagram`, o **IG ID** (não a Page ID), `run_key` único, `limit=3`, `min_age_days=14`;
4. `GET /v1/corpus/data-card` para inspecionar o primeiro lote real auditável.

A pré-verificação não cria grant nem atualiza `technical_verified_at`. O último só é gravado após execução bem-sucedida do conector de ingestão.

**Limites científicos e de autorização:** o acesso à própria conta não autoriza automaticamente outros 29 perfis; a meta de 30 perfis e 2.000–5.000 posts ainda depende de direitos por fonte, comprovação de quota, qualidade e cobertura. Custo financeiro permanece R$0. Nenhuma publicação ou anúncio é executado.
