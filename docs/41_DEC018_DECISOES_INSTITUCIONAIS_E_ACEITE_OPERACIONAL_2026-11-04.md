# DEC-018 — Decisões institucionais consolidadas e execução do Gate 0B (04/11/2026)

**Registro de proveniência:** o responsável do TAPI Stone confirmou que a instituição aprovou **formalmente, de modo abrangente, todas as fontes, operações, expansões, termos e direitos necessários**, incluindo conteúdo de terceiros e dados Stone. Este documento incorpora essa informação como **premissa institucional aprovada** de planejamento e implementação. Não constitui reprodução, auditoria jurídica independente ou alteração das regras técnicas de uma API.

## 1. Decisões institucionais vigentes

| Tema | Confirmação do responsável | Tratamento no plano |
|---|---|---|
| Escopo integral | As 23 capacidades e expansões condicionais estão formalmente liberadas. | **APROVADO institucionalmente**; não solicitar novamente autorização genérica de expansão. |
| Fontes e operações | Todas as fontes e operações estão formalmente liberadas. | **APROVADO institucionalmente**; não solicitar novas aprovações genéricas por fonte/ação. |
| Termos e direitos | A aprovação institucional abrange todos os termos e direitos necessários, inclusive acordo amplo de uso de terceiros. | **APROVADO, conforme declaração expressa do responsável**; não repetir a pendência documental como impedimento para desenvolver. Direitos/termos imperativos de plataformas e terceiros permanecem obrigações aplicáveis à execução, sem implicar necessidade de nova deliberação institucional genérica. |
| Dados Stone | Todos os dados Stone estão liberados para uso. | **APROVADO institucionalmente**; disponibilização técnica e mapeamento dos dados são tarefas de integração. |
| APIs/IDs | Acesso liberado; IDs, recursos e credenciais serão fornecidos sob demanda. | **AUTORIZADO e A DISPONIBILIZAR na hora do teste**; não confundir disponibilidade futura com token/escopo atualmente testado. Guardar segredos fora do Git e do chat. |
| Pessoas | Nenhum humano será disponibilizado para revisão de dados. | Retirar execução da dupla revisão humana do caminho crítico. |
| Ciência | Não haverá validação científica independente. | Não reivindicar gold independente, acurácia/FPR real validada cientificamente ou revisão humana inexistente. |
| Financeiro | Nenhuma alteração na restrição de caixa R$ 0 foi comunicada. | Continuar bloqueando serviços faturáveis e desembolso, inclusive campanha paga real. |

## 2. Gate 0B — separar autorização institucional e execução técnica

**G0B-01 — Autoridade e operações externas:** **RESOLVIDO no âmbito da autorização institucional comunicada**. O operador e a equipe não devem reabrir esse pedido de decisão.

**G0B-02 — Grant por fonte × operação:** **aprovação institucional abrangente resolvida; execução técnica ainda pendente**. O software precisa mapear a autorização já concedida aos IDs, contas, tenants, operações e credenciais reais. Um registro verificável por operação mantém isolamento, expiração, revogação e trilha de auditoria; não representa nova solicitação de autorização à instituição.

**G0B-03 — Termos, retenção e direitos multimodais:** **resolvido no nível de confirmação formal institucional informado pelo responsável**. Na implementação, aplicar a política de armazenamento/retenção e os requisitos de provedores/privacidade correspondentes; isso é trabalho de configuração/conformidade operacional, não nova aprovação institucional.

**Resultado:** para uma primeira integração real, resta **Gate 0B técnico por operação**: configurar identidade e credencial, confirmar os escopos efetivos na API, associar a fonte/conta/grant no sistema, testar operação limitada e registrar resultado. O Gate 0B global não deve ser marcado como tecnicamente PASS antes dessas evidências. Do mesmo modo, não se devem inverter automaticamente as 72 entradas PENDING nem ativar todas as operações de uma vez, porque elas representam **estado de provisionamento técnico**, e não desaprovação institucional.

## 3. Mudança obrigatória no critério histórico de revisão humana

O Plano Único v5.2 exige rubrica de 20 campos, evidências por publicação, abstenção e revisão humana de >=50 publicações. A parte de revisão humana **não será executada**, por decisão comunicada pelo responsável. Registrar como **DISPENSADO POR DECISÃO INSTITUCIONAL**, nunca CONCLUÍDO.

O aceite substitutivo é **técnico e operacional**, com testes automatizados, fixtures sintéticas versionadas, integridade de dados, citações/linhagem, invariantes, privacidade, segurança, testes de integração real e medição descritiva de cobertura e abstenção. Não usar pseudo-gold gerado pelo próprio modelo para alegar validação independente. Manter distinção de modalidade: não observar CTA na legenda não demonstra ausência no vídeo.

O laboratório E1.5 de revisores fictícios não representa pessoas reais. Seus ensaios podem ser usados para verificar software, não para declarar precisão científica. A alteração de aceite deve ser propagada às matrizes da v5.2 e ao termo de aceite final do projeto sem apagar seu histórico.

## 4. Bloqueios remanescentes — estritamente técnicos/operacionais

1. **Conectividade real e segredos:** IDs, endpoints, OAuth/tokens, escopos efetivos, papéis, quotas e vinculação de contas, quando cada integração os exigir.
2. **Provisionamento de grants técnicos:** mapear contas/fontes e operações no sistema autenticado, implementar/liberar seletivamente a política de acesso, registrar auditabilidade, expiração e revogação, sem autorizações em massa por simples edição de JSON.
3. **Ingestão/qualidade:** executar primeiro lote permitido, persistir proveniência, snapshot e resultados, com testes de falha/reprocessamento e limites de quota. Acordo declarado não substitui requisitos técnicos de APIs de terceiros.
4. **Produto:** agente, CreativeSpec, DesignDocument, Creative Studio, editor multimodal, playbook, criativos e integração ponta a ponta.
5. **Governança/finanças:** reconciliar 204 IMP/543 dependências/13 matrizes v5.2, integrar PRs #29/#30/#31 e manter custo financeiro R$ 0.

**Não são mais bloqueios institucionais a serem solicitados:** aprovação das expansões, autorização genérica por fonte/operação, uso de dados Stone, termo genérico de uso de terceiros ou disponibilização de revisores humanos.

## 5. Controles preservados

Esta atualização é documental, sem modificar `config/source_permissions.json`, `src/tapi_gate0/policy.py`, flags de produção, banco, credenciais ou Gate 0B automatizado. A alteração futura da lógica deve ocorrer por PR próprio com regressões e liberação seletiva. Não presume que termos obrigatórios de APIs externas possam ser anulados por acordo institucional. Nunca permitir cobrança real sob a restrição financeira vigente.

**DEC-018** é aditivo à matriz histórica de 15 decisões do Plano v5.2, sem renumerar as decisões anteriores.
