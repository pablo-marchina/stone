"""IMP-078/174: local synthetic editorial proposals, not scientific findings.

Fixed original templates; no model, copied caption or external authority.
A trace identifies an example to inspect, not evidence that a template works.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import insert
from sqlalchemy.exc import SQLAlchemyError

from .agent_evidence_b2 import CreativeBriefRequest, EvidenceRetriever
from .agent_evidence_e1 import EvidenceCitation
from .agent_graph_readonly_runner import LocalGraphPlan, _analysis, _verify_citations
from .agent_trace_draft_handoff import verified_recommendation_trace
from .domain import Id
from .sa_store import domain_events, outbox
from .storage import now_utc
from .studio_e1 import CreativeSpec, StudioStore, draft_from_spec, EDITORIAL_LAYOUT_VERSION

VERSION = "tapi-local-creative-proposals.v1"
AGGREGATE = "agent_generated_draft"
TEMPLATES = (
    ("inventory", "Confira seu estoque", "Liste os itens disponíveis e revise a necessidade de reposição.", "Revise seu estoque."),
    ("cashflow", "Acompanhe entradas e saídas", "Anote recebimentos e pagamentos previstos para organizar o caixa.", "Atualize seu controle."),
    ("service", "Revise seu atendimento", "Identifique dúvidas frequentes e prepare respostas claras para seus clientes.", "Revise as dúvidas."),
    ("pricing", "Conheça seus custos", "Registre despesas e compare seus custos antes de revisar os preços.", "Liste seus custos."),
    ("planning", "Planeje a próxima semana", "Escolha uma prioridade, defina uma tarefa e acompanhe sua execução.", "Escolha sua prioridade."),
)


class ProposalDenied(ValueError):
    """Sanitized denial code."""


class EditorialProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    template_id: Id
    brief: CreativeBriefRequest
    script: tuple[str, str, str]
    caption: str
    citation: EvidenceCitation
    hypothesis: str
    uncertainty: Literal["exploratory_not_scientifically_validated"] = "exploratory_not_scientifically_validated"
    brand_profile: Literal["unbranded_synthetic"] = "unbranded_synthetic"
    segment: Literal["synthetic_mpe_education"] = "synthetic_mpe_education"


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _deny(code):
    raise ProposalDenied("LOCAL_PROPOSAL_" + code)


def _generate(engine, db, *, tenant, actor, run_id, plan):
    if type(plan) is not LocalGraphPlan or engine.dialect.name != "sqlite":
        _deny("VALIDATED_LOCAL_PLAN_REQUIRED")
    try:
        plan = LocalGraphPlan.model_validate(plan.model_dump(mode="python"))
    except (ValueError, TypeError):
        _deny("VALIDATED_LOCAL_PLAN_REQUIRED")
    trace, plan_sha = verified_recommendation_trace(
        engine, db, tenant=tenant, actor=actor, run_id=run_id, plan=plan)
    analysis = _analysis(engine, tenant, plan, connection=db)
    if not _verify_citations(engine, tenant, plan, analysis, connection=db):
        _deny("CITATION_REQUIRED")
    citations = [c for f in analysis.findings for c in f.citations
                 if c.content_id == plan.content_id]
    if len(citations) != 1 or analysis.action != "inspect_ranked_examples":
        _deny("CITATION_REQUIRED")
    citation = citations[0]
    proposals = []
    for key, headline, body, cta in TEMPLATES:
        scope = dict(tenant=tenant, actor=actor, run=run_id, plan=plan_sha,
                     trace=trace["chain_sha256"], template=key, version=VERSION,
                     layout_version=EDITORIAL_LAYOUT_VERSION)
        brief = CreativeBriefRequest(
            spec_id="spec." + _digest(scope)[:32],
            objective="Proposta educativa sintética para revisão editorial de MPEs",
            headline=headline, body=body, cta=cta,
            platform_intent="instagram_carousel" if key == "planning" else "instagram_feed",
            reference_content_ids=[plan.content_id])
        handoff = EvidenceRetriever(engine).handoff(tenant, brief, connection=db)
        spec = CreativeSpec.model_validate(handoff.model_dump(mode="json"))
        preview = draft_from_spec(spec, "preview." + key, editorial_template=key).model_dump(mode="json")
        proposal = EditorialProposal(template_id=key, brief=brief,
            script=(headline, body, cta), caption=body + " " + cta,
            citation=citation,
            hypothesis="Testar clareza educativa; a referência é apenas exemplo para inspeção, não prova de eficácia.")
        raw = proposal.model_dump(mode="json")
        proposals.append({"proposal_sha256": _digest({"scope": scope, "proposal": raw, "preview": preview}),
                          "proposal": raw, "preview_document": preview})
    return trace, plan_sha, proposals


def preview_proposals(engine, *, tenant, actor, run_id, plan):
    try:
        with engine.connect() as db:
            # Replay takes the same SQLite lock as acceptance, but preview
            # never commits even the no-op tenant lock update.
            with db.begin() as tx:
                trace, _, proposals = _generate(engine, db, tenant=tenant, actor=actor,
                                                 run_id=run_id, plan=plan)
                tx.rollback()
            return {"schema_version": VERSION, "trace_chain_sha256": trace["chain_sha256"],
                    "proposals": proposals, "model_calls_performed": 0,
                    "scientifically_validated": False, "studio_write_allowed": False,
                    "publication_allowed": False, "production_approved": False}
    except SQLAlchemyError:
        _deny("TRANSACTION_ABORTED")


def accept_proposal(engine, *, tenant, actor, run_id, plan, proposal_sha256, document_id):
    """Recompute under the same write lock; never accept caller-supplied copy."""
    try:
        with engine.begin() as db:
            trace, plan_sha, proposals = _generate(engine, db, tenant=tenant, actor=actor,
                                                   run_id=run_id, plan=plan)
            selected = next((p for p in proposals if p["proposal_sha256"] == proposal_sha256), None)
            if selected is None:
                _deny("PREVIEW_MISMATCH")
            proposal = EditorialProposal.model_validate_json(json.dumps(selected["proposal"]))
            handoff = EvidenceRetriever(engine).handoff(tenant, proposal.brief, connection=db)
            spec = CreativeSpec.model_validate(handoff.model_dump(mode="json"))
            doc = StudioStore(engine).create(tenant, actor, spec, document_id, connection=db,
                                             editorial_template=proposal.template_id)
            proof = dict(schema_version=VERSION, trace_chain_sha256=trace["chain_sha256"],
                         plan_sha256=plan_sha, proposal_sha256=proposal_sha256,
                         template_id=proposal.template_id, layout_version=EDITORIAL_LAYOUT_VERSION,
                         citation_sha256=_digest(proposal.citation.model_dump(mode="json")),
                         initial_document_sha256=sha256(doc.model_dump_json().encode()).hexdigest(),
                         initial_document_version=1, operator_authored_brief=False,
                         operator_selected_proposal=True, model_calls_performed=0,
                         scientifically_validated=False, external_rights_verified=False,
                         publication_allowed=False, production_approved=False)
            seq = db.execute(insert(domain_events).values(
                event_id=str(uuid4()), tenant_id=tenant, aggregate_type=AGGREGATE,
                aggregate_id=doc.document_id, event_type="agent.generated_draft.created",
                aggregate_version=1, occurred_at=now_utc().isoformat(),
                payload=json.dumps(proof, sort_keys=True, separators=(",", ":")),
            )).inserted_primary_key[0]
            db.execute(insert(outbox).values(seq=seq, attempts=0, dead_letter=0))
            return doc
    except SQLAlchemyError:
        _deny("TRANSACTION_ABORTED")
