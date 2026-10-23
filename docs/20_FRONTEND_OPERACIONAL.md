# Frontend operacional integrado — superfície inicial

**Natureza:** implementação local funcional, sem simulação dos números. Ainda não é a interface final de todas as 22 capacidades nem homologação de produção.

## Funcionalidade

- UI first-party em `/app/`, atendida na mesma origem pelo FastAPI seguro, sem hospedagem, scripts ou fontes de terceiros.
- Autenticação pelo endpoint existente `POST /v1/auth/sessions`; token opaco **somente em memória** (nunca localStorage/cookie), logout revogável.
- Endpoint autenticado `GET /v1/ui/overview` com contadores reais e últimos posts/eventos do tenant; nenhum texto integral ou conteúdo sensível é exibido.
- SSE autenticado via **fetch streaming** (o EventSource nativo não aceita Authorization header); reconexão e cursor. A API já valida sessão em cada consulta do stream.
- Telas de login, KPIs, fluxo de domínio, atividade ao vivo e conteúdos recentes. Estados ausentes são rotulados, não simulados.
- CSS responsivo, navegação por teclado, regiões ARIA e respeito a prefers-reduced-motion; testes de acessibilidade com leitores de tela continuam pendentes.
- Cabeçalhos CSP same-origin, no-store, frame DENY, nosniff, no-referrer.

## Rodar sem custo

```sh
python -m pip install -e '.[dev]'
export TAPI_DATABASE_URL="sqlite:////absolute/path/to/secure.sqlite3"
python -m alembic upgrade head
python -m tapi_gate0.ops bootstrap-admin --tenant local-research --username admin
export TAPI_ALLOW_HTTP_LOOPBACK=1
uvicorn tapi_gate0.secure_api:from_environment --factory --host 127.0.0.1 --port 8000
```

Abrir `http://127.0.0.1:8000/app/`. A instância segura aceita HTTP **somente** na interface de loopback quando ativada explicitamente. Não publicar esse endereço diretamente na internet.

```sh
PYTHONPATH=src python -m pytest -q
node --test tests/frontend/*.mjs
```

## Restrições preservadas

- Custo financeiro obrigatório R$ 0; nenhuma integração externa ou custo de API habilitado.
- Consentimento do solicitante registrado, mas grants por origem/conta/operação e credenciais válidas ainda não vinculados aos conectores. A aprovação não representa direito genérico a baixar mídia de terceiros.
- Não oferece publicação, mídia paga, CRM, inferência multimodal, agentic studio ou PostgreSQL homologado.
- Antes de produção real: benchmark de stack/frontend, UX/a11y, proteções contra XSS/cadeia de suprimentos, testes de carga e integração com banco de produção.
