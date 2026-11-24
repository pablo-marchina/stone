"""Opt-in local demonstration. Fresh disposable SQLite, synthetic data only."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from getpass import getpass
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from fastapi import HTTPException, Request, Response
from tapi_gate0.domain import CreatorCreate, ContentCreate, MetricsCreate, RUBRIC_FIELD_NAMES
from tapi_gate0.identity import IdentityFailure
from tapi_gate0.agent_evidence_b2 import EvidenceRetriever, EvidenceNotFound
from tapi_gate0.classification import TOPICS, CTA
from tapi_gate0.discovery_editorial_descriptive import caption_features
from tapi_gate0.discovery_rubric_coverage import REQUIREMENTS
from scripts.demo_technical_snapshot import project_report
from tapi_gate0.secure_api import create_secure_app

TENANT = 'stone-demo'
USERNAME = 'demo'
AS_OF = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)


def build_demo(path: Path, password: str, technical_snapshot=None):
    if path.exists():
        raise ValueError('DEMO_REQUIRES_NEW_DATABASE')
    app = create_secure_app('sqlite:///' + path.resolve().as_posix(),
                            initialize_schema=True, allow_http_local=True,
                            enable_local_graph_diagnostic=True)
    app.state.identity_store.bootstrap(TENANT, 'Stone · Laboratório sintético', USERNAME, password)
    store = app.state.local_domain_store
    topics = ('Gestão de estoque. Salve este exemplo.', 'Fluxo de caixa. Comente sua dúvida.', 'Atendimento. Siga para novos exemplos.', 'Vendas e precificação. Salve para revisar.')
    for i in range(4):
        store.create_creator(CreatorCreate(creator_id=f'demo.perfil.{i+1}', tenant_id=TENANT,
            origin='synthetic_local', handle=f'perfil_ficticio_{i+1}'))
    for i in range(20):
        cid = f'demo.post.{i+1:02d}'
        store.create_content(ContentCreate(content_id=cid, tenant_id=TENANT,
            creator_id=f'demo.perfil.{i%4+1}', origin='synthetic_local',
            media_type=('imagem','carrossel','reels')[i%3],
            published_at=AS_OF-timedelta(days=20+i), is_synthetic=True,
            caption=f'Exemplo fictício de material educativo: {topics[i%4]}.'))
        store.create_metrics(MetricsCreate(snapshot_id=f'demo.snapshot.{i+1:02d}', tenant_id=TENANT,
            content_id=cid, observed_at=AS_OF-timedelta(days=1),
            followers_measured_at=AS_OF-timedelta(days=1), likes=150-i*5,
            comments=20-i//2, follower_count=1000))
    def authorize(request: Request):
        if request.client is None or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            raise IdentityFailure("FORBIDDEN", 403)
        scheme, sep, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not sep or not token or " " in token:
            raise IdentityFailure()
        principal = app.state.identity_store.resolve(token)
        if principal.tenant_id != TENANT or principal.role not in {"admin", "editor"}:
            raise IdentityFailure("FORBIDDEN", 403)

    @app.get("/v1/demo/rubric/{content_id}")
    def rubric(content_id: str, request: Request, response: Response):
        authorize(request)
        response.headers["Cache-Control"] = "private, no-store"
        try:
            evidence = EvidenceRetriever(app.state.identity_store.engine).get(TENANT, content_id, AS_OF)
        except EvidenceNotFound:
            raise HTTPException(404, "DEMO_REFERENCE_NOT_FOUND") from None
        if evidence.origin != "synthetic_local" or evidence.source_url is not None:
            raise HTTPException(404, "DEMO_REFERENCE_NOT_FOUND")
        fields = {name: {"state": "not_assessed", "value": None, "requirement": REQUIREMENTS[name]}
                  for name in RUBRIC_FIELD_NAMES}
        fields["tipo_post"].update(state="metadata_observed", value=evidence.media_type)
        caption = evidence.caption_excerpt
        if caption and not evidence.caption_was_truncated:
            features = caption_features(caption, TOPICS, CTA)
            fields["legenda_tamanho"].update(state="measurement_only", value=len(caption))
            if features["topic"] is not None:
                fields["tema_principal"].update(state="lexical_candidate", value=features["topic"])
            if features["cta"] is not None:
                fields["tem_cta"].update(state="lexical_candidate", value=True)
                fields["tipo_cta"].update(state="lexical_candidate", value=features["cta"])
        return {"fields": fields, "field_count": len(fields), "canonical": False,
                "media_assessed": False, "scientifically_validated": False}

    @app.get("/v1/demo/technical-snapshot")
    def snapshot(request: Request, response: Response):
        authorize(request)
        response.headers["Cache-Control"] = "private, no-store"
        return {"available": technical_snapshot is not None, "snapshot": technical_snapshot}

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--technical-report', type=Path, help='Relatório privado A6 existente; somente agregados históricos serão mostrados.')
    args = parser.parse_args()
    try:
        snapshot = project_report(args.technical_report) if args.technical_report else None
    except ValueError as exc:
        parser.error(str(exc))
    password = getpass('Crie uma senha local de demonstração (12+ caracteres): ')
    if len(password) < 12:
        parser.error('senha deve ter pelo menos 12 caracteres')
    with TemporaryDirectory(prefix='stone-demo-') as directory:
        app = build_demo(Path(directory) / 'demo.sqlite', password, snapshot)
        print(f'Abra http://127.0.0.1:{args.port}/app/demo.html — tenant {TENANT}, usuário {USERNAME}.')
        print('Banco temporário e dados sintéticos; Ctrl+C encerra e descarta o ambiente.')
        try:
            uvicorn.run(app, host='127.0.0.1', port=args.port, proxy_headers=False)
        finally:
            app.state.identity_store.engine.dispose()


if __name__ == '__main__':
    main()
