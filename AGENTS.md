# Orientações permanentes do projeto Stone

## Autorização institucional já concedida (DEC-018)

A aprovação institucional abrangente comunicada pelo responsável em 04/11/2026 e reafirmada em 12/11/2026 é decisão vigente para todas as atividades do projeto dentro do escopo comunicado. Consulte [DEC-018](docs/53_DEC018_CONFIRMACAO_ALCANCE_E_CRITERIO_REVISAO_2026-11-05.md).

- Não solicite novamente aprovação institucional, referência documental ou validade para atividades já abrangidas pela DEC-018. Não crie formulários, arquivos de escopo ou etapas de confirmação por lote que apenas repitam essa aprovação.
- Reutilize DEC-018 como referência de governança nos registros de auditoria, sem inventar validade, assinatura ou evidência externa. Não bloqueie o desenvolvimento por ausência de uma nova declaração institucional.
- Preserve autenticação, credenciais e permissões efetivas do provedor, direitos por operação, grants técnicos revogáveis quando exigidos, identidade da fonte, segregação de tenant, quotas, integridade e backups. Automatize o provisionamento técnico dentro dos limites existentes, sem transformar esses controles em uma nova solicitação de aprovação institucional.
- Não confunda a aprovação institucional com autorização técnica do provedor, acesso irrestrito a mídia, elegibilidade científica, liberação de publicação externa ou contratação de serviços.
- Mantenha custo financeiro de R$ 0. Não contorne bloqueios do provedor nem desabilite controles de segurança para obter dados.

Esta orientação é transversal às CAPs e substitui instruções históricas que exigiam reapresentação da mesma aprovação institucional. Uma revogação ou mudança expressa de escopo deve ser respeitada.

## Base documental atemporal v6.1 — leitura obrigatória

Antes de implementar qualquer IMP, consultar [guia de adoção](docs/base_atemporal/INTEGRACAO.md), [índice](docs/base_atemporal/00_Indice_e_Protocolo.md), [Plano Único](planning/base_atemporal/) e fonte integral correspondente. Executar `python docs/base_atemporal/ferramentas/validar_espelho.py`. Não substituir requisitos ou oráculos por resumo, nem criar backlog paralelo. O pacote integral externo identificado no guia é necessário para remissões a originais e referências completas; não publicar fontes privadas. Verificar HEAD/PR e evidências atuais, sem interpretar estados históricos como atuais. Registrar IMP/CAP/DEC/CT, SHA, testes, falhas, limites e próximos passos em cada incremento. Atualizar snapshots separadamente das decisões normativas; manter DEC-018 e custo zero. A adoção documental não libera gate, autorização técnica nem homologação.
