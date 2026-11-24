"""Opt-in local demonstration. Fresh disposable SQLite, synthetic data only."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from getpass import getpass
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from tapi_gate0.domain import CreatorCreate, ContentCreate, MetricsCreate
from tapi_gate0.secure_api import create_secure_app

TENANT = 'stone-demo'
USERNAME = 'demo'
AS_OF = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)


def build_demo(path: Path, password: str):
    if path.exists():
        raise ValueError('DEMO_REQUIRES_NEW_DATABASE')
    app = create_secure_app('sqlite:///' + path.resolve().as_posix(),
                            initialize_schema=True, allow_http_local=True,
                            enable_local_graph_diagnostic=True)
    app.state.identity_store.bootstrap(TENANT, 'Stone · Laboratório sintético', USERNAME, password)
    store = app.state.local_domain_store
    topics = ('Estoque', 'Fluxo de caixa', 'Atendimento', 'Precificação')
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
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    password = getpass('Crie uma senha local de demonstração (12+ caracteres): ')
    if len(password) < 12:
        parser.error('senha deve ter pelo menos 12 caracteres')
    with TemporaryDirectory(prefix='stone-demo-') as directory:
        app = build_demo(Path(directory) / 'demo.sqlite', password)
        print(f'Abra http://127.0.0.1:{args.port}/app/demo.html — tenant {TENANT}, usuário {USERNAME}.')
        print('Banco temporário e dados sintéticos; Ctrl+C encerra e descarta o ambiente.')
        try:
            uvicorn.run(app, host='127.0.0.1', port=args.port, proxy_headers=False)
        finally:
            app.state.identity_store.engine.dispose()


if __name__ == '__main__':
    main()
