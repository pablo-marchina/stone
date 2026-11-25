"""Original A/B draft pairs conditioned on anonymous historical contrasts."""
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import insert
from tapi_gate0.sa_store import domain_events, outbox
from tapi_gate0.storage import now_utc
from tapi_gate0.studio_e1 import CreativeSpec, StudioStore, draft_from_spec
from tapi_gate0.studio_e4 import studio_etag

VERSION = 'tapi-demo-experiment-pair.v1'
LAYOUT_VERSION = 'tapi-demo-experiment-layout.v1'
CAROUSEL_LAYOUT_VERSION = 'tapi-demo-experiment-carousel-layout.v1'
FORMATS = ('instagram_feed', 'instagram_carousel')
VISUAL_STYLES = ('classic', 'social')
CTA = {'seguir': 'Siga para mais dicas.', 'comentar': 'Comente sua dúvida.',
       'salvar': 'Salve para consultar depois.'}
TOPIC = {'marketing': ('Planeje sua divulgação', 'Escolha um público e organize uma mensagem clara para esta semana.'),
         'atendimento': ('Revise seu atendimento', 'Escolha uma dúvida frequente e organize uma resposta clara para esta semana.'),
         'gestão': ('Organize sua rotina', 'Escolha uma prioridade e organize uma tarefa clara para esta semana.'),
         'vendas': ('Planeje suas vendas', 'Escolha uma meta e organize uma ação clara para esta semana.'),
         'finanças': ('Organize seu caixa', 'Escolha uma despesa e organize uma previsão para esta semana.')}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def specs(pair, tenant):
    for label, value in (('A', pair['control']), ('B', pair['candidate'])):
        headline, body = TOPIC['gestão'] if pair['field']=='cta' else TOPIC[value]
        cta = CTA[value] if pair['field']=='cta' else 'Escolha uma ação para esta semana.'
        yield CreativeSpec(spec_id='experiment.'+digest([tenant, pair, label])[:32], tenant_id=tenant,
                           objective='Comparação editorial exploratória de um fator; rascunho original.',
                           headline=headline.rsplit(' ', 1)[0]+'\n'+headline.rsplit(' ', 1)[1], body=body, cta=cta,
                           platform_intent=pair.get('platform_intent', 'instagram_feed'))


def template_for(pair):
    if pair.get('visual_style') == 'social':
        return 'social-carousel' if pair.get('platform_intent') == 'instagram_carousel' else 'social-feed'
    return 'experiment-carousel' if pair.get('platform_intent') == 'instagram_carousel' else 'experiment'


def previews(snapshot, tenant, platform_intent='instagram_feed', visual_style='classic'):
    if visual_style not in VISUAL_STYLES:
        raise ValueError('DEMO_EXPERIMENT_STYLE_INVALID')
    if platform_intent not in FORMATS:
        raise ValueError('DEMO_EXPERIMENT_FORMAT_INVALID')
    if not snapshot:
        return []
    packet = snapshot['editorial_hypotheses']
    if packet['report_sha256'] != snapshot['report_sha256']:
        raise ValueError('DEMO_EXPERIMENT_REPORT_MISMATCH')
    rows = []
    for h in packet['hypotheses']:
        field, candidate = h['field'], h['value']
        allowed = {'cta': CTA, 'topic': TOPIC}.get(field, {})
        if candidate not in allowed:
            continue
        alternatives = [r for r in snapshot['editorial_contrast']['fields'][field]['comparisons']
                        if r['value'] != candidate and r['value'] in allowed and r['rest_count'] > 0]
        if not alternatives:
            continue
        control = sorted(alternatives, key=lambda r: (-r['rest_count'], r['value']))[0]['value']
        pair = dict(schema_version=VERSION, report_sha256=packet['report_sha256'], field=field,
                    candidate=candidate, control=control, hypothesis=h, layout_version=LAYOUT_VERSION,
                    control_selection='most_frequent_supported_alternative_in_rest',
                    qa_fixture=snapshot.get('qa_fixture', False), model_calls_performed=0,
                    publication_allowed=False, scientifically_validated=False,
                    joint_effect_estimated=False, external_rights_verified=False)
        if platform_intent == 'instagram_carousel':
            pair.update(platform_intent=platform_intent, layout_version=CAROUSEL_LAYOUT_VERSION)
        if visual_style == 'social':
            pair.update(visual_style='social', layout_version='tapi-social-editorial.v1',
                        aesthetic_evidence='provisional_design_candidate_not_corpus_validated')
        documents = [draft_from_spec(spec, 'preview.'+label, editorial_template=template_for(pair)).model_dump(mode='json')
                     for label, spec in zip(('A','B'), specs(pair, tenant))]
        rows.append(dict(pair=pair, previews=documents, preview_sha256=digest([pair, documents])))
    return rows


def persist(engine, snapshot, tenant, actor, preview_sha256):
    selected = next((r for fmt in FORMATS for style in VISUAL_STYLES for r in previews(snapshot, tenant, fmt, style)
                     if r['preview_sha256']==preview_sha256), None)
    if selected is None:
        raise ValueError('DEMO_EXPERIMENT_PREVIEW_MISMATCH')
    pair = selected['pair']
    pair_id = 'demo.experiment.'+uuid4().hex
    with engine.begin() as db:
        documents = [StudioStore(engine).create(tenant, actor, spec, pair_id+'.'+label,
                     connection=db, editorial_template=template_for(pair)) for label, spec in zip(('A','B'), specs(pair, tenant))]
        proof = dict(**pair, preview_sha256=preview_sha256, pair_id=pair_id,
                     operator_selected=True, documents=[{'document_id':d.document_id, 'version':1,
                     'initial_document_sha256':studio_etag(d).strip('"')} for d in documents])
        seq = db.execute(insert(domain_events).values(event_id=str(uuid4()), tenant_id=tenant,
            aggregate_type='demo_editorial_experiment', aggregate_id=pair_id,
            event_type='demo.editorial_experiment.created', aggregate_version=1,
            occurred_at=now_utc().isoformat(), payload=json.dumps(proof, ensure_ascii=False, sort_keys=True))).inserted_primary_key[0]
        db.execute(insert(outbox).values(seq=seq, attempts=0, dead_letter=0))
    return dict(proof=proof, documents=[d.model_dump(mode='json') for d in documents], etags=[studio_etag(d) for d in documents])
