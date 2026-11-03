# Meta Graph — diagnóstico de `EXPECTED_PAGE_NOT_FOUND`

**Contexto:** uma execução real de `scripts/meta_preflight.py --execute --limit 3` em 03/11/2026 retornou `EXPECTED_PAGE_NOT_FOUND`. O token já estava disponível no processo Python; a API retornou uma resposta bem formada para `/me/accounts`, mas o Page ID esperado `61595867706725` não foi encontrado entre as páginas lidas. Isso **não confirma** autorização de leitura de publicações nem vínculo IG válido.

## Diagnóstico mínimo

Com as variáveis `TAPI_INSTAGRAM_ACCESS_TOKEN`, `TAPI_OFFICIAL_METADATA_READS=1` e `TAPI_ZERO_BILLING_CONFIRMED=1` já configuradas em ambiente local e após verificação de uso gratuito:

```powershell
git pull origin main
python scripts/meta_preflight.py --execute --diagnose-pages
```

O resultado contém somente `page_id`, `page_name`, `instagram_user_id`, total de Páginas no limite de varredura e sinalização de truncamento. A consulta usa o host oficial `graph.facebook.com`, **no máximo três páginas de paginação**, exclusivamente `id,name,instagram_business_account`; não consulta media e não segue `paging.next` retornado pelo provedor. Nunca mostra access tokens, tarefas ou corpo integral da resposta.

### Interpretação

- **Página disponível com ID diferente:** confirmar visualmente na interface Meta a titularidade e correspondência da Página. Se o ID apresentado for o correto, executar `python scripts/meta_preflight.py --execute --page-id <ID_EXIBIDO> --limit 3`. Não substituir IDs automaticamente.
- **`visible_page_count_in_scan: 0`:** confirmar que o token é **Facebook User Access Token** do mesmo aplicativo, identidade e escopos; validar o acesso granular à Página no fluxo de consentimento, `pages_show_list` e demais permissões de leitura necessárias. Caso a Página pertença a um Business Portfolio e a interface Meta solicite `business_management`, verificar essa dependência antes de refazer consentimento. O retorno vazio não prova inexistência da Página.
- **Página existe, mas `instagram_user_id: null`:** confirmar o vínculo Business/Creator entre a Página correta e `@academy_fellow_stone`, e as permissões do token. Não marcar o grant como tecnicamente validado.
- **Página/Instagram corretos:** executar o pré-voo completo com `--page-id`, exigindo `status: OFFICIAL_READ_CONFIRMED` e username esperado. Somente então registrar evidências sanitizadas e iniciar a etapa de ingestão autorizada persistente.

**Segurança operacional:** a varredura não amplia permissões, não registra grants, não persiste posts, não chama serviços de escrita e não habilita funcionalidades cobradas. Ela depende das flags já ativadas pelo operador.

**Limite:** a varredura de três páginas e apresentação de 20 registros é deliberadamente restrita. `expected_page_found: false` significa apenas que o ID esperado não foi visto neste lote; não significa que a Página nunca estará acessível com outra identidade/permissão.
