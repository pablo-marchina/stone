# Integrações oficiais — 2026-10-26

Continuação do registro de 2026-10-24, preservando o Plano Único e orçamento R$ 0.

## Estado observado

O acesso a https://developers.facebook.com/apps/ redirecionou para
https://developers.facebook.com/r/user/error/ com “Confirmação de conta necessária”.
A Meta informa atividade incomum na conta de desenvolvedor e exige confirmação
para recuperar acesso. O botão Confirmar conta abriu a etapa Confirme sua
identidade, oferecendo envio de código ao e-mail cadastrado (endereço omitido).
A solicitação segura de código da tentativa anterior foi interrompida; não há
confirmação de sucesso. A tela atual foi preparada para intervenção pessoal.

## Limites e próximos passos

- Cadastro de desenvolvedor já havia sido concluído, mas acesso atual está bloqueado.
- Criação do aplicativo TAPI Stone não foi confirmada; o preenchimento anterior
  do assistente não comprova criação de app ou concessão de permissões.
- Nenhuma conta Instagram, ID, escopo OAuth ou token foi validado nesta execução.
- Google Cloud não foi reavaliado nesta continuação; última observação: Site Unavailable.
- Nenhum recurso faturável ou leitura real de API foi habilitado; não se atesta
  ausência de cobrança nas contas externas sem inspeção dos consoles.
- Nenhum segredo, código de confirmação ou endereço completo foi registrado.
- Não houve alteração do backend nem nova execução de testes locais nesta etapa.

Após confirmação pessoal: verificar acesso ao painel e inventário de apps antes
de retomar a criação, evitando duplicação. Em seguida conferir permissões de
leitura, conta profissional e evidência de ausência de cobrança antes de habilitar
a integração no backend. Não contornar a verificação de identidade da Meta.

## Acesso restaurado e criação preparada

Na continuação, o checkpoint exibiu “Acesso restaurado ao Meta for Developers”.
O painel confirmou “Nenhum app por enquanto”. O assistente foi preenchido com
nome TAPI Stone e caso de uso “Gerenciar mensagens e conteúdo no Instagram”.
Nenhum portfólio empresarial estava disponível; selecionado conectar mais tarde.
A revisão mostra “Nenhuma empresa selecionada” e nenhum requisito identificado
para o caso de uso atual. Isso não comprova permissões concedidas, acesso a contas
ou dispensa de verificações futuras.

A etapa final informa que Criar aplicativo aceita Termos da Plataforma,
Políticas do Desenvolvedor e demais termos aplicáveis. O botão não foi acionado
pelo agente: configuração preparada para aceite pessoal. App ID ainda indisponível;
nenhum token, acesso real, serviço faturável ou publicação habilitado. A configuração
do assistente pode não persistir se a aba for encerrada; verificar inventário antes
de tentar criar novamente. Backend e Google Cloud sem novas alterações nesta etapa.

## Aplicativo criado — confirmação no console

O usuário concluiu a criação. O painel autenticado confirmou TAPI Stone,
App ID `1763543721612277`:
https://developers.facebook.com/apps/1763543721612277/dashboard/

Na configuração da API com login do Facebook, o console informa que a conta
profissional Instagram deve estar vinculada a uma Página e autorizar o app pelo
Login do Facebook para Empresas. Esta é a modalidade compatível com o host
Graph Facebook do conector atual.

A tabela de permissões mostra apenas `public_profile` como Pronto para teste,
com 0 chamadas. `instagram_basic`, `pages_show_list` e `pages_read_engagement`
estão disponíveis para adicionar, mas ainda não foram adicionadas nem concedidas
por uma conta. Preparada solicitação de consentimento específico para configurar
esses três escopos de leitura. Os pacotes automáticos incluem publicação ou
gerenciamento de mensagens e não foram acionados. Não foi solicitado acesso
a anúncios, publicação, mensagens ou gerenciamento empresarial.

Nova tentativa em https://console.cloud.google.com/ retornou Site Unavailable /
Unable to access this site. Nenhum projeto, canal, cota ou faturamento Google
foi inspecionado. Isso é uma limitação de acesso deste navegador, não evidência
de indisponibilidade geral do serviço.

Não há ainda ID de conta Instagram validado, token OAuth, canal YouTube
validado ou teste real contra provedores. Nenhum recurso faturável foi habilitado.
As travas de ingestão e de confirmação de custo zero permanecem inalteradas;
a ausência de cobrança ainda não foi confirmada nos consoles. Nenhuma alteração
de código nem nova execução de testes locais nesta etapa.
