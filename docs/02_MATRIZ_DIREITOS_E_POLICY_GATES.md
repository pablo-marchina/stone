# Matrizes de autorização — deny by default

Fonte operacional de bloqueio no bootstrap: `src/tapi_gate0/policy.py`. Registro documental: `config/source_permissions.json`.

### Regras

1. Público não significa autorização para download, reuso comercial, armazenamento nem transformação audiovisual.
2. *Nenhuma* das origens Instagram, YouTube, Stone, CRM, publicação ou mídia paga está autorizada no Gate 0.
3. Qualquer aprovação futura precisa ser vinculada a conta/fonte, operação, finalidade, campo, período, retenção, fornecedor e responsável. E deve ser **verificada por um serviço confiável**, não por alteração manual de JSON.
4. No estágio atual não há nenhum conector ativo, nem ferramenta de publicação ou de campanha. O código de bootstrap não consegue acionar serviços externos.
5. Mudança de status documental não remove o bloqueio do código. Um novo componente de autenticação e validação de grants será necessário antes de habilitar fluxos reais.
6. Ações irreversíveis e de efeito externo precisarão de autorização por ação, limites e intervenção humana.

### Fontes

| Fonte | Metadados | Multimodal | Ranking entre criadores | Publicar/operar |
|---|---|---|---|---|
| Instagram | PENDENTE | PENDENTE | PENDENTE | PENDENTE |
| YouTube | PENDENTE | BLOQUEADO sem autorização apropriada | DEPENDE da política de agregação | PENDENTE |
| Stone CRM / contas próprias | PENDENTE | PENDENTE | N/A | PENDENTE |
| Fixturas sintéticas criadas por nós | AVALIAÇÃO INTERNA | AVALIAÇÃO INTERNA | Somente teste sintético | NEGADO |

YouTube: as políticas oficiais restringem download/cache de audiovisual sem aprovação escrita, armazenamento de dados e determinados usos agregados. Instagram: rotas oficiais têm restrições por tipo de conta e permissões. A aplicabilidade concreta deverá ser validada com responsáveis.

Fontes oficiais: https://developers.google.com/youtube/terms/developer-policies e https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api
