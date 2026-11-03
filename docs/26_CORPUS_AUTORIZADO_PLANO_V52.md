# IMP-167 / IMP-170 — cadastro de fontes e auditoria de corpus (v5.2)

**Estado:** infraestrutura offline implementada e testada; ainda não é corpus externo coletado, nem aceite científico final. Nenhuma credencial Meta/YouTube, scraping, mídia de terceiros ou serviço pago utilizado.

## Jornada segura

1. Um administrador verifica separadamente a permissão de cada conta/finalidade, a modalidade Meta OAuth, escopos efetivos, titularidade ou base legítima de consulta e a política de custo R$0. O registro administrativo em `POST /v1/ingestion/grants` é *atestação*, não prova legal automática.
2. O administrador registra a conta e estrato de amostragem em `POST /v1/corpus/profiles`, com `platform`, `source_account_id`, `sector`, `sampling_stratum`, `evidence_reference`. **Este cadastro não cria grant, token ou acesso à API.** Os setores e estratos são rótulos declarados pelo operador, não classificação verificada.
3. A coleta continua sendo uma ação distinta, por `POST /v1/ingestion/runs`, com as flags de leitura por padrão desligadas e todos os gates de permissão, credenciais e custo zero.
4. `GET /v1/corpus/data-card` fornece um resumo por tenant, sem chamar qualquer API externa. A amostra primária contabiliza somente Instagram profissional com registro de corpus, grant atual, evidência de verificação técnica anterior, idade de 14+ dias, formato Reels/carrossel e snapshot com denominador >0.
5. YouTube Shorts permanece **complementar** e é contado separadamente para evitar mistura indevida de métricas e cobertura.

## Dados e critérios auditados

O relatório informa: perfis cadastrados, grants administrativos atuais, perfis anteriormente verificados por API, posts elegíveis do Instagram, perfis com ao menos um post elegível, posts complementares YouTube, exclusões por cadastro/autorização/formato fora do escopo/idade/ausência de métricas/denominador inválido, distribuição por setor e por estrato declarados pelo operador, diferença até as metas de **30 perfis** e **2.000–5.000 posts**, e limitações metodológicas.

A presença de `technical_verified_at` confirma **uma resposta passada**, não um token ainda válido nem autorização jurídica de acesso. Contagens de seguidores Instagram são observadas no momento da coleta; o resultado não autoriza inferência causal ou comparações entre plataformas.

## Bloqueios para coleta real

A issue #6 exige concluir o convite da pessoa administradora da Página como Tester do aplicativo Meta e aceitar o convite, validar a modalidade Facebook Login e a vinculação IG profissional, verificar escopos mínimos de leitura e configurar credenciais fora do repositório. Nada disso foi simulado como concluído.

Para alcançar o volume de referência ainda será necessário: plano de diversidade de perfis reais autorizado por conta, paginação sob quotas, monitoramento de falhas/429, validação de direitos, análise temporal, reamostragem e controle de qualidade. **A implementação deste relatório não satisfaz por si só a IMP-167 ou a IMP-170.**

## Evidências e execução

- Teste local: `PYTHONPATH=src python -m pytest -q tests/test_corpus_audit_v52.py`.
- Teste global: `PYTHONPATH=src python -m pytest -q` e `node --test tests/frontend/*.mjs`.
- Migração nova: `0004_corpus_profiles`, após `0003_ingestion_page_checkpoints`.
- Evidência de testagem mock: `evidence/acquisition/corpus_readiness_mock.json`.
- Todas as contagens de teste são **sintéticas e locais**. Até que haja dados permitidos, a leitura de um banco novo retorna zero posts reais e déficit de cobertura.
