# Pré-voo oficial da Meta: Página conhecida com `/me/accounts` vazio

**Evidência real de 03/11/2026:** o operador confirmou no Graph API Explorer (v26.0) que `GET /me/permissions` concede `pages_show_list`, `instagram_basic` e `pages_read_engagement`. A enumeração `GET /me/accounts?fields=id,name,instagram_business_account` retorna `data: []`, mas `GET /1342848532252679?fields=id,name,instagram_business_account` retorna a Página **Stone Academy Case**, com `instagram_business_account.id=17841459971757521`. Essa evidência **não comprova** ainda que o username do ID IG coincide com `@academy_fellow_stone` ou que há permissão para consultar as mídias via token usado na execução Python.

## Caminho restrito, sem enumerar Páginas

Com o aplicativo e variáveis de ambiente já configurados, mantendo as flags `TAPI_OFFICIAL_METADATA_READS=1` e `TAPI_ZERO_BILLING_CONFIRMED=1` somente após confirmar custo financeiro zero:

```powershell
git pull origin main
python scripts/meta_preflight.py --execute --direct-page --page-id 1342848532252679 --limit 3
```

`--direct-page` escolhe a consulta fixa `GET /{page_id}?fields=id,name,instagram_business_account` em `graph.facebook.com`, **sem** chamar `/me/accounts`. A resposta deve ter o **mesmo Page ID** solicitado e vínculo IG numérico. Em seguida, o script verifica `GET /{ig_user_id}?fields=id,username,followers_count`, exige username `academy_fellow_stone` e, **somente se isso passar**, consulta uma página de até três publicações e devolve exclusivamente contagens agregadas. No sucesso, a saída inclui `page_resolution: direct_id` e `status: OFFICIAL_READ_CONFIRMED`.

**Bloqueios:** ID de Página diferente `PROVIDER_ACCOUNT_MISMATCH`; Page não localizada `EXPECTED_PAGE_NOT_FOUND`; sem link profissional `PAGE_WITHOUT_CONNECTED_IG_PROFESSIONAL`; username divergente `IG_USERNAME_MISMATCH`; sem credencial, permissão, quota ou flag, a execução permanece bloqueada. Nenhuma alteração de conta ou seleção automática de outra Página é feita.

**Controle operacional:** pré-voo não grava banco, não configura grants, não exporta tokens, não insere posts no corpus e não atesta direitos de terceiros. O ID `17841459971757521` é o IG User ID informado pelo operador, não um valor automaticamente autorizado para ingestão. Somente um resultado real com `OFFICIAL_READ_CONFIRMED` permitirá avaliar a primeira ingestão persistida da própria conta.

**Versões:** o Graph API Explorer usado pelo operador mostrou v26.0; o conector atual do repositório permanece fixado em v23.0. Se a consulta direta e o perfil divergirem entre versões, validar a versão do Graph sem alterar permissões, host ou números da conta por tentativa.
