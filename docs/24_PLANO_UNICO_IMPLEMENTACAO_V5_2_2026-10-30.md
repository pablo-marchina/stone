# Plano Único de Implementação Integral — TAPI Stone v5.2

> **Atualização de execução — 05/11/2026:** a estrutura do Plano Único v5.2 permanece como base (**23 CAP, 204 IMP, 15 DEC, 7 gates**), mas a publicação deste Markdown **não sincroniza automaticamente os CSVs do ZIP externo** nem resolve o status por tarefa. Alguns incrementos já existem na `main` até o PR #40. Consultar [51 — decisões pós-v5.2](51_REGISTRO_DECISOES_POS_V52_2026-11-05.md) e [52 — alinhamento e evidências](52_MATRIZ_ALINHAMENTO_FONTES_REPOSITORIO_2026-11-05.md) antes de declarar tarefa/feature executada. Preservar todos os IDs e dependências ao sincronizar matrizes.


**Revisão:** 30/10/2026 · **Estado:** planejamento consolidado e validado estruturalmente; **não significa implementação concluída**. Documentação de referência: [Arquitetura Unificada v5.2](23_ARQUITETURA_UNIFICADA_REVISADA_V5_2_2026-10-30.md), [Studio editável](22_STUDIO_CRIATIVO_EDITAVEL_E_STACK_ALVO.md), Aula 1 da Stone, Documento Mestre e Plano Único v5.1.

## Baseline, alterações e alcance

| Item | v5.1 preservada | v5.2 atualizada |
|---|---:|---:|
| Capacidades | 22 | **23** (CAP-023 editável) |
| Requisitos U | 18 | **18** |
| Decisões tecnológicas | 12 | **15** (DEC-013…015) |
| Grupos de domínio | 16 | **16**, entidades ampliadas |
| Tarefas | 162 | **204** (IMP-163…204) |
| Dependências | 416 | **543**, sem ciclos |
| Relações ISO CAP×9 | 198 | **207** |
| Relações U×CAP | 396 | **414** |
| Testes catalogados | 18 | **28** (CT-STUDIO-01…10) |
| Gates globais | 7 | **7** |
| Lacunas rastreadas | 12 | **18** |

As 162 tarefas históricas, 22 capacidades anteriores, 18 requisitos e 7 gates foram preservados, sem renumeração. O backlog foi reordenado **apenas para inserir as novas dependências**, mantendo a ordem relativa das tarefas originais e a **IMP-131 como tarefa final**. A estimativa não calibrada é **982 horas existentes + 579 horas novas = 1.561 horas**. Não é prazo prometido, nem cabe automaticamente no intervalo acadêmico de quatro semanas.

**Artefatos operacionais:** o pacote integral v5.2 gerado neste trabalho contém 13 matrizes CSV atualizadas, manifesto JSON, checksum SHA-256 e este plano de execução detalhado em Markdown. Os CSVs v5.2 são **arquivos do pacote de entrega desta conversa**, não arquivos que já estejam versionados no GitHub. Não presumir que suas matrizes foram sincronizadas ao repositório somente pela publicação desta síntese.

## Critérios de negócio preservados

1. Base documentada e amostra de referência de 2–5 mil posts / ≥30 perfis / posts com ≥14 dias — ou limitação real tecnicamente demonstrada, **sem simular cumprimento**.
2. Ranking oficial `(curtidas + comentários) / seguidores`, top 10%, controle temporal, estratos e contraste top/restante.
3. Rubrica de 20 atributos, JSON por post, evidências/abstenções e revisão humana de ≥50 publicações.
4. Agente com análise, recomendação e geração, função Python/MCP e referências verificáveis.
5. Playbook com padrões e **pelo menos cinco criativos prontos para produção**.
6. Demonstração executável da pesquisa à peça editável, README com método, arquitetura, resultados reais e limitações.

**Extras da Aula 1:** embaixador real, collab, piloto orgânico, playbook do lojista, painel interativo. **Expansões do projeto:** predição calibrada, assets imagem/vídeo, publicação orgânica autorizada, CRM/resultados, CAP-023 editor visual, qualidade live e roteamento adaptativo. Execução de **mídia paga permanece desativada sob orçamento absoluto R$0**.

## Novas tarefas incorporadas ao backlog

### Base, direitos e aquisição
- **IMP-163 manifesto
- **IMP-164 Meta OAuth/roles
- **IMP-165 paginação Instagram
- **IMP-166 idade 14+
- **IMP-167 descoberta legítima 30+ perfis
- **IMP-168 refresh de snapshots
- **IMP-169 YouTube política por operação
- **IMP-170 auditoria corpus 2–5 mil/30+

### Seleção tecnológica
- **IMP-171 DEC-013 Fabric.js vs Konva
- **IMP-172 DEC-014 vídeo/FFmpeg
- **IMP-173 DEC-015 geração local/templates

### Creative Studio e documentação editável
- **IMP-174 CreativeSpec
- **IMP-175 DesignDocument
- **IMP-176 direitos de assets
- **IMP-177 migrações
- **IMP-178 upload seguro
- **IMP-179 Brand Kit/templates
- **IMP-180 layout com referências
- **IMP-181 editor canvas
- **IMP-182 versões/undo/redo/ETag
- **IMP-183 carrossel
- **IMP-184 export PNG/JPEG/SVG
- **IMP-185 patches IA confirmáveis
- **IMP-186 a11y/desempenho

### Multimodal e vídeo
- **IMP-187 storyboard
- **IMP-188 timeline
- **IMP-189 renderer com worker e quotas
- **IMP-190 assets IA local com fallback

### Editorial e experiência de uso
- **IMP-191 variantes A/B
- **IMP-192 aprovação por revisão
- **IMP-193 modos Stone/lojista
- **IMP-194 embaixador/collab e consentimento
- **IMP-195 protocolo piloto
- **IMP-196 avaliação piloto

### Avaliação e entrega
- **IMP-197 CT-STUDIO 01–10
- **IMP-198 e2e
- **IMP-199 segurança e tenant
- **IMP-200 custos/licenças/benchmark
- **IMP-201 golden preview/export
- **IMP-202 usabilidade
- **IMP-203 README/reprodução
- **IMP-204 integridade release global

### Contratos e testes da CAP-023
`CreativeSpec` (brief/evidências) → `DesignDocument` (páginas/camadas/cenas) → patches validados/confirmados → export `render_job` → aprovação por versão → publicação externa separada. Documento editável é fonte da verdade; export raster/video é derivado. Os 10 testes CT-STUDIO cobrem geração fundamentada, edição de objetos, persistência, preview/export, vídeo, isolamento tenant, direitos, aprovação, custo zero e usabilidade.

## Sequência por dependências — uma entrega final

**P0:** acesso legítimo Meta/YouTube, paginação/idade, corpus, direitos/qualidade, contratos e benchmarks. **P1:** ranking, rubrica/gold, agente, cinco criativos, editor estático e carrossel, playbook e painel com evidência. **P2:** VLM/ASR, timeline/render de vídeo, geração de assets locais e avaliações. **P3:** parcerias/pilotos autorizados, feedback, distribuição orgânica, resultados e outras ampliações condicionadas.

A ordem exata e os pré-requisitos de cada tarefa estão nos CSVs. Nenhuma etapa equivale a uma segunda entrega. Efeitos externos devem ficar OFF sem grant por ação, conta e direitos. Modelos, bibliotecas e codecs exigem validação de licença e benchmark local; serviço faturável é vedado.

## Validação estrutural concluída

- **204 tarefas**, todos os identificadores antigos preservados, 42 novos IDs únicos;
- **543 arestas válidas**, sem ciclos e todas as tarefas alcançando a IMP-131 final;
- **23×9 = 207** linhas ISO; **18×23 = 414** vínculos requisito-capacidade;
- **15 decisões**, **28 testes**, **7 gates**, matrizes com referências válidas;
- arquivos de planejamento continuam `NAO_EXECUTADO` até evidências individuais de código/teste. O repositório possui infraestrutura parcial real, mas isso **não homologou** o produto completo.

## Riscos bloqueantes

Volume de dados autorizado, direitos sobre audiovisual, capacidade local de render/VLM, licenças por peso/fonte/codec, permissões Meta/YouTube, parceiros para piloto, comparabilidade de métricas, conformidade legal e ausência de cobrança. Registro de déficit não é substituto automático do requisito institucional: depende de decisão explícita.

**Regra final:** uma única liberação `ENTREGA-UNICA`, condicionada à comprovação dos gates aplicáveis e ao registro de impossibilidades. Jamais apresentar feature proposta, preview, teste com mocks ou publicação bloqueada como produção efetiva.
