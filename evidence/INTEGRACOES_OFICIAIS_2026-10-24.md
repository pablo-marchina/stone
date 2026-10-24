# Verificação das integrações oficiais — 2026-10-24

## Resultado: parcial; conexões reais não homologadas

Base inspecionada: `d09e3d4d43b4736cd06333716120a112ff36612b`.
Este registro segue o Plano Mestre Único (IMP-106), a arquitetura descrita no README
e as políticas de `docs/14_POLITICA_CUSTO_ZERO.md` e
`docs/21_AQUISICAO_OFICIAL_MULTIMODAL.md`. Não altera gates nem concede acesso.

| Requisito | Evidência desta execução | Estado |
|---|---|---|
| Instagram profissional e ID | Nenhuma conta autenticada consultada | Pendente |
| Escopos Meta concedidos | Nenhum consentimento OAuth concluído | Pendente |
| Projeto Google e YouTube Data API | Console inacessível neste navegador | Pendente |
| Canais e vídeos permitidos | Nenhum identificador real validado | Pendente |
| Ausência de cobrança e overage nos consoles | Consoles autenticados não inspecionados | Não confirmada |
| Backend local | 10 testes de ingestão com MockTransport passaram | Verificado apenas com simulação |
| Segurança financeira local | Script verify_zero_spend passou | Não atesta faturamento externo |
| Credenciais | Nenhum token configurado ou registrado no GitHub | Preservado |

## Evidência observada no navegador na nuvem

1. `https://developers.facebook.com/apps/` apresentou “Página não encontrada” e
   um link Login. O link levou à tela “Entrar no Meta for Developers”.
2. A tela oferecia “Continuar com o Facebook” e “Entrar com uma Conta Meta gerenciada”.
   O fluxo seguro de autenticação retornou a opção escolhida `managed` com
   status `submitted`. Isso não comprova autenticação.
3. A observação seguinte foi bloqueada pela revisão automática de segurança para
   `https://work.meta.com`: risco de acesso a conteúdo de trabalho não relacionado.
   Não houve tentativa de contornar o bloqueio, nem confirmação de login.
4. `https://console.cloud.google.com/` apresentou “Site Unavailable” /
   “Unable to access this site.” Uma única recarga retornou o mesmo estado.
   A causa não foi determinada; não há evidência suficiente para afirmar bloqueio por bots.

Nenhum projeto, aplicativo, assinatura, faturamento, credencial ou permissão foi
criado/alterado nos provedores. Nenhuma chamada autenticada de coleta foi feita.
Não se declara que contas preexistentes do usuário estejam livres de cobranças.

## Verificação local reproduzível

Código recuperado pelo conector GitHub no SHA indicado; dependências instaladas
localmente com `python -m pip install -e '.[dev]'`. GitHub Actions não foi ativado.

- `PYTHONPATH=src python -m pytest -q tests/test_official_ingestion.py`:
  **10 passed, 1 warning in 2.00s**. Aviso de depreciação da integração
  httpx/Starlette TestClient; não impediu os testes.
- `python scripts/verify_zero_spend.py`:
  **PASS — invariantes locais de gasto zero e bloqueio externo**.
- `python -m compileall -q src`: exit code 0.
- A primeira tentativa de pytest falhou porque pytest não estava instalado;
  após instalação das dependências declaradas, a execução acima passou.

Os testes verificam ingestão simulada, autorização, normalização e bloqueios.
Não são testes end-to-end com Meta/Google nem uma execução da suíte completa.

## Limites técnicos encontrados

- Instagram usa host fixo `graph.facebook.com/v23.0`; o provisionamento deve
  corresponder à rota Facebook Login. Não inserir token de outra família de
  integração assumindo compatibilidade.
- YouTube consulta `channels.list(id=...)` e `videos.list(id=...)`.
  Retornar um canal público não comprova que o usuário OAuth é seu proprietário.
- O backend lê `TAPI_INSTAGRAM_ACCESS_TOKEN` e `TAPI_YOUTUBE_ACCESS_TOKEN`
  do ambiente. Não foi encontrado fluxo próprio de autorização OAuth,
  callback, armazenamento seguro de refresh token ou renovação automática.
  Não cadastrar callback fictício para endpoints inexistentes.
- Grants são por conta e finalidade. YouTube também exige IDs explícitos no lote
  e referência da verificação humana de Shorts.
- Flags de habilitação não são controles de faturamento do provedor.
  Permanecem sem habilitação para operação real nesta execução.

## Procedimento para retomar após desbloqueio

### Meta

1. Concluir autenticação no fluxo escolhido, com intervenção pessoal para login,
   consentimento e eventual aceite de termos. A inspeção de work.meta.com depende
   de autorização específica após o bloqueio automático.
2. Identificar aplicativo, proprietário/administrador, modo de operação, conta
   profissional e Página vinculada da rota Facebook Login.
3. Conferir permissões efetivamente disponíveis e concedidas para leitura
   mínima. Não solicitar publicação, anúncios, mensagens ou CRM.
4. Registrar ID do aplicativo, ID profissional, escopos efetivamente concedidos,
   validade, finalidade e referência do consentimento, sem token ou segredo.
5. Inspecionar limites e ausência de produtos faturáveis aplicáveis à conexão.
   Se a ausência de cobrança não puder ser comprovada, manter bloqueada.

### Google/YouTube

1. Retomar somente quando o console estiver acessível; identificar o projeto
   correto e verificar se existe conta de faturamento vinculada.
2. Usar projeto sem faturamento e habilitar apenas a YouTube Data API se o console
   permitir sem cobrança. Não ativar teste pago, créditos, billing, serviços
   auxiliares faturáveis nem solicitar aumento de cota.
3. Preparar cliente OAuth compatível com o fluxo realmente implementado e
   consentimento mínimo de leitura. Concluir consentimento pessoal; segredos
   permanecem fora do GitHub, screenshots e logs.
4. Registrar projeto, cliente (ID público, nunca secret), escopos concedidos,
   canais autorizados, vídeos explicitamente selecionados e validade.
   Se for necessário comprovar propriedade, verificar separadamente
   `channels.list(mine=true)`, que requer autorização; o teste atual por ID
   não substitui essa prova.
5. Registrar a cota efetiva mostrada no projeto e a situação de billing.
   Franquia ou estimativa local não constitui confirmação de ausência de overage.

### Validação no backend, somente após as verificações anteriores

1. Usar instância local segura e sessão de administrador; não expor bootstrap
   público nem publicar um backend na nuvem para contornar o bloqueio.
2. Injetar tokens no ambiente protegido, sem valores em comandos registrados.
3. Criar grant por `POST /v1/ingestion/grants`, com conta real, referência de
   autorização e expiração; consultar
   `GET /v1/ingestion/connections/{platform}/{account_id}`.
4. Habilitar as duas flags existentes somente após evidência financeira e
   autorização. Executar `POST /v1/ingestion/runs` com limite 1 e run_key único.
   Para YouTube, fornecer um ID autorizado e evidência de que é Short.
5. Conferir resultado, conta retornada, registros, métricas ausentes, linagem,
   eventos e `GET /v1/ingestion/runs`. Registrar apenas IDs permitidos, códigos
   de resultado, contagens e referências sanitizadas.
6. Em falha, interromper sem loop de retries. Desabilitar leituras ao terminar
   a validação; revogar credenciais pelo provedor quando necessário.

## Referências públicas consultadas nesta execução

- [Meta — documentação oficial publicada no Postman](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api):
  a rota Facebook Login trabalha com contas profissionais e Página vinculada.
- [YouTube — channels.list](https://developers.google.com/youtube/data/reference/rest/v3/channels/list):
  1 unidade de cota por chamada; `mine=true` restringe aos canais do usuário autenticado.
- [YouTube — videos.list](https://developers.google.com/youtube/data/reference/rest/v3/videos/list):
  1 unidade de cota por chamada.
- [YouTube — cotas](https://developers.google.com/youtube/data/determine_quota_cost?hl=en):
  documentação pública indica 10.000 unidades/dia combinadas para os endpoints
  gerais, com alocações separadas para search.list e videos.insert.
  Esses dois endpoints não fazem parte da coleta atual.

As referências públicas não substituem evidência do console do projeto específico.
O custo de cota em unidades não é um preço monetário e não autoriza ativar billing.

## Continuação após autorização explícita do usuário

O usuário autorizou o acesso necessário ao domínio work.meta.com. A tela de login
pôde ser inspecionada: o bloqueio de observação anterior deixou de impedir esta etapa.
O login organizacional, porém, não foi concluído. O formulário seguro recebeu o
identificador sem expô-lo ao agente na solicitação; a página informou não haver
conta gerenciada associada. Após nova escolha pessoal da mesma modalidade e nova
submissão segura, a Meta retornou o mesmo erro. O endereço de e-mail foi omitido
deste registro por minimização de dados.

O Google Cloud foi novamente verificado e recarregado uma vez: permaneceu em
“Site Unavailable / Unable to access this site”. Nenhum console autenticado,
projeto, cota ou faturamento pôde ser inspecionado.

Próxima intervenção pessoal: concluir o login no navegador na nuvem usando uma
conta organizacional válida ou selecionar o login Facebook apropriado. Não há
nova solicitação de autorização geral; a dependência agora é autenticação válida.
Nenhum OAuth de integração foi consentido, token gerado, grant real cadastrado ou
recurso faturável habilitado. Os resultados de testes anteriores permanecem
históricos; não foram repetidos e não atestam conexão real nesta continuação.

## Login Facebook confirmado; cadastro de desenvolvedor pendente

Após o usuário concluir pessoalmente o login, a página do Facebook apresentou
sessão autenticada. A navegação para /apps/ no Meta for Developers redirecionou
à página inicial com a opção “Começar”. Essa opção abriu
https://developers.facebook.com/async/registration/ com o título
“Crie uma conta do Meta for Developers”.

A etapa Register está incompleta; Verify account, Contact info e About you
aparecem pendentes. A página declara que continuar implica aceitar os Termos da
Plataforma da Meta e as Políticas do Desenvolvedor. O botão não foi acionado pelo
agente: a tela foi preparada para aceite e eventual verificação pessoal do usuário.

O login no Facebook está confirmado, mas não há aplicativo, conta Instagram
profissional, escopos de API ou tokens validados. Nenhuma configuração faturável
foi habilitada. A situação anterior do Google Cloud permanece sem nova verificação
nesta etapa. Não foram repetidos testes locais, pois esta continuação trata apenas
da autenticação e do cadastro externo.
