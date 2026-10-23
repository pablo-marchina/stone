# Identidade, segurança e operação — Gate 0

## Estado deliberado

- Bootstrap somente local (`127.0.0.1`) sem operações externas nem dados de clientes; endpoint de status **não** é backend de produção autenticado.
- Repositório remoto `pablo-marchina/stone` **privado**, criado pelo usuário e acessível ao conector; manter privado até avaliação de licenças e regras Stone.
- Política técnica hard stop deny-all para serviços externos e ações com efeito.
- CI sem secrets, permissões de token GitHub Actions somente leitura.

## Antes de habilitar conexões reais

1. Selecionar OIDC/SSO compatível com Stone, definir `admin`, `researcher`, `annotator`, `editor`, `viewer`, `service_account`, papéis por tenant e testes de isolamento de dados.
2. Selecionar abordagem RLS/Postgres, validar rota de tenant e prevenir bypass administrativo.
3. Encriptar dados em trânsito/repouso conforme contexto, rotacionar segredos, versionar políticas de retenção e exclusão.
4. Criar audit log imutável ou com proteção contra alterações, rate-limit e limite de gasto por identidade.
5. Fazer threat modeling de SSRF, prompt injection em legendas, tool poisoning, exfiltração e *excessive agency*; ferramentas externas precisam de aprovação por ação.
6. Implementar backup e **teste de restore**, observabilidade com logs redigidos, scanner de dependências, SBOM e rollback.
7. Separar *grant* de dados, concessão de credencial OAuth e autorização do projeto; um não substitui os outros.

Nada disso é marcado como executado por existir este documento. O objetivo é bloquear caminhos inseguros desde o início.
