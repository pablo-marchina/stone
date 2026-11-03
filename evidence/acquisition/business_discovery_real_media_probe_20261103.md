# Validação real do Business Discovery — 2026-11-03

Origem: resumo sanitizado enviado pelo operador após executar `scripts/business_discovery_preflight.py` com o token atualizado; API Graph (cliente do repositório: v23.0). **Não contém token nem dados pessoais.**

## Resultado observado

- `status=DISCOVERY_SAMPLE_READ`; origem `instagram_business_discovery`.
- Instagram profissional autenticado: `17841459971757521` (`@academy_fellow_stone`).
- Alvo de teste: `@instagram` (`17841400039600391`), **somente verificação da API**; não acrescentar ao corpus MPE.
- `followers_observed_now=686328572`; `reported_media_count=8634` — contagem total de perfil reportada pela API, **não** posts elegíveis, nem seguidores históricos.
- Amostra: três mídias; um Reel, um carrossel e um outro formato; duas abaixo da idade mínima de 14 dias; zero elegíveis.
- Erros de metadados, métricas ausentes, denominador inválido ou duplicatas: zero **nesta amostra**.
- Uma página examinada; `another_page_possible=false` no código original; zero posts persistidos; `rights_grant_recorded=false`.

## Limite de interpretação e correção

A implementação anterior inferia disponibilidade de próxima página exclusivamente por `paging.next`. Em Business Discovery aninhado, pode haver apenas `paging.cursors.after`. Portanto, quando o resultado contém três itens de três solicitados, sem `next`, não se pode concluir que os demais registros do perfil são inacessíveis ou que a paginação se esgotou. Relatos históricos de uso da API documentam esse padrão, mas o comportamento do Graph v23/v26 deve ser comprovado por nova execução.

A correção de paginação conserva a lista de usernames explícitos e a whitelist de campos, consulta só host fixo, segue apenas cursor opaco válido quando a página é cheia, respeita `max_pages<=3`, sinaliza explicitamente `pagination_status` e sempre retorna `exhaustion_confirmed=false` no pré-voo. Não armazena dados, não concede direitos e não transforma a conta de teste em fonte do corpus.

## Próxima decisão científica

1. Validar o cursor em um teste real com `--limit 3 --max-pages 2` **apenas para perfil de teste**, respeitando limites e aprovações.
2. Selecionar fontes relevantes ao recorte de MPE, documentar permissões e condições de uso por conta/finalidade e diversidade setorial.
3. Avaliar métricas ausentes, mudança de seguidores e período mínimo de 14 dias em amostras reais antes de habilitar qualquer ingestão persistente.

**Estado:** leitura do perfil e três publicações comprovada; elegibilidade científica, exaustividade e persistência ainda não comprovadas.
