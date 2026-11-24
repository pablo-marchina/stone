"""Opt-in local demonstration. Disposable or dedicated persistent SQLite."""
from __future__ import annotations

import argparse
import os
import shutil
from threading import Lock
from hashlib import sha256
import json
from datetime import datetime, timedelta, timezone
from getpass import getpass
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import ExitStack
from scripts.demo_workspace import open_workspace, WorkspaceError, fingerprint
from scripts.demo_saved_library import saved_library

import uvicorn
from fastapi import HTTPException, Request, Response, Query
from pydantic import BaseModel, ConfigDict, Field
from scripts.demo_experiment_pairs import previews, persist
from tapi_gate0.domain import CreatorCreate, ContentCreate, MetricsCreate, RUBRIC_FIELD_NAMES, RankingRequest
from tapi_gate0.identity import IdentityFailure
from tapi_gate0.agent_evidence_b2 import EvidenceRetriever, EvidenceNotFound
from tapi_gate0.classification import TOPICS, CTA
from tapi_gate0.discovery_editorial_descriptive import caption_features
from tapi_gate0.discovery_rubric_coverage import REQUIREMENTS
from scripts.demo_technical_snapshot import project_report
from scripts.demo_av_report import read_report, validate as validate_av_report
from tapi_gate0.secure_api import create_secure_app
from tapi_gate0.discovery_retrieval_fts import TransientScopedFts, RetrievalBaselineError
from sqlalchemy import select, func
from tapi_gate0.agent_graph_checkpoints import agent_graph_runs, agent_graph_events
from tapi_gate0.studio_e1 import studio_documents, studio_versions, StudioError
from tapi_gate0.studio_render_e6 import LocalDraftRenderer, studio_render_artifacts
from tapi_gate0.studio_video_e5 import storyboards
from tapi_gate0.sa_store import domain_events

TENANT = 'stone-demo'
USERNAME = 'demo'
AS_OF = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)


class ExperimentSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def build_demo(path: Path, password: str, technical_snapshot=None, *, video_enabled=False, av_report=None, workspace=None):
    if av_report is not None:
        av_report = validate_av_report(av_report)
    resume = workspace is not None and workspace.resume
    if workspace is not None:
        if path.absolute() != workspace.path or workspace.digest != fingerprint(technical_snapshot, av_report):
            raise WorkspaceError('DEMO_WORKSPACE_INPUT_MISMATCH')
        if resume:
            workspace.verify()
    if not resume and path.exists():
        raise ValueError('DEMO_REQUIRES_NEW_DATABASE')
    if video_enabled:
        LocalDraftRenderer._gates()
        if not shutil.which("ffmpeg"):
            raise ValueError("DEMO_FFMPEG_REQUIRED")
    app = create_secure_app('sqlite:///' + path.resolve().as_posix(),
                            initialize_schema=True, allow_http_local=True,
                            enable_local_graph_diagnostic=True)
    store = app.state.local_domain_store
    if not resume:
        app.state.identity_store.bootstrap(TENANT, 'Stone · Laboratório sintético', USERNAME, password)
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
        return principal

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

    @app.get("/v1/demo/search")
    def search(request: Request, response: Response, q: str = Query(min_length=1, max_length=300)):
        authorize(request)
        response.headers["Cache-Control"] = "private, no-store"
        engine = app.state.identity_store.engine
        with engine.connect() as db:
            ranking = store.ranking(RankingRequest(tenant_id=TENANT, as_of=AS_OF), connection=db)
            if len(ranking.rows) > 1000:
                raise HTTPException(409, "DEMO_CORPUS_LIMIT")
            rows, details = [], {}
            for row in ranking.rows:
                e = EvidenceRetriever(engine).get(TENANT, row.content_id, AS_OF, connection=db)
                if e.origin != "synthetic_local" or e.source_url is not None or e.snapshot_id != row.snapshot_id:
                    raise HTTPException(409, "DEMO_REFERENCE_SCOPE_INVALID")
                if e.caption_excerpt and not e.caption_was_truncated:
                    rows.append(dict(content_id=e.content_id, snapshot_id=e.snapshot_id, caption=e.caption_excerpt))
                    details[e.content_id] = dict(content_id=e.content_id, snapshot_id=e.snapshot_id,
                        caption=e.caption_excerpt, engagement_rate=str(row.engagement_rate), top=row.is_top_decile)
            digest = sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
            try:
                with TransientScopedFts(rows, manifest_sha256=digest) as index:
                    result = index.search(q, limit=10)
            except RetrievalBaselineError:
                raise HTTPException(422, "DEMO_QUERY_INVALID") from None
        return {**result, "indexed_posts": len(rows), "hits": [details[cid] for cid in result["content_ids"]],
                "synthetic_local": True, "publication_allowed": False}

    render_lock = Lock()

    @app.get("/v1/demo/video-status")
    def video_status(request: Request, response: Response):
        p = authorize(request)
        response.headers["Cache-Control"] = "private, no-store"
        return {"enabled": video_enabled and p.role == "admin"}

    @app.post("/v1/demo/render-next")
    def render_next(request: Request, response: Response):
        p = authorize(request)
        if not video_enabled or p.role != "admin":
            raise IdentityFailure("FORBIDDEN", 403)
        if not render_lock.acquire(blocking=False):
            raise HTTPException(409, "DEMO_RENDER_BUSY")
        try:
            renderer = LocalDraftRenderer(app.state.identity_store.engine)
            result = renderer.process_next(TENANT, p.actor_id)
            if result is None:
                raise HTTPException(409, "DEMO_NO_QUEUED_RENDER")
            response.headers["Cache-Control"] = "private, no-store"
            return result
        except StudioError as exc:
            raise HTTPException(exc.status, exc.code) from None
        finally:
            render_lock.release()

    @app.get("/v1/demo/session-results")
    def session_results(request: Request, response: Response):
        authorize(request)
        response.headers["Cache-Control"] = "private, no-store"
        with app.state.identity_store.engine.connect() as db:
            ranking = store.ranking(RankingRequest(tenant_id=TENANT, as_of=AS_OF), connection=db)
            def count(table, *filters):
                return db.scalar(select(func.count()).select_from(table).where(table.c.tenant_id == TENANT, *filters))
            counters = dict(eligible_posts=ranking.n_posts, profiles=ranking.n_creators,
                top_posts=ranking.top_count,
                completed_traces=count(agent_graph_runs, agent_graph_runs.c.status == "TRACE_RECORDED"),
                checkpoint_events=count(agent_graph_events),
                editable_drafts=count(studio_documents), document_versions=count(studio_versions),
                generated_draft_events=count(domain_events, domain_events.c.aggregate_type == "agent_generated_draft"),
                storyboards=count(storyboards), rendered_videos=count(studio_render_artifacts))
            count_experiments = count(domain_events, domain_events.c.aggregate_type == "demo_editorial_experiment")
        return {"schema_version": "tapi-demo-session-results.v1", "as_of": AS_OF.isoformat(),
                "synthetic_counters": counters, "historical_technical_snapshot": technical_snapshot,
                "editorial_experiment_pairs": count_experiments,
                "scientifically_validated": False, "production_approved": False, "publication_allowed": False}

    @app.get("/v1/demo/av-report")
    def av_evidence(request: Request, response: Response):
        authorize(request)
        response.headers["Cache-Control"] = "private, no-store"
        return {"available": av_report is not None, "report": av_report}

    @app.get("/v1/demo/experiments")
    def experiments(request: Request, response: Response):
        authorize(request)
        response.headers["Cache-Control"] = "private, no-store"
        return {"pairs": previews(technical_snapshot, TENANT)}

    @app.post("/v1/demo/experiments", status_code=201)
    def create_experiment(payload: ExperimentSelection, request: Request, response: Response):
        p = authorize(request)
        response.headers["Cache-Control"] = "private, no-store"
        try:
            return persist(app.state.identity_store.engine, technical_snapshot, TENANT, p.actor_id, payload.preview_sha256)
        except ValueError:
            raise HTTPException(409, "DEMO_EXPERIMENT_PREVIEW_MISMATCH") from None
        except StudioError as exc:
            raise HTTPException(exc.status, exc.code) from None

    @app.get("/v1/demo/saved-library")
    def library(request: Request, response: Response):
        authorize(request)
        response.headers["Cache-Control"] = "private, no-store"
        result = saved_library(app.state.identity_store.engine, TENANT,
                               technical_snapshot["report_sha256"] if technical_snapshot else None)
        return {**result, "persistent_workspace": workspace is not None}

    @app.get("/v1/demo/technical-snapshot")
    def snapshot(request: Request, response: Response):
        authorize(request)
        response.headers["Cache-Control"] = "private, no-store"
        return {"available": technical_snapshot is not None, "snapshot": technical_snapshot}

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--video', action='store_true', help='Ativa explicitamente o worker FFmpeg de rascunho local neste processo isolado.')
    parser.add_argument('--technical-report', type=Path, help='Relatório privado A6 existente; somente agregados históricos serão mostrados.')
    parser.add_argument("--av-report", type=Path, help="Relatório dos nove testes sintéticos de fusão e direitos.")
    parser.add_argument("--workspace", type=Path, help="Pasta exclusiva nova ou workspace de demonstração já inicializado.")
    args = parser.parse_args()
    try:
        snapshot = project_report(args.technical_report) if args.technical_report else None
        av_report = read_report(args.av_report) if args.av_report else None
    except ValueError as exc:
        parser.error(str(exc))
    if args.video:
        if not shutil.which("ffmpeg"):
            parser.error("FFmpeg não encontrado no PATH")
        os.environ["TAPI_LOCAL_RENDER_ENABLED"] = "1"
        os.environ["TAPI_ZERO_BILLING_CONFIRMED"] = "1"
    password = None
    if args.workspace is None or not args.workspace.exists():
        password = getpass('Crie uma senha local de demonstração (12+ caracteres): ')
        if len(password) < 12:
            parser.error('senha deve ter pelo menos 12 caracteres')
    try:
        with ExitStack() as stack:
            work = stack.enter_context(open_workspace(args.workspace, snapshot, av_report)) if args.workspace else None
            path = work.path if work else Path(stack.enter_context(TemporaryDirectory(prefix='stone-demo-'))) / 'demo.sqlite'
            if (work is None or not work.resume) and password is None:
                raise WorkspaceError('DEMO_WORKSPACE_NEW_PASSWORD_REQUIRED')
            app = build_demo(path, password, snapshot, video_enabled=args.video, av_report=av_report, workspace=work)
            stack.callback(app.state.identity_store.engine.dispose)
            if work is not None and not work.resume:
                work.seal()
            print(f'Abra http://127.0.0.1:{args.port}/app/demo.html — tenant {TENANT}, usuário {USERNAME}.')
            if work:
                print('Workspace persistente de demonstração; use a senha original ao entrar novamente.')
                print('Ctrl+C encerra o servidor sem descartar os documentos. Preserve a pasta e os relatórios originais.')
            else:
                print('Banco temporário e dados sintéticos; Ctrl+C encerra e descarta o ambiente.')
            uvicorn.run(app, host='127.0.0.1', port=args.port, proxy_headers=False)
    except (WorkspaceError, OSError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
