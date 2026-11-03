# IMP-167 / G0 — Diligência e convite da primeira fonte MPE

**Estado em 03/11/2026:** `PENDENTE_DE_CONVITE`. Este documento é um **pacote de contato e verificação**, não uma autorização obtida. Não há coleta, grant, mudança de status para `approved` nem inclusão no corpus. A fonte está em `candidate` na main; o PR #20 propõe `review`, mas segue como draft.

## 1. Identificação documental (não confundir com verificação de conta na Meta)

- Handle citado publicamente: **`@vaicomeroquee`**.
- Nome associado na reportagem: **Marianna Braga**, chef de cozinha no segmento gastronômico/eventos, em Teixeira de Freitas, Bahia, atuando no setor desde 2019.
- Fonte primária: [Agência Sebrae Bahia — Análise gratuita do Instagram ajuda chef de cozinha a conquistar mais clientes](https://ba.agenciasebrae.com.br/cultura-empreendedora/analise-gratuita-do-instagram-ajuda-chef-de-cozinha-a-conquistar-mais-clientes/).
- Confirmação documental secundária, datada de 29/09/2026: [N1N — Análise gratuita do Sebrae impulsiona vendas de chef de cozinha na Bahia](https://n1n.com.br/negocios-na-bahia/113037/instagram-analise-gratuita-sebrae-impulsiona-vendas-chef/).

**Limites:** reportagem não prova controle atual do perfil, vigência da conta, categoria profissional Business/Creator, ID Graph, porte micro/pequeno segundo critério aplicável, vínculo societário/CNPJ, disponibilidade de Reels/carrosséis, base legal, permissão da plataforma ou direitos de armazenamento. Nenhum dado sobre CPF/telefone/identidade pessoal deve ser colocado no repositório.

## 2. Primeiro contato (convite, não autorização)

Canal sugerido: mensagem direta ao **perfil comercial público mencionado pelo Sebrae**. Conferir que o perfil ainda pertence ao negócio antes de enviar, e registrar apenas a existência do contato no repositório. **Não enviar automaticamente.**

**Mensagem inicial proposta:**

> Olá! Estou desenvolvendo uma pesquisa acadêmica no contexto do projeto TAPI Stone × Inteli sobre padrões de conteúdo no Instagram relevantes para pequenos negócios. Encontrei o perfil @vaicomeroquee em uma matéria do Sebrae Bahia e gostaria de convidar o negócio a participar voluntariamente de um estudo.
>
> A proposta inicial é analisar apenas metadados disponibilizados pela API oficial do Instagram — como links, datas, formato das publicações, curtidas, comentários e contagem de seguidores observada na coleta. Não precisamos da senha, não publicaremos em nome da conta e não pretendemos baixar seus vídeos ou fotos.
>
> Antes de qualquer coleta ou armazenamento, enviaremos a finalidade, os dados exatos, o prazo de retenção, os responsáveis e um termo para sua avaliação, sem compromisso. A pessoa responsável pelo perfil teria interesse em conhecer a proposta?

**Não afirmar parceria contratual, aprovação ética ou chancela institucional que não esteja comprovada.** Adapte a identificação do responsável pela pesquisa antes do envio.

## 3. Evidências obrigatórias para a decisão de inclusão

| Campo / decisão | Evidência necessária | Estado |
|---|---|---|
| `source_username` | Confirmação pelo titular/gestor de que o handle atual é o indicado | PENDENTE |
| `source_ig_id` | Graph Business Discovery com ID profissional e username correspondentes, depois de aprovado o pré-voo | PENDENTE |
| `mpe_size_band` | Critério de enquadramento e declaração/documento apropriado, minimizando dados pessoais; seguidores não comprovam porte | PENDENTE |
| `sector / sampling_stratum` | Setor gastronomia/eventos e porte verificado; `food_unverified` até lá | PARCIAL |
| `legal_basis_and_controller` | Responsável pelo tratamento, hipótese legal aplicável e avaliação de LGPD/ética; não presumir que "público" ou "acadêmico" dispensem análise | PENDENTE |
| `allowed_operations` | Autorizações/condições por leitura Business Discovery, exportação local de metadados e persistência em banco (três decisões distintas) | PENDENTE |
| `retention_and_deletion` | Prazo concreto, local de armazenamento, acesso, descarte e fluxo de oposição/revogação aplicáveis | PENDENTE |
| `meta_platform_terms` | Revisão de uso permitido, retenção, limites de acesso e eventual revisão da aplicação para terceiros | PENDENTE |
| `approval_reference` | Identificador verificável de aprovação, responsável, data e validade, após a resposta efetiva | PENDENTE |
| `approval_proof_sha256` | Hash SHA-256 de prova arquivada **fora** do Git; hash não equivale à base legal | PENDENTE |
| `source_grant` e `corpus_profiles` | Registros administrativos pelo ID IG autorizado, com mesmo escopo e referência; ainda não criar | PENDENTE |
| `eligible_posts` | ≥1 Reel ou carrossel com idade ≥14 dias, metadados e denominador positivo por consulta oficial permitida | PENDENTE |

## 4. Termo de participação e tratamento de metadados — minuta a revisar antes de solicitar aceite

Este texto **não é uma autorização em vigor**; seu conteúdo e versão devem ser aprovados pelo responsável pela pesquisa e pela revisão legal/institucional aplicável.

- **Controlador e contato:** [IDENTIFICAR RESPONSÁVEL / CANAL DE PRIVACIDADE].
- **Participante:** [IDENTIFICAR REPRESENTANTE COM PODER DE AUTORIZAÇÃO].
- **Conta profissional contemplada:** [HANDLE + IG ID VERIFICADO].
- **Finalidade específica:** análise exploratória de padrões editoriais e engajamento de conteúdos direcionados a MPEs; sem afirmações causais; sem mídia paga ou publicação.
- **Campos propostos:** ID da publicação, ID da conta, link público, formato, data de publicação, curtidas, comentários e número de seguidores **na data de observação**, carimbo temporal da coleta e referências técnicas de procedência. **Não** acessar mensagens, dados privados de seguidores, fotos/vídeos binários ou credenciais.
- **Operações independentes:** (A) consulta de metadados via API; (B) armazenamento local de relatório limitado; (C) armazenamento de metadados no corpus de pesquisa; (D) apresentação de resultados agregados/desidentificados. Cada operação requer uma decisão documentada e revisão de conformidade com os termos da Meta.
- **Quem terá acesso / compartilhamento:** [IDENTIFICAR PESQUISADORES E RESTRIÇÕES], vedada redistribuição ampla dos registros brutos sem base própria.
- **Retenção e descarte:** [DEFINIR PRAZO, BASE DE RETENÇÃO, PROCEDIMENTO DE EXCLUSÃO, BACKUPS].
- **Participação e direitos:** voluntariedade, canal para dúvidas, oposição/revogação quando aplicável e mecanismo de tratamento dos pedidos.
- **Regras externas:** autorização do participante não substitui as políticas e permissões da plataforma nem análise dos direitos de terceiros eventualmente retratados nos posts.
- **Decisão de aceite:** [NÃO PREENCHER ANTES DE RECEBER MANIFESTAÇÃO REAL], com data UTC, versão do termo, operações autorizadas, responsável, validade e prova arquivada em local privado.

## 5. Regra de promoção no plano v5.2

`candidate → review` é permitido por evidência documental; `review → approved` **só depois** de decisão verificável por operação, dados de porte, validade e revisão de tratamento. No código, aprovações locais precisam passar por `authorized_source`; a futura persistência permanece protegida por `TAPI_MPE_PERSISTENCE_ENABLED=0` até liberação e revisão do PR #20.

A própria **Metodologia científica v2** descreve o universo como **publicações direcionadas a micro e pequenos empreendedores**, o que **não significa necessariamente perfis pertencentes a MPEs**. O piloto com um pequeno negócio participante é um estrato potencial, não deve redefinir silenciosamente o universo total de 30+ perfis. Amostragem de criadores/empresas e conteúdo relevante a MPEs requer critérios separados.

## 6. Conformidade e rastreabilidade

- Plano Único v5.2: `IMP-167` (descoberta legítima/estratos), `IMP-168` (snapshots), `IMP-170` (data card com déficits), `G0-PERMISSIONS`.
- Referência ANPD: [Guia de tratamento de dados pessoais para fins acadêmicos](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia-orientativo-tratamento-de-dados-pessoais-para-fins-academicos-e-para-a-realizacao-de-estudos-e-pesquisas). Dados acessíveis publicamente também exigem análise de hipótese legal e salvaguardas; o regime acadêmico não dá permissão irrestrita.
- Referência API: [Instagram API oficial da Meta — documentação Postman](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-894be833-d0b6-4877-859e-c61ae6474d64), especialmente contas Business/Creator, limites de acesso e operações.
- Armazenar aprovação/termo privado fora do repositório, com referência não secreta e hash; registrar `approval_reference`, escopo, momento e situação nos controles existentes, sem enviar token ou mensagens privadas ao GitHub.

**Resultado verificado:** reportagem pública e minuta prontas; **nenhum contato enviado, nenhuma resposta recebida, nenhuma permissão obtida e nenhum post MPE coletado**.
